"""The SSE event bus.

Q12 gives the shape: one endpoint, named events, JSON payloads, a heartbeat
every 15s. Q65, Q106, and one late correction give the parts that are easy to
get subtly wrong, and each is load-bearing:

**Event ids are ``<boot_id>:<seq>``, not a bare counter** (Q65). A bare counter
from a previous boot lands inside the current ring buffer's range and replays
confidently wrong events. Replay across a restart is meaningless anyway — the
token rotated and the queue was rebuilt.

**Heartbeats are named events with no ``id:`` field** (Q106). Not comment
frames: ``eventsource`` v3 does not surface ``:`` comments to consumers, so the
client's 45s watchdog would observe nothing and tear down a perfectly healthy
idle connection every 45 seconds forever. And not id-carrying events, because
consuming sequence numbers for keepalives evicts real events from the buffer.
``id:`` is optional in SSE, and an event sent without one does not advance the
client's ``Last-Event-ID``.

**``resync`` carries the current head id and is not buffered** (late
correction). Omitting ``id:`` there produces a subtler failure than it looks:
``eventsource`` v3 manages ``Last-Event-ID`` internally from ``id:`` fields, so
a client receiving an id-less resync keeps its stale id, reconnects with the
same uncoverable value, and gets another resync. Forever. Carrying the head id
advances the client to a point with nothing to replay; not buffering it means
the resync itself can never be replayed.
"""

import asyncio
import json
import logging
import threading
from collections import deque
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = ["ENVELOPE_REQUIRED_KEYS", "EVENT_NAMES", "EventBus", "ServerEvent"]

log = logging.getLogger(__name__)

#: Named constants so publishers do not index into ``EVENT_NAMES`` — inserting
#: a name must not silently repoint ``campaign_lock_changed`` et al.
EVENT_HEARTBEAT: Final = "heartbeat"
EVENT_RESYNC: Final = "resync"
EVENT_CAMPAIGN_LOCK_CHANGED: Final = "campaign_lock_changed"
EVENT_RENDER_JOB_CHANGED: Final = "render_job_changed"
EVENT_BATCH_PROGRESS_CHANGED: Final = "batch_progress_changed"

#: Every event name this backend can emit.
#:
#: Q114: ``/events`` is excluded from the OpenAPI schema, so these types are
#: hand-written on the frontend in ``core/sse/events.ts`` and a cross-language
#: parity test reads *this tuple* to check them. The test is scoped
#: deliberately — the set of names and the required envelope keys, not full
#: payload shapes. Payload-shape parity across two languages is where this gets
#: fragile and starts wanting a generator.
EVENT_NAMES: Final = (
    EVENT_HEARTBEAT,
    EVENT_RESYNC,
    EVENT_CAMPAIGN_LOCK_CHANGED,
    EVENT_RENDER_JOB_CHANGED,
    EVENT_BATCH_PROGRESS_CHANGED,
)

#: Keys every event payload carries, whatever its name.
ENVELOPE_REQUIRED_KEYS: Final = ("boot_id",)

#: Q65: "~200 is right". Large enough to cover a reconnect during a render
#: batch, small enough that a disconnected client cannot pin much memory.
RING_CAPACITY: Final = 200

#: Q12. The client watchdog is 45s (three missed beats) — see `core/sse` on the
#: frontend.
HEARTBEAT_INTERVAL_SECONDS: Final = 15.0

#: Bounded so one stalled consumer cannot grow without limit. Overflowing does
#: not drop the client: it gets a `resync`, which is exactly the situation
#: resync exists for.
_SUBSCRIBER_QUEUE_SIZE: Final = 256


@dataclass(frozen=True)
class ServerEvent:
    name: str
    data: Mapping[str, Any]
    id: str | None = None

    def encode(self) -> str:
        """Serialise to the SSE wire format.

        ``json.dumps`` with compact separators produces no newlines, so the
        payload is always exactly one ``data:`` line. A multi-line payload
        would need splitting, and forgetting that is a truncation bug that only
        shows up once a message contains a newline.
        """
        lines = []
        if self.id is not None:
            lines.append(f"id: {self.id}")
        lines.append(f"event: {self.name}")
        lines.append(f"data: {json.dumps(dict(self.data), separators=(',', ':'))}")
        return "\n".join(lines) + "\n\n"


# Control markers pushed into a subscriber's queue. Identity-compared, never
# serialised.
class _Close:
    pass


class _Resync:
    pass


_CLOSE: Final = _Close()
_RESYNC: Final = _Resync()


# `eq=False` keeps the dataclass hashable. A generated `__eq__` sets
# `__hash__ = None`, and these live in a set keyed by identity — two
# subscribers are never "equal", they are two different open connections.
@dataclass(eq=False)
class _Subscriber:
    queue: asyncio.Queue[ServerEvent | _Close | _Resync] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_SIZE)
    )

    def offer(self, item: ServerEvent | _Close | _Resync) -> None:
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            # This consumer is not keeping up. Everything queued for it is now
            # suspect, so throw it away and tell it to refetch rather than
            # deliver a sequence with a hole in it.
            log.warning("an SSE subscriber fell behind; forcing a resync")
            while not self.queue.empty():
                self.queue.get_nowait()
            self.queue.put_nowait(_RESYNC)


class EventBus:
    """Fan-out with a replay buffer, scoped to one boot.

    Publishing is thread-safe because it will be called from the render worker
    in P4, which runs in its own thread rather than on the event loop. Getting
    that wrong is invisible until the first background job.
    """

    def __init__(self, boot_id: str, capacity: int = RING_CAPACITY) -> None:
        self._boot_id = boot_id
        self._buffer: deque[tuple[int, ServerEvent]] = deque(maxlen=capacity)
        self._seq = 0
        self._subscribers: set[_Subscriber] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    # -- lifecycle ---------------------------------------------------------

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the loop that owns the subscriber queues.

        Called from the lifespan startup hook. Until then ``publish`` is a
        no-op fan-out — it still assigns a sequence number and buffers the
        event, so anything published during startup is replayed to the first
        subscriber rather than lost.
        """
        self._loop = loop

    def begin_shutdown(self) -> None:
        """Release every open stream.

        Q118 orders this **before** uvicorn's own shutdown, and the order is
        not cosmetic: uvicorn waits for open connections to close, and an SSE
        stream never closes on its own. Skipping this means the 5s grace period
        expires and Rust hard-kills a process that was shutting down correctly.
        """
        with self._lock:
            self._closed = True
            subscribers = list(self._subscribers)
            loop = self._loop

        if loop is None:
            return

        for subscriber in subscribers:
            loop.call_soon_threadsafe(subscriber.offer, _CLOSE)

    # -- publishing --------------------------------------------------------

    def publish(self, name: str, data: Mapping[str, Any]) -> ServerEvent:
        """Append a real event to the buffer and fan it out."""
        with self._lock:
            self._seq += 1
            event = ServerEvent(name=name, data=dict(data), id=f"{self._boot_id}:{self._seq}")
            self._buffer.append((self._seq, event))
            subscribers = list(self._subscribers)
            loop = self._loop

        if loop is not None:
            for subscriber in subscribers:
                loop.call_soon_threadsafe(subscriber.offer, event)

        return event

    def heartbeat(self) -> ServerEvent:
        """A named event with **no id**. See the module docstring."""
        return ServerEvent(name=EVENT_HEARTBEAT, data={"boot_id": self._boot_id})

    def resync(self) -> ServerEvent:
        """Carries the head id at time of send; never buffered."""
        with self._lock:
            head = self._seq
        return ServerEvent(
            name=EVENT_RESYNC,
            data={"boot_id": self._boot_id, "reason": "replay_unavailable"},
            id=f"{self._boot_id}:{head}",
        )

    def campaign_lock_changed(self, campaign_id: str, *, locked: bool) -> ServerEvent:
        """Ticket 21: a campaign's editor lock state changed.

        Unlike ``heartbeat``/``resync`` this carries real application data, so
        it goes through ``publish`` and is buffered/replayed like any other
        event rather than constructed inline at the call site.
        """
        return self.publish(
            EVENT_CAMPAIGN_LOCK_CHANGED,
            {"boot_id": self._boot_id, "campaign_id": campaign_id, "locked": locked},
        )

    def render_job_changed(self, job: Mapping[str, Any]) -> ServerEvent:
        """Ticket 15: a render job's status or progress changed.

        Called from the render worker thread — see the class docstring for why
        ``publish`` is thread-safe. Carries the full job row rather than a
        delta: the queue view is small (global, not per-campaign) and a full
        row lets a listener patch its cache directly instead of refetching.
        """
        return self.publish(
            EVENT_RENDER_JOB_CHANGED,
            {"boot_id": self._boot_id, "job": dict(job)},
        )

    def batch_progress_changed(self, batch: Mapping[str, Any]) -> ServerEvent:
        """Ticket 18: the queue-wide rollup (counts, progress, ETA) changed.

        Published alongside ``render_job_changed`` so the sidebar badge and the
        batch header update from the same stream without polling. Carries the
        full ``BatchProgress`` snapshot for the same reason job events carry a
        full row — patch, don't refetch.
        """
        return self.publish(
            EVENT_BATCH_PROGRESS_CHANGED,
            {"boot_id": self._boot_id, "batch": dict(batch)},
        )

    # -- replay ------------------------------------------------------------

    def replay_for(self, last_event_id: str | None) -> list[ServerEvent]:
        """What a reconnecting client is owed.

        Returns either the events it missed, or a single ``resync`` when they
        cannot be reconstructed.
        """
        if not last_event_id:
            # A first connection has missed nothing by definition. Sending a
            # resync here would make every page load refetch twice.
            return []

        boot_id, separator, raw_seq = last_event_id.partition(":")

        if not separator or boot_id != self._boot_id:
            # Q65: a different boot. The token rotated and the queue was
            # rebuilt, so there is nothing meaningful to replay.
            return [self.resync()]

        try:
            seen = int(raw_seq)
        except ValueError:
            return [self.resync()]

        with self._lock:
            buffered = list(self._buffer)
            head = self._seq

        if seen >= head:
            # Already current — including the case where this client is
            # resuming from a `resync` we just sent it.
            return []

        if not buffered:
            return [self.resync()]

        oldest = buffered[0][0]
        if seen + 1 < oldest:
            # The next event it needs has already been evicted.
            return [self.resync()]

        return [event for seq, event in buffered if seq > seen]

    # -- subscription ------------------------------------------------------

    async def stream(self, last_event_id: str | None) -> AsyncGenerator[str, None]:
        """Yield encoded SSE frames until shutdown or client disconnect.

        Typed as a generator rather than an iterator so callers can `aclose()`
        it. Starlette does exactly that when the client disconnects, and the
        `finally` below is what detaches the subscriber — an iterator type
        would compile and silently leak one subscriber per dropped connection.
        """
        subscriber = _Subscriber()

        with self._lock:
            if self._closed:
                return
            self._subscribers.add(subscriber)

        log.debug("SSE subscriber attached (last_event_id=%s)", last_event_id or "-")

        try:
            for event in self.replay_for(last_event_id):
                yield event.encode()

            # An immediate beat before the interval loop. It costs nothing, it
            # confirms the stream is genuinely open rather than merely
            # accepted, and it starts the client's 45s watchdog from an
            # observation instead of from an assumption. Without it the first
            # 15 seconds of every connection are indistinguishable from a
            # stream that will never produce anything.
            yield self.heartbeat().encode()

            loop = asyncio.get_running_loop()
            next_beat = loop.time() + HEARTBEAT_INTERVAL_SECONDS

            while True:
                now = loop.time()
                if next_beat <= now:
                    # The loop fell behind. Resetting rather than catching up
                    # avoids emitting a burst of backdated heartbeats.
                    next_beat = now + HEARTBEAT_INTERVAL_SECONDS

                try:
                    item = await asyncio.wait_for(subscriber.queue.get(), timeout=next_beat - now)
                except TimeoutError:
                    next_beat += HEARTBEAT_INTERVAL_SECONDS
                    yield self.heartbeat().encode()
                    continue

                if isinstance(item, _Close):
                    break
                if isinstance(item, _Resync):
                    yield self.resync().encode()
                    continue

                yield item.encode()
        finally:
            with self._lock:
                self._subscribers.discard(subscriber)
            log.debug("SSE subscriber detached")
