import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EventSource } from 'eventsource';

import { currentBackend } from '@/core/api/client';
import { EventStream } from '@/core/sse/client';

vi.mock('@/core/api/client', () => ({
  currentBackend: vi.fn(),
}));

const mockClose = vi.fn();

vi.mock('eventsource', () => ({
  EventSource: vi.fn().mockImplementation(() => ({
    onopen: null,
    onerror: null,
    addEventListener: vi.fn(),
    close: mockClose,
  })),
}));

describe('EventStream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(currentBackend).mockReturnValue({
      port: 42_000,
      token: 'a'.repeat(64),
      boot_id: 'boot-1',
    });
    mockClose.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('retries opening when backend credentials are not ready yet', () => {
    vi.mocked(currentBackend).mockReturnValue(null);

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

  it('closes and schedules a manual reconnect on transport error', () => {
    const onDisconnect = vi.fn();
    const stream = new EventStream({ onDisconnect });
    stream.start();

    const source = vi.mocked(EventSource).mock.results.at(-1)?.value as {
      onerror: (() => void) | null;
    };
    source.onerror?.();

    expect(mockClose).toHaveBeenCalled();
    expect(onDisconnect).toHaveBeenCalledWith('The event stream errored.');

    vi.advanceTimersByTime(1_000);
    expect(vi.mocked(EventSource)).toHaveBeenCalledTimes(2);

    stream.close();
  });

  it('does not create overlapping sources while a reconnect is scheduled', () => {
    const stream = new EventStream({});
    stream.start();

    const firstCount = vi.mocked(EventSource).mock.calls.length;
    const source = vi.mocked(EventSource).mock.results.at(-1)?.value as {
      onerror: (() => void) | null;
    };
    source.onerror?.();
    source.onerror?.();

    expect(vi.mocked(EventSource).mock.calls.length).toBe(firstCount);

    stream.close();
  });
});
