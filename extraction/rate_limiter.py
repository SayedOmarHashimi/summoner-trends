"""Client-side rate limiting for the Riot API.

A Personal API key is limited to 20 requests per second and 100 requests per
2 minutes, per region. Both windows apply at once, so the limiter tracks every
window and sleeps until the tightest one has room.

This is the polite half of the contract: staying under the limit locally means
the server rarely has to send a 429 at all. The other half — honouring
Retry-After when one arrives anyway — lives in `riot_client`.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Waits longer than this are announced. A long silent pause is
# indistinguishable from a hang, so say what is happening.
LOG_WAIT_THRESHOLD_SECONDS = 2.0

# Personal key defaults, per region.
PERSONAL_KEY_LIMITS: tuple[tuple[int, float], ...] = (
    (20, 1.0),      # 20 requests per 1 second
    (100, 120.0),   # 100 requests per 2 minutes
)


@dataclass
class _Window:
    limit: int
    seconds: float

    def __post_init__(self) -> None:
        self.hits: deque[float] = deque()

    def prune(self, now: float) -> None:
        cutoff = now - self.seconds
        while self.hits and self.hits[0] <= cutoff:
            self.hits.popleft()

    def wait_seconds(self, now: float) -> float:
        """How long until this window has room for one more request."""
        self.prune(now)
        if len(self.hits) < self.limit:
            return 0.0
        # The oldest hit has to age out of the window before we may proceed.
        return max(0.0, self.hits[0] + self.seconds - now)

    def record(self, now: float) -> None:
        self.hits.append(now)


class RateLimiter:
    """Sliding-window limiter covering several concurrent windows.

    Thread-safe, so a future threaded fetcher can share one limiter per region.
    """

    def __init__(
        self,
        limits: tuple[tuple[int, float], ...] = PERSONAL_KEY_LIMITS,
        safety_margin: float = 0.05,
    ) -> None:
        if not limits:
            raise ValueError("At least one (limit, seconds) window is required.")
        self._windows = [_Window(limit, seconds) for limit, seconds in limits]
        self._safety_margin = safety_margin
        self._lock = threading.Lock()
        # Set by the client when the server tells us to back off.
        self._blocked_until = 0.0

    def acquire(self) -> None:
        """Block until a request may be sent, then record it."""
        while True:
            with self._lock:
                now = time.monotonic()
                penalty_wait = self._blocked_until - now
                window_waits = [w.wait_seconds(now) for w in self._windows]
                wait = max(window_waits + [penalty_wait])
                if wait <= 0:
                    for window in self._windows:
                        window.record(now)
                    return
                reason = self._describe_wait(now, wait, penalty_wait, window_waits)
            if wait >= LOG_WAIT_THRESHOLD_SECONDS:
                logger.info("Rate limit reached — waiting %.0fs before next request (%s).", wait, reason)
            # Sleep outside the lock so other threads can make progress.
            time.sleep(wait + self._safety_margin)

    def _describe_wait(
        self, now: float, wait: float, penalty_wait: float, window_waits: list[float]
    ) -> str:
        """Name whichever limit is holding us back, for the log line."""
        if penalty_wait >= wait:
            return "server asked us to back off"
        for window, window_wait in zip(self._windows, window_waits):
            if window_wait >= wait:
                return f"local limit {len(window.hits)}/{window.limit} per {window.seconds:g}s"
        return "local limit"

    def penalize(self, seconds: float) -> None:
        """Block all requests for `seconds` — used when the API returns 429."""
        with self._lock:
            self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)

    def snapshot(self) -> list[tuple[int, int, float]]:
        """(used, limit, window_seconds) per window, for logging."""
        with self._lock:
            now = time.monotonic()
            for window in self._windows:
                window.prune(now)
            return [(len(w.hits), w.limit, w.seconds) for w in self._windows]

    def wait_for_penalty(self) -> float:
        """Seconds still remaining on a server-instructed backoff, for tests
        and logging. Zero once the penalty has elapsed."""
        with self._lock:
            return max(0.0, self._blocked_until - time.monotonic())
