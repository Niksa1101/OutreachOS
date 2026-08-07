"""Encoder capability detection with real-dimension trial encodes."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.process import FfmpegProcess

__all__ = ["default_encoder_from_list", "detect_encoders", "select_encoder"]

log = logging.getLogger(__name__)

_CANDIDATES: list[tuple[str, list[str]]] = [
    ("h264_nvenc", ["-rc", "vbr", "-b:v", "0", "-cq", "23"]),
    ("h264_qsv", ["-global_quality", "23"]),
    ("h264_amf", ["-quality", "balanced", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]),
    ("libx264", ["-crf", "23", "-preset", "medium"]),
]

_cache: dict[str, list[str]] = {}


def detect_encoders(binaries: Binaries) -> list[str]:
    key = binaries.version_line
    if key in _cache:
        return list(_cache[key])

    available: list[str] = []
    encoders = _list_encoders(binaries)
    for name, extra in _CANDIDATES:
        if name not in encoders:
            continue
        if _trial_encode(binaries, name, extra):
            available.append(name)
        else:
            log.info("encoder %s failed trial encode at 1920x1080", name)

    if "libx264" not in available and "libx264" in encoders:
        # Deliberate last resort: if even the software encoder fails its trial there
        # is nothing left to fall back to, so surface it and let the real encode
        # report the actual error rather than claiming no encoders exist.
        log.warning("libx264 failed its trial encode; keeping it as the only fallback")
        available.append("libx264")

    _cache[key] = available
    return list(available)


def default_encoder_from_list(available: list[str]) -> str:
    """Pick the auto-detect default from a precomputed availability list."""
    for name, _ in _CANDIDATES:
        if name in available:
            return name
    return "libx264"


def select_encoder(binaries: Binaries, override: str | None = None) -> str:
    detected = detect_encoders(binaries)
    if override:
        if override not in detected and override != "libx264":
            log.warning("encoder override %s not available; falling back", override)
        else:
            return override
    return default_encoder_from_list(detected)


def _list_encoders(binaries: Binaries) -> set[str]:
    proc = FfmpegProcess([str(binaries.ffmpeg), "-hide_banner", "-encoders"])
    proc.run()
    names: set[str] = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            names.add(parts[1])
    return names


def _trial_encode(binaries: Binaries, encoder: str, extra: list[str]) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "trial.mp4"
        command = [
            str(binaries.ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=1920x1080:d=0.04",
            "-frames:v",
            "1",
            "-c:v",
            encoder,
            *extra,
            "-y",
            str(out),
        ]
        proc = FfmpegProcess(command)
        try:
            proc.run(stall_timeout_s=30.0)
        except Exception:
            return False
        return out.is_file() and out.stat().st_size > 0
