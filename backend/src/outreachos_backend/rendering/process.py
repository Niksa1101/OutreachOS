"""FFmpeg subprocess wrapper with pipe draining and stall detection."""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from outreachos_backend.rendering.errors import RenderFatalError, RenderProcessError

__all__ = [
    "FfmpegProcess",
    "creation_flags",
    "kill_all",
    "register_shutdown_hook",
    "run_tool",
]

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


def creation_flags() -> int:
    """Keep console windows from flashing on Windows for every child process."""
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def run_tool(command: list[str], *, timeout_s: float = 120.0) -> str:
    """Run a short-lived ffmpeg/ffprobe query and return stdout.

    For one-shot queries whose output is small enough not to need the pipe-draining
    machinery of `FfmpegProcess`. Failures surface as `RenderError` subclasses so no
    caller has to handle raw `CalledProcessError`.
    """
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags(),
            timeout=timeout_s,
        )
    except subprocess.CalledProcessError as exc:
        raise RenderProcessError(
            f"{Path(command[0]).name} exited {exc.returncode}",
            command=command,
            stderr=exc.stderr or "",
            returncode=exc.returncode,
        ) from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RenderFatalError(f"Cannot execute {command[0]}: {exc}") from exc
    return completed.stdout


_live: list[subprocess.Popen[str]] = []
_live_lock = threading.Lock()
_shutdown_registered = False


@dataclass
class FfmpegProcess:
    command: list[str]
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    _proc: subprocess.Popen[str] | None = field(default=None, repr=False)

    def run(
        self,
        *,
        stall_timeout_s: float = 120.0,
        on_progress_line: ProgressCallback | None = None,
    ) -> None:
        creationflags = creation_flags()

        proc = subprocess.Popen(
            self.command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        self._proc = proc
        with _live_lock:
            _live.append(proc)

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        last_activity = time.monotonic()

        def reader(stream: TextIO, sink: list[str], is_progress: bool) -> None:
            nonlocal last_activity
            for line in iter(stream.readline, ""):
                sink.append(line)
                last_activity = time.monotonic()
                if is_progress and on_progress_line is not None:
                    on_progress_line(line.rstrip("\n"))

        assert proc.stdout is not None
        assert proc.stderr is not None
        out_thread = threading.Thread(
            target=reader, args=(proc.stdout, stdout_chunks, on_progress_line is not None)
        )
        err_thread = threading.Thread(target=reader, args=(proc.stderr, stderr_chunks, False))
        out_thread.start()
        err_thread.start()

        try:
            while proc.poll() is None:
                if time.monotonic() - last_activity > stall_timeout_s:
                    proc.kill()
                    raise RenderProcessError(
                        f"FFmpeg stalled for {stall_timeout_s}s",
                        command=self.command,
                        stderr="".join(stderr_chunks),
                    )
                time.sleep(0.1)
        finally:
            out_thread.join()
            err_thread.join()
            with _live_lock:
                if proc in _live:
                    _live.remove(proc)

        self.stdout = "".join(stdout_chunks)
        self.stderr = "".join(stderr_chunks)
        self.returncode = proc.returncode
        if proc.returncode != 0:
            raise RenderProcessError(
                f"FFmpeg exited {proc.returncode}",
                command=self.command,
                stderr=self.stderr,
                returncode=proc.returncode,
            )


def kill_all() -> None:
    with _live_lock:
        for proc in list(_live):
            with contextlib.suppress(OSError):
                proc.kill()
        _live.clear()


def register_shutdown_hook() -> None:
    global _shutdown_registered
    if _shutdown_registered:
        return
    _shutdown_registered = True
    import atexit

    atexit.register(kill_all)
