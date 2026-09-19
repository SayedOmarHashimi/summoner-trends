"""Generate a synthetic raw dataset so CI can run `dbt build` without the API.

CI must not call the Riot API: it would need a key in the repo and would burn
rate limit on every push. Instead this writes deterministic fake match data in
the same shape the extraction layer lands, so every model, test, and snapshot
runs against realistic input.

    python ci/generate_fixtures.py --output data/ci --duckdb ci.duckdb
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extraction.warehouse import connect, load_jsonl, write_jsonl  # noqa: E402

SEED = 20260919
# Champion ids present in seeds/champion_static.csv — the relationship tests
# on dim_champions require fixture champions to exist there.
CHAMPION_IDS = [1, 2, 3, 4, 5, 11, 17, 18, 22, 51, 64, 84, 86, 103, 157, 222, 238, 412, 777, 875]
POSITIONS = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
QUEUES = [420, 440]
# ARAM is deliberately outside included_queue_ids, so fixtures carry a few to
# prove the queue filter is applied consistently across the marts.
EXCLUDED_QUEUE = 450
PATCHES = ["14.17.600.1234", "14.18.615.9137"]

TRACKED = [
    {"puuid": "puuid-tracked-0001", "game_name": "TrendTester", "tag_line": "NA1", "level": 214},
    {"puuid": "puuid-tracked-0002", "game_name": "SecondSmurf", "tag_line": "NA2", "level": 67},
]


def build(matches_per_player: int = 14) -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    extracted_at = datetime(2026, 9, 19, tzinfo=timezone.utc).isoformat()

    matches, participants, teams, bans, mastery = [], [], [], [], []
    base_time = datetime(2026, 8, 1, tzinfo=timezone.utc)
    match_counter = 0

    for player_index, player in enumerate(TRACKED):
        for n in range(matches_per_player):
            match_counter += 1
            match_id = f"NA1_{5000000000 + match_counter}"
            started = base_time + timedelta(days=n, hours=player_index * 3)

            # A couple of short games so the remake filter has something to drop.
            duration = 240 if n == 3 else rng.randint(1200, 2400)
            early_surrender = duration < 300
            winning_team = rng.choice([100, 200])

            matches.append(
                {
                    "match_id": match_id,
                    "data_version": "2",
                    "platform_id": "NA1",
                    "queue_id": EXCLUDED_QUEUE if n % 7 == 6 else rng.choice(QUEUES),
                    "game_mode": "CLASSIC",
                    "game_type": "MATCHED_GAME",
                    "map_id": 11,
                    "game_version": PATCHES[n % len(PATCHES)],
                    "game_creation": int(started.timestamp() * 1000),
                    "game_start_timestamp": int(started.timestamp() * 1000),
                    "game_end_timestamp": int((started + timedelta(seconds=duration)).timestamp() * 1000),
                    "game_duration": duration,
                    "_extracted_at": extracted_at,
                }
            )

            champion_pool = rng.sample(CHAMPION_IDS, 10)

            # Kills first, so assists can respect the real invariant: a player
            # earns at most one kill OR one assist per team kill, which keeps
            # kill participation inside [0, 1] the way live data does.
            slot_kills = [rng.randint(0, 14) for _ in range(10)]
            team_kill_totals = {
                100: sum(slot_kills[:5]),
                200: sum(slot_kills[5:]),
            }

            for slot in range(10):
                team_id = 100 if slot < 5 else 200
                is_tracked = slot == player_index
                puuid = player["puuid"] if is_tracked else f"puuid-other-{match_counter}-{slot}"
                kills = slot_kills[slot]
                max_assists = max(0, team_kill_totals[team_id] - kills)

                participants.append(
                    {
                        "match_id": match_id,
                        "puuid": puuid,
                        "participant_id": slot + 1,
                        "team_id": team_id,
                        "riot_id_game_name": player["game_name"] if is_tracked else f"Player{slot}",
                        "riot_id_tagline": player["tag_line"] if is_tracked else "NA1",
                        "champion_id": champion_pool[slot],
                        "champion_name": f"Champion{champion_pool[slot]}",
                        "champ_level": rng.randint(9, 18),
                        "team_position": POSITIONS[slot % 5],
                        "individual_position": POSITIONS[slot % 5],
                        "lane": POSITIONS[slot % 5],
                        "role": "SOLO",
                        "kills": kills,
                        "deaths": rng.randint(0, 11),
                        "assists": rng.randint(0, min(22, max_assists)),
                        "total_damage_dealt_to_champions": rng.randint(4000, 42000),
                        "total_damage_taken": rng.randint(6000, 48000),
                        "damage_dealt_to_objectives": rng.randint(0, 22000),
                        "total_heal": rng.randint(0, 14000),
                        "gold_earned": rng.randint(6000, 19000),
                        "gold_spent": rng.randint(5000, 18000),
                        "total_minions_killed": rng.randint(20, 280),
                        "neutral_minions_killed": rng.randint(0, 130),
                        "vision_score": rng.randint(8, 90),
                        "wards_placed": rng.randint(2, 40),
                        "wards_killed": rng.randint(0, 18),
                        "vision_wards_bought_in_game": rng.randint(0, 7),
                        "turret_takedowns": rng.randint(0, 6),
                        "dragon_kills": rng.randint(0, 3),
                        "baron_kills": rng.randint(0, 2),
                        "time_played": duration,
                        "win": team_id == winning_team,
                        "game_ended_in_early_surrender": early_surrender,
                        "game_ended_in_surrender": False,
                        "_extracted_at": extracted_at,
                    }
                )

            for team_id in (100, 200):
                teams.append(
                    {
                        "match_id": match_id,
                        "team_id": team_id,
                        "win": team_id == winning_team,
                        "baron_kills": rng.randint(0, 2),
                        "dragon_kills": rng.randint(0, 4),
                        "herald_kills": rng.randint(0, 2),
                        "tower_kills": rng.randint(0, 11),
                        "inhibitor_kills": rng.randint(0, 3),
                        "champion_kills": team_kill_totals[team_id],
                        "first_blood": team_id == 100,
                        "first_tower": team_id == winning_team,
                        "_extracted_at": extracted_at,
                    }
                )
                # Five bans a side, with one declined ban (-1) to exercise the filter.
                for turn, champion_id in enumerate(rng.sample(CHAMPION_IDS, 5), start=1):
                    bans.append(
                        {
                            "match_id": match_id,
                            "team_id": team_id,
                            "champion_id": -1 if (turn == 5 and team_id == 200) else champion_id,
                            "pick_turn": turn + (0 if team_id == 100 else 5),
                            "_extracted_at": extracted_at,
                        }
                    )

        for champion_id in rng.sample(CHAMPION_IDS, 8):
            mastery.append(
                {
                    "puuid": player["puuid"],
                    "champion_id": champion_id,
                    "champion_level": rng.randint(1, 7),
                    "champion_points": rng.randint(1000, 400000),
                    "tokens_earned": rng.randint(0, 2),
                    "last_play_time": int(base_time.timestamp() * 1000),
                    "_extracted_at": extracted_at,
                }
            )

    summoners = [
        {
            "puuid": player["puuid"],
            "game_name": player["game_name"],
            "tag_line": player["tag_line"],
            "platform": "na1",
            "summoner_level": player["level"],
            "profile_icon_id": 4568,
            "revision_date": int(base_time.timestamp() * 1000),
            "_extracted_at": extracted_at,
        }
        for player in TRACKED
    ]

    return {
        "raw_matches": matches,
        "raw_match_participants": participants,
        "raw_match_teams": teams,
        "raw_match_bans": bans,
        "raw_summoners": summoners,
        "raw_champion_mastery": mastery,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/ci"))
    parser.add_argument("--duckdb", type=Path, default=Path("ci.duckdb"))
    parser.add_argument("--matches-per-player", type=int, default=14)
    args = parser.parse_args(argv)

    rows = build(args.matches_per_player)
    con = connect(args.duckdb)
    try:
        for table, table_rows in rows.items():
            path = write_jsonl(table_rows, args.output / f"{table}.jsonl")
            load_jsonl(con, table, path)
    finally:
        con.close()

    print(f"Fixture warehouse ready at {args.duckdb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
