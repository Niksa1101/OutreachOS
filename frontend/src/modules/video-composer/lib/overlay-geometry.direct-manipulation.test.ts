import { describe, expect, it } from 'vitest';

import {
  type Anchor,
  type OverlayConfig,
  DEFAULT_CANVAS,
  DEFAULT_OVERLAY_CONFIG,
  MIN_OVERLAY_DIMENSION_PX,
  SAFE_MARGIN_PX,
  boxPositionForAnchor,
  computeOverlayBox,
  dragOverlayBy,
  nearestAnchorForPosition,
  offsetForAnchorPosition,
  resizeOverlayBy,
  snapOffset,
} from '@/modules/video-composer/lib/overlay-geometry';

const ANCHORS: Anchor[] = ['top_left', 'top_right', 'bottom_left', 'bottom_right'];

describe('boxPositionForAnchor / offsetForAnchorPosition are inverses', () => {
  for (const anchor of ANCHORS) {
    it(anchor, () => {
      // Even values survive `anchorXY`'s internal `evenRound` unchanged, so the
      // round trip is exact — odd values are a rounding (not correctness) concern.
      const offset = { x: 36, y: 90 };
      const { x, y } = boxPositionForAnchor(anchor, offset, 200, 150);
      const roundTripped = offsetForAnchorPosition(anchor, x, y, 200, 150);
      expect(roundTripped).toEqual(offset);
    });
  }
});

describe('nearestAnchorForPosition', () => {
  it('picks the canvas quadrant the box center falls in', () => {
    expect(nearestAnchorForPosition(0, 0, 100, 100)).toBe('top_left');
    expect(nearestAnchorForPosition(DEFAULT_CANVAS.width - 100, 0, 100, 100)).toBe('top_right');
    expect(nearestAnchorForPosition(0, DEFAULT_CANVAS.height - 100, 100, 100)).toBe('bottom_left');
    expect(
      nearestAnchorForPosition(DEFAULT_CANVAS.width - 100, DEFAULT_CANVAS.height - 100, 100, 100),
    ).toBe('bottom_right');
  });
});

describe('snapOffset', () => {
  it('snaps to 0 and the safe margin within the threshold', () => {
    expect(snapOffset({ x: 5, y: 5 })).toEqual({ x: 0, y: 0 });
    expect(snapOffset({ x: SAFE_MARGIN_PX + 3, y: SAFE_MARGIN_PX - 3 })).toEqual({
      x: SAFE_MARGIN_PX,
      y: SAFE_MARGIN_PX,
    });
  });

  it('leaves values outside the threshold untouched — snap releases when dragging away', () => {
    expect(snapOffset({ x: 200, y: 200 })).toEqual({ x: 200, y: 200 });
  });
});

describe('dragOverlayBy', () => {
  const base: OverlayConfig = {
    ...DEFAULT_OVERLAY_CONFIG,
    anchor: 'bottom_right',
    size: { width: 200, height: 200 },
    offset: { x: 100, y: 100 },
  };

  it('moves the box by the pointer delta', () => {
    const before = computeOverlayBox(base);
    const dragged = dragOverlayBy(base, -20, -10);
    const after = computeOverlayBox(dragged);
    expect(after.x).toBe(before.x - 20);
    expect(after.y).toBe(before.y - 10);
  });

  it('switches anchor when dragged across the canvas midline', () => {
    const dragged = dragOverlayBy(base, -DEFAULT_CANVAS.width, -DEFAULT_CANVAS.height);
    expect(dragged.anchor).toBe('top_left');
  });

  it('snaps into the safe margin near an edge and can be dragged back out', () => {
    const start: OverlayConfig = {
      ...DEFAULT_OVERLAY_CONFIG,
      anchor: 'top_left',
      size: { width: 200, height: 200 },
      offset: { x: 100, y: 100 },
    };
    const nearMargin = dragOverlayBy(start, -76, -76); // 100 -> 24, within threshold
    expect(nearMargin.offset).toEqual({ x: SAFE_MARGIN_PX, y: SAFE_MARGIN_PX });

    const draggedFurther = dragOverlayBy(start, -200, -200); // well past the threshold
    expect(draggedFurther.offset.x).toBeLessThan(SAFE_MARGIN_PX);
  });

  it('never produces an off-frame or inverted box, for any delta', () => {
    const deltas: Array<[number, number]> = [
      [999999, 999999],
      [-999999, -999999],
      [999999, -999999],
      [-999999, 999999],
    ];
    for (const [dx, dy] of deltas) {
      const dragged = dragOverlayBy(base, dx, dy);
      const box = computeOverlayBox(dragged);
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(DEFAULT_CANVAS.width);
      expect(box.y + box.height).toBeLessThanOrEqual(DEFAULT_CANVAS.height);
    }
  });

  it('always persists integer offsets, even for a fractional pointer delta', () => {
    const dragged = dragOverlayBy(base, 13.37, -4.2);
    expect(Number.isInteger(dragged.offset.x)).toBe(true);
    expect(Number.isInteger(dragged.offset.y)).toBe(true);
  });
});

describe('resizeOverlayBy', () => {
  // Screen-space delta that moves the free-corner handle away from each
  // anchor's own (pinned) corner — the direction a real drag-to-grow gesture
  // produces once the handle sits at the correct corner (finding D1).
  const AWAY_FROM_ANCHOR_DELTA: Record<Anchor, [number, number]> = {
    top_left: [40, 20],
    top_right: [-40, 20],
    bottom_left: [40, -20],
    bottom_right: [-40, -20],
  };

  for (const anchor of ANCHORS) {
    it(`grows the box when the handle moves away from the ${anchor} anchor corner`, () => {
      const overlay: OverlayConfig = {
        ...DEFAULT_OVERLAY_CONFIG,
        anchor,
        size: { width: 200, height: 200 },
        offset: { x: 50, y: 50 },
      };
      const [dx, dy] = AWAY_FROM_ANCHOR_DELTA[anchor];
      const grown = resizeOverlayBy(overlay, dx, dy);
      expect(grown.size.width).toBeGreaterThan(200);
      expect(grown.size.height).toBeGreaterThan(200);
      // The anchor's own corner is pinned by offset and never moves.
      expect(grown.offset).toEqual({ x: 50, y: 50 });

      const shrunk = resizeOverlayBy(overlay, -dx, -dy);
      expect(shrunk.size.width).toBeLessThan(200);
      expect(shrunk.size.height).toBeLessThan(200);
      expect(shrunk.offset).toEqual({ x: 50, y: 50 });
    });
  }

  it('always persists integer sizes, even for a fractional pointer delta', () => {
    const overlay: OverlayConfig = {
      ...DEFAULT_OVERLAY_CONFIG,
      anchor: 'top_left',
      size: { width: 200, height: 200 },
      offset: { x: 50, y: 50 },
    };
    const resized = resizeOverlayBy(overlay, 9.81, 2.5);
    expect(Number.isInteger(resized.size.width)).toBe(true);
    expect(Number.isInteger(resized.size.height)).toBe(true);
    expect(Number.isInteger(resized.offset.x)).toBe(true);
    expect(Number.isInteger(resized.offset.y)).toBe(true);
  });

  it('respects the minimum size floor', () => {
    const overlay: OverlayConfig = {
      ...DEFAULT_OVERLAY_CONFIG,
      anchor: 'top_left',
      size: { width: 200, height: 200 },
      offset: { x: 50, y: 50 },
    };
    const shrunk = resizeOverlayBy(overlay, -999999, -999999);
    expect(shrunk.size).toEqual({
      width: MIN_OVERLAY_DIMENSION_PX,
      height: MIN_OVERLAY_DIMENSION_PX,
    });
  });

  it('never produces an off-frame or inverted box, for any delta', () => {
    const overlay: OverlayConfig = {
      ...DEFAULT_OVERLAY_CONFIG,
      anchor: 'bottom_right',
      size: { width: 200, height: 200 },
      offset: { x: 50, y: 50 },
    };
    const deltas: Array<[number, number]> = [
      [999999, 999999],
      [-999999, -999999],
    ];
    for (const [dx, dy] of deltas) {
      const resized = resizeOverlayBy(overlay, dx, dy);
      const box = computeOverlayBox(resized);
      expect(box.width).toBeGreaterThan(0);
      expect(box.height).toBeGreaterThan(0);
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(DEFAULT_CANVAS.width);
      expect(box.y + box.height).toBeLessThanOrEqual(DEFAULT_CANVAS.height);
    }
  });
});
