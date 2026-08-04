"""The ``@@OOS`` stdout control channel.

Q39: lines prefixed ``@@OOS `` are structured messages for Rust; everything
else on stdout and stderr is forwarded verbatim into the rolling log. A prefix
rather than a separate pipe because the sidecar already owns stdout and a third
handle would need plumbing on both sides for one line of traffic.

ADR-0002 is why this exists at all: Python binds port 0 itself and reports the
result, instead of Rust picking a port and hoping it is still free by the time
uvicorn gets there.

The parser is in ``src-tauri/src/sidecar.rs`` and is unit-tested there. Keep the
two in step — this is the narrowest and most load-bearing interface in the
application.
"""

import json
import sys
from collections.abc import Mapping

__all__ = ["CONTROL_PREFIX", "emit"]

CONTROL_PREFIX = "@@OOS "


def emit(payload: Mapping[str, object]) -> None:
    """Write one control line and flush it.

    The flush is not optional. Python buffers stdout when it is a pipe, which
    is exactly what it is here, and Rust is blocking on this line with a 10s
    budget (Q76). Without the flush the handshake times out on a message that
    was already written.
    """
    line = CONTROL_PREFIX + json.dumps(dict(payload), separators=(",", ":"))
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
