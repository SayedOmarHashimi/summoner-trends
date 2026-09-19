import time

from extraction.rate_limiter import PERSONAL_KEY_LIMITS, RateLimiter


def test_allows_requests_up_to_the_limit_without_waiting():
    limiter = RateLimiter(limits=((5, 60.0),), safety_margin=0.0)
    started = time.monotonic()
    for _ in range(5):
        limiter.acquire()
    assert time.monotonic() - started < 0.1


def test_blocks_once_the_window_is_full():
    limiter = RateLimiter(limits=((2, 0.3),), safety_margin=0.0)
    limiter.acquire()
    limiter.acquire()

    started = time.monotonic()
    limiter.acquire()  # must wait for the oldest hit to age out
    assert time.monotonic() - started >= 0.25


def test_tightest_window_wins():
    # 10/sec is generous, 2 per 0.3s is not: the second window governs.
    limiter = RateLimiter(limits=((10, 1.0), (2, 0.3)), safety_margin=0.0)
    limiter.acquire()
    limiter.acquire()

    started = time.monotonic()
    limiter.acquire()
    assert time.monotonic() - started >= 0.25


def test_penalty_blocks_every_caller():
    limiter = RateLimiter(limits=((100, 60.0),), safety_margin=0.0)
    limiter.penalize(0.3)

    started = time.monotonic()
    limiter.acquire()
    assert time.monotonic() - started >= 0.25


def test_snapshot_reports_usage():
    limiter = RateLimiter(limits=((20, 1.0),), safety_margin=0.0)
    limiter.acquire()
    assert limiter.snapshot() == [(1, 20, 1.0)]


def test_personal_key_defaults_match_riot_documented_limits():
    assert PERSONAL_KEY_LIMITS == ((20, 1.0), (100, 120.0))


class FakeClock:
    """Virtual clock: sleeping advances time, so waits are instant but real."""

    def __init__(self, start=1000.0):
        self.now = start
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_long_wait_is_announced(monkeypatch, caplog):
    # A silent 30s pause is indistinguishable from a hang, so it must be logged.
    clock = FakeClock()
    monkeypatch.setattr(time, "sleep", clock.sleep)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)

    limiter = RateLimiter(limits=((100, 120.0),), safety_margin=0.0)
    limiter.penalize(30.0)

    with caplog.at_level("INFO"):
        limiter.acquire()

    assert "waiting 30s" in caplog.text
    assert "server asked us to back off" in caplog.text


def test_short_wait_is_not_announced(monkeypatch, caplog):
    clock = FakeClock()
    monkeypatch.setattr(time, "sleep", clock.sleep)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)

    limiter = RateLimiter(limits=((1, 0.5),), safety_margin=0.0)
    limiter.acquire()

    with caplog.at_level("INFO"):
        limiter.acquire()  # waits 0.5s — below the threshold

    assert "Rate limit reached" not in caplog.text


def test_wait_names_the_local_window_that_blocked(monkeypatch, caplog):
    clock = FakeClock()
    monkeypatch.setattr(time, "sleep", clock.sleep)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)

    limiter = RateLimiter(limits=((2, 10.0),), safety_margin=0.0)
    limiter.acquire()
    limiter.acquire()

    with caplog.at_level("INFO"):
        limiter.acquire()

    assert "local limit 2/2 per 10s" in caplog.text
