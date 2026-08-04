"""The dev-only token file.

Q43, and the third location in the threat model sentence.

The token exists in exactly three places:

1. On stdin, written once by Rust and read once here.
2. In one non-exported module binding in ``frontend/src/core/api``.
3. **In ``--dev`` builds only**, at ``%TEMP%\\outreachos-dev-token``.

The third is deliberate, not a leak. It is gated on ``cfg!(debug_assertions)``
in Rust, absent from packaged builds, and never written to the rolling log. It
is named explicitly here because a threat-model sentence that says "only" and
omits it leads someone reading this in six months to conclude the file is a bug
and delete it.

Unlike ``.oos-lock``, this file **is** swept at next boot. The distinction is
real: a stale lock may belong to a live instance on another machine, so
sweeping it would bypass the foreign-host warning it exists to raise. A stale
token file can only ever be ours and is worthless the moment the process that
wrote it exits.
"""

import logging
import tempfile
from pathlib import Path

__all__ = ["dev_token_path", "sweep_dev_token", "write_dev_token"]

log = logging.getLogger(__name__)

FILENAME = "outreachos-dev-token"


def dev_token_path() -> Path:
    return Path(tempfile.gettempdir()) / FILENAME


def write_dev_token(token: str) -> None:
    """Overwrite, never append.

    Appending would leave every previous boot's token in a file that is
    supposed to hold exactly one — and the reader would take the wrong one.
    """
    path = dev_token_path()
    try:
        path.write_text(token, encoding="utf-8")
        log.debug("dev token written to %s", path)
    except OSError:
        # Not fatal. This is a debugging convenience, not a dependency.
        log.warning("could not write the dev token file at %s", path, exc_info=True)


def sweep_dev_token() -> None:
    """Remove the file. Safe to call when it does not exist."""
    path = dev_token_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.warning("could not remove the dev token file at %s", path, exc_info=True)
