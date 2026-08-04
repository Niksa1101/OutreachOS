"""The models and the migration describe the same schema.

Q59 keeps two layers deliberately: the app imports live ``StrEnum``s, and the
migration hardcodes literals so a frozen historical snapshot stays frozen. Q61
adds this test, and it is what makes having two layers safe rather than merely
duplicated — without it, the enum could gain a member and only the models would
know.

The comparison runs Alembic's own autogenerate against a database built by the
real migration. An empty diff means the two agree; a non-empty one names
exactly what drifted.
"""

from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from outreachos_backend.core import migrate
from outreachos_backend.core.db import Database
from outreachos_backend.core.enums import AssetRole, JobStatus, JobType, ProbeStatus
from outreachos_backend.core.models import Base
from outreachos_backend.core.workspace import WorkspaceLayout

# Differences Alembic reports that are not drift.
#
# SQLite has no native boolean or enum, so DB.md §2 stores them as INTEGER 0/1
# and TEXT + CHECK. Alembic's reflection cannot see a CHECK constraint's
# semantics, so it has nothing to compare against and reports nothing — but
# `add_constraint`/`remove_constraint` pairs for unnamed constraints do show up
# on some SQLAlchemy versions and carry no signal.
_IGNORED_DIFF_KINDS = {"add_constraint", "remove_constraint"}


def _significant(diff: Any) -> bool:
    kind = diff[0] if isinstance(diff, tuple) else None
    return not (isinstance(kind, str) and kind in _IGNORED_DIFF_KINDS)


def test_the_models_match_the_migration_head(tmp_workspace: WorkspaceLayout) -> None:
    database = Database(tmp_workspace.database)
    outcome = migrate.run_migrations(database.engine, database.path)
    assert outcome.ok, outcome.detail

    with database.engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={"compare_type": True, "compare_server_default": True},
        )
        diffs = [diff for diff in compare_metadata(context, Base.metadata) if _significant(diff)]

    assert diffs == [], (
        "The SQLAlchemy models and the Alembic migration have drifted.\n"
        "Q59 keeps them as two layers on purpose; this is the test that keeps "
        "them honest.\n\n" + "\n".join(repr(diff) for diff in diffs)
    )


@pytest.mark.parametrize(
    ("enum_type", "table", "column"),
    [
        (AssetRole, "media_assets", "role"),
        (ProbeStatus, "media_assets", "probe_status"),
        (JobType, "render_jobs", "job_type"),
        (JobStatus, "render_jobs", "status"),
    ],
)
def test_every_enum_member_is_accepted_by_the_migrations_check_constraint(
    tmp_workspace: WorkspaceLayout,
    enum_type: type[AssetRole] | type[ProbeStatus] | type[JobType] | type[JobStatus],
    table: str,
    column: str,
) -> None:
    """The half `compare_metadata` cannot see.

    Alembic does not compare ``CHECK`` constraint *contents*, so a member added
    to a ``StrEnum`` without a migration would pass the diff above and then
    fail at runtime on the first insert. Reading the constraint's SQL out of
    ``sqlite_master`` is the only way to check it.
    """
    from sqlalchemy import text

    database = Database(tmp_workspace.database)
    assert migrate.run_migrations(database.engine, database.path).ok

    with database.engine.connect() as connection:
        ddl = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table},
        ).scalar_one()

    for member in enum_type:
        assert f"'{member.value}'" in ddl, (
            f"{enum_type.__name__}.{member.name} = '{member.value}' is not in the "
            f"CHECK constraint on {table}.{column}. Add a migration — do not edit "
            f"revision 0001, which is a frozen snapshot (Q59)."
        )
