# `core/sse/`

One SSE connection for the whole application, mounted inside the ready-state
shell.

Uses `eventsource` v3 with a custom `fetch`, because native `EventSource` cannot
send an `Authorization` header and the token must not travel in a query string.
See `docs/decisions/0005-sse-client-library.md`.

Event contract:

- Real events carry `id: <boot_id>:<seq>` and enter a 200-entry replay ring buffer.
- `heartbeat` is a named event sent **without** an `id:` field, so it consumes no
  sequence number and cannot evict real events during an idle period.
- `resync` carries the current head id and is **not** buffered, so `Last-Event-ID`
  advances to head and a client can never loop on an uncoverable id.

Handlers dispatch into TanStack Query via `setQueryData` / `invalidateQueries`.
A `boot_id` change invalidates the entire cache. No heartbeat for 45s closes and
reconnects.
