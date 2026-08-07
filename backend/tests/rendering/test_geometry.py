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
    clamp_overlay_config,
    clamp_overlay_size,
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


# --- clamp_overlay_config -----------------------------------------------
#
# Ticket 10 parity fixtures. This table is duplicated verbatim in
# frontend/src/modules/video-composer/lib/overlay-geometry.parity.test.ts —
# the frontend's `clampOverlayConfig` + `computeOverlayBox` must reproduce
# these exact numbers, since compute_geometry() (below) is a pure function
# of (anchor, clamped size, clamped offset). Keep both tables in sync.

CLAMP_FIXTURES = [
    pytest.param(
        "default",
        "bottom_right",
        (480, 480),
        (48, 48),
        (480, 480),
        (48, 48),
        (1392, 552),
        id="default",
    ),
    pytest.param(
        "oversized_width_clamped",
        "top_left",
        (3000, 200),
        (0, 0),
        (1920, 200),
        (0, 0),
        (0, 0),
        id="oversized_width_clamped",
    ),
    pytest.param(
        "negative_offset_clamped_to_zero",
        "top_left",
        (320, 320),
        (-50, -30),
        (320, 320),
        (0, 0),
        (0, 0),
        id="negative_offset_clamped_to_zero",
    ),
    pytest.param(
        "offset_exceeds_canvas_clamped",
        "bottom_right",
        (200, 200),
        (5000, 5000),
        (200, 200),
        (1720, 880),
        (0, 0),
        id="offset_exceeds_canvas_clamped",
    ),
    pytest.param(
        "inverted_prevention_large_size_and_offset",
        "bottom_left",
        (1900, 1000),
        (500, 500),
        (1900, 1000),
        (20, 80),
        (20, 0),
        id="inverted_prevention_large_size_and_offset",
    ),
]
# Note: a "size clamped up to 1" fixture isn't representable here — `SizeConfig`
# already enforces `ge=1` at construction, so the backend can never receive a
# zero size to clamp. The frontend has no such guarantee (a user can type 0
# into a form field before any validation runs), so its parity suite keeps
# that case as a frontend-only defensive-floor test; `test_clamp_overlay_size_floor_is_defensive`
# below covers the same lower bound via `SizeConfig.model_construct`.


@pytest.mark.parametrize(
    "name,anchor,size,offset,expected_size,expected_offset,expected_xy",
    CLAMP_FIXTURES,
)
def test_clamp_overlay_config_fixtures(
    name: str,
    anchor: str,
    size: tuple[int, int],
    offset: tuple[int, int],
    expected_size: tuple[int, int],
    expected_offset: tuple[int, int],
    expected_xy: tuple[int, int],
) -> None:
    overlay = OverlayConfig(
        anchor=anchor,  # type: ignore[arg-type]
        size=SizeConfig(width=size[0], height=size[1]),
        offset=OffsetConfig(x=offset[0], y=offset[1]),
    )
    clamped = clamp_overlay_config(overlay)
    assert (clamped.size.width, clamped.size.height) == expected_size, name
    assert (clamped.offset.x, clamped.offset.y) == expected_offset, name

    geom = compute_geometry(clamped)
    box_left = geom.overlay_x + geom.bleed_insets.left
    box_top = geom.overlay_y + geom.bleed_insets.top
    assert (box_left, box_top) == expected_xy, name


@pytest.mark.parametrize("anchor", ANCHORS)
@pytest.mark.parametrize(
    "size,offset",
    [
        ((10000, 10000), (0, 0)),
        ((1, 1), (-99999, -99999)),
        ((1, 1), (99999, 99999)),
        ((CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0)),
    ],
)
def test_clamp_overlay_config_never_off_frame_or_inverted(
    anchor: str,
    size: tuple[int, int],
    offset: tuple[int, int],
) -> None:
    overlay = OverlayConfig(
        anchor=anchor,  # type: ignore[arg-type]
        size=SizeConfig(width=size[0], height=size[1]),
        offset=OffsetConfig(x=offset[0], y=offset[1]),
    )
    clamped = clamp_overlay_config(overlay)
    geom = compute_geometry(clamped)
    box_left = geom.overlay_x + geom.bleed_insets.left
    box_top = geom.overlay_y + geom.bleed_insets.top
    box_right = box_left + geom.box_width
    box_bottom = box_top + geom.box_height

    assert box_left >= 0
    assert box_top >= 0
    assert box_right <= CANVAS_WIDTH
    assert box_bottom <= CANVAS_HEIGHT
    assert box_right > box_left
    assert box_bottom > box_top


# --- padding -------------------------------------------------------------


def test_padding_zero_leaves_inner_box_equal_to_box() -> None:
    overlay = OverlayConfig(size=SizeConfig(width=320, height=320), padding=0)
    geom = compute_geometry(overlay)
    assert geom.padding == 0
    assert (geom.inner_width, geom.inner_height) == (geom.box_width, geom.box_height)


def test_padding_within_bounds_shrinks_inner_box_symmetrically() -> None:
    overlay = OverlayConfig(size=SizeConfig(width=320, height=320), padding=20)
    geom = compute_geometry(overlay)
    assert geom.padding == 20
    assert geom.inner_width == geom.box_width - 40
    assert geom.inner_height == geom.box_height - 40


def test_padding_forced_down_when_it_would_collapse_the_inner_box() -> None:
    """Padding larger than half the box floors to a positive inner box, never zero/negative."""
    overlay = OverlayConfig(size=SizeConfig(width=100, height=100), padding=10_000)
    geom = compute_geometry(overlay)
    assert geom.inner_width > 0
    assert geom.inner_height > 0
    assert geom.padding < 10_000


@pytest.mark.parametrize("box", [(320, 320), (321, 201), (100, 100), (2, 2)])
@pytest.mark.parametrize("padding", [0, 1, 5, 40, 200, 10_000])
def test_padding_never_collapses_inner_box(box: tuple[int, int], padding: int) -> None:
    overlay = OverlayConfig(size=SizeConfig(width=box[0], height=box[1]), padding=padding)
    geom = compute_geometry(overlay)
    assert geom.inner_width > 0
    assert geom.inner_height > 0
    assert geom.padding % 2 == 0
    assert geom.padding >= 0


def test_clamp_overlay_size_floor_is_defensive() -> None:
    """`SizeConfig` blocks width/height < 1 at construction; this exercises
    `clamp_overlay_size`'s own floor directly, bypassing that guard, so the
    lower bound stays correct even if a future caller stops going through
    the validated constructor (e.g. `model_construct` from a partial patch).
    """
    size = SizeConfig.model_construct(width=0, height=0)
    clamped = clamp_overlay_size(size)
    assert (clamped.width, clamped.height) == (1, 1)
