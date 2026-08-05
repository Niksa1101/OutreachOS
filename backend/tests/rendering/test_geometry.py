"""Pure geometry unit tests."""

import math

import pytest

from outreachos_backend.rendering.config import (
    BorderConfig,
    OffsetConfig,
    OverlayConfig,
    ShadowConfig,
    SizeConfig,
)
from outreachos_backend.rendering.geometry import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    compute_bleed_insets,
    compute_geometry,
    quantize_duration,
)

ANCHORS = ["top_left", "top_right", "bottom_left", "bottom_right"]


def test_bleed_zero_when_shadow_and_border_disabled() -> None:
    overlay = OverlayConfig(
        shadow=ShadowConfig(enabled=False),
        border=BorderConfig(enabled=False),
    )
    insets = compute_bleed_insets(overlay)
    assert insets.left == insets.right == insets.top == insets.bottom == 0


def test_bleed_reserves_room_for_border_without_shadow() -> None:
    """_draw_frame strokes outside the box, so a shadowless border still needs bleed."""
    overlay = OverlayConfig(
        shadow=ShadowConfig(enabled=False),
        border=BorderConfig(enabled=True, width=6),
    )
    insets = compute_bleed_insets(overlay)
    assert insets.left == insets.right == insets.top == insets.bottom == 6


def test_bleed_takes_the_larger_of_shadow_and_border() -> None:
    overlay = OverlayConfig(
        shadow=ShadowConfig(enabled=True, blur=2, offset_x=0, offset_y=0),
        border=BorderConfig(enabled=True, width=40),
    )
    insets = compute_bleed_insets(overlay)
    assert insets.left == 40  # ceil(1.5 * 2) == 3 loses to the border


def test_bleed_asymmetric_with_offset() -> None:
    overlay = OverlayConfig(shadow=ShadowConfig(enabled=True, blur=32, offset_x=0, offset_y=8))
    insets = compute_bleed_insets(overlay)
    base = math.ceil(1.5 * 32)
    assert insets.top == base
    assert insets.bottom == base + 8


def test_bleed_insets_are_even() -> None:
    """Even insets keep box-inset and box+2*inset even without a second rounding pass."""
    overlay = OverlayConfig(shadow=ShadowConfig(enabled=True, blur=15, offset_x=3, offset_y=7))
    insets = compute_bleed_insets(overlay)
    assert insets.left % 2 == 0
    assert insets.right % 2 == 0
    assert insets.top % 2 == 0
    assert insets.bottom % 2 == 0


@pytest.mark.parametrize("anchor", ANCHORS)
@pytest.mark.parametrize("blur", [0, 24, 64, 120])
def test_offset_measures_to_the_visible_box_regardless_of_blur(anchor: str, blur: int) -> None:
    """ADR-0008: bleed extends outward, so growing the shadow must not move the overlay.

    Regression guard — anchoring the bleed box instead of the visible box put the
    overlay 84px from the right edge when 48 was configured, and made the position
    a function of shadow.blur.
    """
    overlay = OverlayConfig(
        anchor=anchor,  # type: ignore[arg-type]
        size=SizeConfig(width=320, height=320),
        offset=OffsetConfig(x=48, y=48),
        shadow=ShadowConfig(enabled=True, blur=blur, offset_x=0, offset_y=8),
    )
    geom = compute_geometry(overlay)

    box_left = geom.overlay_x + geom.bleed_insets.left
    box_top = geom.overlay_y + geom.bleed_insets.top
    box_right = box_left + geom.box_width
    box_bottom = box_top + geom.box_height

    if anchor.endswith("left"):
        assert box_left == 48
    else:
        assert CANVAS_WIDTH - box_right == 48
    if anchor.startswith("top"):
        assert box_top == 48
    else:
        assert CANVAS_HEIGHT - box_bottom == 48


def test_large_bleed_pushes_coordinates_off_canvas() -> None:
    """The case ADR-0008 exists for: bleed overhangs both near and far edges."""
    overlay = OverlayConfig(
        anchor="bottom_right",
        size=SizeConfig(width=320, height=320),
        offset=OffsetConfig(x=0, y=0),
        shadow=ShadowConfig(enabled=True, blur=64, offset_x=0, offset_y=0),
    )
    geom = compute_geometry(overlay)
    # Right/bottom bleed runs past the canvas rather than being clamped back inside.
    assert geom.overlay_x + geom.bleed_width > CANVAS_WIDTH
    assert geom.overlay_y + geom.bleed_height > CANVAS_HEIGHT


def test_negative_overlay_offset_is_not_clamped_to_zero() -> None:
    overlay = OverlayConfig(
        anchor="top_left",
        offset=OffsetConfig(x=-24, y=10),
        shadow=ShadowConfig(enabled=False),
        border=BorderConfig(enabled=False),
    )
    geom = compute_geometry(overlay)
    assert geom.overlay_x < 0


def test_overlay_coordinates_are_even() -> None:
    overlay = OverlayConfig(
        anchor="bottom_right",
        offset=OffsetConfig(x=47, y=13),
        shadow=ShadowConfig(enabled=True, blur=15, offset_x=3, offset_y=7),
    )
    geom = compute_geometry(overlay)
    assert geom.overlay_x % 2 == 0
    assert geom.overlay_y % 2 == 0
    assert geom.bleed_width % 2 == 0
    assert geom.bleed_height % 2 == 0


def test_quantize_duration() -> None:
    n, d = quantize_duration(2.5, 30)
    assert n == 75
    assert abs(d - 2.5) < 0.001
