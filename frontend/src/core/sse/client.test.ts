import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { currentBackend } from '@/core/api/client';
import { EventStream } from '@/core/sse/client';

vi.mock('@/core/api/client', () => ({
  currentBackend: vi.fn(),
}));

vi.mock('eventsource', () => ({
  EventSource: vi.fn().mockImplementation(() => ({
    onopen: null,
    onerror: null,
    addEventListener: vi.fn(),
    close: vi.fn(),
  })),
}));

describe('EventStream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(currentBackend).mockReturnValue(null);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('retries opening when backend credentials are not ready yet', () => {
    const stream = new EventStream({});
    stream.start();

    expect(vi.mocked(currentBackend)).toHaveBeenCalledTimes(1);

    vi.mocked(currentBackend).mockReturnValue({
      port: 42_000,
      token: 'a'.repeat(64),
      boot_id: 'boot-1',
    });

    vi.advanceTimersByTime(1_000);

    expect(vi.mocked(currentBackend)).toHaveBeenCalledTimes(2);
    stream.close();
  });
});
