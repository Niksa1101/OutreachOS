"""Every enumerated value in the schema, defined once.

Q59 sets the rule and it has a sharp edge worth restating:

    **Migration files hardcode the literal values. They never import these.**

A migration is a frozen historical snapshot of what the schema was. If it
imported a live enum, adding a member here would silently rewrite the meaning
of a migration that already ran — the ``CHECK`` constraint in revision 0001
would start describing a constraint that revision never created.

``test_schema_drift.py`` is what keeps the two honest: it compares the models
against the migration head, so the duplication cannot rot unnoticed.

``StrEnum`` rather than ``Enum``: DB.md §2 stores enums as ``TEXT`` with a
``CHECK`` constraint, and a ``StrEnum`` member *is* its string. It goes into
SQLite, into JSON, and into the OpenAPI schema without a conversion step
anywhere.
"""

from enum import StrEnum

__all__ = [
    "AssetRole",
    "JobStatus",
    "JobType",
    "ProbeStatus",
    "QualityPreset",
]


class AssetRole(StrEnum):
    """DB.md §3.2."""

    TALKING_HEAD = "talking_head"
    SCREEN_RECORDING = "screen_recording"


class ProbeStatus(StrEnum):
    """DB.md §3.2. ``pending`` is the state a row is created in."""

    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"


class JobType(StrEnum):
    """DB.md §3.3. One table serves both so the queue is genuinely unified."""

    ALPHA_PREPARE = "alpha_prepare"
    VIDEO_RENDER = "video_render"


class JobStatus(StrEnum):
    """DB.md §4.2.

    Note that ``rendering`` belongs to ``alpha_prepare`` and ``encoding`` to
    ``video_render`` — they are stages of different job types, not a sequence
    one job passes through.
    """

    WAITING = "waiting"
    PREPARING = "preparing"
    RENDERING = "rendering"
    ENCODING = "encoding"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def active(cls) -> tuple["JobStatus", ...]:
        """The statuses that mean "this campaign is busy".

        DB.md §6's editor lock check. Also the set that DB.md §3.3 resets to
        ``waiting`` at startup, minus ``waiting`` itself.
        """
        return (cls.WAITING, cls.PREPARING, cls.RENDERING, cls.ENCODING)

    @classmethod
    def interrupted(cls) -> tuple["JobStatus", ...]:
        """Statuses that cannot survive a restart.

        DB.md §3.3: any job left in one of these resets to ``waiting`` and its
        partial output is deleted. A process that was mid-encode when it died
        left a truncated file behind.
        """
        return (cls.PREPARING, cls.RENDERING, cls.ENCODING)


class QualityPreset(StrEnum):
    """DB.md §3.1 and §3.5."""

    DRAFT = "draft"
    STANDARD = "standard"
    HIGH = "high"
