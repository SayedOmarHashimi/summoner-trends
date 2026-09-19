import pytest

from viz.plot_trends import METRICS, build_panel, fmt, nice_bounds, render


def rows(n=12):
    return [
        {
            "match_sequence_number": i + 1,
            "match_id": f"NA1_{i}",
            "champion_name": "Ahri",
            "queue_id": 420,
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


def test_nice_bounds_never_goes_below_zero():
    # Rates cannot be negative, so padding must not invent a negative floor.
    lo, _ = nice_bounds([0.1, 0.4, 0.9])
    assert lo >= 0.0


def test_nice_bounds_handles_a_flat_series():
    lo, hi = nice_bounds([3.0, 3.0, 3.0])
    assert hi > lo


def test_panel_draws_both_series():
    svg = build_panel("cs_per_minute", "CS per minute", "num", rows())
    assert 'class="series-raw"' in svg
    assert 'class="series-roll"' in svg
    assert "data-panel=" in svg


def test_panel_is_skipped_when_there_is_nothing_to_plot():
    assert build_panel("cs_per_minute", "CS per minute", "num", rows(1)) == ""


def test_panel_tolerates_a_missing_rolling_value():
    data = rows()
    data[0]["cs_per_minute_rolling_avg"] = None
    assert 'class="series-roll"' in build_panel("cs_per_minute", "CS", "num", data)


def test_render_produces_a_standalone_page_with_both_themes():
    page = render("TrendTester#NA1", rows(), [METRICS[0]])
    assert page.startswith("<!DOCTYPE html>")
    # Dark mode is declared under both the OS query and the explicit toggle.
    assert "prefers-color-scheme: dark" in page
    assert ':root[data-theme="dark"]' in page
    # A legend and a table view both exist: identity is never colour-alone.
    assert 'class="legend"' in page
    assert "View as table" in page
    # No external requests — the page must work offline.
    assert "https://" not in page.split("<script>")[0].replace("http-equiv", "")


def test_render_escapes_the_player_name():
    page = render("<script>x</script>#NA1", rows(), [METRICS[0]])
    assert "<script>x</script>#NA1" not in page
    assert "&lt;script&gt;" in page
