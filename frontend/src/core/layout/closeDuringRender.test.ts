import { describe, expect, it } from 'vitest';

import {
  jobIsActivelyRendering,
  queueHasActiveRender,
} from '@/core/layout/closeDuringRender';

describe('queueHasActiveRender', () => {
  it('is true when any job is preparing, rendering, or encoding', () => {
    expect(
      queueHasActiveRender({
        jobs: [
          { status: 'waiting' },
          { status: 'encoding' },
        ] as never,
        batch: { active: 1 } as never,
      }),
    ).toBe(true);
  });

  it('is false when the queue is only waiting / terminal', () => {
    expect(
      queueHasActiveRender({
        jobs: [
          { status: 'waiting' },
          { status: 'completed' },
          { status: 'failed' },
        ] as never,
        batch: { active: 0 } as never,
      }),
    ).toBe(false);
  });

  it('falls back to job statuses when batch.active is missing', () => {
    expect(
      queueHasActiveRender({
        jobs: [{ status: 'rendering' }] as never,
        batch: undefined as never,
      }),
    ).toBe(true);
  });
});

describe('jobIsActivelyRendering', () => {
  it.each(['preparing', 'rendering', 'encoding'] as const)('%s counts as active', (status) => {
    expect(jobIsActivelyRendering({ status })).toBe(true);
  });

  it.each(['waiting', 'completed', 'failed'] as const)('%s does not', (status) => {
    expect(jobIsActivelyRendering({ status })).toBe(false);
  });
});
