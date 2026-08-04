# ADR-0005: SSE client is `eventsource` v3, not native `EventSource`

**Status:** Accepted. Elaborates Tech.md §4.1, which specifies "one SSE stream …
auto-reconnecting" without naming an implementation.

---

## Context

Tech.md §4.2 requires a shared-secret token on **every** request. Browser
`EventSource` cannot send custom headers — there is no API for it.

That leaves three ways to authenticate the stream, and the choice is forced
rather than stylistic.

## Decision

Use `eventsource` v3, which accepts a custom `fetch` implementation. That is the
exact seam needed to attach the `Authorization` header, and it is spec-compliant
and maintained.

## Alternatives considered

- **`@microsoft/fetch-event-source`.** The obvious first choice and the wrong
  one: unmaintained since 2022 (v2.0.1), with known reconnect bugs nobody is
  fixing. Inheriting an abandoned dependency for the reconnect path of a
  long-running batch tool is a poor trade.
- **Token as a query parameter with native `EventSource`.** Works, but puts the
  secret in URLs and access logs.
- **Native `EventSource`, unauthenticated, relying on loopback binding alone.**
  Rejected: Tech.md §4.2's stated threat model is explicitly that another local
  process — "including a browser tab" — must not be able to drive the renderer.
- **Hand-rolled SSE over `fetch` + `ReadableStream`.** Around 80 lines, no
  dependency. Remains a viable fallback; rejected only because owning reconnect,
  backoff, and `Last-Event-ID` semantics is work with no upside here.

## Consequences

The client manages `Last-Event-ID` internally from `id:` fields, which shapes the
event contract:

- Real events carry `id: <boot_id>:<seq>` and enter a 200-entry ring buffer.
- `heartbeat` is a named event sent **without** an `id:` field. It therefore
  consumes no sequence number and cannot evict real events during an idle period.
  It must be a named event rather than a comment frame, because the library does
  not surface `:` comments to consumers and the 45s watchdog would have nothing
  to observe.
- `resync` carries the **current head id** and is not buffered. This inverts the
  intuition that a resync should be unreplayable by omitting its id — omitting it
  would leave the client's `Last-Event-ID` stale, producing a resync on every
  reconnect forever.

## References

Questionnaire Q42, Q65, Q106. Tech.md §4.1, §4.2, §8.
