"""Logging configuration.

Q35: stdlib ``logging`` with ``dictConfig`` at boot and a rotating file handler,
with uvicorn's own loggers re-parented so access logs cannot land somewhere
else. Q24: human-readable text lines, 10 MB x 5 — a user opens this file.

Two Windows-specific hazards are handled here rather than discovered later:

- ``RotatingFileHandler`` cannot rename a file another process holds open, and
  the diagnostics screen is *designed* to read this file. Stock behaviour is to
  raise out of ``emit``, which the logging module then reports and swallows
  while leaving the handler with a closed stream — so every subsequent log line
  vanishes. Q86 asks for the failure to be tolerated; ``_SafeRotatingHandler``
  does that and reopens.
- ``delay=True`` so the file is not created until something is actually logged.

Also note what is *not* here: ``fileConfig``. Alembic's stock ``env.py`` calls
it, which reconfigures the root logger and destroys every handler set up below.
Migrations run at boot, so that call silently kills logging for the rest of the
process. It is deleted in ``alembic/env.py`` — see Q58.
"""

import logging
import logging.config
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from outreachos_backend.core.config import LogLevel

__all__ = ["configure_logging"]

# Q24: 10 MB x 5. Bigger than boot.log's 2 MB x 3 because this one carries
# per-job FFmpeg output from P1 onward.
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

# Matches boot.log's shape so a user reading both files reads one format.
# `[python]` is this process's counterpart to Rust's `[rust]` and the webview's
# `[client]`.
LINE_FORMAT = "%(asctime)s.%(msecs)03dZ %(levelname)-5s [python] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


class _SafeRotatingHandler(RotatingFileHandler):
    """A rotating handler that survives a locked file.

    See the module docstring. The important part is the reopen: the base class
    closes the stream *before* attempting the rename, so swallowing the error
    without reopening leaves a handler that silently discards everything.
    """

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError:
            if self.stream is None:
                self.stream = self._open()
            # Rotation will be retried on the next record. Until then this file
            # grows past maxBytes, which is strictly better than losing lines.
            self.stream.write(
                "--- log rotation deferred: the previous file is held open by another process ---\n"
            )


def _dict_config(log_file: Path, level: LogLevel) -> dict[str, Any]:
    return {
        "version": 1,
        # False, and it matters: uvicorn creates its loggers at import time,
        # which is before this runs. Disabling them here would silence the
        # server's own startup and error reporting.
        "disable_existing_loggers": False,
        "formatters": {
            "text": {
                "format": LINE_FORMAT,
                "datefmt": DATE_FORMAT,
            }
        },
        "handlers": {
            "file": {
                "()": _SafeRotatingHandler,
                "filename": str(log_file),
                "maxBytes": MAX_BYTES,
                "backupCount": BACKUP_COUNT,
                "encoding": "utf-8",
                "delay": True,
                "formatter": "text",
            },
            # Rust forwards everything non-control from stdout and stderr into
            # boot.log (Q39). This handler is what makes a crash during startup
            # — before the file handler has a workspace to write to — visible
            # at all.
            "stderr": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "text",
            },
        },
        "root": {
            "handlers": ["file", "stderr"],
            "level": level,
        },
        "loggers": {
            # Re-parented, not silenced: they keep propagating to root, which
            # owns the handlers. Q35.
            "uvicorn": {"handlers": [], "propagate": True, "level": level},
            "uvicorn.error": {"handlers": [], "propagate": True, "level": level},
            # `access_log=False` is set on the uvicorn Config as well. The boot
            # health poll runs at 250ms (Q76) and would otherwise write ~80
            # lines into a file a user is expected to read.
            "uvicorn.access": {"handlers": [], "propagate": True, "level": "WARNING"},
        },
    }


def configure_logging(log_file: Path, level: LogLevel) -> None:
    """Install the logging configuration. Call once, at boot, before anything
    that might log."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    # UTC, to agree with `utcnow_iso` and with the Rust log. Two log files from
    # the same incident in two timezones is a genuinely painful way to spend an
    # afternoon. Set before dictConfig so the first record is already correct.
    logging.Formatter.converter = time.gmtime
    logging.config.dictConfig(_dict_config(log_file, level))
