"""Shared model infrastructure, and the one table that is not a module's.

DB.md §2 fixes the conventions and Q33/Q71 fix how they are enforced:

- Primary keys are ``TEXT`` UUIDv4, generated **Python-side** rather than by a
  database default. Keeps it testable and DB-agnostic.
- Timestamps are ``TEXT`` ISO-8601 UTC with a ``Z`` suffix, produced only by
  :func:`utcnow_iso`. They live in a mixin so ``created_at``/``updated_at`` are
  inherited and never hand-written — which makes the grep for violations
  trivial, and is the actual enforcement. The columns are ``Mapped[str]``, so
  nothing at the type level would stop someone writing a raw string; the mixin
  is what means nobody has to.
"""

import uuid

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from outreachos_backend.core.enums import QualityPreset
from outreachos_backend.core.timeutil import utcnow_iso

__all__ = ["AppSettings", "Base", "TimestampMixin", "new_id"]


def new_id() -> str:
    """DB.md §2: ``TEXT`` UUIDv4."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Declarative base for every table in the application.

    One base across ``core`` and every module, because Alembic autogenerate
    needs a single ``metadata`` to compare against. Modules add tables to it;
    they do not get their own.
    """


class TimestampMixin:
    """``created_at`` and ``updated_at`` on every table (DB.md §2)."""

    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=utcnow_iso,
        # `onupdate` fires on a flush that actually changes something, which is
        # the definition that matters — an unchanged row keeps its timestamp.
        onupdate=utcnow_iso,
    )


class AppSettings(TimestampMixin, Base):
    """DB.md §3.5. A single row, ``id = 1``.

    Q60: seeded by the migration **and** self-healed at boot with an idempotent
    ``INSERT OR IGNORE``. A missing singleton is a crash on every settings
    read; three lines of self-healing removes an entire class of "how did this
    database get into this state" support work.

    The workspace path is deliberately absent — DB.md §1 puts it in OS app-data,
    because a pointer cannot live inside the thing it points to.
    """

    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_app_settings_singleton"),
        CheckConstraint(
            "quality_preset IN ('draft', 'standard', 'high')",
            name="ck_app_settings_quality_preset",
        ),
    )

    # INTEGER, not TEXT: DB.md §3.5 is explicit, and it is what makes the
    # `id = 1` constraint meaningful.
    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    quality_preset: Mapped[str] = mapped_column(
        String, nullable=False, default=QualityPreset.STANDARD.value
    )
    encoder_override: Mapped[str | None] = mapped_column(String, nullable=True)
    """NULL means auto-detect (Tech.md §5.2: NVENC → QSV → AMF → libx264)."""

    default_export_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    ffmpeg_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_encoders: Mapped[str | None] = mapped_column(Text, nullable=True)
    """JSON array from the capability probe, shown in Settings."""
