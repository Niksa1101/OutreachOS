"""Migrations, backups, and the refusal to open a database we do not understand.

Q61: real temp directory, file-backed SQLite, **real migrations**. Not
`create_all` — that would test a schema the application never runs, and the
whole point of Q16's full initial migration is that it is the thing executed on
a user's machine.
"""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from outreachos_backend.core import migrate
from outreachos_backend.core.boot import BootReport
from outreachos_backend.core.db import Database
from outreachos_backend.core.workspace import WorkspaceLayout


@pytest.fixture
def database(tmp_workspace: WorkspaceLayout) -> Database:
    return Database(tmp_workspace.database)


def migrated(database: Database) -> migrate.MigrationOutcome:
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail
    return outcome


# --- the schema ------------------------------------------------------------


def test_a_fresh_database_reaches_head(database: Database) -> None:
    outcome = migrated(database)
    assert outcome.current == outcome.head
    assert outcome.head is not None


def test_every_table_in_db_md_section_3_exists(database: Database) -> None:
    migrated(database)
    tables = set(inspect(database.engine).get_table_names())

    assert {
        "campaigns",
        "media_assets",
        "render_jobs",
        "overlay_presets",
        "app_settings",
    } <= tables


def test_the_talking_head_index_is_partial(database: Database) -> None:
    # DB.md §3.2. A plain unique index on (campaign_id, role) would also forbid
    # a second screen recording, and a campaign is a batch of them — so the
    # `WHERE` clause is the whole constraint, not a detail of it.
    migrated(database)

    with database.engine.connect() as connection:
        sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE name = 'uq_media_assets_one_talking_head'")
        ).scalar_one()

    assert "WHERE" in sql.upper(), sql
    assert "talking_head" in sql


def test_foreign_keys_are_enforced_on_every_connection(database: Database) -> None:
    # Q32. The pragma is per-connection, so setting it once at startup would
    # configure exactly one connection out of the pool and silently turn every
    # ON DELETE CASCADE in DB.md §3 into a no-op on the rest.
    migrated(database)

    for _ in range(3):
        with database.engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_wal_and_busy_timeout_are_set(database: Database) -> None:
    migrated(database)

    with database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000


def test_cascade_delete_actually_cascades(database: Database) -> None:
    # The observable consequence of the pragma above. Asserting the pragma
    # alone would not catch a migration that omitted `ondelete`.
    migrated(database)

    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO campaigns (id, name, overlay_config, overlay_schema_version,"
                " created_at, updated_at) VALUES ('c1', 'x', '{}', 1, 'now', 'now')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO media_assets (id, campaign_id, role, source_path, source_filename,"
                " sort_order, probe_status, file_missing, created_at, updated_at)"
                " VALUES ('a1', 'c1', 'screen_recording', 'C:/x.mp4', 'x.mp4', 0, 'pending', 0,"
                " 'now', 'now')"
            )
        )

    with database.engine.begin() as connection:
        connection.execute(text("DELETE FROM campaigns WHERE id = 'c1'"))

    with database.engine.connect() as connection:
        remaining = connection.execute(text("SELECT COUNT(*) FROM media_assets")).scalar_one()

    assert remaining == 0, "ON DELETE CASCADE did not fire"


def test_the_check_constraints_reject_an_invalid_enum_value(database: Database) -> None:
    migrated(database)

    with (
        pytest.raises(Exception, match="CHECK constraint failed"),
        database.engine.begin() as connection,
    ):
        connection.execute(
            text(
                "INSERT INTO campaigns (id, name, overlay_config, overlay_schema_version,"
                " quality_override, created_at, updated_at)"
                " VALUES ('c2', 'x', '{}', 1, 'ultra', 'now', 'now')"
            )
        )


# --- the singleton (Q60) ---------------------------------------------------


def test_the_migration_seeds_app_settings(database: Database) -> None:
    migrated(database)

    with database.engine.connect() as connection:
        row = connection.execute(
            text("SELECT id, quality_preset FROM app_settings")
        ).one()

    assert row.id == 1
    assert row.quality_preset == "standard"


def test_the_singleton_constraint_forbids_a_second_row(database: Database) -> None:
    migrated(database)

    with (
        pytest.raises(Exception, match="CHECK constraint failed"),
        database.engine.begin() as connection,
    ):
        connection.execute(
            text(
                "INSERT INTO app_settings (id, quality_preset, created_at, updated_at)"
                " VALUES (2, 'standard', 'now', 'now')"
            )
        )


def test_boot_heals_a_deleted_singleton(database: Database) -> None:
    # Q60: a missing singleton is a crash on every settings read. Three lines
    # of self-healing removes an entire class of "how did this database get
    # into this state" support work.
    migrated(database)

    with database.engine.begin() as connection:
        connection.execute(text("DELETE FROM app_settings"))

    migrate.heal_app_settings(database.engine)

    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM app_settings")).scalar_one() == 1


def test_healing_does_not_overwrite_a_present_singleton(database: Database) -> None:
    migrated(database)

    with database.engine.begin() as connection:
        connection.execute(text("UPDATE app_settings SET quality_preset = 'high' WHERE id = 1"))

    migrate.heal_app_settings(database.engine)

    with database.engine.connect() as connection:
        preset = connection.execute(text("SELECT quality_preset FROM app_settings")).scalar_one()

    assert preset == "high", "INSERT OR IGNORE must not clobber the user's setting"


# --- a database from the future (Q84) --------------------------------------


def test_an_unknown_revision_is_refused_before_upgrading(database: Database) -> None:
    # Manual checklist item 7. The refusal has to happen *before* the upgrade
    # runs — a database written by a newer version is not "behind", it is
    # unreadable, and `upgrade head` against it would either no-op or run
    # downgrade-shaped logic while the app writes against a schema it
    # misunderstands.
    migrated(database)

    with database.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '9999'"))

    outcome = migrate.run_migrations(database.engine, database.path)

    assert not outcome.ok
    assert outcome.newer_than_app
    assert outcome.detail is not None
    assert "9999" in outcome.detail


def test_a_refused_database_leaves_the_report_degraded(database: Database) -> None:
    migrated(database)
    with database.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '9999'"))

    report = BootReport(
        boot_id="b",
        workspace_path="w",
        boot_log_path="b.log",
        backend_log_path="s.log",
    )
    migrate.apply_outcome(report, migrate.run_migrations(database.engine, database.path))

    # Q84: degraded means zero sessions handed out — `get_session` raises 503
    # before yielding, so nothing can write against a schema it does not
    # understand.
    assert report.status == "degraded"
    assert report.detail is not None


# --- backups (Q85) ---------------------------------------------------------


def test_no_backup_is_taken_for_a_database_that_does_not_exist_yet(
    database: Database,
) -> None:
    outcome = migrated(database)
    assert outcome.backup_path is None, "there is nothing to back up on a first run"


def test_a_backup_is_a_real_database_not_a_copy_of_the_main_file(
    tmp_workspace: WorkspaceLayout,
) -> None:
    # Q85: this is the one that would have cost data. In WAL mode, recently
    # committed transactions live in `outreachos.db-wal`, so a `shutil.copy`
    # produces a backup silently missing the most recent work. `VACUUM INTO`
    # reads through the WAL.
    database = Database(tmp_workspace.database)
    migrated(database)

    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO campaigns (id, name, overlay_config, overlay_schema_version,"
                " created_at, updated_at) VALUES ('recent', 'x', '{}', 1, 'now', 'now')"
            )
        )

    # The row is committed but, in WAL mode, is not necessarily in the main
    # file yet — which is exactly the condition a naive copy gets wrong.
    backup = migrate._backup(database.path, "0001")

    restored = sqlite3.connect(str(backup))
    try:
        found = restored.execute("SELECT COUNT(*) FROM campaigns WHERE id = 'recent'").fetchone()
    finally:
        restored.close()

    assert found[0] == 1, "the backup is missing a committed transaction"


def test_backups_are_pruned_to_three(tmp_workspace: WorkspaceLayout) -> None:
    database = Database(tmp_workspace.database)
    migrated(database)

    for revision in ("a", "b", "c", "d", "e"):
        migrate._backup(database.path, revision)

    backups = sorted(Path(database.path).parent.glob(f"{database.path.name}.bak-*"))
    assert len(backups) == migrate.BACKUP_RETENTION
