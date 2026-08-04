/**
 * The SSE client.
 *
 * ADR-0005 / Q42: `eventsource` v3 (rexxars), not the native `EventSource` and
 * not `@microsoft/fetch-event-source`.
 *
 * Reconnect is owned here — on transport error the source is closed and rebuilt
 * manually after `RECONNECT_DELAY_MS`. The library's own retry is not relied
 * on, because it would compete with the heartbeat watchdog.
 *
 * The watchdog: a half-open TCP connection produces no error — it simply goes
 * quiet forever. 45 seconds without a heartbeat, which the server sends every
 * 15, means three missed beats and is unambiguous enough to act on.
 */

import { EventSource } from 'eventsource';

import { currentBackend } from '@/core/api/client';
import {
  SERVER_EVENT_NAMES,
  type HeartbeatEvent,
  type ResyncEvent,
  type ServerEvent,
  type ServerEventName,
} from '@/core/sse/events';

/** Q106: the server beats every 15s, so this is three missed beats. */
export const HEARTBEAT_WATCHDOG_MS = 45_000;

/** How long to wait before rebuilding a stream the watchdog tore down. */
const RECONNECT_DELAY_MS = 1_000;

export interface EventStreamHandlers {
  onEvent?: (event: ServerEvent) => void;
  /** Fired when the stream opens or reopens. */
  onOpen?: () => void;
  /** Fired when the watchdog or the transport tears the stream down. */
  onDisconnect?: (reason: string) => void;
}

function parseHeartbeat(payload: unknown): HeartbeatEvent | null {
  if (typeof payload !== 'object' || payload === null || !('boot_id' in payload)) {
    return null;
  }
  const bootId: unknown = payload.boot_id;
  if (typeof bootId !== 'string' || bootId.length === 0) {
    return null;
  }
  return { boot_id: bootId };
}

function parseResync(payload: unknown): ResyncEvent | null {
  if (typeof payload !== 'object' || payload === null) {
    return null;
  }
  const record = payload as { boot_id?: unknown; reason?: unknown };
  if (typeof record.boot_id !== 'string' || record.boot_id.length === 0) {
    return null;
  }
  if (typeof record.reason !== 'string') {
    return null;
  }
  return { boot_id: record.boot_id, reason: record.reason };
}

/**
 * One connection to `/api/v1/events`.
 *
 * Q66: exactly one of these exists, owned by a provider inside the ready-state
 * shell. Two would double every cache invalidation and halve the value of the
 * server's ring buffer.
 */
export class EventStream {
  #source: EventSource | null = null;
  #watchdog: ReturnType<typeof setTimeout> | null = null;
  #reconnect: ReturnType<typeof setTimeout> | null = null;
  #lastEventId: string | null = null;
  #closed = false;
  #opening = false;

  constructor(private readonly handlers: EventStreamHandlers) {}

  start(): void {
    this.#closed = false;
    this.#open();
  }

  close(): void {
    this.#closed = true;
    this.#clearTimers();
    this.#source?.close();
    this.#source = null;
    this.#opening = false;
  }

  #clearTimers(): void {
    if (this.#watchdog !== null) clearTimeout(this.#watchdog);
    if (this.#reconnect !== null) clearTimeout(this.#reconnect);
    this.#watchdog = null;
    this.#reconnect = null;
  }

  #scheduleReconnect(reason: string): void {
    if (this.#closed) return;

    this.handlers.onDisconnect?.(reason);
    this.#source?.close();
    this.#source = null;
    this.#opening = false;

    if (this.#reconnect !== null) clearTimeout(this.#reconnect);
    this.#reconnect = setTimeout(() => this.#open(), RECONNECT_DELAY_MS);
  }

  #open(): void {
    if (this.#closed || this.#opening) return;

    const backend = currentBackend();
    if (!backend) {
      if (!this.#closed) {
        this.#reconnect = setTimeout(() => this.#open(), RECONNECT_DELAY_MS);
      }
      return;
    }

    this.#opening = true;
    const url = `http://127.0.0.1:${backend.port}/api/v1/events`;

    const source = new EventSource(url, {
      fetch: (input, init) => {
        const headers = new Headers(init?.headers);
        headers.set('Authorization', `Bearer ${backend.token}`);
        headers.set('Accept', 'text/event-stream');

        if (this.#lastEventId) {
          headers.set('Last-Event-ID', this.#lastEventId);
        }

        return fetch(input, { ...init, headers });
      },
    });

    source.onopen = () => {
      this.#opening = false;
      this.handlers.onOpen?.();
      this.#armWatchdog();
    };

    source.onerror = () => {
      this.#scheduleReconnect('The event stream errored.');
    };

    for (const name of SERVER_EVENT_NAMES) {
      source.addEventListener(name, (event: MessageEvent<string>) => {
        this.#handle(name, event);
      });
    }

    this.#source = source;
  }

  #handle(name: ServerEventName, event: MessageEvent<string>): void {
    if (event.lastEventId) {
      this.#lastEventId = event.lastEventId;
    }

    this.#armWatchdog();

    let payload: unknown;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }

    switch (name) {
      case 'heartbeat': {
        const heartbeat = parseHeartbeat(payload);
        if (heartbeat) {
          this.handlers.onEvent?.({ name: 'heartbeat', payload: heartbeat });
        }
        return;
      }
      case 'resync': {
        const resync = parseResync(payload);
        if (resync) {
          this.handlers.onEvent?.({ name: 'resync', payload: resync });
        }
        return;
      }
    }
  }

  #armWatchdog(): void {
    if (this.#watchdog !== null) clearTimeout(this.#watchdog);
    if (this.#closed) return;

    this.#watchdog = setTimeout(() => {
      this.#scheduleReconnect(`No heartbeat for ${HEARTBEAT_WATCHDOG_MS / 1000}s; reconnecting.`);
    }, HEARTBEAT_WATCHDOG_MS);
  }
}
