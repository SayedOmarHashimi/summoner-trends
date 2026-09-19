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
