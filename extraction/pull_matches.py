"""Pull a player's match history from the Riot API and land it for dbt.

    python -m extraction.pull_matches --count 100 --queue 420

Flow:
    Account-V1          Riot ID -> PUUID
    Summoner-V4         PUUID   -> summoner level, profile
    Match-V5            PUUID   -> match ids -> full match detail
    Champion-Mastery-V4 PUUID   -> mastery per champion

Every call goes through the shared rate limiter (20 req/s and 100 req/2min for
a Personal key) and retries 429s using the Retry-After header the API sends.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import transform
from .config import ConfigError, Settings, load_settings, split_riot_id
from .rate_limiter import RateLimiter
from .riot_client import RiotAPIError, RiotClient
from .warehouse import connect, load_jsonl, write_jsonl

logger = logging.getLogger("extraction.pull_matches")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull League of Legends match data from the Riot API.",
    )
    parser.add_argument(
        "--riot-id",
        help="Riot ID to pull, as gameName#tagLine. Defaults to RIOT_ID in .env.",
    )
    parser.add_argument(
        "--count", type=int, default=20,
        help="How many matches to fetch, newest first (default: 20).",
    )
    parser.add_argument(
        "--queue", type=int, default=None,
        help="Restrict to a queue id, e.g. 420 for ranked solo/duo.",
    )
    parser.add_argument(
        "--start-time", type=int, default=None,
        help="Only matches started after this epoch second.",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Directory to land raw JSONL in (default: RAW_DATA_DIR).",
    )
    parser.add_argument(
        "--no-load", action="store_true",
        help="Land raw JSONL but skip the DuckDB load.",
    )
    parser.add_argument(
        "--no-mastery", action="store_true",
        help="Skip the Champion-Mastery-V4 call.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Log every request, including rate limiter waits.",
    )
    return parser.parse_args(argv)


def pull(
    client: RiotClient,
    settings: Settings,
    riot_id: str,
    count: int,
    queue: int | None = None,
    start_time: int | None = None,
    include_mastery: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch everything for one account and return rows keyed by raw table."""
    extracted_at = datetime.now(timezone.utc).isoformat()
    game_name, tag_line = split_riot_id(riot_id)

    logger.info("Resolving Riot ID %s via Account-V1...", riot_id)
    account = client.get_account_by_riot_id(game_name, tag_line)
    puuid = account["puuid"]

    logger.info("Fetching summoner profile via Summoner-V4...")
    summoner = client.get_summoner_by_puuid(puuid)

    logger.info("Listing up to %d match ids via Match-V5...", count)
    match_ids = list(
        client.iter_match_ids(puuid, count=count, queue=queue, start_time=start_time)
    )
    logger.info("Found %d match ids.", len(match_ids))

    matches: list[dict[str, Any]] = []
    participants: list[dict[str, Any]] = []
    teams: list[dict[str, Any]] = []
    bans: list[dict[str, Any]] = []

    for index, match_id in enumerate(match_ids, start=1):
        try:
            match = client.get_match(match_id)
        except RiotAPIError as exc:
            # A single unreadable match shouldn't sink the whole run.
            logger.error("Skipping %s: %s", match_id, exc)
            continue

        matches.append(transform.match_row(match, extracted_at))
        participants.extend(transform.participant_rows(match, extracted_at))
        teams.extend(transform.team_rows(match, extracted_at))
        bans.extend(transform.ban_rows(match, extracted_at))

        if index % 10 == 0 or index == len(match_ids):
            used = ", ".join(
                f"{u}/{lim} per {sec:g}s" for u, lim, sec in client.limiter.snapshot()
            )
            logger.info("Fetched %d/%d matches (rate limit: %s).", index, len(match_ids), used)

    rows: dict[str, list[dict[str, Any]]] = {
        "raw_matches": matches,
        "raw_match_participants": participants,
        "raw_match_teams": teams,
        "raw_match_bans": bans,
        "raw_summoners": [
            transform.summoner_row(account, summoner, settings.region, extracted_at)
        ],
    }

    if include_mastery:
        logger.info("Fetching champion mastery via Champion-Mastery-V4...")
        mastery = client.get_champion_mastery(puuid)
        rows["raw_champion_mastery"] = transform.mastery_rows(puuid, mastery, extracted_at)

    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        settings = load_settings()
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2

    riot_id = args.riot_id or settings.riot_id
    if not riot_id:
        logger.error(
            "No Riot ID given. Pass --riot-id gameName#tagLine or set RIOT_ID in .env."
        )
        return 2

    client = RiotClient(settings, rate_limiter=RateLimiter())

    try:
        rows = pull(
            client,
            settings,
            riot_id=riot_id,
            count=args.count,
            queue=args.queue,
            start_time=args.start_time,
            include_mastery=not args.no_mastery,
        )
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2
    except RiotAPIError as exc:
        logger.error("Extraction failed: %s", exc)
        return 1

    output_dir = args.output or settings.raw_data_dir
    landed: dict[str, Path] = {}
    for table, table_rows in rows.items():
        landed[table] = write_jsonl(table_rows, output_dir / f"{table}.jsonl")

    if args.no_load:
        logger.info("Landed raw JSONL in %s (--no-load, skipping DuckDB).", output_dir)
        return 0

    con = connect(settings.duckdb_path)
    try:
        for table, path in landed.items():
            load_jsonl(con, table, path)
    finally:
        con.close()

    logger.info("Done. Run `dbt build --profiles-dir .` to rebuild the models.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
