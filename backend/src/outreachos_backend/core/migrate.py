"""Migrations at boot: back up, check, upgrade, self-heal.

DB.md §7: Alembic runs automatically at startup, before the API accepts
requests. A failed migration surfaces on the diagnostics screen **rather than
crashing the sidecar** — the process stays alive serving `/health` with
`status: degraded` so there is something to ask (Q17).

Two decisions here would have cost real data if taken the other way:

**`VACUUM INTO`, not a file copy** (Q85). The database is in WAL mode, so
recently committed transactions live in `outreachos.db-wal`, not the main file.
A `shutil.copy` produces a backup silently missing the most recent work — the
exact failure the backup exists to prevent, discovered only when someone
restores it. `VACUUM INTO` is atomic, consistent, single-file, and needs no WAL
handling.

**Check the revision before upgrading** (Q84). A database at a revision this
build does not know is not "ahead"; it is unreadable, and `upgrade head` would
happily run *downgrade-shaped* logic against it or no-op while the app writes
against a schema it misunderstands.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from outreachos_backend.core.boot import BootReport

__all__ = ["MigrationOutcome", "run_migrations"]

log = logging.getLogger(__name__)

#: Q85: keep 3.
BACKUP_RETENTION = 3


class MigrationOutcome:
    """What happened, in the terms `BootReport` needs."""

    def __init__(
        self,
        *,
        ok: bool,
        head: str | None,
        current: str | None,
        backup_path: Path | None = None,
        detail: str | None = None,
        newer_than_app: bool = False,
    ) -> None:
        self.ok = ok
        self.head = head
        self.current = current
        self.backup_path = backup_path
        self.detail = detail
        self.newer_than_app = newer_than_app


def _alembic_config(engine: Engine) -> Config:
    """Build the config with the script location resolved absolutely.

    Q58: `script_location` must resolve absolutely under `sys._MEIPASS`, and
    `versions/` must be in the PyInstaller `datas`. A frozen build with zero
    migration files "succeeds" at `upgrade head` against an empty script
    directory — which is the worst possible failure mode, because it looks
    exactly like a database that was already current.
    """
    backend_root = Path(__file__).resolve().parents[3]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))

    # Never `set_main_option("sqlalchemy.url", ...)`: ConfigParser does
    # %-interpolation, and the path is chosen by the user.
    config.attributes["engine"] = engine
    return config


def _script_directory(config: Config) -> ScriptDirectory:
    return ScriptDirectory.from_config(config)


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _known_revisions(scripts: ScriptDirectory) -> set[str]:
    return {revision.revision for revision in scripts.walk_revisions()}


def _backup(database: Path, revision: str | None) -> Path:
    """`VACUUM INTO 'outreachos.db.bak-<rev>'`. See the module docstring."""
    import sqlite3

    label = revision or "initial"
    destination = database.with_name(f"{database.name}.bak-{label}")
    destination.unlink(missing_ok=True)

    connection = sqlite3.connect(str(database))
    try:
        # Parameterised: the destination is a path the user indirectly chose,
        # and `VACUUM INTO` takes an expression.
        connection.execute("VACUUM INTO ?", (str(destination),))
    finally:
        connection.close()

    _prune_backups(database)
    return destination


def _prune_backups(database: Path) -> None:
    backups = sorted(
        database.parent.glob(f"{database.name}.bak-*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in backups[BACKUP_RETENTION:]:
        try:
            stale.unlink()
        except OSError:
            log.warning("could not remove the stale backup %s", stale, exc_info=True)


def run_migrations(
    engine: Engine, database: Path, *, allow_without_backup: bool = False
) -> MigrationOutcome:
    """Bring the database to head, backing up first if anything will change."""
    config = _alembic_config(engine)
    scripts = _script_directory(config)

    head = scripts.get_current_head()
    current = current_revision(engine)

    if current == head:
        log.info("database is at head (%s)", head)
        return MigrationOutcome(ok=True, head=head, current=current)

    # Q84: **before** upgrading. A revision this build has never heard of means
    # the database was written by a newer version, and the only safe action is
    # to refuse.
    if current is not None and current not in _known_revisions(scripts):
        log.error("database revision %s is unknown to this build (head=%s)", current, head)
        return MigrationOutcome(
            ok=False,
            head=head,
            current=current,
            newer_than_app=True,
            detail=(
                f"This workspace is at revision {current}, which this version of "
                f"OutreachOS does not know about. It expects {head}."
            ),
        )

    backup_path: Path | None = None
    if current is not None:
        # Only when there is something to lose. A database that does not exist
        # yet has no state worth a backup, and `VACUUM INTO` on an empty file
        # would just produce an empty file.
        try:
            backup_path = _backup(database, current)
            log.info("pre-migration backup written to %s", backup_path)
        except Exception as error:
            if not allow_without_backup:
                # Q85: backup fails -> do not migrate -> diagnostics, folded
                # into migration_failed with the detail naming the backup.
                log.error("pre-migration backup failed", exc_info=True)
                return MigrationOutcome(
                    ok=False,
                    head=head,
                    current=current,
                    detail=(
                        f"The pre-migration backup could not be written, so the update was "
                        f"not started. Your data has not been changed.\n\n{error}"
                    ),
                )
            log.warning("proceeding without a backup at the user's request", exc_info=True)

    log.info("migrating %s -> %s", current or "(empty)", head)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    except Exception as error:
        log.error("migration failed", exc_info=True)
        return MigrationOutcome(
            ok=False,
            head=head,
            current=current,
            backup_path=backup_path,
            detail=str(error),
        )

    return MigrationOutcome(
        ok=True,
        head=head,
        current=current_revision(engine),
        backup_path=backup_path,
    )


def heal_app_settings(engine: Engine) -> None:
    """Q60: idempotent `INSERT OR IGNORE` for the singleton.

    The migration seeds it; this covers a database somebody deleted the row
    from. Three lines, and it removes an entire class of "how did this database
    get into this state" support work — a missing singleton is otherwise a
    crash on every settings read.
    """
    from outreachos_backend.core.timeutil import utcnow_iso

    now = utcnow_iso()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT OR IGNORE INTO app_settings "
                "(id, quality_preset, created_at, updated_at) "
                "VALUES (1, 'standard', :now, :now)"
            ),
            {"now": now},
        )


def apply_outcome(report: BootReport, outcome: MigrationOutcome) -> None:
    """Fold the result into the boot report the diagnostics screen reads."""
    report.migration_head = outcome.head
    report.migration_current = outcome.current
    report.backup_path = str(outcome.backup_path) if outcome.backup_path else None

    if not outcome.ok:
        # Q84: degraded means zero sessions handed out. `get_session` raises
        # 503 before yielding, so nothing can write against a schema it does
        # not understand.
        report.status = "degraded"
        report.detail = outcome.detail
