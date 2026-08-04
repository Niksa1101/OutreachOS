"""Alembic environment.

Two things are **deleted** from the stock template, and both deletions matter:

1. ``fileConfig(config.config_file_name)`` (Q58). It reconfigures the root
   logger and destroys the ``dictConfig`` handlers installed at boot.
   Migrations run at boot, so keeping it would silently kill logging for the
   rest of the process — the failure being that the log goes quiet, not that
   anything errors.

2. The offline path. ``run_migrations_offline()`` emits SQL to stdout, and
   stdout is the ``@@OOS`` control channel (Q39). Generating SQL there would at
   best be noise Rust forwards to the log and at worst a parse failure. There
   is no scenario in this application where offline mode is wanted.

The connection arrives through ``config.attributes["connection"]`` rather than
``set_main_option``, because ConfigParser does %-interpolation and the database
path is chosen by the user.
"""

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool

# Importing the models is what populates `Base.metadata`. Both modules are
# needed: `core` owns `app_settings`, `video_composer` owns the other four.
from outreachos_backend.core.models import Base
from outreachos_backend.modules.video_composer import models as _video_composer_models  # noqa: F401

config = context.config

target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite cannot ALTER most things in place, so any future migration
        # that changes a column has to rebuild the table. Turning this on here
        # means a generated migration works rather than raising at runtime on
        # the one database that matters.
        render_as_batch=True,
        # Without this, autogenerate ignores every server-side default and
        # reports a clean diff against a schema that differs.
        compare_server_default=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")

    if connection is not None:
        # The normal path: the application hands us its own connection, so
        # migrations run inside the process that is about to use the database.
        run_migrations(connection)
        return

    # `alembic revision --autogenerate` from a shell, where there is no
    # application to supply one. The URL comes from `-x url=...`.
    url = context.get_x_argument(as_dictionary=True).get("url")
    if not url:
        raise RuntimeError(
            "No connection was supplied. Run migrations through the application, "
            "or pass a URL: alembic -x url=sqlite:///path/to/outreachos.db ..."
        )

    engine = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with engine.connect() as standalone:
        run_migrations(standalone)


run_migrations_online()
