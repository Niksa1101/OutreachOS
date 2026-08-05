"""FFprobe wrapper returning frozen probe results."""

from __future__ import annotations

import json
from fractions import Fraction
from typing import Any

from pydantic import BaseModel, ConfigDict

from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.errors import RenderError, RenderFatalError
from outreachos_backend.rendering.process import run_tool

__all__ = ["ProbeResult", "probe_media"]


class ProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    duration_s: float
    width: int
    height: int
    display_width: int
    display_height: int
    fps: float
    codec_name: str
    has_audio: bool
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    rotation: int = 0
    nb_frames: int | None = None


def probe_media(binaries: Binaries, path: str) -> ProbeResult:
    command = [
        str(binaries.ffprobe),
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,"
        "sample_rate,channels,nb_frames:stream_tags=rotate:stream_side_data",
        "-of",
        "json",
        path,
    ]
    try:
        stdout = run_tool(command, timeout_s=60.0)
    except RenderError as exc:
        raise RenderFatalError(f"FFprobe failed for {path}: {exc}") from exc

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RenderFatalError(f"Unparseable ffprobe output for {path}: {exc}") from exc
    streams: list[dict[str, Any]] = payload.get("streams", [])
    video = next(
        (s for s in streams if s.get("codec_type") == "video"), streams[0] if streams else None
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise RenderFatalError(f"No video stream in {path}")

    rotation = _rotation_from_stream(video)
    width = int(video["width"])
    height = int(video["height"])
    display_width, display_height = _display_dimensions(width, height, rotation)

    fps = _parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1")
    duration = _parse_float(payload.get("format", {}).get("duration"))

    nb_raw = video.get("nb_frames")
    nb_frames = int(nb_raw) if nb_raw not in (None, "N/A") else None

    return ProbeResult(
        path=path,
        duration_s=duration,
        width=width,
        height=height,
        display_width=display_width,
        display_height=display_height,
        fps=fps,
        codec_name=str(video.get("codec_name", "unknown")),
        has_audio=audio is not None,
        audio_sample_rate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        audio_channels=int(audio["channels"]) if audio and audio.get("channels") else None,
        rotation=rotation,
        nb_frames=nb_frames,
    )


def _parse_float(value: Any) -> float:
    """Containers without a duration report it absent or as the string "N/A"."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_fps(value: str) -> float:
    if value in ("0/0", "N/A", ""):
        return 30.0
    try:
        frac = Fraction(value)
        if frac.numerator == 0:
            return 30.0
        return float(frac)
    except (ValueError, ZeroDivisionError):
        return 30.0


def _rotation_from_stream(stream: dict[str, Any]) -> int:
    # ffprobe reports a display-matrix rotation of -90 for a quarter turn clockwise;
    # Python's % maps that onto 270, which is what _display_dimensions expects.
    for side in stream.get("side_data_list") or []:
        if side.get("side_data_type") == "Display Matrix" and "rotation" in side:
            return round(_parse_float(side["rotation"])) % 360
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        return round(_parse_float(tags["rotate"])) % 360
    return 0


def _display_dimensions(width: int, height: int, rotation: int) -> tuple[int, int]:
    if rotation in (90, 270):
        return height, width
    return width, height
