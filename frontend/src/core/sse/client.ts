/**
 * The SSE client.
 *
 * ADR-0005 / Q42: `eventsource` v3 (rexxars), not the native `EventSource` and
 * not `@microsoft/fetch-event-source`.
 *
 * - Native `EventSource` cannot set an `Authorization` header, and Q43 allows
 *   no exemptions — including for this stream.
 * - `@microsoft/fetch-event-source` has been unmaintained since 2022 with known
 *   reconnect bugs nobody is fixing.
 *
 * `eventsource` v3 accepts a custom `fetch`, which is exactly the seam the
 * bearer token needs.
 *
 * The watchdog (Q-assumptions): the library reconnects when the connection
 * *errors*, but a half-open TCP connection produces no error — it simply goes
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
  }

  #clearTimers(): void {
    if (this.#watchdog !== null) clearTimeout(this.#watchdog);
    if (this.#reconnect !== null) clearTimeout(this.#reconnect);
    this.#watchdog = null;
    this.#reconnect = null;
  }

  #open(): void {
    const backend = currentBackend();
    if (!backend) {
      // No credentials yet. The provider only mounts in the ready phase, so
      // this means a teardown raced us.
      return;
    }

    const url = `http://127.0.0.1:${backend.port}/api/v1/events`;

    const source = new EventSource(url, {
      fetch: (input, init) => {
        const headers = new Headers(init?.headers);
        headers.set('Authorization', `Bearer ${backend.token}`);
        headers.set('Accept', 'text/event-stream');

        // On the library's own reconnects it sets this itself and the two
        // values agree. Setting it here as well is what makes a *manual*
        // rebuild after a watchdog trip resume from the right place instead of
        // silently restarting the stream from scratch.
        if (this.#lastEventId) {
          headers.set('Last-Event-ID', this.#lastEventId);
        }

        // No timeout: this connection is meant to stay open. `core/api`'s 15s
        // default would kill it on schedule.
        return fetch(input, { ...init, headers });
      },
    });

    source.onopen = () => {
      this.handlers.onOpen?.();
      this.#armWatchdog();
    };

    source.onerror = () => {
      // The library retries on its own; this is reporting, not recovery.
      this.handlers.onDisconnect?.('The event stream errored.');
    };

    for (const name of SERVER_EVENT_NAMES) {
      source.addEventListener(name, (event: MessageEvent<string>) => {
        this.#handle(name, event);
      });
    }

    this.#source = source;
    this.#armWatchdog();
  }

  #handle(name: ServerEventName, event: MessageEvent<string>): void {
    // Heartbeats carry no `id:`, so `lastEventId` is empty on them and the
    // stored value correctly stays where the last *real* event left it.
    if (event.lastEventId) {
      this.#lastEventId = event.lastEventId;
    }

    // Any traffic proves the connection is alive. The watchdog is specified
    // against heartbeats, and resetting on real events too can only make it
    // less trigger-happy — never more.
    this.#armWatchdog();

    let payload: unknown;
    try {
      payload = JSON.parse(event.data);
    } catch {
      // A frame we cannot parse is a protocol violation, not data. Dropping it
      // is right; tearing down the stream over it is not.
      return;
    }

    // The casts are the JSON boundary and nothing more: `JSON.parse` returns
    // `unknown`, and this is the one place a wire frame becomes a typed event.
    switch (name) {
      case 'heartbeat':
        this.handlers.onEvent?.({ name: 'heartbeat', payload: payload as HeartbeatEvent });
        return;
      case 'resync':
        this.handlers.onEvent?.({ name: 'resync', payload: payload as ResyncEvent });
        return;
    }
  }

  #armWatchdog(): void {
    if (this.#watchdog !== null) clearTimeout(this.#watchdog);
    if (this.#closed) return;

    this.#watchdog = setTimeout(() => {
      this.handlers.onDisconnect?.(
        `No heartbeat for ${HEARTBEAT_WATCHDOG_MS / 1000}s; reconnecting.`,
      );

      this.#source?.close();
      this.#source = null;

      if (this.#closed) return;
      this.#reconnect = setTimeout(() => this.#open(), RECONNECT_DELAY_MS);
    }, HEARTBEAT_WATCHDOG_MS);
  }
}
