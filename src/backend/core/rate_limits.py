"""Bounded sliding windows with an injectable monotonic clock."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from backend.core.errors import ApplicationError


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def sweep(self) -> None:
        with self._lock:
            self._sweep(self.clock())

    def _sweep(self, now: float) -> None:
        for key, events in list(self.events.items()):
            if not events or now - events[-1] >= 120:
                del self.events[key]

    def check(self, *limits: tuple[str, int]) -> None:
        """Admit atomically; downstream validation failures still consume quota."""
        with self._lock:
            now = self.clock()
            self._sweep(now)
            queues = []
            for key, limit in limits:
                events = self.events.setdefault(key, deque())
                while events and now - events[0] >= 60:
                    events.popleft()
                queues.append((events, limit))
            if any(len(events) >= limit for events, limit in queues):
                raise ApplicationError(
                    "RATE_LIMIT", "Prea multe cereri. Încercați mai târziu.", 429
                )
            for events, _ in queues:
                events.append(now)
