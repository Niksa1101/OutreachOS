"""Engine, session, and the dependency every DB route goes through.

Q31: **fully sync**, with `def` endpoints that FastAPI runs in its threadpool.
SQLite is local and fast; `aiosqlite` adds a driver layer for no gain. Async is
reserved for SSE, which genuinely needs it.

Q120 fixes the session pattern, and it is the one P1 through P5 inherit:

    The dependency yields a session, rolls back on exception, closes always,
    and **never commits.**

Commit-on-success in the teardown runs *after* the route returns and the
response model is serialised. A commit that fails there — constraint violation,
disk full, lock timeout — happens when the response is already composed, so it
cannot be mapped to the error envelope and the client can receive a 200 for a
transaction that rolled back. It also makes every read path a latent writer: any
route that accidentally dirties the session issues a write on the way out.

So services commit explicitly, inside the code that knows what the transaction
meant and can handle its failure. A `UnitOfWork` wrapper is abstraction this
application does not have the complexity to earn.
"""

import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import Request, status
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from outreachos_backend.core.errors import ApiError, ApiErrorCode

__all__ = ["Database", "get_session"]

log = logging.getLogger(__name__)


def _apply_pragmas(connection: Any, _record: Any) -> None:
    """Q32, on **every** connect.

    SQLite pragmas are per-connection, not per-database. Setting them once at
    startup would configure exactly one connection out of the pool and leave
    the rest on defaults — including `foreign_keys=OFF`, which silently turns
    every `ON DELETE CASCADE` in DB.md §3 into a no-op.
    """
    if not isinstance(connection, sqlite3.Connection):
        return

    cursor = connection.cursor()
    try:
        # Readers do not block the writer. The render worker writes progress
        # while the UI reads the queue, continuously, for minutes at a time.
        cursor.execute("PRAGMA journal_mode = WAL")
        # 5s before "database is locked" becomes an error rather than a wait.
        cursor.execute("PRAGMA busy_timeout = 5000")
        # DB.md §2. Off by default in SQLite, which is the trap.
        cursor.execute("PRAGMA foreign_keys = ON")
        # Durable across process crash, not across power loss. The correct
        # trade for a local application whose data is regenerable from source
        # files the app never modifies.
        cursor.execute("PRAGMA synchronous = NORMAL")
    finally:
        cursor.close()


class Database:
    """Owns the engine and the one `sessionmaker`.

    Q120: the future render worker uses `session_factory` directly, in its own
    thread, rather than going through the request dependency. There is one
    factory and two ways in — not two factories.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.engine: Engine = create_engine(
            # `sqlite:///` plus an absolute path. Passed as a URL rather than
            # through `set_main_option`, because Alembic's ConfigParser does
            # %-interpolation and a workspace path containing `%` — which the
            # user chose — would raise.
            f"sqlite:///{path}",
            connect_args={
                # Q32. Sessions are created and used within one request, but
                # FastAPI's threadpool does not guarantee the same thread
                # across a request's lifetime.
                "check_same_thread": False,
            },
            # Every statement at DEBUG would drown the log a user reads.
            echo=False,
            future=True,
        )
        event.listen(self.engine, "connect", _apply_pragmas)

        self.session_factory = sessionmaker(
            bind=self.engine,
            # Attribute access after commit must not silently issue a SELECT
            # on a session the caller may already have closed.
            expire_on_commit=False,
            autoflush=False,
        )

    def dispose(self) -> None:
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    """The DB dependency.

    Q84: **degraded means zero sessions are handed out.** Not "the database is
    available but flagged" — this raises *before* yielding, so every
    DB-touching route returns 503 and there is no path by which the app writes
    against a schema it does not understand. Stated here because "degraded" is
    otherwise ambiguous enough that someone adds a read-only exception later.

    Q104 is the other half: the shell never mounts in that state, so no screen
    ever encounters the 503. It exists so that the invariant holds regardless.
    """
    runtime = request.app.state.runtime

    if runtime.report.status != "ok":
        raise ApiError(
            ApiErrorCode.WORKSPACE_ERROR,
            "The workspace database is not available.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"detail": runtime.report.detail},
        )

    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        raise ApiError(
            ApiErrorCode.WORKSPACE_ERROR,
            "The workspace database is not available.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    session = database.session_factory()
    try:
        yield session
    except Exception:
        # Rolls back on the way out. Does not commit on the way out — see the
        # module docstring for why that asymmetry is the whole point.
        session.rollback()
        raise
    finally:
        session.close()
