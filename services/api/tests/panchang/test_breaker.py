"""Provider circuit breaker — SPEC §8.

"circuit breakers on every provider adapter (fail fast after 5 errors/30s,
half-open probes)". The clock is injected so these run in microseconds and
never sleep.
"""

import pytest

from sitara_api.panchang.providers.breaker import BreakerOpen, CircuitBreaker, CircuitState


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture()
def breaker(clock: FakeClock) -> CircuitBreaker:
    return CircuitBreaker(
        name="divineapi", errors=5, window_seconds=30, half_open_after_seconds=60, clock=clock
    )


def trip(breaker: CircuitBreaker, count: int = 5) -> None:
    for _ in range(count):
        breaker.record_failure()


class TestOpening:
    def test_starts_closed(self, breaker: CircuitBreaker) -> None:
        assert breaker.state is CircuitState.CLOSED
        breaker.check()  # does not raise

    def test_four_errors_do_not_open_it(self, breaker: CircuitBreaker) -> None:
        trip(breaker, 4)
        assert breaker.state is CircuitState.CLOSED

    def test_fifth_error_opens_it(self, breaker: CircuitBreaker) -> None:
        trip(breaker)
        assert breaker.state is CircuitState.OPEN

    def test_open_circuit_fails_fast(self, breaker: CircuitBreaker) -> None:
        """Fail FAST — an open breaker must not spend the caller's latency
        budget on a call we already know will fail (§8 SLOs)."""
        trip(breaker)
        with pytest.raises(BreakerOpen):
            breaker.check()

    def test_errors_outside_the_window_do_not_count(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        """Five errors spread over an hour is a flaky provider, not an outage."""
        for _ in range(4):
            breaker.record_failure()
            clock.advance(10)
        breaker.record_failure()
        assert breaker.state is CircuitState.CLOSED

    def test_success_clears_the_error_run(self, breaker: CircuitBreaker) -> None:
        trip(breaker, 4)
        breaker.record_success()
        trip(breaker, 4)
        assert breaker.state is CircuitState.CLOSED


class TestHalfOpenProbe:
    def test_stays_open_until_the_cooldown_elapses(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        trip(breaker)
        clock.advance(59)
        with pytest.raises(BreakerOpen):
            breaker.check()

    def test_admits_one_probe_after_cooldown(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        trip(breaker)
        clock.advance(61)
        breaker.check()
        assert breaker.state is CircuitState.HALF_OPEN

    def test_half_open_admits_only_one_caller(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        """A probe is a single request, not a reopening of the floodgates —
        otherwise recovery stampedes the provider we just stopped hammering."""
        trip(breaker)
        clock.advance(61)
        breaker.check()
        with pytest.raises(BreakerOpen):
            breaker.check()

    def test_successful_probe_closes_the_circuit(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        trip(breaker)
        clock.advance(61)
        breaker.check()
        breaker.record_success()
        assert breaker.state is CircuitState.CLOSED
        breaker.check()

    def test_failed_probe_reopens_for_a_full_cooldown(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        trip(breaker)
        clock.advance(61)
        breaker.check()
        breaker.record_failure()
        assert breaker.state is CircuitState.OPEN
        clock.advance(59)
        with pytest.raises(BreakerOpen):
            breaker.check()
        clock.advance(2)
        breaker.check()


class TestObservability:
    def test_exposes_state_for_the_admin_dashboard(self, breaker: CircuitBreaker) -> None:
        """§12 admin: 'provider dashboards, circuit-breaker states'."""
        trip(breaker)
        snapshot = breaker.snapshot()
        assert snapshot["name"] == "divineapi"
        assert snapshot["state"] == CircuitState.OPEN.value
        assert snapshot["recent_failures"] == 5

    def test_breaker_open_names_the_provider(self, breaker: CircuitBreaker) -> None:
        trip(breaker)
        with pytest.raises(BreakerOpen) as exc:
            breaker.check()
        assert "divineapi" in str(exc.value)
