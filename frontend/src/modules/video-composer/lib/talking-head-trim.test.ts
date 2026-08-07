import { describe, expect, it } from 'vitest';

import {
  clampFocalPoint,
  clampTrimWindow,
  resolvedDurationMs,
} from '@/modules/video-composer/lib/talking-head-trim';

describe('clampTrimWindow', () => {
  it('clamps into [0, duration]', () => {
    expect(clampTrimWindow({ trim_start_ms: -500, trim_end_ms: 999999 }, 10000)).toEqual({
      trim_start_ms: 0,
      trim_end_ms: 10000,
    });
  });

  it('never inverts — end always stays after start', () => {
    expect(clampTrimWindow({ trim_start_ms: 8000, trim_end_ms: 2000 }, 10000)).toEqual({
      trim_start_ms: 8000,
      trim_end_ms: 8001,
    });
  });

  it('never resolves to a zero-length clip', () => {
    expect(clampTrimWindow({ trim_start_ms: 5000, trim_end_ms: 5000 }, 10000)).toEqual({
      trim_start_ms: 5000,
      trim_end_ms: 5001,
    });
  });

  it('handles a degenerate zero-duration source without throwing', () => {
    const result = clampTrimWindow({ trim_start_ms: 0, trim_end_ms: 0 }, 0);
    expect(result.trim_end_ms).toBeGreaterThan(result.trim_start_ms);
  });
});

describe('resolvedDurationMs', () => {
  it('is end minus start', () => {
    expect(resolvedDurationMs({ trim_start_ms: 1000, trim_end_ms: 9000 })).toBe(8000);
  });
});

describe('clampFocalPoint', () => {
  it('clamps both axes to [0, 1]', () => {
    expect(clampFocalPoint({ focal_x: -1, focal_y: 2 })).toEqual({ focal_x: 0, focal_y: 1 });
    expect(clampFocalPoint({ focal_x: 0.25, focal_y: 0.75 })).toEqual({
      focal_x: 0.25,
      focal_y: 0.75,
    });
  });
});
