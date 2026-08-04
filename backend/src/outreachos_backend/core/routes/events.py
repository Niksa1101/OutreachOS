"""``GET /api/v1/events`` — the one SSE stream.

Tech.md §4.1: one-directional, auto-reconnecting, no protocol machinery. The
interesting decisions are in ``core/events.py``; this is the transport.

Q114: ``include_in_schema=False``. An SSE stream has no response body OpenAPI
can describe, and a generated type claiming it returns ``string`` would be
worse than no type at all. The event names and envelope keys are hand-written
in ``frontend/src/core/sse/events.ts`` with a parity test across the two
languages — scoped to the *set of names* and the required top-level keys, which
is the cheap robust check. Full payload-shape parity across two languages is
where this gets fragile and starts wanting a generator.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["system"])
router.redirect_slashes = False


@router.get("/events", include_in_schema=False)
async def stream_events(
    request: Request,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    bus = request.app.state.event_bus

    return StreamingResponse(
        bus.stream(last_event_id),
        media_type="text/event-stream",
        headers={
            # Nothing is proxying this — it is loopback — but a stale
            # intermediate cache on an SSE stream is unrecoverable rather than
            # merely slow, so the headers are cheap insurance.
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Suppresses proxy buffering where anything does intervene.
            "X-Accel-Buffering": "no",
        },
    )
