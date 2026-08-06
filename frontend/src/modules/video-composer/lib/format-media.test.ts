import { describe, expect, it } from 'vitest';

import { formatDurationMs } from '@/modules/video-composer/lib/format-media';

describe('formatDurationMs', () => {
  it('formats sub-hour durations as m:ss', () => {
    expect(formatDurationMs(75_000)).toBe('1:15');
    expect(formatDurationMs(0)).toBe('0:00');
  });

  it('formats hour-long durations as h:mm:ss', () => {
    expect(formatDurationMs(3_600_000)).toBe('1:00:00');
    expect(formatDurationMs(4_500_000)).toBe('1:15:00');
  });

  it('returns a dash for non-finite input', () => {
    expect(formatDurationMs(Number.NaN)).toBe('—');
    expect(formatDurationMs(Number.POSITIVE_INFINITY)).toBe('—');
  });
});
