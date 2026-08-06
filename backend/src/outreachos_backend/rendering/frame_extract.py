"""Single-frame JPEG extraction for the campaign preview background."""

from __future__ import annotations

import os
from pathlib import Path

from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.cache import temp_sibling
from outreachos_backend.rendering.errors import RenderFatalError, RenderProcessError
from outreachos_backend.rendering.process import run_tool

__all__ = ["extract_frame"]


def extract_frame(binaries: Binaries, source: Path, timestamp_s: float, dest: Path) -> None:
    """Write one JPEG frame from ``source`` at ``timestamp_s`` to ``dest``.

    Writes through a temp sibling and ``os.replace`` — the same atomic-write
    shape as ``rendering.cache.atomic_write`` — so a reader can never observe a
    partially written cache file.

    Raises ``RenderProcessError``/``RenderFatalError`` on failure; callers
    degrade to the placeholder rather than letting this reach the client as a
    500 (ticket 09: "extraction failure degrades to the placeholder").
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = temp_sibling(dest, suffix=".tmp.jpg")
    command = [
        str(binaries.ffmpeg),
        "-y",
        "-ss",
        f"{timestamp_s:.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(tmp),
    ]
    try:
        run_tool(command, timeout_s=30.0)
        if not tmp.is_file():
            raise RenderFatalError(f"FFmpeg produced no output frame for {source}")
        os.replace(tmp, dest)
    except (RenderProcessError, RenderFatalError, OSError):
        tmp.unlink(missing_ok=True)
        raise
