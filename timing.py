from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time


@dataclass
class CandleClock:
    timeframe_seconds: int = 30
    offset_seconds: int = 0

    def now(self) -> float:
        return time.time() + self.offset_seconds

    def window(self):
        t = self.now()
        start = int(t // self.timeframe_seconds) * self.timeframe_seconds
        end = start + self.timeframe_seconds
        remaining = max(0, int(end - t))
        return start, end, remaining

    def formatted(self):
        start, end, remaining = self.window()
        s = datetime.fromtimestamp(start)
        e = datetime.fromtimestamp(end)
        return (
            s.strftime("%H:%M:%S"),
            e.strftime("%H:%M:%S"),
            remaining,
        )

    def source_label(self) -> str:
        if self.offset_seconds == 0:
            return "PC CLOCK"
        return f"PC CLOCK + {self.offset_seconds:+d}s"
