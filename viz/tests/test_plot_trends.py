import json

import pytest

from viz.plot_trends import (
    METRICS,
    MIN_CHAMPION_GAMES,
    build_payload,
    fmt,
    range_choices,
    render,
)


def overall(n=12):
    """Rows as fct_player_rolling_trends returns them: seq is the match number."""
    return [
        {
            "seq": i + 1,
            "match_sequence_number": i + 1,
            "champion_name": "Ahri" if i % 2 else "Garen",
            "game_date": "2026-09-01",
            "is_win": i % 2 == 0,
            "rolling_window_matches": 10,
            "cs_per_minute": 5.0 + i * 0.1,
            "cs_per_minute_rolling_avg": 5.2 + i * 0.05,
        }
        for i in range(n)
    ]


def champions(counts):
    """Rows as fct_player_champion_trends returns them: seq counts that champion."""
    rows = []
    match_no = 0
    for name, n in counts.items():
        for i in range(n):
            match_no += 1
            rows.append(
                {
                    "seq": i + 1,
                    "match_sequence_number": match_no,
                    "champion_name": name,
                    "game_date": "2026-09-01",
                    "is_win": True,
                    "rolling_window_matches": 10,
                    "player_champion_match_count": n,
                    "cs_per_minute": 6.0 + i * 0.1,
                    "cs_per_minute_rolling_avg": 6.1 + i * 0.05,
                }
            )
    return rows


@pytest.mark.parametrize(
    "value,kind,expected",
    [(0.42, "pct", "42%"), (1234.6, "int", "1,235"), (6.789, "num", "6.79"), (None, "num", "—")],
)
def test_fmt(value, kind, expected):
    assert fmt(value, kind) == expected


def test_range_choices_only_offers_ranges_the_history_can_fill():
    assert range_choices(100) == [10, 20, 50]
    assert range_choices(137) == [10, 20, 50, 100]
    assert range_choices(8) == []


def test_payload_always_carries_the_overall_dataset():
    payload = build_payload(overall(), [], [METRICS[0]])
    assert payload["datasets"]["all"]["total"] == 12
    assert payload["champions"] == []


def test_champions_need_enough_games_to_appear():
    rows = champions({"Ahri": MIN_CHAMPION_GAMES, "Zed": MIN_CHAMPION_GAMES - 1})
    payload = build_payload(overall(), rows, [METRICS[0]])
    keys = [c["key"] for c in payload["champions"]]
    assert "Ahri" in keys
    # Too few games for a rolling average to describe anything.
    assert "Zed" not in keys
    assert "Zed" not in payload["datasets"]


def test_champions_are_ordered_by_games_played():
    rows = champions({"Ahri": 6, "Garen": 11, "Zed": 8})
    payload = build_payload(overall(), rows, [METRICS[0]])
    assert [c["key"] for c in payload["champions"]] == ["Garen", "Zed", "Ahri"]
    assert [c["games"] for c in payload["champions"]] == [11, 8, 6]


def test_champion_dataset_counts_games_on_that_champion():
    rows = champions({"Ahri": 7})
    payload = build_payload(overall(), rows, [METRICS[0]])
    points = payload["datasets"]["Ahri"]["series"][0]["points"]
    # x restarts at 1 per champion rather than carrying the overall match number.
    assert [p["x"] for p in points] == [1, 2, 3, 4, 5, 6, 7]
    # The overall match number is still available for the tooltip.
    assert payload["datasets"]["Ahri"]["meta"][0]["seq"] >= 1


def test_payload_keeps_a_null_rolling_value():
    data = overall()
    data[0]["cs_per_minute_rolling_avg"] = None
    payload = build_payload(data, [], [METRICS[0]])
    assert payload["datasets"]["all"]["series"][0]["points"][0]["roll"] is None


def test_payload_is_json_serialisable():
    json.dumps(build_payload(overall(), champions({"Ahri": 6}), [METRICS[0]]))


def test_render_produces_a_standalone_page():
    page = render("TrendTester#NA1", overall(30), [], [METRICS[0]])
    assert page.startswith("<!DOCTYPE html>")
    assert "prefers-color-scheme: dark" in page
    assert ':root[data-theme="dark"]' in page
    assert 'class="legend"' in page
    assert "View as table" in page
    assert "https://" not in page.split("<script>")[0]


def test_render_lists_champions_in_the_picker():
    page = render("P#NA1", overall(30), champions({"Ahri": 9}), [METRICS[0]])
    assert '<option value="all">All champions</option>' in page
    assert "Ahri (9 games)" in page


def test_table_rows_carry_champion_and_sequence_for_filtering():
    page = render("P#NA1", overall(12), [], [METRICS[0]])
    assert 'data-seq="1"' in page
    assert 'data-champion="Garen"' in page


def test_render_escapes_the_player_name():
    page = render("<script>x</script>#NA1", overall(), [], [METRICS[0]])
    assert "<script>x</script>#NA1" not in page
    assert "&lt;script&gt;" in page


def test_render_escapes_a_champion_name_in_the_picker():
    rows = champions({"<img src=x onerror=alert(1)>": 6})
    page = render("P#NA1", overall(), rows, [METRICS[0]])
    assert "<img src=x" not in page


def test_embedded_json_cannot_break_out_of_the_script_block():
    # json.dumps leaves `<` alone, so an unescaped name could close the tag.
    rows = champions({"</script><script>alert(1)</script>": 6})
    page = render("P#NA1", overall(), rows, [METRICS[0]])
    script = page[page.rindex("<script>") + len("<script>"):]
    assert "</script>" not in script[: script.rindex("</script>")]
    assert "\\u003c" in script
