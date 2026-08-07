/**
 * Pure trim-window and focal-point math for the Talking Head Editor (ticket
 * 13). Ports the server's clamp rule 1:1 (`service._clamp_trim_window`) so the
 * timeline gives immediate, correct feedback; the server re-clamps on commit
 * regardless, per the same "server is the actual source of truth" pattern as
 * `overlay-geometry.ts`.
 */

export interface TrimWindow {
  trim_start_ms: number;
  trim_end_ms: number;
}

export interface FocalPoint {
  focal_x: number;
  focal_y: number;
}

/** Never inverted, never past `[0, durationMs]`, never zero-length. */
export function clampTrimWindow(trim: TrimWindow, durationMs: number): TrimWindow {
  const duration = Math.max(1, durationMs);
  const start = Math.max(0, Math.min(trim.trim_start_ms, duration - 1));
  const end = Math.max(start + 1, Math.min(trim.trim_end_ms, duration));
  return { trim_start_ms: start, trim_end_ms: end };
}

/** The resolved output duration — `D` in the PRD — after trim. */
export function resolvedDurationMs(trim: TrimWindow): number {
  return trim.trim_end_ms - trim.trim_start_ms;
}

function clampUnit(value: number): number {
  return Math.max(0, Math.min(1, value));
}

/** Normalized crop center, DB.md §4.1: always clamped to `[0, 1]`. */
export function clampFocalPoint(focal: FocalPoint): FocalPoint {
  return { focal_x: clampUnit(focal.focal_x), focal_y: clampUnit(focal.focal_y) };
}
