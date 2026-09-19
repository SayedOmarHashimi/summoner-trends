import json

import pytest

from viz.plot_trends import (
    METRICS,
    build_payload,
    fmt,
    range_choices,
    render,
)


def rows(n=12):
    return [
        {
            "match_sequence_number": i + 1,
            "champion_name": "Ahri",
            "game_date": "2026-09-01",
            "is_win": i % 2 == 0,
            "rolling_window_matches": 10,
            "cs_per_minute": 5.0 + i * 0.1,
            "cs_per_minute_rolling_avg": 5.2 + i * 0.05,
        }
        for i in range(n)
    ]


@pytest.mark.parametrize(
    "value,kind,expected",
    [
        (0.42, "pct", "42%"),
        (1234.6, "int", "1,235"),
        (6.789, "num", "6.79"),
        (None, "num", "—"),
    ],
)
def test_fmt(value, kind, expected):
    assert fmt(value, kind) == expected


def test_range_choices_only_offers_ranges_the_history_can_fill():
    # 100 matches: "last 100" would be identical to "all", so it is dropped.
    assert range_choices(100) == [10, 20, 50]
    assert range_choices(137) == [10, 20, 50, 100]
    assert range_choices(25) == [10, 20]
    assert range_choices(8) == []


def test_payload_carries_points_and_match_metadata():
    payload = build_payload(rows(), [METRICS[0]])
    assert len(payload["series"]) == 1
    series = payload["series"][0]
    assert series["key"] == "cs_per_minute"
    assert len(series["points"]) == 12
    assert series["points"][0]["x"] == 1
    # Metadata is keyed by match number so the tooltip can name the champion.
    assert payload["meta"][0]["champion"] == "Ahri"
    assert payload["meta"][0]["result"] == "Win"


def test_payload_skips_a_series_with_too_few_points():
    assert build_payload(rows(1), [METRICS[0]])["series"] == []


def test_payload_keeps_a_null_rolling_value():
    # The first matches have no rolling average yet; the gap must survive.
    data = rows()
    data[0]["cs_per_minute_rolling_avg"] = None
    payload = build_payload(data, [METRICS[0]])
    assert payload["series"][0]["points"][0]["roll"] is None


def test_payload_is_json_serialisable():
    json.dumps(build_payload(rows(), [METRICS[0]]))


def test_render_produces_a_standalone_page():
    page = render("TrendTester#NA1", rows(30), [METRICS[0]])
    assert page.startswith("<!DOCTYPE html>")
    assert "prefers-color-scheme: dark" in page
    assert ':root[data-theme="dark"]' in page
    assert 'class="legend"' in page
    assert "View as table" in page
    # Self-contained: nothing is fetched at render time.
    assert "https://" not in page.split("<script>")[0]


def test_render_emits_range_controls_that_fit_the_history():
    page = render("P#NA1", rows(30), [METRICS[0]])
    assert 'data-range="10"' in page
    assert 'data-range="20"' in page
    assert 'data-range="50"' not in page  # only 30 matches exist
    assert 'data-range="all"' in page


def test_render_defaults_to_showing_everything():
    page = render("P#NA1", rows(30), [METRICS[0]])
    assert 'data-range="all" aria-pressed="true"' in page


def test_table_rows_carry_the_sequence_number_for_range_filtering():
    page = render("P#NA1", rows(12), [METRICS[0]])
    assert 'data-seq="1"' in page
    assert 'data-seq="12"' in page


def test_render_escapes_the_player_name():
    page = render("<script>x</script>#NA1", rows(), [METRICS[0]])
    assert "<script>x</script>#NA1" not in page
    assert "&lt;script&gt;" in page
