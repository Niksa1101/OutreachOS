"""FFmpeg binary resolution — never from PATH."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from outreachos_backend.rendering.errors import RenderFatalError, RenderVersionError
from outreachos_backend.rendering.process import run_tool

__all__ = ["PINNED_VERSION_PREFIX", "Binaries", "resolve_binaries"]

log = logging.getLogger(__name__)

# First line prefix from vendor/ffmpeg/VERSION.txt after fetch-ffmpeg.ps1
PINNED_VERSION_PREFIX = "ffmpeg version n7.1.5"

# Windows is the only shipping target, but keeping the suffix conditional lets the
# package be imported and unit-tested elsewhere instead of failing at path building.
_EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""


@dataclass(frozen=True)
class Binaries:
    directory: Path
    ffmpeg: Path
    ffprobe: Path
    version_line: str


def resolve_binaries(
    ffmpeg_dir: Path | None,
    *,
    strict_version: bool = False,
) -> Binaries:
    if ffmpeg_dir is None:
        raise RenderFatalError(
            "FFmpeg directory not configured. Pass --ffmpeg-dir or set OOS_FFMPEG_DIR."
        )
    directory = ffmpeg_dir.resolve()
    ffmpeg = directory / f"ffmpeg{_EXE_SUFFIX}"
    ffprobe = directory / f"ffprobe{_EXE_SUFFIX}"
    for path in (ffmpeg, ffprobe):
        if not path.is_file():
            raise RenderFatalError(f"Missing FFmpeg binary: {path}")
    version_line = _read_version(ffmpeg)
    if not version_line.startswith(PINNED_VERSION_PREFIX):
        message = (
            f"FFmpeg version mismatch. Expected prefix {PINNED_VERSION_PREFIX!r}, "
            f"got {version_line!r}. Re-run scripts/fetch-ffmpeg.ps1."
        )
        if strict_version:
            raise RenderVersionError(message)
        log.warning(message)
    return Binaries(
        directory=directory,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        version_line=version_line,
    )


def _read_version(ffmpeg: Path) -> str:
    stdout = run_tool([str(ffmpeg), "-version"], timeout_s=30.0)
    first = stdout.splitlines()
    if not first:
        raise RenderFatalError(f"No output from {ffmpeg} -version")
    return first[0].strip()
