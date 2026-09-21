from __future__ import annotations

from unittest import mock

import pytest

from ckanext.event_audit import rate_limit
from ckanext.event_audit.rate_limit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestRateLimiter:
    @pytest.fixture
    def clock(self) -> FakeClock:
        return FakeClock()

    @pytest.fixture
    def limiter(self, clock: FakeClock) -> RateLimiter:
        return RateLimiter(window=60, clock=clock)

    def test_events_up_to_the_limit_are_allowed(self, limiter: RateLimiter):
        assert [limiter.allow(3) for _ in range(5)] == [True, True, True, False, False]

    def test_a_new_window_starts_a_new_count(
        self, limiter: RateLimiter, clock: FakeClock
    ):
        assert [limiter.allow(1) for _ in range(2)] == [True, False]

        clock.now += 59

        assert not limiter.allow(1)

        clock.now += 1

        assert limiter.allow(1)
        assert not limiter.allow(1)

    def test_limit_change_applies_to_the_current_window(self, limiter: RateLimiter):
        assert [limiter.allow(1) for _ in range(2)] == [True, False]

        assert limiter.allow(3)

    def test_warns_once_per_window(
        self,
        monkeypatch: pytest.MonkeyPatch,
        limiter: RateLimiter,
        clock: FakeClock,
    ):
        # CKAN's logging setup disables loggers created before it ran, so the
        # module's logger can't be observed with `caplog`
        log = mock.Mock()
        monkeypatch.setattr(rate_limit, "log", log)

        for _ in range(5):
            limiter.allow(1)

        assert log.warning.call_count == 1

        clock.now += 60

        for _ in range(5):
            limiter.allow(1)

        assert log.warning.call_count == 2
