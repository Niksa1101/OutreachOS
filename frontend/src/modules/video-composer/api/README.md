# `video-composer/api/`

TanStack Query hooks over the generated, typed client in `core/api`.

TanStack Query owns all server state. Query defaults are event-driven, not
time-driven — `staleTime: Infinity`, `retry: false`, no refetch on window focus —
because this is a local backend and invalidation arrives over SSE.

No global store for server data. Ever.
