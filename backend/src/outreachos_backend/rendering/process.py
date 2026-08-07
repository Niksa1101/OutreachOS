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
    "clear_cancel",
    "creation_flags",
    "is_cancelled",
    "kill_all",
    "kill_job",
    "register_shutdown_hook",
    "request_cancel",
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
_by_job: dict[str, subprocess.Popen[str]] = {}
_cancelled: set[str] = set()
_live_lock = threading.Lock()
_shutdown_registered = False


def request_cancel(job_id: str) -> None:
    """Mark ``job_id`` cancelled and kill its live FFmpeg process, if any."""
    with _live_lock:
        _cancelled.add(job_id)
        proc = _by_job.get(job_id)
    if proc is not None:
        with contextlib.suppress(OSError):
            proc.kill()


def is_cancelled(job_id: str) -> bool:
    with _live_lock:
        return job_id in _cancelled


def clear_cancel(job_id: str) -> None:
    with _live_lock:
        _cancelled.discard(job_id)


def kill_job(job_id: str) -> bool:
    """Kill the live process for ``job_id``. Returns whether one was found."""
    with _live_lock:
        proc = _by_job.get(job_id)
    if proc is None:
        return False
    with contextlib.suppress(OSError):
        proc.kill()
    return True


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
        job_id: str | None = None,
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
            if job_id is not None:
                _by_job[job_id] = proc

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
                if job_id is not None and _by_job.get(job_id) is proc:
                    del _by_job[job_id]

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
        _by_job.clear()


def register_shutdown_hook() -> None:
    global _shutdown_registered
    if _shutdown_registered:
        return
    _shutdown_registered = True
    import atexit

    atexit.register(kill_all)
