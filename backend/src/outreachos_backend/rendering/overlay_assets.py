"""Pillow overlay asset generation — backdrop, mask, frame layers."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from outreachos_backend.rendering.cache import atomic_write
from outreachos_backend.rendering.config import OverlayConfig
from outreachos_backend.rendering.geometry import OverlayGeometry, compute_geometry

__all__ = ["OverlayAssets", "asset_paths_for", "render_overlay_assets"]

_SUPERSAMPLE = 4


def asset_paths_for(directory: Path, assets_key: str) -> tuple[Path, Path, Path]:
    """(backdrop, mask, frame) paths for a key — the one place this naming lives."""
    prefix = directory / assets_key
    return (
        Path(f"{prefix}_backdrop.png"),
        Path(f"{prefix}_mask.png"),
        Path(f"{prefix}_frame.png"),
    )


def _save_atomic(image: Image.Image, path: Path) -> None:
    """PNGs are cache entries keyed by content, and `ensure_overlay_assets` accepts
    them on `is_file()` alone — a half-written file would be a permanent cache hit.
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    atomic_write(path, buffer.getvalue())


@dataclass(frozen=True)
class OverlayAssets:
    backdrop: Path
    mask: Path
    frame: Path
    geometry: OverlayGeometry


def render_overlay_assets(
    overlay: OverlayConfig,
    output_dir: Path,
    *,
    assets_key: str,
) -> OverlayAssets:
    output_dir.mkdir(parents=True, exist_ok=True)
    geometry = compute_geometry(overlay)
    w, h = geometry.bleed_width, geometry.bleed_height
    ss_w, ss_h = w * _SUPERSAMPLE, h * _SUPERSAMPLE

    backdrop_ss = Image.new("RGBA", (ss_w, ss_h), (0, 0, 0, 0))
    mask_ss = Image.new("RGBA", (ss_w, ss_h), (0, 0, 0, 0))
    frame_ss = Image.new("RGBA", (ss_w, ss_h), (0, 0, 0, 0))

    inset_left = geometry.bleed_insets.left * _SUPERSAMPLE
    inset_top = geometry.bleed_insets.top * _SUPERSAMPLE
    box_w = geometry.box_width * _SUPERSAMPLE
    box_h = geometry.box_height * _SUPERSAMPLE

    _draw_shape_mask(mask_ss, overlay, inset_left, inset_top, box_w, box_h)
    _draw_backdrop(backdrop_ss, overlay, inset_left, inset_top, box_w, box_h)
    _draw_frame(frame_ss, overlay, inset_left, inset_top, box_w, box_h)

    backdrop = _downscale(backdrop_ss)
    mask = _downscale(mask_ss)
    frame = _downscale(frame_ss)

    backdrop_path, mask_path, frame_path = asset_paths_for(output_dir, assets_key)
    _save_atomic(backdrop, backdrop_path)
    _save_atomic(mask, mask_path)
    _save_atomic(frame, frame_path)

    return OverlayAssets(
        backdrop=backdrop_path,
        mask=mask_path,
        frame=frame_path,
        geometry=geometry,
    )


def _downscale(image: Image.Image) -> Image.Image:
    return image.resize(
        (image.width // _SUPERSAMPLE, image.height // _SUPERSAMPLE),
        Image.Resampling.LANCZOS,
    )


def _draw_shape_mask(
    canvas: Image.Image,
    overlay: OverlayConfig,
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    alpha = int(255 * overlay.opacity)
    fill = (255, 255, 255, alpha)
    _draw_shape(draw, overlay, x, y, w, h, fill)
    canvas.alpha_composite(layer)


def _draw_backdrop(
    canvas: Image.Image,
    overlay: OverlayConfig,
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    if overlay.background.enabled:
        bg = Image.new("RGBA", canvas.size, _hex_rgba(overlay.background.color, 255))
        shape = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(shape)
        _draw_shape(draw, overlay, x, y, w, h, (255, 255, 255, 255))
        layer = Image.alpha_composite(layer, Image.composite(bg, layer, shape.split()[3]))

    if overlay.shadow.enabled:
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow)
        sx = x + overlay.shadow.offset_x * _SUPERSAMPLE
        sy = y + overlay.shadow.offset_y * _SUPERSAMPLE
        shadow_fill = _hex_rgba(overlay.shadow.color, int(255 * overlay.shadow.opacity))
        _draw_shape(draw, overlay, int(sx), int(sy), w, h, shadow_fill)
        sigma = max(0.5, overlay.shadow.blur / 2.0)
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=sigma * _SUPERSAMPLE))
        layer = Image.alpha_composite(layer, shadow)

    canvas.alpha_composite(layer)


def _draw_frame(
    canvas: Image.Image,
    overlay: OverlayConfig,
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    if not overlay.border.enabled or overlay.border.width <= 0:
        return
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bw = overlay.border.width * _SUPERSAMPLE
    color = _hex_rgba(overlay.border.color, 255)
    if overlay.shape == "circle":
        draw.ellipse((x - bw, y - bw, x + w + bw, y + h + bw), outline=color, width=int(bw))
    elif overlay.shape == "rounded_rect":
        radius = overlay.border_radius * _SUPERSAMPLE + bw
        draw.rounded_rectangle(
            (x - bw, y - bw, x + w + bw, y + h + bw),
            radius=radius,
            outline=color,
            width=int(bw),
        )
    else:
        draw.rectangle((x - bw, y - bw, x + w + bw, y + h + bw), outline=color, width=int(bw))
    canvas.alpha_composite(layer)


def _draw_shape(
    draw: ImageDraw.ImageDraw,
    overlay: OverlayConfig,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: tuple[int, int, int, int],
) -> None:
    if overlay.shape == "circle":
        draw.ellipse((x, y, x + w, y + h), fill=fill)
    elif overlay.shape == "rounded_rect":
        draw.rounded_rectangle(
            (x, y, x + w, y + h),
            radius=overlay.border_radius * _SUPERSAMPLE,
            fill=fill,
        )
    else:
        draw.rectangle((x, y, x + w, y + h), fill=fill)


def _hex_rgba(value: str, alpha: int) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    if len(value) == 6:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
        return r, g, b, alpha
    raise ValueError(f"Invalid hex color: {value}")
