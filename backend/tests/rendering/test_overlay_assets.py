"""Overlay asset PNG regression snapshots."""

from pathlib import Path

import pytest
from PIL import Image

from outreachos_backend.rendering.config import BackgroundConfig, OverlayConfig, ShadowConfig
from outreachos_backend.rendering.overlay_assets import render_overlay_assets

REF_DIR = Path(__file__).resolve().parent / "fixtures" / "overlay_refs"


@pytest.mark.parametrize(
    "name,overlay",
    [
        (
            "circle_default",
            OverlayConfig(),
        ),
        (
            "rounded_shadow",
            OverlayConfig(
                shape="rounded_rect",
                border_radius=32,
                shadow=ShadowConfig(
                    enabled=True,
                    blur=48,
                    offset_x=4,
                    offset_y=12,
                    opacity=0.5,
                    color="#000000",
                ),
            ),
        ),
        (
            "rect",
            OverlayConfig(shape="rect"),
        ),
        (
            "padded_background",
            OverlayConfig(
                padding=40,
                background=BackgroundConfig(enabled=True, color="#0A0A0A"),
            ),
        ),
    ],
)
def test_overlay_mask_matches_reference(name: str, overlay: OverlayConfig, tmp_path: Path) -> None:
    ref_mask = REF_DIR / f"{name}_mask.png"
    if not ref_mask.exists():
        REF_DIR.mkdir(parents=True, exist_ok=True)
        assets = render_overlay_assets(overlay, REF_DIR, assets_key=name)
        Image.open(assets.mask).save(ref_mask)
        pytest.skip(f"Reference created at {ref_mask}")

    assets = render_overlay_assets(overlay, tmp_path, assets_key=name)
    _assert_png_similar(assets.mask, ref_mask)


def _assert_png_similar(actual: Path, expected: Path) -> None:
    a = Image.open(actual).convert("RGBA")
    b = Image.open(expected).convert("RGBA")
    assert a.size == b.size
    diff = sum(abs(x - y) for x, y in zip(a.tobytes(), b.tobytes(), strict=True))
    assert diff == 0
