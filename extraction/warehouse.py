"""Loads landed JSONL into the local DuckDB warehouse.

Extraction lands one newline-delimited JSON file per raw table, then DuckDB
reads those files directly. Keeping the landed files means a load can be
replayed without re-hitting the API — which matters when a Personal key only
allows 100 requests per 2 minutes.

Loads are idempotent: rows whose natural key is present in the incoming file
are deleted before the insert, so re-running an extraction updates rather than
duplicates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence

import duckdb

logger = logging.getLogger(__name__)

# Natural key per raw table, used to delete-then-insert on reload.
TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "raw_matches": ("match_id",),
    "raw_match_participants": ("match_id", "puuid"),
    "raw_match_teams": ("match_id", "team_id"),
    "raw_match_bans": ("match_id", "team_id", "champion_id"),
    "raw_summoners": ("puuid",),
    "raw_champion_mastery": ("puuid", "champion_id"),
}


def write_jsonl(rows: Sequence[dict[str, Any]], path: Path) -> Path:
    """Land `rows` as newline-delimited JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    logger.info("Wrote %d rows to %s.", len(rows), path)
    return path


def connect(duckdb_path: Path) -> duckdb.DuckDBPyConnection:
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(duckdb_path))


def load_jsonl(
    con: duckdb.DuckDBPyConnection,
    table: str,
    path: Path,
) -> int:
    """Load a landed JSONL file into `table`, replacing rows with matching keys."""
    if not path.exists() or path.stat().st_size == 0:
        logger.info("Nothing landed for %s — skipping.", table)
        return 0

    source = "read_json_auto(?, format='newline_delimited', union_by_name=true)"
    file_arg = [str(path)]

    con.execute(
        f'create table if not exists "{table}" as '
        f"select * from {source} limit 0",
        file_arg,
    )

    keys = TABLE_KEYS.get(table)
    if keys:
        predicate = " and ".join(f't."{k}" = i."{k}"' for k in keys)
        con.execute(
            f'delete from "{table}" t where exists '
            f"(select 1 from {source} i where {predicate})",
            file_arg,
        )

    # BY NAME so a column added to a later extraction does not shift the insert.
    con.execute(
        f'insert into "{table}" by name select * from {source}',
        file_arg,
    )

    loaded = con.execute(f'select count(*) from "{table}"').fetchone()[0]
    logger.info("Loaded %s — %d rows now in table.", path.name, loaded)
    return loaded
