import pytest

from extraction import transform

MATCH = {
    "metadata": {"matchId": "NA1_5012345678", "dataVersion": "2"},
    "info": {
        "platformId": "NA1",
        "queueId": 420,
        "gameMode": "CLASSIC",
        "gameType": "MATCHED_GAME",
        "mapId": 11,
        "gameVersion": "14.18.615.9137",
        "gameCreation": 1726790000000,
        "gameStartTimestamp": 1726790100000,
        "gameEndTimestamp": 1726791900000,
        "gameDuration": 1800,
        "participants": [
            {
                "puuid": "puuid-a",
                "participantId": 1,
                "teamId": 100,
                "riotIdGameName": "TrendTester",
                "riotIdTagline": "NA1",
                "championId": 103,
                "championName": "Ahri",
                "champLevel": 16,
                "teamPosition": "MIDDLE",
                "kills": 8,
                "deaths": 3,
                "assists": 7,
                "totalDamageDealtToChampions": 24000,
                "goldEarned": 13500,
                "totalMinionsKilled": 210,
                "neutralMinionsKilled": 12,
                "visionScore": 31,
                "timePlayed": 1800,
                "win": True,
            }
        ],
        "teams": [
            {
                "teamId": 100,
                "win": True,
                "objectives": {
                    "baron": {"first": True, "kills": 1},
                    "dragon": {"first": False, "kills": 3},
                    "champion": {"first": True, "kills": 28},
                    "tower": {"first": True, "kills": 9},
                    "inhibitor": {"first": True, "kills": 2},
                    "riftHerald": {"first": False, "kills": 1},
                },
                "bans": [
                    {"championId": 157, "pickTurn": 1},
                    {"championId": -1, "pickTurn": 2},
                ],
            }
        ],
    },
}


def test_match_row_maps_riot_keys_to_staging_columns():
    row = transform.match_row(MATCH, extracted_at="2026-09-19T00:00:00+00:00")
    assert row["match_id"] == "NA1_5012345678"
    assert row["platform_id"] == "NA1"
    assert row["queue_id"] == 420
    assert row["game_version"] == "14.18.615.9137"
    assert row["game_duration"] == 1800
    assert row["_extracted_at"] == "2026-09-19T00:00:00+00:00"


def test_match_row_tolerates_a_missing_end_timestamp():
    match = {"metadata": MATCH["metadata"], "info": dict(MATCH["info"])}
    del match["info"]["gameEndTimestamp"]
    assert transform.match_row(match)["game_end_timestamp"] is None


def test_participant_rows_carry_the_match_id_and_counts():
    rows = transform.participant_rows(MATCH)
    assert len(rows) == 1
    row = rows[0]
    assert row["match_id"] == "NA1_5012345678"
    assert row["puuid"] == "puuid-a"
    assert row["champion_id"] == 103
    assert (row["kills"], row["deaths"], row["assists"]) == (8, 3, 7)
    assert row["total_minions_killed"] == 210
    assert row["neutral_minions_killed"] == 12


def test_participant_rows_default_missing_counts_to_zero():
    # turretTakedowns is absent from the fixture participant.
    assert transform.participant_rows(MATCH)[0]["turret_takedowns"] == 0


def test_team_rows_flatten_the_objectives_block():
    row = transform.team_rows(MATCH)[0]
    assert row["team_id"] == 100
    assert row["baron_kills"] == 1
    assert row["herald_kills"] == 1
    assert row["champion_kills"] == 28
    assert row["first_blood"] is True
    assert row["first_tower"] is True


def test_ban_rows_keep_declined_bans_for_staging_to_filter():
    rows = transform.ban_rows(MATCH)
    assert [r["champion_id"] for r in rows] == [157, -1]


def test_summoner_row_combines_account_and_summoner_payloads():
    row = transform.summoner_row(
        {"puuid": "puuid-a", "gameName": "TrendTester", "tagLine": "NA1"},
        {"summonerLevel": 214, "profileIconId": 4568, "revisionDate": 1726790000000},
        platform="na1",
    )
    assert row["puuid"] == "puuid-a"
    assert row["game_name"] == "TrendTester"
    assert row["platform"] == "na1"
    assert row["summoner_level"] == 214


def test_mastery_rows_default_absent_tokens_to_zero():
    rows = transform.mastery_rows(
        "puuid-a", [{"championId": 103, "championLevel": 7, "championPoints": 250000}]
    )
    assert rows[0]["tokens_earned"] == 0
    assert rows[0]["champion_id"] == 103


@pytest.mark.parametrize(
    "builder", [transform.participant_rows, transform.team_rows, transform.ban_rows]
)
def test_builders_return_empty_for_an_empty_match(builder):
    assert builder({"metadata": {}, "info": {}}) == []
