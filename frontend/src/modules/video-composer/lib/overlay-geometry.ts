/**
 * Pure overlay geometry — ports `rendering/geometry.py` and
 * `rendering/config.py`'s `OverlayConfig` 1:1 for the CSS overlay preview
 * (ticket 10). Only the clamp path is ported; `compute_geometry`'s bleed-box
 * math stays server-side per ADR-0008 and is deliberately not duplicated here.
 */

export type Anchor = 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right';
export type Shape = 'circle' | 'rounded_rect' | 'rect';
export type AnimationType = 'fade';

export interface SizeConfig {
  width: number;
  height: number;
}

export interface OffsetConfig {
  x: number;
  y: number;
}

export interface BorderConfig {
  enabled: boolean;
  width: number;
  color: string;
}

export interface ShadowConfig {
  enabled: boolean;
  blur: number;
  offset_x: number;
  offset_y: number;
  opacity: number;
  color: string;
}

export interface BackgroundConfig {
  enabled: boolean;
  color: string;
}

export interface AnimationConfig {
  type: AnimationType;
  duration_ms: number;
}

export interface OverlayConfig {
  schema_version: number;
  anchor: Anchor;
  size: SizeConfig;
  offset: OffsetConfig;
  shape: Shape;
  border_radius: number;
  opacity: number;
  padding: number;
  border: BorderConfig;
  shadow: ShadowConfig;
  background: BackgroundConfig;
  animation: AnimationConfig;
}

export const DEFAULT_OVERLAY_CONFIG: OverlayConfig = {
  schema_version: 1,
  anchor: 'bottom_right',
  size: { width: 480, height: 480 },
  offset: { x: 48, y: 48 },
  shape: 'circle',
  border_radius: 24,
  opacity: 1.0,
  padding: 0,
  border: { enabled: true, width: 4, color: '#FFFFFF' },
  shadow: { enabled: true, blur: 32, offset_x: 0, offset_y: 8, opacity: 0.45, color: '#000000' },
  background: { enabled: false, color: '#0A0A0A' },
  animation: { type: 'fade', duration_ms: 500 },
};

export interface Canvas {
  width: number;
  height: number;
}

export const DEFAULT_CANVAS: Canvas = { width: 1920, height: 1080 };

export interface OverlayBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface InnerOverlayBox {
  padding: number;
  width: number;
  height: number;
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

/**
 * Round-half-away-from-zero, then nudge to the nearest even integer. Note
 * this disagrees with Python's `round` (round-half-to-even) at exactly `.5`
 * — but `clampOverlaySize`/`clampOverlayOffset` round their inputs to
 * integers before this ever runs, so a `.5` input is unreachable here and
 * the two implementations never actually diverge. Keep it that way: don't
 * reintroduce a fractional path into `size`/`offset` upstream of this.
 */
export function evenRound(value: number): number {
  let rounded = Math.sign(value) * Math.round(Math.abs(value));
  if (rounded % 2 !== 0) {
    rounded += rounded >= 0 ? 1 : -1;
  }
  return rounded;
}

export function clampOverlaySize(size: SizeConfig, canvas: Canvas = DEFAULT_CANVAS): SizeConfig {
  return {
    width: clamp(Math.round(size.width), 1, canvas.width),
    height: clamp(Math.round(size.height), 1, canvas.height),
  };
}

/**
 * `boxWidth`/`boxHeight` must already be even-rounded (as `clampOverlayConfig`
 * passes them) — clamping against the raw, unrounded size would let a
 * rounded-up box edge slip past the canvas by a pixel.
 */
export function clampOverlayOffset(
  offset: OffsetConfig,
  boxWidth: number,
  boxHeight: number,
  canvas: Canvas = DEFAULT_CANVAS,
): OffsetConfig {
  const maxX = Math.max(0, canvas.width - boxWidth);
  const maxY = Math.max(0, canvas.height - boxHeight);
  return {
    x: clamp(Math.round(offset.x), 0, maxX),
    y: clamp(Math.round(offset.y), 0, maxY),
  };
}

/** Single source of truth for "can never be described off-frame or inverted" (PRD §6.2). */
export function clampOverlayConfig(
  overlay: OverlayConfig,
  canvas: Canvas = DEFAULT_CANVAS,
): OverlayConfig {
  const size = clampOverlaySize(overlay.size, canvas);
  const boxW = evenRound(size.width);
  const boxH = evenRound(size.height);
  const offset = clampOverlayOffset(overlay.offset, boxW, boxH, canvas);
  return { ...overlay, size, offset };
}

function anchorXY(
  anchor: Anchor,
  canvasW: number,
  canvasH: number,
  boxW: number,
  boxH: number,
  offsetX: number,
  offsetY: number,
): [number, number] {
  let x: number;
  let y: number;
  if (anchor === 'top_left') {
    x = offsetX;
    y = offsetY;
  } else if (anchor === 'top_right') {
    x = canvasW - boxW - offsetX;
    y = offsetY;
  } else if (anchor === 'bottom_left') {
    x = offsetX;
    y = canvasH - boxH - offsetY;
  } else {
    x = canvasW - boxW - offsetX;
    y = canvasH - boxH - offsetY;
  }
  return [evenRound(x), evenRound(y)];
}

/**
 * The clamped, even-rounded visible box in canvas pixels — the CSS overlay
 * preview's positioning contract. Callers convert to percentages against the
 * canvas for responsive layout.
 */
export function computeOverlayBox(
  overlay: OverlayConfig,
  canvas: Canvas = DEFAULT_CANVAS,
): OverlayBox {
  const clamped = clampOverlayConfig(overlay, canvas);
  const boxW = evenRound(clamped.size.width);
  const boxH = evenRound(clamped.size.height);
  const [x, y] = anchorXY(
    clamped.anchor,
    canvas.width,
    canvas.height,
    boxW,
    boxH,
    clamped.offset.x,
    clamped.offset.y,
  );
  return { x, y, width: boxW, height: boxH };
}

/**
 * The inset (padding) applied to the visible box, mirroring the backend's
 * `_clamp_padding` in `geometry.py`: floored at 0, capped so the inner box
 * never collapses to zero/negative, then floored to even (never rounded up
 * past the cap).
 */
export function clampOverlayPadding(padding: number, boxWidth: number, boxHeight: number): number {
  const maxPadding = Math.max(0, Math.floor((Math.min(boxWidth, boxHeight) - 2) / 2));
  const clamped = clamp(padding, 0, maxPadding);
  return clamped - (clamped % 2);
}

/**
 * The padded inner box — where the video content sits — inset from
 * `computeOverlayBox`'s visible box by `overlay.padding` on every side.
 * Single source of truth shared by `OverlayPreview` and any future consumer,
 * mirroring `geometry.py::compute_geometry`'s `inner_width`/`inner_height`.
 */
export function computeInnerOverlayBox(
  overlay: OverlayConfig,
  canvas: Canvas = DEFAULT_CANVAS,
): InnerOverlayBox {
  const box = computeOverlayBox(overlay, canvas);
  const padding = clampOverlayPadding(overlay.padding, box.width, box.height);
  return {
    padding,
    width: box.width - 2 * padding,
    height: box.height - 2 * padding,
  };
}

// --- Direct manipulation (ticket 11) --------------------------------------
//
// Drag, resize, and snap are pure functions of (overlay, pointer delta) so
// they can be unit-tested without a DOM and reused identically for mouse
// drag, keyboard nudge, or a pasted value. Every path below funnels through
// `clampOverlayConfig`/`clampOverlayOffset` — the single source of truth for
// "never off-frame or inverted" — so no input path can bypass it.

/** Logical canvas pixels a dragged offset snaps to near an edge (PRD §6.2 "safe margin"). */
export const SAFE_MARGIN_PX = 24;

/** How close (in logical canvas pixels) a dragged offset must be to a snap target to engage. */
export const SNAP_THRESHOLD_PX = 16;

/** Floor for interactive resize — smaller than `clampOverlaySize`'s floor of 1, which stays as the absolute invariant for typed/pasted values. */
export const MIN_OVERLAY_DIMENSION_PX = 24;

/** The box's top-left corner in canvas pixels, given an offset already measured from `anchor`'s corner. Inverse of `offsetForAnchorPosition`. */
export function boxPositionForAnchor(
  anchor: Anchor,
  offset: OffsetConfig,
  boxWidth: number,
  boxHeight: number,
  canvas: Canvas = DEFAULT_CANVAS,
): { x: number; y: number } {
  const [x, y] = anchorXY(
    anchor,
    canvas.width,
    canvas.height,
    boxWidth,
    boxHeight,
    offset.x,
    offset.y,
  );
  return { x, y };
}

/** The offset `anchor` implies for a box whose top-left corner sits at `(x, y)`. Inverse of `boxPositionForAnchor`. */
export function offsetForAnchorPosition(
  anchor: Anchor,
  x: number,
  y: number,
  boxWidth: number,
  boxHeight: number,
  canvas: Canvas = DEFAULT_CANVAS,
): OffsetConfig {
  const offsetX =
    anchor === 'top_left' || anchor === 'bottom_left' ? x : canvas.width - boxWidth - x;
  const offsetY =
    anchor === 'top_left' || anchor === 'top_right' ? y : canvas.height - boxHeight - y;
  return { x: offsetX, y: offsetY };
}

/** Which canvas corner a box at `(x, y)` is nearest to — the anchor a drag should adopt. */
export function nearestAnchorForPosition(
  x: number,
  y: number,
  boxWidth: number,
  boxHeight: number,
  canvas: Canvas = DEFAULT_CANVAS,
): Anchor {
  const centerX = x + boxWidth / 2;
  const centerY = y + boxHeight / 2;
  const left = centerX < canvas.width / 2;
  const top = centerY < canvas.height / 2;
  if (top && left) return 'top_left';
  if (top && !left) return 'top_right';
  if (!top && left) return 'bottom_left';
  return 'bottom_right';
}

function snapValue(value: number, targets: number[], threshold: number): number {
  for (const target of targets) {
    if (Math.abs(value - target) <= threshold) return target;
  }
  return value;
}

/**
 * Magnetically snap an offset near the anchor's own corner (0) or the safe
 * margin. Purely a function of the current value, so continuing to drag past
 * the threshold naturally releases the snap — there is no sticky state.
 */
export function snapOffset(offset: OffsetConfig): OffsetConfig {
  const targets = [0, SAFE_MARGIN_PX];
  return {
    x: snapValue(offset.x, targets, SNAP_THRESHOLD_PX),
    y: snapValue(offset.y, targets, SNAP_THRESHOLD_PX),
  };
}

/**
 * Reposition `overlay` by a pointer delta (in logical canvas pixels). The
 * anchor follows the nearest canvas corner, offset snaps magnetically near
 * corners/safe-margin, and the result is always clamped — this is the only
 * function `OverlayPreview`'s drag handler calls.
 */
export function dragOverlayBy(
  overlay: OverlayConfig,
  deltaX: number,
  deltaY: number,
  canvas: Canvas = DEFAULT_CANVAS,
): OverlayConfig {
  const box = computeOverlayBox(overlay, canvas);
  const rawX = box.x + deltaX;
  const rawY = box.y + deltaY;
  const anchor = nearestAnchorForPosition(rawX, rawY, box.width, box.height, canvas);
  const rawOffset = offsetForAnchorPosition(anchor, rawX, rawY, box.width, box.height, canvas);
  const snapped = snapOffset(rawOffset);
  const offset = clampOverlayOffset(snapped, box.width, box.height, canvas);
  return { ...overlay, anchor, offset };
}

/**
 * Resize `overlay` by a pointer delta (in logical canvas pixels) applied at
 * the handle diagonally opposite the anchor's corner, respecting a usability
 * floor above the absolute clamp, and re-deriving offset so the anchor's own
 * corner stays pinned to the canvas.
 */
export function resizeOverlayBy(
  overlay: OverlayConfig,
  deltaX: number,
  deltaY: number,
  canvas: Canvas = DEFAULT_CANVAS,
): OverlayConfig {
  const clamped = clampOverlayConfig(overlay, canvas);
  const boxW = evenRound(clamped.size.width);
  const boxH = evenRound(clamped.size.height);
  const growsRight = clamped.anchor === 'top_left' || clamped.anchor === 'bottom_left';
  const growsDown = clamped.anchor === 'top_left' || clamped.anchor === 'top_right';
  const rawWidth = growsRight ? boxW + deltaX : boxW - deltaX;
  const rawHeight = growsDown ? boxH + deltaY : boxH - deltaY;
  const size = {
    width: clamp(rawWidth, MIN_OVERLAY_DIMENSION_PX, canvas.width),
    height: clamp(rawHeight, MIN_OVERLAY_DIMENSION_PX, canvas.height),
  };
  return clampOverlayConfig({ ...clamped, size }, canvas);
}

/** Parse `CampaignDetail.overlay_config`'s raw JSON string, falling back to defaults on any error. */
export function parseOverlayConfig(json: string | null | undefined): OverlayConfig {
  if (!json) {
    return DEFAULT_OVERLAY_CONFIG;
  }
  try {
    const parsed = JSON.parse(json) as Partial<OverlayConfig>;
    return {
      ...DEFAULT_OVERLAY_CONFIG,
      ...parsed,
      size: { ...DEFAULT_OVERLAY_CONFIG.size, ...parsed.size },
      offset: { ...DEFAULT_OVERLAY_CONFIG.offset, ...parsed.offset },
      border: { ...DEFAULT_OVERLAY_CONFIG.border, ...parsed.border },
      shadow: { ...DEFAULT_OVERLAY_CONFIG.shadow, ...parsed.shadow },
      background: { ...DEFAULT_OVERLAY_CONFIG.background, ...parsed.background },
      animation: { ...DEFAULT_OVERLAY_CONFIG.animation, ...parsed.animation },
    };
  } catch {
    return DEFAULT_OVERLAY_CONFIG;
  }
}
