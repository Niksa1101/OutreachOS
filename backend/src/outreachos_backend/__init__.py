"""OutreachOS backend — the FastAPI sidecar.

Spawned by Tauri with ``--workspace``, ``--log-level`` and ``--dev``, plus a
single JSON line on stdin carrying ``boot_id`` and the shared-secret token. The
process binds port 0 itself and reports the resolved port on an ``@@OOS``
control line; stdin EOF is its shutdown signal.

The token is read once from stdin and never appears in argv, in the environment,
or in any log.
"""

from outreachos_backend._version import __version__

__all__ = ["__version__"]
