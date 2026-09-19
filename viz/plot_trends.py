"""Render a player's rolling performance trends as a self-contained HTML page.

    python -m viz.plot_trends
    open trends.html

Reads `marts.fct_player_rolling_trends` from the local DuckDB warehouse and
writes one small-multiple panel per metric: the per-game value as context, with
the rolling average drawn over it.

Each metric gets its own panel and its own y-axis. CS/min sits around 6 and
gold/min around 400, so plotting them together would need two y-scales — which
makes the lines' relative positions meaningless. Separate panels instead.

The output is descriptive: it shows how a metric moved over time. It does not
score, rank, or grade the player.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import duckdb

# (column, label, formatter) — `pct` renders 0.42 as "42%".
METRICS: list[tuple[str, str, str]] = [
    ("cs_per_minute", "CS per minute", "num"),
    ("gold_per_minute", "Gold per minute", "int"),
    ("damage_per_minute", "Damage to champions per minute", "int"),
    ("kda_ratio_perfect_adjusted", "KDA ratio", "num"),
    ("kill_participation", "Kill participation", "pct"),
    ("damage_share", "Damage share", "pct"),
    ("vision_score_per_minute", "Vision score per minute", "num"),
]

# Panel geometry, in viewBox units.
VIEW_W, VIEW_H = 520, 210
PAD_L, PAD_R, PAD_T, PAD_B = 48, 58, 14, 28


def fetch(con: duckdb.DuckDBPyConnection, puuid: str | None, metrics: list[str]):
    if puuid is None:
        row = con.execute(
            "select puuid from marts.dim_players order by matches_extracted desc limit 1"
        ).fetchone()
        if row is None:
            raise SystemExit(
                "No players found. Run `python -m extraction.pull_matches` first."
            )
        puuid = row[0]

    label_row = con.execute(
        "select riot_id, matches_extracted from marts.dim_players where puuid = ?",
        [puuid],
    ).fetchone()
    riot_id = label_row[0] if label_row else puuid[:12]

    selected = []
    for metric in metrics:
        selected.append(f"t.{metric}")
        selected.append(f"t.{metric}_rolling_avg")

    query = f"""
        select
            t.match_sequence_number,
            t.match_id,
            t.champion_name,
            t.queue_id,
            cast(t.game_start_at as date) as game_date,
            t.is_win,
            t.rolling_window_matches,
            {", ".join(selected)}
        from marts.fct_player_rolling_trends t
        where t.puuid = ?
        order by t.match_sequence_number
    """
    cursor = con.execute(query, [puuid])
    names = [d[0] for d in cursor.description]
    rows = [dict(zip(names, r)) for r in cursor.fetchall()]
    if not rows:
        raise SystemExit(f"No rolling trend rows for puuid {puuid}.")
    return riot_id, rows


def fmt(value: float | None, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "pct":
        return f"{value * 100:.0f}%"
    if kind == "int":
        return f"{value:,.0f}"
    return f"{value:.2f}"


def nice_bounds(values: list[float]) -> tuple[float, float]:
    """A padded y-range. Rates are never negative, so the floor clamps at zero."""
    lo, hi = min(values), max(values)
    if hi == lo:
        hi = lo + 1.0
    pad = (hi - lo) * 0.12
    return max(0.0, lo - pad), hi + pad


def build_panel(metric: str, label: str, kind: str, rows: list[dict]) -> str:
    raw_key, roll_key = metric, f"{metric}_rolling_avg"
    points = [
        (r["match_sequence_number"], r[raw_key], r[roll_key])
        for r in rows
        if r[raw_key] is not None
    ]
    if len(points) < 2:
        return ""

    xs = [p[0] for p in points]
    present = [p[1] for p in points] + [p[2] for p in points if p[2] is not None]
    y_lo, y_hi = nice_bounds(present)
    x_lo, x_hi = min(xs), max(xs)

    def sx(x: float) -> float:
        return PAD_L + (x - x_lo) / max(x_hi - x_lo, 1) * (VIEW_W - PAD_L - PAD_R)

    def sy(y: float) -> float:
        return VIEW_H - PAD_B - (y - y_lo) / (y_hi - y_lo) * (VIEW_H - PAD_T - PAD_B)

    def path(index: int) -> str:
        segments, pen_down = [], False
        for point in points:
            value = point[index]
            if value is None:
                pen_down = False
                continue
            cmd = "L" if pen_down else "M"
            segments.append(f"{cmd}{sx(point[0]):.1f},{sy(value):.1f}")
            pen_down = True
        return "".join(segments)

    # Four gridlines, labelled on the left.
    ticks = [y_lo + (y_hi - y_lo) * i / 3 for i in range(4)]
    grid = "".join(
        f'<line class="grid" x1="{PAD_L}" x2="{VIEW_W - PAD_R}" '
        f'y1="{sy(t):.1f}" y2="{sy(t):.1f}"/>'
        f'<text class="tick" x="{PAD_L - 8}" y="{sy(t) + 3.5:.1f}" '
        f'text-anchor="end">{html.escape(fmt(t, kind))}</text>'
        for t in ticks
    )

    x_ticks = "".join(
        f'<text class="tick" x="{sx(x):.1f}" y="{VIEW_H - 9}" text-anchor="middle">{x}</text>'
        for x in (x_lo, (x_lo + x_hi) // 2, x_hi)
    )

    # Direct label on the last rolling value: identity without relying on color.
    last = next((p for p in reversed(points) if p[2] is not None), None)
    end_label = ""
    if last:
        end_label = (
            f'<circle class="end-dot" cx="{sx(last[0]):.1f}" cy="{sy(last[2]):.1f}" r="3.5"/>'
            f'<text class="end-label" x="{sx(last[0]) + 8:.1f}" y="{sy(last[2]) + 3.5:.1f}">'
            f"{html.escape(fmt(last[2], kind))}</text>"
        )

    payload = json.dumps(
        {
            "metric": metric,
            "kind": kind,
            "label": label,
            "xLo": x_lo,
            "xHi": x_hi,
            "padL": PAD_L,
            "padR": PAD_R,
            "points": [
                {
                    "x": p[0],
                    "raw": p[1],
                    "roll": p[2],
                    "sx": round(sx(p[0]), 1),
                    "syRaw": round(sy(p[1]), 1),
                    "syRoll": round(sy(p[2]), 1) if p[2] is not None else None,
                }
                for p in points
            ],
        }
    )

    return f"""
<figure class="panel">
  <figcaption>{html.escape(label)}</figcaption>
  <svg viewBox="0 0 {VIEW_W} {VIEW_H}" role="img"
       aria-label="{html.escape(label)} across matches"
       data-panel='{html.escape(payload, quote=True)}'>
    {grid}
    <line class="axis" x1="{PAD_L}" x2="{VIEW_W - PAD_R}" y1="{VIEW_H - PAD_B}" y2="{VIEW_H - PAD_B}"/>
    {x_ticks}
    <path class="series-raw" d="{path(1)}"/>
    <path class="series-roll" d="{path(2)}"/>
    {end_label}
    <g class="hover-layer" hidden>
      <line class="crosshair" y1="{PAD_T}" y2="{VIEW_H - PAD_B}"/>
      <circle class="hover-dot raw" r="3"/>
      <circle class="hover-dot roll" r="4"/>
    </g>
  </svg>
</figure>"""


def build_table(rows: list[dict], metrics: list[tuple[str, str, str]]) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label, _ in metrics)
    body = []
    for r in rows:
        cells = "".join(
            f"<td>{html.escape(fmt(r[m], kind))}</td>" for m, _, kind in metrics
        )
        body.append(
            f"<tr><td>{r['match_sequence_number']}</td>"
            f"<td>{html.escape(str(r['game_date']))}</td>"
            f"<td>{html.escape(r['champion_name'] or '—')}</td>"
            f"<td>{'Win' if r['is_win'] else 'Loss'}</td>{cells}</tr>"
        )
    return f"""
<details class="table-view">
  <summary>View as table</summary>
  <div class="table-scroll">
    <table>
      <thead><tr><th>#</th><th>Date</th><th>Champion</th><th>Result</th>{head}</tr></thead>
      <tbody>{"".join(body)}</tbody>
    </table>
  </div>
</details>"""


def render(riot_id: str, rows: list[dict], metrics: list[tuple[str, str, str]]) -> str:
    window = rows[0].get("rolling_window_matches") or 10
    panels = "".join(build_panel(m, label, kind, rows) for m, label, kind in metrics)
    first, last = rows[0]["game_date"], rows[-1]["game_date"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Performance Trends</title>
<style>
  :root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --plane: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #898781;
    --grid: #e1e0d9;
    --axis: #c3c2b7;
    --series-1: #2a78d6;
    --border: rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --surface-1: #1a1a19;
      --plane: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #898781;
      --grid: #2c2c2a;
      --axis: #383835;
      --series-1: #3987e5;
      --border: rgba(255,255,255,0.10);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-1: #1a1a19;
    --plane: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --grid: #2c2c2a;
    --axis: #383835;
    --series-1: #3987e5;
    --border: rgba(255,255,255,0.10);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 32px 16px 64px;
    background: var(--plane);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 1120px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  .sub {{ color: var(--text-secondary); margin: 0 0 4px; }}
  .note {{ color: var(--muted); margin: 0 0 24px; font-size: 13px; max-width: 62ch; }}
  .legend {{ display: flex; gap: 20px; align-items: center; margin: 0 0 20px; flex-wrap: wrap; }}
  .legend span {{ display: inline-flex; align-items: center; gap: 8px; color: var(--text-secondary); }}
  .swatch {{ width: 18px; height: 2px; border-radius: 1px; }}
  .swatch.roll {{ background: var(--series-1); height: 3px; }}
  .swatch.raw {{ background: var(--muted); }}
  .grid-panels {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); }}
  .panel {{
    margin: 0; padding: 14px 12px 6px;
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    position: relative;
  }}
  figcaption {{ font-size: 13px; font-weight: 600; margin: 0 0 6px 4px; }}
  svg {{ width: 100%; height: auto; display: block; overflow: visible; }}
  .grid {{ stroke: var(--grid); stroke-width: 1; }}
  .axis {{ stroke: var(--axis); stroke-width: 1; }}
  .tick {{ fill: var(--muted); font-size: 9px; font-variant-numeric: tabular-nums; }}
  .series-raw {{ fill: none; stroke: var(--muted); stroke-width: 1.25; opacity: 0.55; }}
  .series-roll {{ fill: none; stroke: var(--series-1); stroke-width: 2;
                  stroke-linejoin: round; stroke-linecap: round; }}
  .end-dot {{ fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2; }}
  .end-label {{ fill: var(--text-secondary); font-size: 10px; font-weight: 600;
                font-variant-numeric: tabular-nums; }}
  /* `hidden` alone does not hide an SVG group in every browser — say it in CSS. */
  .hover-layer[hidden] {{ display: none; }}
  .crosshair {{ stroke: var(--axis); stroke-width: 1; stroke-dasharray: 3 3; }}
  .hover-dot.raw {{ fill: var(--muted); stroke: var(--surface-1); stroke-width: 2; }}
  .hover-dot.roll {{ fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2; }}
  .tip {{
    position: absolute; pointer-events: none; opacity: 0;
    transform: translate(-50%, -100%);
    background: var(--surface-1); color: var(--text-primary);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 7px 10px; font-size: 12px; white-space: nowrap;
    box-shadow: 0 4px 14px rgba(0,0,0,0.13); transition: opacity .1s; z-index: 5;
  }}
  .tip b {{ font-variant-numeric: tabular-nums; }}
  .tip .row {{ color: var(--text-secondary); }}
  .table-view {{ margin-top: 28px; }}
  summary {{ cursor: pointer; color: var(--text-secondary); }}
  .table-scroll {{ overflow-x: auto; margin-top: 12px; }}
  table {{ border-collapse: collapse; font-size: 12px; font-variant-numeric: tabular-nums; }}
  th, td {{ padding: 5px 10px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  th:nth-child(-n+4), td:nth-child(-n+4) {{ text-align: left; }}
  thead th {{ color: var(--text-secondary); font-weight: 600; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Performance trends — {html.escape(riot_id)}</h1>
  <p class="sub">{len(rows)} matches · {html.escape(str(first))} to {html.escape(str(last))} · {window}-match rolling average</p>
  <p class="note">
    Each panel shows one metric across matches in chronological order. The faint
    line is the per-game value; the solid line is the {window}-match rolling
    average. Panels have separate y-axes because the metrics are on different
    scales. These are descriptive trends, not a score or rating.
  </p>
  <div class="legend">
    <span><i class="swatch raw"></i> Per-game value</span>
    <span><i class="swatch roll"></i> {window}-match rolling average</span>
  </div>
  <div class="grid-panels">{panels}</div>
  {build_table(rows, metrics)}
</div>
<script>
const fmt = (v, kind) => v === null || v === undefined ? "—"
  : kind === "pct" ? (v * 100).toFixed(0) + "%"
  : kind === "int" ? Math.round(v).toLocaleString()
  : v.toFixed(2);

document.querySelectorAll(".panel").forEach(panel => {{
  const svg = panel.querySelector("svg");
  const spec = JSON.parse(svg.dataset.panel);
  const layer = svg.querySelector(".hover-layer");
  const cross = svg.querySelector(".crosshair");
  const dotRaw = svg.querySelector(".hover-dot.raw");
  const dotRoll = svg.querySelector(".hover-dot.roll");
  const tip = document.createElement("div");
  tip.className = "tip";
  panel.appendChild(tip);

  const nearest = clientX => {{
    const box = svg.getBoundingClientRect();
    const vx = (clientX - box.left) / box.width * {VIEW_W};
    let best = spec.points[0], bestDist = Infinity;
    for (const p of spec.points) {{
      const d = Math.abs(p.sx - vx);
      if (d < bestDist) {{ bestDist = d; best = p; }}
    }}
    return best;
  }};

  const show = event => {{
    const p = nearest(event.clientX);
    layer.removeAttribute("hidden");
    cross.setAttribute("x1", p.sx); cross.setAttribute("x2", p.sx);
    dotRaw.setAttribute("cx", p.sx); dotRaw.setAttribute("cy", p.syRaw);
    if (p.syRoll === null) {{ dotRoll.setAttribute("opacity", 0); }}
    else {{
      dotRoll.setAttribute("opacity", 1);
      dotRoll.setAttribute("cx", p.sx); dotRoll.setAttribute("cy", p.syRoll);
    }}
    const box = svg.getBoundingClientRect();
    const panelBox = panel.getBoundingClientRect();
    tip.innerHTML =
      "<div><b>Match " + p.x + "</b></div>" +
      "<div class='row'>Game: <b>" + fmt(p.raw, spec.kind) + "</b></div>" +
      "<div class='row'>Rolling: <b>" + fmt(p.roll, spec.kind) + "</b></div>";
    tip.style.left = (box.left - panelBox.left + p.sx / {VIEW_W} * box.width) + "px";
    tip.style.top = (box.top - panelBox.top + Math.min(p.syRaw, p.syRoll ?? p.syRaw)
                     / {VIEW_H} * box.height - 10) + "px";
    tip.style.opacity = 1;
  }};

  const hide = () => {{ layer.setAttribute("hidden", ""); tip.style.opacity = 0; }};
  svg.addEventListener("mousemove", show);
  svg.addEventListener("mouseleave", hide);
  svg.addEventListener("touchmove", e => {{ show(e.touches[0]); e.preventDefault(); }}, {{passive: false}});
  svg.addEventListener("touchend", hide);
}});
</script>
</body>
</html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb", type=Path, default=Path("summoner_trends.duckdb"))
    parser.add_argument("--output", type=Path, default=Path("trends.html"))
    parser.add_argument("--puuid", default=None, help="Defaults to the most-tracked player.")
    parser.add_argument(
        "--metrics",
        nargs="*",
        default=[m for m, _, _ in METRICS[:6]],
        help="Metric columns to plot (default: the first six).",
    )
    args = parser.parse_args(argv)

    if not args.duckdb.exists():
        raise SystemExit(
            f"{args.duckdb} not found. Run the extraction and `dbt build` first."
        )

    chosen = [m for m in METRICS if m[0] in args.metrics]
    if not chosen:
        raise SystemExit(f"No known metrics in {args.metrics}.")

    con = duckdb.connect(str(args.duckdb), read_only=True)
    try:
        riot_id, rows = fetch(con, args.puuid, [m[0] for m in chosen])
    finally:
        con.close()

    args.output.write_text(render(riot_id, rows, chosen), encoding="utf-8")
    print(f"Wrote {args.output} — {len(rows)} matches, {len(chosen)} panels.")
    print(f"Open it with:  open {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
