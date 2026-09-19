"""Flattens Riot API JSON into the flat rows the raw DuckDB tables expect.

Nothing is cleaned or derived here — casting and renaming are dbt's job in the
staging layer. This module only unnests the JSON and maps camelCase keys to the
snake_case column names the staging models read.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def match_row(match: dict[str, Any], extracted_at: str | None = None) -> dict[str, Any]:
    """One row for `raw_matches`."""
    metadata = match.get("metadata", {})
    info = match.get("info", {})
    return {
        "match_id": metadata.get("matchId"),
        "data_version": metadata.get("dataVersion"),
        "platform_id": info.get("platformId"),
        "queue_id": info.get("queueId"),
        "game_mode": info.get("gameMode"),
        "game_type": info.get("gameType"),
        "map_id": info.get("mapId"),
        "game_version": info.get("gameVersion"),
        "game_creation": info.get("gameCreation"),
        "game_start_timestamp": info.get("gameStartTimestamp"),
        # Absent on some older matches.
        "game_end_timestamp": info.get("gameEndTimestamp"),
        "game_duration": info.get("gameDuration"),
        "_extracted_at": extracted_at or _now(),
    }


# Participant fields kept, as (riot_key, column_name).
_PARTICIPANT_FIELDS: tuple[tuple[str, str], ...] = (
    ("puuid", "puuid"),
    ("participantId", "participant_id"),
    ("teamId", "team_id"),
    ("riotIdGameName", "riot_id_game_name"),
    ("riotIdTagline", "riot_id_tagline"),
    ("championId", "champion_id"),
    ("championName", "champion_name"),
    ("champLevel", "champ_level"),
    ("teamPosition", "team_position"),
    ("individualPosition", "individual_position"),
    ("lane", "lane"),
    ("role", "role"),
    ("kills", "kills"),
    ("deaths", "deaths"),
    ("assists", "assists"),
    ("totalDamageDealtToChampions", "total_damage_dealt_to_champions"),
    ("totalDamageTaken", "total_damage_taken"),
    ("damageDealtToObjectives", "damage_dealt_to_objectives"),
    ("totalHeal", "total_heal"),
    ("goldEarned", "gold_earned"),
    ("goldSpent", "gold_spent"),
    ("totalMinionsKilled", "total_minions_killed"),
    ("neutralMinionsKilled", "neutral_minions_killed"),
    ("visionScore", "vision_score"),
    ("wardsPlaced", "wards_placed"),
    ("wardsKilled", "wards_killed"),
    ("visionWardsBoughtInGame", "vision_wards_bought_in_game"),
    ("turretTakedowns", "turret_takedowns"),
    ("dragonKills", "dragon_kills"),
    ("baronKills", "baron_kills"),
    ("timePlayed", "time_played"),
    ("win", "win"),
    ("gameEndedInEarlySurrender", "game_ended_in_early_surrender"),
    ("gameEndedInSurrender", "game_ended_in_surrender"),
)

# Counts default to 0; everything else defaults to None.
_NUMERIC_DEFAULTS = frozenset(
    column
    for _, column in _PARTICIPANT_FIELDS
    if column.endswith(("kills", "deaths", "assists", "score", "placed", "takedowns"))
)


def participant_rows(
    match: dict[str, Any], extracted_at: str | None = None
) -> list[dict[str, Any]]:
    """One row per participant for `raw_match_participants`."""
    extracted_at = extracted_at or _now()
    match_id = match.get("metadata", {}).get("matchId")
    rows = []
    for participant in match.get("info", {}).get("participants", []):
        row: dict[str, Any] = {"match_id": match_id}
        for riot_key, column in _PARTICIPANT_FIELDS:
            default = 0 if column in _NUMERIC_DEFAULTS else None
            row[column] = participant.get(riot_key, default)
        row["_extracted_at"] = extracted_at
        rows.append(row)
    return rows


def team_rows(
    match: dict[str, Any], extracted_at: str | None = None
) -> list[dict[str, Any]]:
    """One row per team for `raw_match_teams`."""
    extracted_at = extracted_at or _now()
    match_id = match.get("metadata", {}).get("matchId")
    rows = []
    for team in match.get("info", {}).get("teams", []):
        objectives = team.get("objectives", {})

        def objective(name: str, field: str = "kills", default: Any = 0) -> Any:
            return objectives.get(name, {}).get(field, default)

        rows.append(
            {
                "match_id": match_id,
                "team_id": team.get("teamId"),
                "win": team.get("win"),
                "baron_kills": objective("baron"),
                "dragon_kills": objective("dragon"),
                "herald_kills": objective("riftHerald"),
                "tower_kills": objective("tower"),
                "inhibitor_kills": objective("inhibitor"),
                "champion_kills": objective("champion"),
                "first_blood": objective("champion", "first", False),
                "first_tower": objective("tower", "first", False),
                "_extracted_at": extracted_at,
            }
        )
    return rows


def ban_rows(
    match: dict[str, Any], extracted_at: str | None = None
) -> list[dict[str, Any]]:
    """One row per ban for `raw_match_bans`."""
    extracted_at = extracted_at or _now()
    match_id = match.get("metadata", {}).get("matchId")
    rows = []
    for team in match.get("info", {}).get("teams", []):
        for ban in team.get("bans", []) or []:
            rows.append(
                {
                    "match_id": match_id,
                    "team_id": team.get("teamId"),
                    "champion_id": ban.get("championId"),
                    "pick_turn": ban.get("pickTurn"),
                    "_extracted_at": extracted_at,
                }
            )
    return rows


def summoner_row(
    account: dict[str, Any],
    summoner: dict[str, Any],
    platform: str,
    extracted_at: str | None = None,
) -> dict[str, Any]:
    """One row for `raw_summoners`, combining Account-V1 and Summoner-V4."""
    return {
        "puuid": account.get("puuid") or summoner.get("puuid"),
        "game_name": account.get("gameName"),
        "tag_line": account.get("tagLine"),
        "platform": platform,
        "summoner_level": summoner.get("summonerLevel"),
        "profile_icon_id": summoner.get("profileIconId"),
        "revision_date": summoner.get("revisionDate"),
        "_extracted_at": extracted_at or _now(),
    }


def mastery_rows(
    puuid: str, entries: list[dict[str, Any]], extracted_at: str | None = None
) -> list[dict[str, Any]]:
    """One row per champion for `raw_champion_mastery`."""
    extracted_at = extracted_at or _now()
    return [
        {
            "puuid": puuid,
            "champion_id": entry.get("championId"),
            "champion_level": entry.get("championLevel"),
            "champion_points": entry.get("championPoints"),
            "tokens_earned": entry.get("tokensEarned", 0),
            "last_play_time": entry.get("lastPlayTime"),
            "_extracted_at": extracted_at,
        }
        for entry in entries
    ]
