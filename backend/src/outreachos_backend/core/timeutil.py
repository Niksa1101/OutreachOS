"""The one place a timestamp is constructed.

Q33/Q71: every timestamp in this application is ISO-8601 UTC with a ``Z``
suffix, produced here and nowhere else.

``datetime.now(UTC).isoformat()`` emits ``+00:00``, not ``Z``. Both sort
correctly as strings and both are valid ISO-8601, which is exactly why mixing
them is dangerous: nothing fails, until two phases later a string comparison
against a hardcoded ``Z`` literal silently matches nothing. Routing every
timestamp through one helper makes the grep for violations trivial.
"""

from datetime import UTC, datetime

__all__ = ["utcnow_iso"]


def utcnow_iso() -> str:
    """Current UTC time as ``2026-08-04T11:50:52.253Z``.

    Millisecond precision, deliberately. DB.md §2 measures durations in integer
    milliseconds; a timestamp with more resolution than the data it describes
    invites someone to compare the two.
    """
    now = datetime.now(UTC)
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{now.microsecond // 1000:03d}Z"
