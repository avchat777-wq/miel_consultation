from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class RateLimiter:
    """Small in-process limiter suitable for a single-container MVP."""

    def __init__(self, requests: int, window_seconds: int):
        self.requests = requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self.requests:
                return False
            events.append(now)
            return True

