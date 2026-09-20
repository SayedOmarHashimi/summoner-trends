"""Retry behaviour tests. No network: a fake session stands in for requests."""

import time

import pytest

from extraction.config import Settings
from extraction.rate_limiter import RateLimiter
from extraction.riot_client import RiotAPIError, RiotClient


class FakeResponse:
    def __init__(self, status_code, json_body=None, headers=None, reason="error"):
        self.status_code = status_code
        self._json = json_body
        self.headers = headers or {}
        self.reason = reason

    def json(self):
        return self._json


class FakeSession:
    """Returns queued responses in order and records the calls it received."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if not self._responses:
            raise AssertionError("FakeSession ran out of queued responses")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def settings(tmp_path):
    return Settings(
        api_key="RGAPI-test-key",
        region="na1",
        routing="americas",
        riot_id="TrendTester#NA1",
        duckdb_path=tmp_path / "test.duckdb",
        raw_data_dir=tmp_path / "raw",
    )


class FakeClock:
    """A virtual clock so backoff is instant but still measurable.

    `time` is one shared module object, so patching it here covers both the
    client's backoff and the rate limiter's waits. Sleeping advances the clock,
    which is what lets the limiter's wait loop terminate.
    """

    def __init__(self, start=1000.0):
        self.now = start
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds

    @property
    def total_slept(self):
        return sum(self.slept)


@pytest.fixture
def no_sleep(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(time, "sleep", clock.sleep)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    return clock


def build_client(settings, responses, **kwargs):
    session = FakeSession(responses)
    client = RiotClient(
        settings,
        rate_limiter=RateLimiter(limits=((1000, 1.0),), safety_margin=0.0),
        session=session,
        **kwargs,
    )
    return client, session


def test_api_key_is_sent_as_a_header_not_a_query_parameter(settings):
    client, session = build_client(settings, [FakeResponse(200, {"puuid": "p"})])
    client.get_account_by_riot_id("TrendTester", "NA1")
    assert session.headers["X-Riot-Token"] == "RGAPI-test-key"
    url, params = session.calls[0]
    assert "RGAPI" not in url
    assert params is None


def test_successful_request_returns_the_json_body(settings):
    client, _ = build_client(settings, [FakeResponse(200, {"puuid": "puuid-a"})])
    assert client.get_account_by_riot_id("TrendTester", "NA1") == {"puuid": "puuid-a"}


def test_429_is_retried_and_honours_retry_after(settings, no_sleep):
    client, _ = build_client(
        settings,
        [
            FakeResponse(429, headers={"Retry-After": "7", "X-Rate-Limit-Type": "application"}),
            FakeResponse(200, {"puuid": "puuid-a"}),
        ],
    )
    assert client.get_account_by_riot_id("TrendTester", "NA1") == {"puuid": "puuid-a"}
    # Waited for exactly what the server asked for, not a guess.
    assert no_sleep.total_slept == pytest.approx(7.0)


def test_429_without_retry_after_falls_back_instead_of_crashing(settings, no_sleep):
    client, _ = build_client(
        settings, [FakeResponse(429), FakeResponse(200, {"puuid": "puuid-a"})]
    )
    client.get_account_by_riot_id("TrendTester", "NA1")
    assert no_sleep.total_slept == pytest.approx(10.0)


def test_429_penalizes_the_shared_limiter(settings, no_sleep):
    client, _ = build_client(
        settings,
        [FakeResponse(429, headers={"Retry-After": "5"}), FakeResponse(200, {"ok": True})],
    )
    client.get_account_by_riot_id("TrendTester", "NA1")
    # The limiter, not just this call, is held back so parallel callers wait too.
    assert client.limiter.wait_for_penalty() == pytest.approx(0.0)
    assert no_sleep.total_slept == pytest.approx(5.0)


def test_server_errors_back_off_exponentially(settings, no_sleep):
    client, _ = build_client(
        settings,
        [FakeResponse(500), FakeResponse(503), FakeResponse(200, {"ok": True})],
    )
    assert client.get_match("NA1_1") == {"ok": True}
    assert len(no_sleep.slept) == 2
    # Full jitter: each delay is bounded by the doubling ceiling.
    assert no_sleep.slept[0] <= 1.0
    assert no_sleep.slept[1] <= 2.0


def test_client_errors_are_not_retried(settings, no_sleep):
    client, session = build_client(settings, [FakeResponse(404, reason="Not Found")])
    with pytest.raises(RiotAPIError) as excinfo:
        client.get_match("NA1_missing")
    assert excinfo.value.status_code == 404
    assert len(session.calls) == 1
    assert no_sleep.slept == []


def test_403_points_at_the_api_key(settings, no_sleep):
    client, _ = build_client(settings, [FakeResponse(403)])
    with pytest.raises(RiotAPIError, match="RIOT_API_KEY"):
        client.get_match("NA1_1")


def test_retries_are_bounded(settings, no_sleep):
    client, session = build_client(
        settings, [FakeResponse(500)] * 4, max_retries=2
    )
    with pytest.raises(RiotAPIError):
        client.get_match("NA1_1")
    assert len(session.calls) == 3  # initial attempt plus two retries


def test_match_ids_are_paged_until_count_is_reached(settings, no_sleep):
    client, session = build_client(
        settings,
        [
            FakeResponse(200, [f"NA1_{i}" for i in range(100)]),
            FakeResponse(200, [f"NA1_{i}" for i in range(100, 120)]),
        ],
    )
    ids = list(client.iter_match_ids("puuid-a", count=120))
    assert len(ids) == 120
    assert session.calls[0][1]["count"] == 100
    assert session.calls[1][1] == {"start": 100, "count": 20}


def test_paging_stops_when_the_history_runs_out(settings, no_sleep):
    client, _ = build_client(settings, [FakeResponse(200, ["NA1_1", "NA1_2"])])
    assert list(client.iter_match_ids("puuid-a", count=50)) == ["NA1_1", "NA1_2"]


def test_match_ids_pass_through_queue_and_start_time(settings, no_sleep):
    client, session = build_client(settings, [FakeResponse(200, [])])
    client.get_match_ids("puuid-a", count=10, queue=420, start_time=1726790000)
    assert session.calls[0][1] == {
        "start": 0,
        "count": 10,
        "queue": 420,
        "startTime": 1726790000,
    }


def test_platform_and_regional_hosts_are_routed_separately(settings, no_sleep):
    client, session = build_client(
        settings, [FakeResponse(200, {}), FakeResponse(200, [])]
    )
    client.get_summoner_by_puuid("puuid-a")
    client.get_match("NA1_1")
    assert session.calls[0][0].startswith("https://na1.api.riotgames.com")
    assert session.calls[1][0].startswith("https://americas.api.riotgames.com")
