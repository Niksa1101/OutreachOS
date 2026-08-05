"""FFmpeg -progress parser unit tests."""

from outreachos_backend.rendering.progress import ProgressParser


def _block(out_us: int, out_time: str) -> list[str]:
    """One `-progress pipe:1` block, in the order FFmpeg actually writes it."""
    return [
        "frame=30",
        "fps=29.9",
        "bitrate=1500.0kbits/s",
        "total_size=187500",
        f"out_time_us={out_us}",
        f"out_time_ms={out_us}",
        f"out_time={out_time}",
        "speed=1.01x",
        "progress=continue",
    ]


def test_out_time_fraction_is_microseconds_not_centiseconds() -> None:
    """Regression: reading the 6-digit fraction as centiseconds inflated out_time ~10^4x."""
    parser = ProgressParser(duration_us=10_000_000)
    percent = parser.feed_line("out_time=00:00:01.500000")
    assert percent is not None
    assert abs(percent - 15.0) < 0.001


def test_progress_climbs_across_blocks_instead_of_pinning_at_100() -> None:
    """The bogus out_time value used to latch last_percent at 100 on the first block,
    after which the monotonic guard swallowed every real update."""
    parser = ProgressParser(duration_us=10_000_000)
    seen: list[float] = []
    for out_us, out_time in [
        (1_000_000, "00:00:01.000000"),
        (2_500_000, "00:00:02.500000"),
        (5_000_000, "00:00:05.000000"),
        (10_000_000, "00:00:10.000000"),
    ]:
        for line in _block(out_us, out_time):
            percent = parser.feed_line(line)
            if percent is not None:
                seen.append(percent)

    assert seen == sorted(seen), "percentages must be monotonic"
    assert seen[0] < 50.0, f"first reading saturated: {seen[0]}"
    assert abs(seen[-1] - 100.0) < 0.001
    assert len({round(p, 3) for p in seen}) >= 4, "each block should report progress"


def test_hours_and_minutes_are_carried() -> None:
    parser = ProgressParser(duration_us=7_200_000_000)  # 2h
    percent = parser.feed_line("out_time=01:30:00.000000")
    assert percent is not None
    assert abs(percent - 75.0) < 0.001


def test_na_and_malformed_lines_are_ignored() -> None:
    parser = ProgressParser(duration_us=1_000_000)
    assert parser.feed_line("out_time_us=N/A") is None
    assert parser.feed_line("out_time=N/A") is None
    assert parser.feed_line("progress=continue") is None
    assert parser.feed_line("no equals sign") is None


def test_zero_duration_reports_nothing() -> None:
    parser = ProgressParser(duration_us=0)
    assert parser.feed_line("out_time_us=500000") is None


def test_percent_is_clamped_to_100_when_ffmpeg_overshoots() -> None:
    parser = ProgressParser(duration_us=1_000_000)
    assert parser.feed_line("out_time_us=9000000") == 100.0
