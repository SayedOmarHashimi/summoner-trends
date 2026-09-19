"""Refresh the champion seed from Data Dragon.

Data Dragon is Riot's official static data CDN and needs no API key. Run this
after a patch, then commit the regenerated seed so `dbt build` works offline:

    python -m extraction.fetch_static_data
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

import requests

from .config import PROJECT_ROOT

logger = logging.getLogger("extraction.fetch_static_data")

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
CHAMPIONS_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/{locale}/champion.json"

SEED_PATH = PROJECT_ROOT / "seeds" / "champion_static.csv"
FIELDNAMES = [
    "champion_id",
    "champion_key",
    "champion_name",
    "champion_title",
    "primary_role",
    "secondary_role",
    "resource_type",
    "data_dragon_version",
]


def latest_version(session: requests.Session) -> str:
    response = session.get(VERSIONS_URL, timeout=15)
    response.raise_for_status()
    return response.json()[0]


def fetch_champions(session: requests.Session, version: str, locale: str) -> list[dict]:
    response = session.get(CHAMPIONS_URL.format(version=version, locale=locale), timeout=30)
    response.raise_for_status()
    payload = response.json()["data"]

    rows = []
    for champion in payload.values():
        tags = champion.get("tags") or []
        rows.append(
            {
                "champion_id": int(champion["key"]),
                "champion_key": champion["id"],
                "champion_name": champion["name"],
                "champion_title": champion.get("title", ""),
                "primary_role": tags[0] if tags else "",
                "secondary_role": tags[1] if len(tags) > 1 else "",
                "resource_type": champion.get("partype", ""),
                "data_dragon_version": version,
            }
        )
    rows.sort(key=lambda row: row["champion_id"])
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Data Dragon version (default: latest).")
    parser.add_argument("--locale", default="en_US", help="Locale (default: en_US).")
    parser.add_argument("--output", type=Path, default=SEED_PATH)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    session = requests.Session()
    session.headers.update({"User-Agent": "summoner-trends (personal portfolio project)"})

    try:
        version = args.version or latest_version(session)
        logger.info("Using Data Dragon version %s.", version)
        rows = fetch_champions(session, version, args.locale)
    except requests.RequestException as exc:
        logger.error("Data Dragon request failed: %s", exc)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Wrote %d champions to %s.", len(rows), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
