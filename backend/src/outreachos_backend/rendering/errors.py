"""Render-engine errors and warning codes — separate from core/errors.py (FastAPI)."""

from __future__ import annotations

import shlex
import subprocess
import sys

__all__ = [
    "WARN_ASPECT_RATIO_NOT_16_9",
    "WARN_RECORDING_SHORTER_THAN_TALKING_HEAD",
    "RenderError",
    "RenderFatalError",
    "RenderProcessError",
    "RenderUsageError",
    "RenderVersionError",
    "RenderWarning",
    "cap_stderr",
    "format_command",
]

WARN_ASPECT_RATIO_NOT_16_9 = "aspect_ratio_not_16_9"
WARN_RECORDING_SHORTER_THAN_TALKING_HEAD = "recording_shorter_than_talking_head"

_ERROR_DETAILS_CAP = 64 * 1024
_HEAD_TAIL_EACH = _ERROR_DETAILS_CAP // 2 - 64


class RenderError(Exception):
    """Base class for render-engine failures."""


class RenderUsageError(RenderError):
    """Invalid CLI usage — exit code 2."""


class RenderFatalError(RenderError):
    """Unrecoverable engine failure before or during a batch."""


class RenderProcessError(RenderError):
    """An FFmpeg subprocess exited non-zero."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str] | None = None,
        stderr: str = "",
        returncode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        # Full stream here — ADR-0011 caps at persistence / CLI print sites so
        # the rolling log can still receive the uncapped copy (ticket 20).
        self.stderr = stderr
        self.returncode = returncode


class RenderVersionError(RenderFatalError):
    """Pinned FFmpeg version mismatch under strict mode."""


class RenderWarning:
    """Non-fatal issue emitted alongside successful output."""

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message


def cap_stderr(text: str, *, limit: int = _ERROR_DETAILS_CAP) -> str:
    """Head+tail cap for stored error details (ADR-0011)."""
    if len(text) <= limit:
        return text
    omitted = len(text) - (_HEAD_TAIL_EACH * 2)
    marker = f"\n… [{omitted} bytes elided] …\n"
    return text[:_HEAD_TAIL_EACH] + marker + text[-_HEAD_TAIL_EACH:]


def format_command(command: list[str]) -> str:
    """Exact argv as a shell-pasteable string (Tech.md §5 / ticket 20)."""
    if sys.platform == "win32":
        return subprocess.list2cmdline(command)
    return shlex.join(command)
