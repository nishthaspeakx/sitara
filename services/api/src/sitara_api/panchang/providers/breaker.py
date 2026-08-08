"""Provider circuit breaker — SPEC §8.

"circuit breakers on every provider adapter (fail fast after 5 errors/30s,
half-open probes)". One breaker per provider; state is exposed for the §12
admin provider dashboard.

Failing FAST matters as much as failing: an open breaker that still burns the
caller's timeout would spend the §8 latency budget discovering what we already
know, and the degradation ladder below it would never get its turn.
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from enum import StrEnum
from typing import Any


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BreakerOpen(Exception):
    """Raised instead of calling a provider we believe is down.

    Callers translate this into the next rung of the §8 ladder — never into a
    user-visible error on its own.
    """

    def __init__(self, name: str) -> None:
        super().__init__(f"circuit open for provider {name!r}")
        self.provider = name


class CircuitBreaker:
    """Rolling-window breaker with a single-flight half-open probe."""

    def __init__(
        self,
        name: str,
        errors: int = 5,
        window_seconds: float = 30.0,
        half_open_after_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self._threshold = errors
        self._window = window_seconds
        self._cooldown = half_open_after_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: deque[float] = deque()
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def check(self) -> None:
        """Gate a call. Raises BreakerOpen when the provider must not be hit.

        Transitions OPEN → HALF_OPEN once the cooldown has elapsed and admits
        exactly ONE caller through; a recovering provider must not be met with
        the full stampede that knocked it over.
        """
        with self._lock:
            if self._state is CircuitState.CLOSED:
                return
            if self._state is CircuitState.HALF_OPEN:
                # A probe is already in flight.
                raise BreakerOpen(self.name)
            assert self._opened_at is not None
            if self._clock() - self._opened_at < self._cooldown:
                raise BreakerOpen(self.name)
            self._state = CircuitState.HALF_OPEN

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()
            self._state = CircuitState.CLOSED
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            now = self._clock()
            if self._state is CircuitState.HALF_OPEN:
                # The probe failed: back to open for a fresh cooldown.
                self._state = CircuitState.OPEN
                self._opened_at = now
                return
            self._failures.append(now)
            self._evict(now)
            if len(self._failures) >= self._threshold:
                self._state = CircuitState.OPEN
                self._opened_at = now

    def snapshot(self) -> dict[str, Any]:
        """State for the §12 admin provider dashboard."""
        with self._lock:
            self._evict(self._clock())
            return {
                "name": self.name,
                "state": self._state.value,
                "recent_failures": len(self._failures),
                "threshold": self._threshold,
                "window_seconds": self._window,
            }

    def _evict(self, now: float) -> None:
        while self._failures and now - self._failures[0] > self._window:
            self._failures.popleft()
