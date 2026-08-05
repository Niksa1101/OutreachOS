"""Cache key and invalidation tests."""

import json
from pathlib import Path

import pytest

from outreachos_backend.rendering.binaries import Binaries
from outreachos_backend.rendering.cache import (
    alpha_cache_key,
    assets_cache_key,
    atomic_write,
    probe_alpha_cache_hit,
    temp_sibling,
)
from outreachos_backend.rendering.config import (
    BorderConfig,
    OverlayConfig,
    TalkingHeadConfig,
)


def test_assets_key_changes_when_overlay_changes() -> None:
    a = OverlayConfig()
    b = OverlayConfig(border=BorderConfig(enabled=True, width=8, color="#FF0000"))
    assert assets_cache_key(a) != assets_cache_key(b)


def test_alpha_key_nested_under_assets_key(tmp_path: Path) -> None:
    overlay = OverlayConfig()
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"\x00")
    head = TalkingHeadConfig(source_path=sample)
    assets = assets_cache_key(overlay)
    k1 = alpha_cache_key(head, overlay, assets)
    k2 = alpha_cache_key(
        head.model_copy(update={"focal_x": 0.25}),
        overlay,
        assets,
    )
    assert k1 != k2


@pytest.mark.render
def test_cache_hit_requires_probe_ok(
    ffmpeg_binaries: Binaries,
    render_fixtures: Path,
    tmp_path: Path,
) -> None:
    from outreachos_backend.rendering.alpha import build_alpha_clip
    from outreachos_backend.rendering.cache import CacheLayout
    from outreachos_backend.rendering.config import RenderBatchConfig

    config = RenderBatchConfig.model_validate(
        json.loads((render_fixtures / "batch.json").read_text(encoding="utf-8"))
    )
    layout = CacheLayout(root=tmp_path / "cache")
    first = build_alpha_clip(ffmpeg_binaries, config, layout)
    assert first.cache_hit is False
    second = build_alpha_clip(ffmpeg_binaries, config, layout)
    assert second.cache_hit is True
    assert probe_alpha_cache_hit(ffmpeg_binaries, first.clip_path) is not None


@pytest.mark.render
def test_cache_miss_on_unreadable_clip(ffmpeg_binaries: Binaries, tmp_path: Path) -> None:
    missing = tmp_path / "absent.mov"
    assert probe_alpha_cache_hit(ffmpeg_binaries, missing) is None
    garbage = tmp_path / "garbage.mov"
    garbage.write_bytes(b"not a movie")
    assert probe_alpha_cache_hit(ffmpeg_binaries, garbage) is None


def test_atomic_write_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    target = tmp_path / "entry.json"
    atomic_write(target, b'{"ok":true}')
    assert target.read_bytes() == b'{"ok":true}'
    assert list(tmp_path.glob("*.tmp")) == []


def test_temp_sibling_is_writer_private(tmp_path: Path) -> None:
    """Two writers racing on the same cache key must not share a temp path."""
    target = tmp_path / "entry.mov"
    assert temp_sibling(target, ".mov") != temp_sibling(target, ".mov")
    assert temp_sibling(target, ".mov").parent == target.parent
