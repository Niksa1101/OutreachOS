"""Pure overlay geometry — no FFmpeg or Pillow imports."""

from __future__ import annotations

import math
from dataclasses import dataclass

from outreachos_backend.rendering.config import OverlayConfig

__all__ = [
    "BleedInsets",
    "Canvas",
    "OverlayGeometry",
    "compute_bleed_insets",
    "compute_geometry",
    "quantize_duration",
]

CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
OUTPUT_FPS = 30


@dataclass(frozen=True)
class Canvas:
    width: int = CANVAS_WIDTH
    height: int = CANVAS_HEIGHT


@dataclass(frozen=True)
class BleedInsets:
    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True)
class OverlayGeometry:
    box_width: int
    box_height: int
    bleed_width: int
    bleed_height: int
    overlay_x: int
    overlay_y: int
    bleed_insets: BleedInsets


def compute_bleed_insets(overlay: OverlayConfig) -> BleedInsets:
    """Per-side outward expansion of the visible box (ADR-0008).

    Covers both the shadow (``ceil(1.5 * blur) + |offset|``, asymmetric per side)
    and the border, which ``overlay_assets._draw_frame`` strokes *outside* the box:
    a border on a shadowless overlay still needs room or it is clipped away.

    Insets are rounded up to even so that ``box - inset`` and ``box + 2*inset``
    both stay even without a second rounding pass; overlay coordinates must be
    even for 4:2:0 chroma siting.
    """
    border = overlay.border.width if overlay.border.enabled else 0
    if not overlay.shadow.enabled:
        return BleedInsets(
            left=_even_ceil(border),
            top=_even_ceil(border),
            right=_even_ceil(border),
            bottom=_even_ceil(border),
        )
    base = math.ceil(1.5 * overlay.shadow.blur)
    return BleedInsets(
        left=_even_ceil(max(border, base + abs(min(0, overlay.shadow.offset_x)))),
        right=_even_ceil(max(border, base + max(0, overlay.shadow.offset_x))),
        top=_even_ceil(max(border, base + abs(min(0, overlay.shadow.offset_y)))),
        bottom=_even_ceil(max(border, base + max(0, overlay.shadow.offset_y))),
    )


def compute_geometry(overlay: OverlayConfig, canvas: Canvas | None = None) -> OverlayGeometry:
    c = canvas or Canvas()
    insets = compute_bleed_insets(overlay)
    box_w = _even_round(overlay.size.width)
    box_h = _even_round(overlay.size.height)
    bleed_w = _even_round(box_w + insets.left + insets.right)
    bleed_h = _even_round(box_h + insets.top + insets.bottom)

    # ADR-0008: the anchor positions the *visible* box, so `offset` keeps meaning
    # "distance from the canvas edge to the overlay" no matter how large the shadow
    # is. The bleed then extends outward from there, which is exactly why x/y may
    # land negative or past the far edge — clamping either side would reintroduce
    # the shadow clipping this ADR exists to prevent.
    box_x, box_y = _anchor_xy(
        overlay.anchor,
        c.width,
        c.height,
        box_w,
        box_h,
        overlay.offset.x,
        overlay.offset.y,
    )
    x = box_x - insets.left
    y = box_y - insets.top

    return OverlayGeometry(
        box_width=box_w,
        box_height=box_h,
        bleed_width=bleed_w,
        bleed_height=bleed_h,
        overlay_x=x,
        overlay_y=y,
        bleed_insets=insets,
    )


def quantize_duration(duration_s: float, fps: int = OUTPUT_FPS) -> tuple[int, float]:
    """Return (N frames, D_exact seconds)."""
    n = max(1, round(duration_s * fps))
    d_exact = n / fps
    return n, d_exact


def _anchor_xy(
    anchor: str,
    canvas_w: int,
    canvas_h: int,
    box_w: int,
    box_h: int,
    offset_x: int,
    offset_y: int,
) -> tuple[int, int]:
    if anchor == "top_left":
        x, y = offset_x, offset_y
    elif anchor == "top_right":
        x, y = canvas_w - box_w - offset_x, offset_y
    elif anchor == "bottom_left":
        x, y = offset_x, canvas_h - box_h - offset_y
    else:  # bottom_right
        x, y = canvas_w - box_w - offset_x, canvas_h - box_h - offset_y
    return _even_round(x), _even_round(y)


def _even_round(value: int | float) -> int:
    rounded = round(value)
    if rounded % 2 != 0:
        rounded += 1 if rounded >= 0 else -1
    return int(rounded)


def _even_ceil(value: int) -> int:
    return value + (value % 2)
