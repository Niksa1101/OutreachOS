"""Process entry point: ``python -m outreachos_backend``.

The whole sidecar contract lives in this file, in the order it happens.

1. Parse CLI arguments (Q34: everything except the token).
2. Read **one line** from stdin carrying ``{"boot_id", "token"}`` (Q75). The
   token never appears in argv, in the environment, or in any log — any
   same-user process can read another's command line through WMI.
3. Create the workspace directory tree and start logging.
4. Bind ``127.0.0.1:0`` **here**, not in Rust, and report the resolved port on
   an ``@@OOS`` control line (ADR-0002). The socket is then handed to uvicorn,
   so there is no window in which the port is known but unbound.
5. Serve until stdin reaches EOF, which is the shutdown signal (Q37).

Shutdown order is Q118's and is not arbitrary: SSE streams are released
*before* uvicorn begins its own shutdown, because uvicorn waits for open
connections and an SSE stream never closes on its own. Getting this backwards
means the 5s grace period expires and Rust hard-kills a process that was
shutting down correctly.
"""

import contextlib
import json
import logging
import os
import secrets
import socket
import sys
import tempfile
import threading
import uuid
from pathlib import Path

import uvicorn

from outreachos_backend.core import control, devtoken
from outreachos_backend.core.app import create_app
from outreachos_backend.core.boot import BootReport, Runtime
from outreachos_backend.core.config import LaunchConfig, parse_launch_config
from outreachos_backend.core.events import EventBus
from outreachos_backend.core.logging import configure_logging
from outreachos_backend.core.workspace import prepare_workspace

log = logging.getLogger(__name__)

#: Q62: Rust writes here too, and the diagnostics screen reads it. Recomputed
#: rather than passed so the two sides cannot disagree about where it is.
_BOOT_LOG_RELATIVE = Path("OutreachOS") / "logs" / "boot.log"


class Handshake:
    """What arrived on the first line of stdin."""

    def __init__(self, boot_id: str, token: str, *, from_shell: bool) -> None:
        self.boot_id = boot_id
        self.token = token
        self.from_shell = from_shell
        """False when the sidecar was started by hand rather than by Tauri.

        Q126: ``pnpm dev:backend`` runs this process standalone with no Rust in
        the picture. That mode has to work — it is where you debug ``/health``
        — so it synthesises its own identity rather than refusing to start.
        """


def read_handshake() -> Handshake:
    """Read exactly one line from stdin and parse it.

    Binary mode throughout: the shutdown watcher reads the same stream, and
    mixing ``sys.stdin.readline()`` with ``sys.stdin.buffer.read()`` leaves
    bytes stranded in the text wrapper's buffer.
    """
    raw = b""
    # No stdin at all — a double-clicked exe, or a test harness. Falls through
    # to the standalone branch below rather than failing.
    with contextlib.suppress(OSError, ValueError):
        raw = sys.stdin.buffer.readline()

    if raw.strip():
        try:
            payload = json.loads(raw.decode("utf-8"))
            return Handshake(
                boot_id=str(payload["boot_id"]),
                token=str(payload["token"]),
                from_shell=True,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            # Deliberately not fatal-with-a-dump: the line contains the token,
            # so it must not be echoed into the error. Rust's handshake budget
            # will surface this as `handshake_timeout` with the stderr below.
            print(
                f"outreachos-backend: unusable handshake line ({type(error).__name__}); "
                "expected one line of JSON with boot_id and token",
                file=sys.stderr,
            )
            raise SystemExit(2) from error

    return Handshake(
        boot_id=str(uuid.uuid4()),
        token=secrets.token_hex(32),
        from_shell=False,
    )


def _boot_log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return Path(base) / _BOOT_LOG_RELATIVE


def _bind(port: int) -> socket.socket:
    """Bind and listen, returning the socket uvicorn will serve on.

    Note the absence of ``SO_REUSEADDR``. On Windows it does not mean what it
    means on Unix — it permits binding a port another socket is *actively*
    using, which would turn "the port is taken" into two processes silently
    sharing one and is precisely the race ADR-0002 removed.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port))
    sock.listen(128)
    sock.set_inheritable(True)
    return sock


def _watch_stdin_for_eof(on_eof: threading.Event) -> None:
    """Block until stdin closes, then set the event.

    Q37: Rust closes the sidecar's stdin to request shutdown, and hard-kills
    after a 5s grace period. This works identically in dev and packaged, which
    is the reason it was chosen over a console control event.
    """
    try:
        while sys.stdin.buffer.read(1):
            # Nothing else is ever sent on this channel. Bytes arriving here
            # are a protocol violation, not data — ignore rather than parse.
            pass
    except (OSError, ValueError):
        pass
    finally:
        on_eof.set()


def _serve(config: LaunchConfig, handshake: Handshake, report: BootReport) -> int:
    app = create_app(dev=config.dev)

    bus = EventBus(boot_id=handshake.boot_id)
    app.state.event_bus = bus
    app.state.runtime = Runtime(report=report, token=handshake.token, dev=config.dev)

    sock = _bind(config.port)
    port = int(sock.getsockname()[1])

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            # Both deliberate. `log_config=None` stops uvicorn replacing the
            # dictConfig set up above; `access_log=False` stops the boot health
            # poll — 250ms intervals for up to 20s — writing ~80 lines into a
            # file a user is expected to read.
            log_config=None,
            access_log=False,
            # There is exactly one client and it is on loopback. Waiting on a
            # peer that has already gone away only delays shutdown.
            timeout_graceful_shutdown=3,
        )
    )

    # Only now, with the socket bound and the server constructed, is the port
    # real. Rust is blocked on this line with a 10s budget (Q76).
    control.emit({"port": port, "boot_id": handshake.boot_id})
    log.info("listening on 127.0.0.1:%d (boot_id=%s)", port, handshake.boot_id)

    if handshake.from_shell:
        eof = threading.Event()
        threading.Thread(
            target=_watch_stdin_for_eof, args=(eof,), name="stdin-eof", daemon=True
        ).start()
        threading.Thread(
            target=_shutdown_on_eof, args=(eof, bus, server), name="shutdown", daemon=True
        ).start()
    else:
        log.warning(
            "no handshake on stdin; running standalone with a self-generated token. "
            "This mode exists for `pnpm dev:backend` and has no shutdown channel — "
            "use Ctrl-C."
        )

    server.run(sockets=[sock])
    return 0


def _shutdown_on_eof(eof: threading.Event, bus: EventBus, server: uvicorn.Server) -> None:
    eof.wait()
    log.info("stdin closed; shutting down")

    # Q118, and the order matters. Releasing the SSE streams first is what lets
    # uvicorn's graceful shutdown actually complete.
    bus.begin_shutdown()
    server.should_exit = True


def main() -> int:
    config = parse_launch_config()
    handshake = read_handshake()

    layout = prepare_workspace(config.workspace)
    configure_logging(layout.log_file, config.log_level)

    log.info(
        "outreachos-backend starting (workspace=%s, dev=%s, level=%s)",
        layout.root,
        config.dev,
        config.log_level,
    )
    if config.ffmpeg_dir is not None:
        # Accepted and recorded in P0, used in P1. Logging it now means a
        # wrong path is visible one phase before it matters.
        log.info("ffmpeg directory: %s", config.ffmpeg_dir)

    # Swept unconditionally, written only in dev. A packaged build inheriting a
    # stale file from a dev session on the same machine would leave a valid-
    # looking token on disk that unlocks nothing.
    devtoken.sweep_dev_token()
    if config.dev:
        devtoken.write_dev_token(handshake.token)

    report = BootReport(
        boot_id=handshake.boot_id,
        workspace_path=str(layout.root),
        boot_log_path=str(_boot_log_path()),
        backend_log_path=str(layout.log_file),
        app_version=config.app_version,
    )

    try:
        return _serve(config, handshake, report)
    finally:
        # Q118's tail. `.oos-lock` removal joins here in checkpoint 5, between
        # the server stopping and the handlers flushing.
        devtoken.sweep_dev_token()
        logging.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
