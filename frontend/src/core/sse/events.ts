/**
 * The SSE event vocabulary.
 *
 * Hand-written, because Q114 excludes `/events` from the OpenAPI schema: a
 * stream has no response body OpenAPI can describe, and a generated type
 * claiming it returns `string` would be worse than none.
 *
 * `events.parity.test.ts` reads `EVENT_NAMES` out of
 * `backend/.../core/events.py` and asserts these two lists agree. Scoped to the
 * *set of names* and the required envelope keys — that is the cheap, robust
 * check. Full payload-shape parity across two languages is where this gets
 * fragile.
 */

/** Must match `EVENT_NAMES` in `core/events.py`. */
export const SERVER_EVENT_NAMES = ['heartbeat', 'resync'] as const;

export type ServerEventName = (typeof SERVER_EVENT_NAMES)[number];

/** Must match `ENVELOPE_REQUIRED_KEYS` in `core/events.py`. */
export const ENVELOPE_REQUIRED_KEYS = ['boot_id'] as const;

/** Common to every payload. */
export interface ServerEventEnvelope {
  boot_id: string;
}

/**
 * Named, and deliberately **without an `id:` field** (Q106).
 *
 * Not a `:` comment frame: `eventsource` v3 does not surface comments to
 * consumers, so a watchdog attached to comments would observe nothing and tear
 * down a healthy idle connection every 45 seconds forever. And not an
 * id-carrying event, because keepalives consuming sequence numbers would evict
 * real events from the server's ring buffer.
 */
export interface HeartbeatEvent extends ServerEventEnvelope {
  _tag?: 'heartbeat';
}

/**
 * "Your `Last-Event-ID` cannot be covered; refetch everything."
 *
 * Carries the current head id and is **not** written to the ring buffer, so
 * receiving one advances `Last-Event-ID` to a point with nothing to replay and
 * the resync itself can never be replayed. Without that, a client that gets an
 * id-less resync keeps its stale id and reconnects into the same resync
 * forever.
 */
export interface ResyncEvent extends ServerEventEnvelope {
  reason: string;
}

/**
 * A received event, discriminated by `name`.
 *
 * A union rather than a `{ name, payload }` pair over a generic map: only a
 * union narrows `payload` inside a `switch`, and a handler that has to cast to
 * read its own payload will eventually cast to the wrong member.
 */
export type ServerEvent =
  { name: 'heartbeat'; payload: HeartbeatEvent } | { name: 'resync'; payload: ResyncEvent };

export function isServerEventName(value: string): value is ServerEventName {
  return (SERVER_EVENT_NAMES as readonly string[]).includes(value);
}
