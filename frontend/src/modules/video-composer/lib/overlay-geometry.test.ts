import { describe, expect, it } from 'vitest';

import {
  type Anchor,
  clampOverlayConfig,
  clampOverlayPadding,
  clampOverlaySize,
  computeInnerOverlayBox,
  computeOverlayBox,
  DEFAULT_CANVAS,
  DEFAULT_OVERLAY_CONFIG,
  evenRound,
  parseOverlayConfig,
} from '@/modules/video-composer/lib/overlay-geometry';

const ANCHORS: Anchor[] = ['top_left', 'top_right', 'bottom_left', 'bottom_right'];

describe('evenRound', () => {
  it('rounds half away from zero, then nudges to even', () => {
    expect(evenRound(1)).toBe(2);
    expect(evenRound(2)).toBe(2);
    expect(evenRound(2.5)).toBe(4);
    expect(evenRound(-1)).toBe(-2);
    expect(evenRound(0)).toBe(0);
  });
});

describe('clampOverlaySize', () => {
  it('floors at 1 and ceils at the canvas dimensions', () => {
    expect(clampOverlaySize({ width: 0, height: 0 })).toEqual({ width: 1, height: 1 });
    expect(clampOverlaySize({ width: 5000, height: 5000 })).toEqual({
      width: 1920,
      height: 1080,
    });
  });
});

describe('clampOverlayConfig never off-frame or inverted', () => {
  const cases: Array<[number, number, number, number]> = [
    [10000, 10000, 0, 0],
    [1, 1, -99999, -99999],
    [1, 1, 99999, 99999],
    [DEFAULT_CANVAS.width, DEFAULT_CANVAS.height, 0, 0],
  ];

  for (const anchor of ANCHORS) {
    for (const [width, height, x, y] of cases) {
      it(`${anchor} size=(${width},${height}) offset=(${x},${y})`, () => {
        const overlay = {
          ...DEFAULT_OVERLAY_CONFIG,
          anchor,
          size: { width, height },
          offset: { x, y },
        };
        clampOverlayConfig(overlay);
        const box = computeOverlayBox(overlay);

        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.y).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(DEFAULT_CANVAS.width);
        expect(box.y + box.height).toBeLessThanOrEqual(DEFAULT_CANVAS.height);
        expect(box.width).toBeGreaterThan(0);
        expect(box.height).toBeGreaterThan(0);
      });
    }
  }
});

describe('clampOverlayPadding', () => {
  it('floors negative-would-be-collapsed padding to a positive inner box, never zero/negative', () => {
    const padding = clampOverlayPadding(10_000, 100, 100);
    expect(padding).toBeGreaterThanOrEqual(0);
    expect(100 - 2 * padding).toBeGreaterThan(0);
  });

  it('leaves small padding unchanged when it fits', () => {
    expect(clampOverlayPadding(20, 320, 320)).toBe(20);
  });
});

describe('computeInnerOverlayBox', () => {
  it('insets the box by padding on every side', () => {
    const overlay = { ...DEFAULT_OVERLAY_CONFIG, size: { width: 320, height: 320 }, padding: 20 };
    const inner = computeInnerOverlayBox(overlay);
    expect(inner.padding).toBe(20);
    expect(inner.width).toBe(320 - 40);
    expect(inner.height).toBe(320 - 40);
  });

  it('padding larger than half the box floors to a positive inner box, never zero/negative', () => {
    const overlay = {
      ...DEFAULT_OVERLAY_CONFIG,
      size: { width: 100, height: 100 },
      padding: 10_000,
    };
    const inner = computeInnerOverlayBox(overlay);
    expect(inner.width).toBeGreaterThan(0);
    expect(inner.height).toBeGreaterThan(0);
  });
});

describe('parseOverlayConfig', () => {
  it('falls back to defaults for null/undefined/invalid JSON', () => {
    expect(parseOverlayConfig(null)).toEqual(DEFAULT_OVERLAY_CONFIG);
    expect(parseOverlayConfig(undefined)).toEqual(DEFAULT_OVERLAY_CONFIG);
    expect(parseOverlayConfig('not json')).toEqual(DEFAULT_OVERLAY_CONFIG);
  });

  it('merges a partial config over the defaults, including nested objects', () => {
    const json = JSON.stringify({ anchor: 'top_left', size: { width: 200, height: 200 } });
    const parsed = parseOverlayConfig(json);
    expect(parsed.anchor).toBe('top_left');
    expect(parsed.size).toEqual({ width: 200, height: 200 });
    expect(parsed.offset).toEqual(DEFAULT_OVERLAY_CONFIG.offset);
    expect(parsed.border).toEqual(DEFAULT_OVERLAY_CONFIG.border);
  });
});
