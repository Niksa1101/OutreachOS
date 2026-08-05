"""Quality presets and encoder argument bundles."""

from __future__ import annotations

from typing import Literal

from outreachos_backend.rendering.config import QualityPreset

__all__ = [
    "audio_encode_args",
    "video_encode_args",
]

_GOP = ["-g", "60", "-keyint_min", "60"]

_COLOR = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]

# ADR-0009: libx264's default thread count derives from core count, and frame/slice
# threading changes the bitstream. Reproducible output therefore needs threading
# pinned — production keeps the default and pays nothing for it.
_DETERMINISTIC = ["-threads", "1", "-x264-params", "sliced-threads=0"]


def video_encode_args(
    encoder: str,
    quality: QualityPreset,
    *,
    force_libx264: bool = False,
    deterministic: bool = False,
) -> list[str]:
    enc = "libx264" if force_libx264 or deterministic else encoder
    tier = _CRF[quality]
    if enc == "libx264":
        return [
            "-c:v",
            "libx264",
            "-crf",
            str(tier),
            "-preset",
            _PRESET[quality],
            *_GOP,
            *_COLOR,
            *(_DETERMINISTIC if deterministic else []),
        ]
    if enc == "h264_nvenc":
        return [
            "-c:v",
            "h264_nvenc",
            "-rc",
            "vbr",
            "-b:v",
            "0",
            "-cq",
            str(tier),
            *_GOP,
            *_COLOR,
        ]
    if enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", str(tier), *_GOP, *_COLOR]
    if enc == "h264_amf":
        return [
            "-c:v",
            "h264_amf",
            "-quality",
            "balanced",
            "-rc",
            "cqp",
            "-qp_i",
            str(tier),
            "-qp_p",
            str(tier),
            *_GOP,
            *_COLOR,
        ]
    return video_encode_args("libx264", quality, force_libx264=True, deterministic=deterministic)


def audio_encode_args() -> list[str]:
    return ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


_CRF: dict[QualityPreset, int] = {
    "draft": 28,
    "standard": 23,
    "high": 18,
}

_PRESET: dict[QualityPreset, Literal["ultrafast", "medium", "slow"]] = {
    "draft": "ultrafast",
    "standard": "medium",
    "high": "slow",
}
