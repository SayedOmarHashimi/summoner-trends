"""HTTP client for the official Riot Games API.

Covers only documented endpoints:

  * Account-V1            /riot/account/v1/accounts/by-riot-id/{name}/{tag}
  * Summoner-V4           /lol/summoner/v4/summoners/by-puuid/{puuid}
  * Match-V5              /lol/match/v5/matches/by-puuid/{puuid}/ids
                          /lol/match/v5/matches/{matchId}
  * Champion-Mastery-V4   /lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}

Retry policy:
  * 429  — honour Retry-After exactly; that header is authoritative.
  * 5xx  — exponential backoff with jitter, since these are usually transient.
  * 4xx  — raised immediately; retrying a bad request just burns rate limit.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Iterable

import requests

from .config import Settings
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Retried on: transient server-side problems and gateway hiccups.
RETRYABLE_STATUS = frozenset({500, 502, 503, 504})

DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_BASE = 1.0
DEFAULT_BACKOFF_CAP = 60.0
DEFAULT_TIMEOUT = 15.0

# If a 429 arrives without Retry-After (shouldn't happen, but don't crash).
FALLBACK_RETRY_AFTER = 10.0


class RiotAPIError(RuntimeError):
    """A Riot API request failed in a way that is not worth retrying."""

    def __init__(self, status_code: int, url: str, message: str) -> None:
        super().__init__(f"{status_code} from {url}: {message}")
        self.status_code = status_code
        self.url = url


class RiotClient:
    """Rate-limited, retrying client for the Riot API."""

    def __init__(
        self,
        settings: Settings,
        rate_limiter: RateLimiter | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.limiter = rate_limiter or RateLimiter()
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = session or requests.Session()
        # The key travels in a header, never in the URL, so it cannot end up in
        # logs, proxy access logs, or an exception message containing the URL.
        self.session.headers.update(
            {
                "X-Riot-Token": settings.api_key,
                "Accept": "application/json",
                "User-Agent": "summoner-trends (personal portfolio project)",
            }
        )

    # ---------------------------------------------------------------- core

    def _request(
        self,
        host: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{host}{path}"

        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()

            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise RiotAPIError(0, url, f"network error: {exc}") from exc
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "Network error on %s (attempt %d/%d): %s — retrying in %.1fs",
                    path, attempt + 1, self.max_retries, exc, delay,
                )
                time.sleep(delay)
                continue

            if response.status_code == 200:
                return response.json()

            if response.status_code == 429:
                retry_after = self._retry_after_seconds(response)
                limit_type = response.headers.get("X-Rate-Limit-Type", "unknown")
                # Hand the wait to the limiter rather than sleeping here: it
                # holds back every caller sharing it, not just this one, and
                # keeps a single source of truth for when we may send again.
                # The next acquire() at the top of the loop does the waiting.
                self.limiter.penalize(retry_after)
                if attempt >= self.max_retries:
                    raise RiotAPIError(
                        429, url, f"rate limited ({limit_type}) after {attempt + 1} attempts"
                    )
                logger.warning(
                    "Rate limited (%s) on %s — backing off %.1fs as instructed by Retry-After",
                    limit_type, path, retry_after,
                )
                continue

            if response.status_code in RETRYABLE_STATUS:
                if attempt >= self.max_retries:
                    raise RiotAPIError(
                        response.status_code, url, "server error, retries exhausted"
                    )
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "Server error %d on %s (attempt %d/%d) — retrying in %.1fs",
                    response.status_code, path, attempt + 1, self.max_retries, delay,
                )
                time.sleep(delay)
                continue

            if response.status_code == 401 or response.status_code == 403:
                raise RiotAPIError(
                    response.status_code,
                    url,
                    "unauthorized — check RIOT_API_KEY. A Development key expires "
                    "24 hours after it is issued; a Personal or Production key does "
                    "not, but can be revoked or regenerated on the developer portal",
                )

            raise RiotAPIError(response.status_code, url, response.reason or "request failed")

        raise RiotAPIError(0, url, "retry loop exited without a response")

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped."""
        ceiling = min(DEFAULT_BACKOFF_CAP, DEFAULT_BACKOFF_BASE * (2 ** attempt))
        return random.uniform(0, ceiling)

    @staticmethod
    def _retry_after_seconds(response: requests.Response) -> float:
        raw = response.headers.get("Retry-After")
        if raw is None:
            return FALLBACK_RETRY_AFTER
        try:
            # Riot sends Retry-After in whole seconds.
            return max(0.0, float(raw))
        except ValueError:
            logger.warning("Could not parse Retry-After %r — falling back", raw)
            return FALLBACK_RETRY_AFTER

    # ----------------------------------------------------------- endpoints

    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> dict[str, Any]:
        """Account-V1. Returns puuid, gameName, tagLine."""
        return self._request(
            self.settings.regional_host,
            f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}",
        )

    def get_summoner_by_puuid(self, puuid: str) -> dict[str, Any]:
        """Summoner-V4. Returns summoner level, profile icon, revision date."""
        return self._request(
            self.settings.platform_host,
            f"/lol/summoner/v4/summoners/by-puuid/{puuid}",
        )

    def get_match_ids(
        self,
        puuid: str,
        count: int = 20,
        start: int = 0,
        queue: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[str]:
        """Match-V5 match id list. The API caps `count` at 100 per call."""
        params: dict[str, Any] = {"start": start, "count": min(count, 100)}
        if queue is not None:
            params["queue"] = queue
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return self._request(
            self.settings.regional_host,
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
            params=params,
        )

    def iter_match_ids(
        self,
        puuid: str,
        count: int,
        queue: int | None = None,
        start_time: int | None = None,
    ) -> Iterable[str]:
        """Page through match ids until `count` are yielded or the history ends."""
        fetched = 0
        start = 0
        while fetched < count:
            page_size = min(100, count - fetched)
            page = self.get_match_ids(
                puuid,
                count=page_size,
                start=start,
                queue=queue,
                start_time=start_time,
            )
            if not page:
                return
            for match_id in page:
                yield match_id
                fetched += 1
            start += len(page)
            if len(page) < page_size:
                return

    def get_match(self, match_id: str) -> dict[str, Any]:
        """Match-V5 full match detail."""
        return self._request(
            self.settings.regional_host,
            f"/lol/match/v5/matches/{match_id}",
        )

    def get_champion_mastery(self, puuid: str) -> list[dict[str, Any]]:
        """Champion-Mastery-V4. One entry per champion the player has played."""
        return self._request(
            self.settings.platform_host,
            f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}",
        )
