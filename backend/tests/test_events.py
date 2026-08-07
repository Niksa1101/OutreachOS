"""The SSE bus: ids, replay, and the two events that are not ordinary events.

Everything here is a rule from Q65, Q106, or the late `resync` correction. Each
of those rules exists because its absence produced a failure that looked like
something else — a replay of the wrong boot's events, a watchdog tearing down a
healthy connection, a reconnect storm. None of them are visible by reading the
stream.
"""

import asyncio

import pytest

from outreachos_backend.core.events import (
    ENVELOPE_REQUIRED_KEYS,
    EVENT_NAMES,
    EventBus,
    ServerEvent,
)

BOOT = "boot-aaaa"


def parse_frame(frame: str) -> dict[str, str]:
    """Split an encoded SSE frame into its fields."""
    fields: dict[str, str] = {}
    for line in frame.strip().split("\n"):
        key, _, value = line.partition(": ")
        fields[key] = value
    return fields


# --- encoding --------------------------------------------------------------


def test_an_event_with_an_id_emits_all_three_fields() -> None:
    frame = parse_frame(ServerEvent(name="thing", data={"a": 1}, id=f"{BOOT}:7").encode())
    assert frame == {"id": f"{BOOT}:7", "event": "thing", "data": '{"a":1}'}


def test_the_payload_is_always_exactly_one_data_line() -> None:
    # A newline inside the payload would be parsed as a field separator and
    # truncate the event. Compact JSON never produces one, and this is the
    # assertion that keeps it that way if the separators ever change.
    event = ServerEvent(name="thing", data={"text": "line one\nline two"}, id="x:1")
    encoded = event.encode()
    assert encoded.count("data: ") == 1
    assert encoded.endswith("\n\n")


# --- heartbeat (Q106) ------------------------------------------------------


def test_a_heartbeat_carries_no_id() -> None:
    # The whole point. An `id:` here would consume a sequence number and evict
    # real events from the ring buffer, and would also advance the client's
    # Last-Event-ID past events it never received.
    frame = parse_frame(EventBus(BOOT).heartbeat().encode())
    assert "id" not in frame
    assert frame["event"] == "heartbeat"


def test_a_heartbeat_is_a_named_event_not_a_comment_frame() -> None:
    # Comment frames (`: keepalive`) are not surfaced to consumers by
    # `eventsource` v3, so the client's 45s watchdog would observe nothing and
    # tear down a healthy idle connection every 45 seconds forever.
    encoded = EventBus(BOOT).heartbeat().encode()
    assert not encoded.startswith(":")
    assert "event: heartbeat" in encoded


def test_heartbeats_do_not_consume_sequence_numbers() -> None:
    bus = EventBus(BOOT)
    bus.heartbeat()
    bus.heartbeat()
    assert bus.publish("thing", {}).id == f"{BOOT}:1"


# --- resync (the late correction) ------------------------------------------


def test_resync_carries_the_current_head_id() -> None:
    # Omitting `id:` here looks harmless and is not: `eventsource` v3 manages
    # Last-Event-ID internally from `id:` fields, so a client receiving an
    # id-less resync keeps its stale id, reconnects with the same uncoverable
    # value, and gets another resync. Forever.
    bus = EventBus(BOOT)
    bus.publish("thing", {})
    bus.publish("thing", {})

    assert parse_frame(bus.resync().encode())["id"] == f"{BOOT}:2"


def test_resync_is_not_written_into_the_ring_buffer() -> None:
    # If it were buffered it could be replayed, which would hand a client a
    # resync it had already acted on.
    bus = EventBus(BOOT)
    bus.publish("thing", {"n": 1})
    bus.resync()

    replayed = bus.replay_for(f"{BOOT}:0")
    assert [event.name for event in replayed] == ["thing"]


def test_a_client_resuming_from_a_resync_is_owed_nothing() -> None:
    # This is what stops the loop: the resync advanced them to head, so the
    # next reconnect resumes cleanly with nothing to replay.
    bus = EventBus(BOOT)
    bus.publish("thing", {})
    resync_id = bus.resync().id
    assert resync_id is not None

    assert bus.replay_for(resync_id) == []


# --- replay (Q65) ----------------------------------------------------------


def test_a_first_connection_replays_nothing() -> None:
    # Sending a resync here would make every page load refetch twice.
    bus = EventBus(BOOT)
    bus.publish("thing", {})
    assert bus.replay_for(None) == []
    assert bus.replay_for("") == []


def test_an_id_from_a_different_boot_forces_a_resync() -> None:
    # Q65: without the boot scope, a sequence number from a previous boot lands
    # inside the current buffer's range and replays confidently wrong events.
    bus = EventBus(BOOT)
    for index in range(5):
        bus.publish("thing", {"n": index})

    replayed = bus.replay_for("some-earlier-boot:3")
    assert [event.name for event in replayed] == ["resync"]


def test_a_malformed_last_event_id_forces_a_resync() -> None:
    bus = EventBus(BOOT)
    bus.publish("thing", {})

    for bad in ("garbage", f"{BOOT}:not-a-number", BOOT):
        assert [event.name for event in bus.replay_for(bad)] == ["resync"], bad


def test_replay_returns_only_the_events_after_the_last_seen() -> None:
    bus = EventBus(BOOT)
    for index in range(5):
        bus.publish("thing", {"n": index})

    replayed = bus.replay_for(f"{BOOT}:2")
    assert [event.data["n"] for event in replayed] == [2, 3, 4]


def test_a_client_already_at_head_is_owed_nothing() -> None:
    bus = EventBus(BOOT)
    bus.publish("thing", {})
    assert bus.replay_for(f"{BOOT}:1") == []


def test_an_evicted_sequence_forces_a_resync() -> None:
    # The buffer is finite, so a client offline long enough cannot be caught
    # up. Saying so beats delivering a sequence with a hole in it.
    bus = EventBus(BOOT, capacity=3)
    for index in range(10):
        bus.publish("thing", {"n": index})

    assert [event.name for event in bus.replay_for(f"{BOOT}:1")] == ["resync"]


def test_the_oldest_still_buffered_event_is_replayable() -> None:
    # The boundary: with events 8, 9, 10 buffered, a client that saw 7 is owed
    # exactly those three and must *not* get a resync.
    bus = EventBus(BOOT, capacity=3)
    for index in range(1, 11):
        bus.publish("thing", {"n": index})

    replayed = bus.replay_for(f"{BOOT}:7")
    assert [event.data["n"] for event in replayed] == [8, 9, 10]


def test_the_ring_buffer_is_bounded() -> None:
    bus = EventBus(BOOT, capacity=4)
    for index in range(100):
        bus.publish("thing", {"n": index})

    assert len(bus.replay_for(f"{BOOT}:96")) == 4


# --- streaming -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_new_stream_opens_with_an_immediate_heartbeat() -> None:
    # Without it the first 15 seconds of every connection are
    # indistinguishable from a stream that will never produce anything.
    bus = EventBus(BOOT)
    bus.attach_loop(asyncio.get_running_loop())

    stream = bus.stream(None)
    first = await anext(stream)

    assert parse_frame(first)["event"] == "heartbeat"
    await stream.aclose()


@pytest.mark.asyncio
async def test_a_reconnect_from_another_boot_gets_resync_then_heartbeat() -> None:
    bus = EventBus(BOOT)
    bus.attach_loop(asyncio.get_running_loop())

    stream = bus.stream("other-boot:99")
    assert parse_frame(await anext(stream))["event"] == "resync"
    assert parse_frame(await anext(stream))["event"] == "heartbeat"
    await stream.aclose()


@pytest.mark.asyncio
async def test_a_published_event_reaches_an_open_stream() -> None:
    bus = EventBus(BOOT)
    bus.attach_loop(asyncio.get_running_loop())

    stream = bus.stream(None)
    await anext(stream)  # the opening heartbeat

    bus.publish("thing", {"n": 42})
    frame = parse_frame(await anext(stream))

    assert frame["event"] == "thing"
    assert frame["id"] == f"{BOOT}:1"
    await stream.aclose()


@pytest.mark.asyncio
async def test_shutdown_ends_open_streams() -> None:
    # Q118: this is what lets uvicorn's graceful shutdown complete. An SSE
    # stream never closes on its own, so without it the 5s grace period expires
    # and Rust hard-kills a process that was shutting down correctly.
    bus = EventBus(BOOT)
    bus.attach_loop(asyncio.get_running_loop())

    stream = bus.stream(None)
    await anext(stream)

    bus.begin_shutdown()

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=2)


@pytest.mark.asyncio
async def test_a_stream_opened_after_shutdown_yields_nothing() -> None:
    bus = EventBus(BOOT)
    bus.attach_loop(asyncio.get_running_loop())
    bus.begin_shutdown()

    assert [frame async for frame in bus.stream(None)] == []


# --- the frontend contract -------------------------------------------------


def test_every_declared_event_name_is_actually_emitted() -> None:
    # `EVENT_NAMES` is what the frontend parity test reads. A name listed there
    # but never sent would make that test pass while the client waited for
    # something that does not exist.
    bus = EventBus(BOOT)
    emitted = {
        bus.heartbeat().name,
        bus.resync().name,
        bus.campaign_lock_changed("campaign-1", locked=True).name,
        bus.render_job_changed({"id": "job-1"}).name,
        bus.batch_progress_changed({"total": 0, "active_job_count": 0}).name,
    }
    assert emitted == set(EVENT_NAMES)


def test_every_event_payload_carries_the_required_envelope_keys() -> None:
    bus = EventBus(BOOT)
    events = (
        bus.heartbeat(),
        bus.resync(),
        bus.campaign_lock_changed("campaign-1", locked=True),
        bus.render_job_changed({"id": "job-1"}),
        bus.batch_progress_changed({"total": 0, "active_job_count": 0}),
    )
    for event in events:
        for key in ENVELOPE_REQUIRED_KEYS:
            assert key in event.data, f"{event.name} is missing {key}"
