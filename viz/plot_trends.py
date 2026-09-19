"""Render a player's rolling performance trends as a self-contained HTML page.

    python -m viz.plot_trends
    open trends.html

Reads `marts.fct_player_rolling_trends` from the local DuckDB warehouse and
writes one small-multiple panel per metric: the per-game value as context, with
the rolling average drawn over it.

Each metric gets its own panel and its own y-axis. CS/min sits around 6 and
gold/min around 400, so plotting them together would need two y-scales — which
makes the lines' relative positions meaningless. Separate panels instead.

The page carries a range filter (last 10 / 20 / 50 / all matches). That narrows
which matches are *shown*; it does not recompute the rolling average, which
stays the window dbt built. A point's rolling value always means the same thing
whatever range is on screen.

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

# Panel geometry, in viewBox units. The page redraws panels on range change,
# so the browser owns the scales; these are the only fixed dimensions.
VIEW_W, VIEW_H = 520, 210
PAD_L, PAD_R, PAD_T, PAD_B = 48, 58, 14, 28

RANGE_OPTIONS = [10, 20, 50, 100]


def fetch(con: duckdb.DuckDBPyConnection, puuid: str | None, metrics: list[str]):
    """Return (riot_id, rows) for one player's rolling trend history."""
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
        "select riot_id from marts.dim_players where puuid = ?", [puuid]
    ).fetchone()
    riot_id = label_row[0] if label_row else puuid[:12]

    selected = []
    for metric in metrics:
        selected.append(f"t.{metric}")
        selected.append(f"t.{metric}_rolling_avg")

    query = f"""
        select
            t.match_sequence_number,
            t.champion_name,
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


def range_choices(total: int) -> list[int]:
    """Offer only ranges the history can actually fill, plus 'all' implicitly."""
    return [n for n in RANGE_OPTIONS if n < total]


def build_payload(rows: list[dict], metrics: list[tuple[str, str, str]]) -> dict:
    series = []
    for key, label, kind in metrics:
        points = [
            {
                "x": r["match_sequence_number"],
                "raw": r[key],
                "roll": r[f"{key}_rolling_avg"],
            }
            for r in rows
            if r[key] is not None
        ]
        if len(points) >= 2:
            series.append({"key": key, "label": label, "kind": kind, "points": points})

    meta = [
        {
            "x": r["match_sequence_number"],
            "date": str(r["game_date"]),
            "champion": r["champion_name"] or "—",
            "result": "Win" if r["is_win"] else "Loss",
        }
        for r in rows
    ]
    return {
        "series": series,
        "meta": meta,
        "view": {"w": VIEW_W, "h": VIEW_H, "l": PAD_L, "r": PAD_R, "t": PAD_T, "b": PAD_B},
    }


def build_table(rows: list[dict], metrics: list[tuple[str, str, str]]) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label, _ in metrics)
    body = []
    for r in rows:
        cells = "".join(
            f"<td>{html.escape(fmt(r[m], kind))}</td>" for m, _, kind in metrics
        )
        body.append(
            f"<tr data-seq=\"{r['match_sequence_number']}\">"
            f"<td>{r['match_sequence_number']}</td>"
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


CSS = """
  :root {
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
    --chip: rgba(11,11,11,0.05);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
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
      --chip: rgba(255,255,255,0.07);
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --surface-1: #1a1a19;
    --plane: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --grid: #2c2c2a;
    --axis: #383835;
    --series-1: #3987e5;
    --border: rgba(255,255,255,0.10);
    --chip: rgba(255,255,255,0.07);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 32px 16px 64px;
    background: var(--plane); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 14px; line-height: 1.5;
  }
  .wrap { max-width: 1120px; margin: 0 auto; }
  h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: -0.01em; }
  .sub { color: var(--text-secondary); margin: 0 0 4px; }
  .note { color: var(--muted); margin: 0 0 20px; font-size: 13px; max-width: 64ch; }
  .controls {
    display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
    margin: 0 0 14px; padding-bottom: 14px; border-bottom: 1px solid var(--border);
  }
  .controls .label { color: var(--text-secondary); font-size: 13px; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip {
    font: inherit; font-size: 13px; cursor: pointer;
    padding: 5px 12px; min-height: 32px;
    border: 1px solid var(--border); border-radius: 999px;
    background: transparent; color: var(--text-secondary);
  }
  .chip:hover { background: var(--chip); }
  .chip[aria-pressed="true"] {
    background: var(--series-1); border-color: var(--series-1);
    color: #fff; font-weight: 600;
  }
  .chip:focus-visible { outline: 2px solid var(--series-1); outline-offset: 2px; }
  .legend { display: flex; gap: 20px; align-items: center; margin: 0 0 18px; flex-wrap: wrap; }
  .legend span { display: inline-flex; align-items: center; gap: 8px; color: var(--text-secondary); }
  .swatch { width: 18px; height: 2px; border-radius: 1px; }
  .swatch.roll { background: var(--series-1); height: 3px; }
  .swatch.raw { background: var(--muted); }
  .grid-panels { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); }
  .panel {
    margin: 0; padding: 14px 12px 6px; position: relative;
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
  }
  figcaption { font-size: 13px; font-weight: 600; margin: 0 0 6px 4px; }
  svg { width: 100%; height: auto; display: block; overflow: visible; }
  .grid { stroke: var(--grid); stroke-width: 1; }
  .axis { stroke: var(--axis); stroke-width: 1; }
  .tick { fill: var(--muted); font-size: 9px; font-variant-numeric: tabular-nums; }
  .series-raw { fill: none; stroke: var(--muted); stroke-width: 1.25; opacity: 0.55; }
  .series-roll { fill: none; stroke: var(--series-1); stroke-width: 2;
                 stroke-linejoin: round; stroke-linecap: round; }
  .end-dot { fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2; }
  .end-label { fill: var(--text-secondary); font-size: 10px; font-weight: 600;
               font-variant-numeric: tabular-nums; }
  /* `hidden` alone does not hide an SVG group in every browser — say it in CSS. */
  .hover-layer[hidden] { display: none; }
  .crosshair { stroke: var(--axis); stroke-width: 1; stroke-dasharray: 3 3; }
  .hover-dot.raw { fill: var(--muted); stroke: var(--surface-1); stroke-width: 2; }
  .hover-dot.roll { fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2; }
  .tip {
    position: absolute; pointer-events: none; opacity: 0;
    transform: translate(-50%, -100%);
    background: var(--surface-1); color: var(--text-primary);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 7px 10px; font-size: 12px; white-space: nowrap;
    box-shadow: 0 4px 14px rgba(0,0,0,0.13); transition: opacity .1s; z-index: 5;
  }
  .tip b { font-variant-numeric: tabular-nums; }
  .tip .row { color: var(--text-secondary); }
  .tip .head { font-weight: 600; margin-bottom: 2px; }
  .table-view { margin-top: 28px; }
  summary { cursor: pointer; color: var(--text-secondary); }
  .table-scroll { overflow-x: auto; margin-top: 12px; }
  table { border-collapse: collapse; font-size: 12px; font-variant-numeric: tabular-nums; }
  th, td { padding: 5px 10px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th:nth-child(-n+4), td:nth-child(-n+4) { text-align: left; }
  thead th { color: var(--text-secondary); font-weight: 600; }
  tr[hidden] { display: none; }
"""

JS = r"""
const DATA = __PAYLOAD__;
const V = DATA.view;
const SVG_NS = "http://www.w3.org/2000/svg";
const metaByX = new Map(DATA.meta.map(m => [m.x, m]));

const fmt = (v, kind) => v === null || v === undefined ? "—"
  : kind === "pct" ? (v * 100).toFixed(0) + "%"
  : kind === "int" ? Math.round(v).toLocaleString()
  : v.toFixed(2);

// Rates are never negative, so the padded floor clamps at zero.
function niceBounds(values) {
  let lo = Math.min(...values), hi = Math.max(...values);
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.12;
  return [Math.max(0, lo - pad), hi + pad];
}

const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function drawPanel(panel, spec, range) {
  const all = spec.points;
  const points = range === "all" ? all : all.slice(-range);
  const svg = panel.querySelector("svg");
  if (points.length < 2) { svg.innerHTML = ""; return; }

  const xs = points.map(p => p.x);
  const values = points.map(p => p.raw)
    .concat(points.filter(p => p.roll !== null).map(p => p.roll));
  const [yLo, yHi] = niceBounds(values);
  const xLo = Math.min(...xs), xHi = Math.max(...xs);

  const sx = x => V.l + (x - xLo) / Math.max(xHi - xLo, 1) * (V.w - V.l - V.r);
  const sy = y => V.h - V.b - (y - yLo) / (yHi - yLo) * (V.h - V.t - V.b);

  const path = key => {
    let d = "", down = false;
    for (const p of points) {
      const v = p[key];
      if (v === null || v === undefined) { down = false; continue; }
      d += (down ? "L" : "M") + sx(p.x).toFixed(1) + "," + sy(v).toFixed(1);
      down = true;
    }
    return d;
  };

  let out = "";
  for (let i = 0; i < 4; i++) {
    const t = yLo + (yHi - yLo) * i / 3;
    out += `<line class="grid" x1="${V.l}" x2="${V.w - V.r}" y1="${sy(t).toFixed(1)}" y2="${sy(t).toFixed(1)}"/>`
         + `<text class="tick" x="${V.l - 8}" y="${(sy(t) + 3.5).toFixed(1)}" text-anchor="end">${esc(fmt(t, spec.kind))}</text>`;
  }
  out += `<line class="axis" x1="${V.l}" x2="${V.w - V.r}" y1="${V.h - V.b}" y2="${V.h - V.b}"/>`;

  for (const x of [xLo, Math.round((xLo + xHi) / 2), xHi]) {
    out += `<text class="tick" x="${sx(x).toFixed(1)}" y="${V.h - 9}" text-anchor="middle">${x}</text>`;
  }

  out += `<path class="series-raw" d="${path("raw")}"/>`;
  out += `<path class="series-roll" d="${path("roll")}"/>`;

  // Direct label on the latest rolling value: identity without relying on colour.
  const last = [...points].reverse().find(p => p.roll !== null);
  if (last) {
    out += `<circle class="end-dot" cx="${sx(last.x).toFixed(1)}" cy="${sy(last.roll).toFixed(1)}" r="3.5"/>`
         + `<text class="end-label" x="${(sx(last.x) + 8).toFixed(1)}" y="${(sy(last.roll) + 3.5).toFixed(1)}">${esc(fmt(last.roll, spec.kind))}</text>`;
  }

  out += `<g class="hover-layer" hidden>`
       + `<line class="crosshair" y1="${V.t}" y2="${V.h - V.b}"/>`
       + `<circle class="hover-dot raw" r="3"/><circle class="hover-dot roll" r="4"/></g>`;

  svg.innerHTML = out;
  panel._plot = { points, sx, sy, spec };
}

function attachHover(panel) {
  const svg = panel.querySelector("svg");
  const tip = document.createElement("div");
  tip.className = "tip";
  panel.appendChild(tip);

  const show = event => {
    const plot = panel._plot;
    if (!plot) return;
    const box = svg.getBoundingClientRect();
    const vx = (event.clientX - box.left) / box.width * V.w;
    let best = null, bestDist = Infinity;
    for (const p of plot.points) {
      const d = Math.abs(plot.sx(p.x) - vx);
      if (d < bestDist) { bestDist = d; best = p; }
    }
    if (!best) return;

    const layer = svg.querySelector(".hover-layer");
    const cross = svg.querySelector(".crosshair");
    const dotRaw = svg.querySelector(".hover-dot.raw");
    const dotRoll = svg.querySelector(".hover-dot.roll");
    const px = plot.sx(best.x), pyRaw = plot.sy(best.raw);
    layer.removeAttribute("hidden");
    cross.setAttribute("x1", px); cross.setAttribute("x2", px);
    dotRaw.setAttribute("cx", px); dotRaw.setAttribute("cy", pyRaw);
    let pyRoll = pyRaw;
    if (best.roll === null) { dotRoll.setAttribute("opacity", 0); }
    else {
      pyRoll = plot.sy(best.roll);
      dotRoll.setAttribute("opacity", 1);
      dotRoll.setAttribute("cx", px); dotRoll.setAttribute("cy", pyRoll);
    }

    const meta = metaByX.get(best.x);
    tip.innerHTML =
      `<div class="head">Match ${best.x}${meta ? " · " + esc(meta.champion) : ""}</div>` +
      (meta ? `<div class="row">${esc(meta.date)} · ${esc(meta.result)}</div>` : "") +
      `<div class="row">Game: <b>${fmt(best.raw, plot.spec.kind)}</b></div>` +
      `<div class="row">Rolling: <b>${fmt(best.roll, plot.spec.kind)}</b></div>`;

    const panelBox = panel.getBoundingClientRect();
    tip.style.left = (box.left - panelBox.left + px / V.w * box.width) + "px";
    tip.style.top = (box.top - panelBox.top + Math.min(pyRaw, pyRoll) / V.h * box.height - 10) + "px";
    tip.style.opacity = 1;
  };

  const hide = () => {
    const layer = svg.querySelector(".hover-layer");
    if (layer) layer.setAttribute("hidden", "");
    tip.style.opacity = 0;
  };
  svg.addEventListener("mousemove", show);
  svg.addEventListener("mouseleave", hide);
  svg.addEventListener("touchmove", e => { show(e.touches[0]); e.preventDefault(); }, { passive: false });
  svg.addEventListener("touchend", hide);
}

const panels = [...document.querySelectorAll(".panel")];
panels.forEach(attachHover);

function applyRange(range) {
  panels.forEach(panel => {
    const spec = DATA.series.find(s => s.key === panel.dataset.metric);
    if (spec) drawPanel(panel, spec, range);
  });

  // The table follows the same range, so the two views never disagree.
  const total = DATA.meta.length;
  const cutoff = range === "all" ? -Infinity : DATA.meta[Math.max(0, total - range)].x;
  document.querySelectorAll("tbody tr").forEach(tr => {
    tr.hidden = Number(tr.dataset.seq) < cutoff;
  });

  const shown = range === "all" ? total : Math.min(range, total);
  document.getElementById("range-note").textContent =
    shown === total ? `all ${total} matches` : `last ${shown} of ${total} matches`;

  // The dates have to follow the range too, or the header describes a
  // different set of matches than the charts do.
  const visible = DATA.meta.slice(total - shown);
  document.getElementById("date-note").textContent =
    visible.length ? `${visible[0].date} to ${visible[visible.length - 1].date}` : "";

  document.querySelectorAll(".chip").forEach(chip => {
    chip.setAttribute("aria-pressed", String(chip.dataset.range === String(range)));
  });
}

document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    const value = chip.dataset.range;
    applyRange(value === "all" ? "all" : Number(value));
  });
});

applyRange("all");
"""


def render(riot_id: str, rows: list[dict], metrics: list[tuple[str, str, str]]) -> str:
    window = rows[0].get("rolling_window_matches") or 10
    total = len(rows)
    payload = build_payload(rows, metrics)

    panels = "".join(
        f'<figure class="panel" data-metric="{html.escape(s["key"])}">'
        f'<figcaption>{html.escape(s["label"])}</figcaption>'
        f'<svg viewBox="0 0 {VIEW_W} {VIEW_H}" role="img" '
        f'aria-label="{html.escape(s["label"])} across matches"></svg>'
        f"</figure>"
        for s in payload["series"]
    )

    chips = "".join(
        f'<button class="chip" type="button" data-range="{n}" aria-pressed="false">Last {n}</button>'
        for n in range_choices(total)
    )
    chips += '<button class="chip" type="button" data-range="all" aria-pressed="true">All</button>'

    first, last = rows[0]["game_date"], rows[-1]["game_date"]
    js = JS.replace("__PAYLOAD__", json.dumps(payload))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Performance Trends</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>Performance trends — {html.escape(riot_id)}</h1>
  <p class="sub">Showing <span id="range-note">all {total} matches</span> · <span id="date-note">{html.escape(str(first))} to {html.escape(str(last))}</span> · {window}-match rolling average</p>
  <p class="note">
    Each panel shows one metric across matches in chronological order. The faint
    line is the per-game value; the solid line is the {window}-match rolling
    average. Panels have separate y-axes because the metrics are on different
    scales. Changing the range zooms in on recent matches — it does not change
    how the rolling average is calculated, so a point means the same thing at
    every range. These are descriptive trends, not a score or rating.
  </p>
  <div class="controls">
    <span class="label">Range</span>
    <div class="chips" role="group" aria-label="Number of recent matches to show">{chips}</div>
  </div>
  <div class="legend">
    <span><i class="swatch raw"></i> Per-game value</span>
    <span><i class="swatch roll"></i> {window}-match rolling average</span>
  </div>
  <div class="grid-panels">{panels}</div>
  {build_table(rows, metrics)}
</div>
<script>{js}</script>
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
