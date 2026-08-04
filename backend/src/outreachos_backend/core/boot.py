"""The boot report, and the process-level state that hangs off it.

Q113: ``/health`` serialises a struct captured once at boot and **never opens a
database session**. Q104 requires the diagnostics screen to be DB-free —
everything it shows comes from here or from a Rust ``invoke`` — and this struct
is the only thing standing between that screen and a session it must not take.

That constraint is why the report carries more than migration state: workspace
path, both log paths, both versions, ``boot_id``, and the failure detail. If any
of those had to be fetched separately, the fetch would be a DB route.

There is deliberately no ``?refresh=1``. Refreshing would have to re-run
migrations to mean anything, which puts DB access back into ``/health`` and
duplicates what Retry already does (Q78).
"""

from dataclasses import dataclass, field
from typing import Literal

from outreachos_backend._version import __version__
from outreachos_backend.core.timeutil import utcnow_iso

__all__ = ["BootReport", "BootStatus", "DegradedDiagnosticCode", "Runtime"]

BootStatus = Literal["ok", "degraded"]

DegradedDiagnosticCode = Literal[
    "workspace_locked",
    "migration_failed",
    "database_newer_than_app",
]


@dataclass
class BootReport:
    """A snapshot of how this process started.

    Mutable during boot and effectively frozen afterwards: the migration fields
    are filled in by checkpoint 5's startup sequence, and nothing writes to it
    once the server is accepting requests.
    """

    boot_id: str
    workspace_path: str
    boot_log_path: str
    backend_log_path: str
    backend_version: str = __version__
    app_version: str | None = None
    started_at: str = field(default_factory=utcnow_iso)

    status: BootStatus = "ok"
    """``degraded`` means **zero database sessions are handed out** — Q84.

    Not "the database is available but flagged". The dependency that yields a
    session raises 503 before yielding, so every DB-touching route fails and
    there is no path by which the app writes against a schema it does not
    understand. Stated here because "degraded" is otherwise ambiguous enough
    that someone adds a read-only exception later.
    """

    migration_head: str | None = None
    """The revision this build knows about."""

    migration_current: str | None = None
    """The revision the database is actually at."""

    backup_path: str | None = None
    """Where the pre-migration ``VACUUM INTO`` backup was written, if one was.
    Q85."""

    detail: str | None = None
    """Human-readable cause when ``status`` is ``degraded``. Surfaced verbatim
    on the diagnostics screen, so it is written for a user, not a grep."""

    diagnostic_code: DegradedDiagnosticCode | None = None
    """Structured reason when ``status`` is ``degraded``. Matches the frontend
    ``DiagnosticCode`` union so Rust can map boot failures without parsing
    ``detail``."""


@dataclass
class Runtime:
    """Per-process state reachable from a request via ``request.app.state``.

    Held here rather than in module globals so tests can build an app without
    a running process behind it.
    """

    report: BootReport
    token: str
    dev: bool
