"""Cache key computation and filesystem cache."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.config import OverlayConfig, TalkingHeadConfig
from outreachos_backend.rendering.errors import RenderError
from outreachos_backend.rendering.geometry import OverlayGeometry, compute_geometry
from outreachos_backend.rendering.probe import ProbeResult, probe_media

__all__ = [
    "ALPHA_FORMAT_VERSION",
    "ASSETS_FORMAT_VERSION",
    "PREVIEW_FRAME_FORMAT_VERSION",
    "AlphaManifest",
    "CacheLayout",
    "alpha_cache_key",
    "assets_cache_key",
    "canonical_json",
    "preview_frame_cache_key",
    "preview_frame_path",
    "stat_fingerprint",
    "temp_sibling",
]

ASSETS_FORMAT_VERSION = 1
ALPHA_FORMAT_VERSION = 1
PREVIEW_FRAME_FORMAT_VERSION = 1


@dataclass(frozen=True)
class CacheLayout:
    root: Path

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets"

    @property
    def alpha_dir(self) -> Path:
        return self.root / "alpha"

    @property
    def frames_dir(self) -> Path:
        return self.root / "frames"


@dataclass(frozen=True)
class AlphaManifest:
    owner_ref: str
    owner_kind: str
    alpha_key: str
    assets_key: str


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def stat_fingerprint(path: Path) -> str:
    stat = path.stat()
    normalized = os.path.normcase(str(path.resolve()))
    return f"{normalized}|{stat.st_mtime_ns}|{stat.st_size}"


def assets_cache_key(overlay: OverlayConfig, geometry: OverlayGeometry | None = None) -> str:
    geom = geometry or compute_geometry(overlay)
    payload = {
        "version": ASSETS_FORMAT_VERSION,
        "overlay": overlay.model_dump(mode="json"),
        "bleed": {
            "width": geom.bleed_width,
            "height": geom.bleed_height,
            "insets": geom.bleed_insets.__dict__,
        },
    }
    return _sha256(canonical_json(payload))


def alpha_cache_key(
    talking_head: TalkingHeadConfig,
    overlay: OverlayConfig,
    assets_key: str,
) -> str:
    source = talking_head.source_path
    payload = {
        "version": ALPHA_FORMAT_VERSION,
        "source": stat_fingerprint(source),
        "trim_start_ms": talking_head.trim_start_ms,
        "trim_end_ms": talking_head.trim_end_ms,
        "focal_x": talking_head.focal_x,
        "focal_y": talking_head.focal_y,
        "assets_key": assets_key,
    }
    return _sha256(canonical_json(payload))


def preview_frame_cache_key(source_path: Path, timestamp_ms: int) -> str:
    """Content-addressed by source file identity, not by campaign or asset id.

    Ticket 09: re-extraction on a source change falls out for free — relocating
    or replacing the first recording changes ``stat_fingerprint`` and therefore
    the key, so a stale frame is never served without any explicit invalidation
    step, the same self-invalidating shape as ``alpha_cache_key``.
    """
    payload = {
        "version": PREVIEW_FRAME_FORMAT_VERSION,
        "source": stat_fingerprint(source_path),
        "timestamp_ms": timestamp_ms,
    }
    return _sha256(canonical_json(payload))


def preview_frame_path(layout: CacheLayout, frame_key: str) -> Path:
    return layout.frames_dir / f"{frame_key}.jpg"


def alpha_clip_path(layout: CacheLayout, alpha_key: str) -> Path:
    return layout.alpha_dir / f"{alpha_key}.mov"


def alpha_manifest_path(layout: CacheLayout, alpha_key: str) -> Path:
    return layout.alpha_dir / f"{alpha_key}.manifest.json"


def probe_alpha_cache_hit(binaries: Binaries, clip: Path) -> ProbeResult | None:
    """The cached clip's probe result, or None if it is missing or unreadable.

    Returns the probe rather than a bool so callers don't have to spawn ffprobe a
    second time for the frame count.
    """
    if not clip.is_file():
        return None
    try:
        return probe_media(binaries, str(clip))
    except RenderError:
        return None


def temp_sibling(path: Path, suffix: str = ".tmp") -> Path:
    """A writer-private temp path next to ``path``.

    The pid/uuid component matters: cache paths are content-addressed, so two
    processes building the same key would otherwise pick the same temp name and
    interleave their writes into it.
    """
    return path.with_name(f"{path.name}.{os.getpid()}-{uuid4().hex[:8]}{suffix}")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = temp_sibling(path)
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write(path, text.encode("utf-8"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
