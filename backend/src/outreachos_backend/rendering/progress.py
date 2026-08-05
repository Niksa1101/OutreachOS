"""FFmpeg -progress pipe:1 parser."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ProgressParser"]


@dataclass
class ProgressParser:
    duration_us: int
    last_percent: float = 0.0

    def feed_line(self, line: str) -> float | None:
        if "=" not in line:
            return None
        key, _, value = line.partition("=")
        if key == "out_time_us" and value != "N/A":
            return self._percent_from_us(int(value))
        if key == "out_time":
            return self._percent_from_time(value)
        return None

    def _percent_from_us(self, out_us: int) -> float | None:
        if self.duration_us <= 0:
            return None
        pct = min(100.0, max(0.0, (out_us / self.duration_us) * 100.0))
        if pct < self.last_percent:
            return None
        self.last_percent = pct
        return pct

    def _percent_from_time(self, value: str) -> float | None:
        parts = value.strip().split(":")
        if len(parts) != 3:
            return None
        hours, minutes, seconds = parts
        sec_parts = seconds.split(".")
        try:
            whole = int(hours) * 3600 + int(minutes) * 60 + int(sec_parts[0])
        except ValueError:
            return None
        # FFmpeg writes microseconds here (`00:00:01.500000`), not centiseconds.
        # Reading them as centiseconds inflated out_time by ~10^4, which pinned
        # last_percent at 100 on the first progress block and made the monotonic
        # guard swallow every later update.
        frac = int(sec_parts[1].ljust(6, "0")[:6]) if len(sec_parts) > 1 else 0
        return self._percent_from_us(whole * 1_000_000 + frac)
