import { describe, expect, it } from 'vitest';

import {
  type Anchor,
  clampOverlayConfig,
  computeInnerOverlayBox,
  computeOverlayBox,
  DEFAULT_OVERLAY_CONFIG,
} from '@/modules/video-composer/lib/overlay-geometry';

/**
 * Ticket 10 parity fixtures. This table is duplicated verbatim from
 * `backend/tests/rendering/test_geometry.py`'s `CLAMP_FIXTURES` — the
 * backend's `clamp_overlay_config` and this module's `clampOverlayConfig` +
 * `computeOverlayBox` must reproduce these exact numbers. Keep both tables
 * in sync.
 */
const CLAMP_FIXTURES: Array<{
  name: string;
  anchor: Anchor;
  size: [number, number];
  offset: [number, number];
  expectedSize: [number, number];
  expectedOffset: [number, number];
  expectedXY: [number, number];
}> = [
  {
    name: 'default',
    anchor: 'bottom_right',
    size: [480, 480],
    offset: [48, 48],
    expectedSize: [480, 480],
    expectedOffset: [48, 48],
    expectedXY: [1392, 552],
  },
  {
    name: 'oversized_width_clamped',
    anchor: 'top_left',
    size: [3000, 200],
    offset: [0, 0],
    expectedSize: [1920, 200],
    expectedOffset: [0, 0],
    expectedXY: [0, 0],
  },
  {
    name: 'negative_offset_clamped_to_zero',
    anchor: 'top_left',
    size: [320, 320],
    offset: [-50, -30],
    expectedSize: [320, 320],
    expectedOffset: [0, 0],
    expectedXY: [0, 0],
  },
  {
    name: 'offset_exceeds_canvas_clamped',
    anchor: 'bottom_right',
    size: [200, 200],
    offset: [5000, 5000],
    expectedSize: [200, 200],
    expectedOffset: [1720, 880],
    expectedXY: [0, 0],
  },
  {
    name: 'inverted_prevention_large_size_and_offset',
    anchor: 'bottom_left',
    size: [1900, 1000],
    offset: [500, 500],
    expectedSize: [1900, 1000],
    expectedOffset: [20, 80],
    expectedXY: [20, 0],
  },
];

// Frontend-only: a user can type 0 into a form field before validation runs,
// unlike the backend's `SizeConfig` (`ge=1` at construction), so this case
// has no backend-side equivalent.
const ZERO_SIZE_FIXTURE = {
  name: 'zero_size_clamped_to_floor',
  anchor: 'top_right' as Anchor,
  size: [0, 0] as [number, number],
  offset: [10, 10] as [number, number],
  expectedSize: [1, 1] as [number, number],
  expectedOffset: [10, 10] as [number, number],
  expectedXY: [1908, 10] as [number, number],
};

describe('clampOverlayConfig / computeOverlayBox parity', () => {
  it.each(CLAMP_FIXTURES)(
    '$name',
    ({ anchor, size, offset, expectedSize, expectedOffset, expectedXY }) => {
      const overlay = {
        ...DEFAULT_OVERLAY_CONFIG,
        anchor,
        size: { width: size[0], height: size[1] },
        offset: { x: offset[0], y: offset[1] },
      };

      const clamped = clampOverlayConfig(overlay);
      expect([clamped.size.width, clamped.size.height]).toEqual(expectedSize);
      expect([clamped.offset.x, clamped.offset.y]).toEqual(expectedOffset);

      const box = computeOverlayBox(overlay);
      expect([box.x, box.y]).toEqual(expectedXY);
    },
  );

  it(ZERO_SIZE_FIXTURE.name, () => {
    const { anchor, size, offset, expectedSize, expectedOffset, expectedXY } = ZERO_SIZE_FIXTURE;
    const overlay = {
      ...DEFAULT_OVERLAY_CONFIG,
      anchor,
      size: { width: size[0], height: size[1] },
      offset: { x: offset[0], y: offset[1] },
    };

    const clamped = clampOverlayConfig(overlay);
    expect([clamped.size.width, clamped.size.height]).toEqual(expectedSize);
    expect([clamped.offset.x, clamped.offset.y]).toEqual(expectedOffset);

    const box = computeOverlayBox(overlay);
    expect([box.x, box.y]).toEqual(expectedXY);
    expect([box.width, box.height]).toEqual([2, 2]);
  });
});

/**
 * Ticket 12 parity fixtures for the padding clamp — mirrors
 * `backend/tests/rendering/test_geometry.py`'s padding fixture table
 * (`test_padding_*`). Both `_clamp_padding` (geometry.py) and
 * `clampOverlayPadding` (overlay-geometry.ts) must floor to the same even
 * number for the same (box, padding) input.
 */
const PADDING_FIXTURES: Array<{
  name: string;
  size: [number, number];
  padding: number;
  expectedPadding: number;
}> = [
  { name: 'padding_zero', size: [320, 320], padding: 0, expectedPadding: 0 },
  { name: 'padding_within_bounds', size: [320, 320], padding: 20, expectedPadding: 20 },
  { name: 'padding_forced_down_to_fit', size: [100, 100], padding: 10_000, expectedPadding: 48 },
];

describe('computeInnerOverlayBox parity', () => {
  it.each(PADDING_FIXTURES)('$name', ({ size, padding, expectedPadding }) => {
    const overlay = {
      ...DEFAULT_OVERLAY_CONFIG,
      anchor: 'top_left' as Anchor,
      size: { width: size[0], height: size[1] },
      offset: { x: 0, y: 0 },
      padding,
    };
    const inner = computeInnerOverlayBox(overlay);
    expect(inner.padding).toBe(expectedPadding);
    expect(inner.width).toBeGreaterThan(0);
    expect(inner.height).toBeGreaterThan(0);
  });
});
