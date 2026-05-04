"""Web UI for the picks aggregator.

Run:
    ODDS_API_KEY=... python -m src.picks.web
    # then open http://localhost:5050

Self-contained on purpose — does not import the trading-bot server so it
runs even without the legacy model file.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict
from typing import List, Optional, Tuple

from flask import Flask, render_template_string, request

from .odds import OddsAPI, OddsAPIError
from .parlays import Parlay, build_parlays
from .scanner import Pick, only_today, scan_all

log = logging.getLogger(__name__)

app = Flask(__name__)

# Tiny in-process cache so refreshes don't burn API quota.
_CACHE: dict = {}
_CACHE_TTL_SEC = 90


def _cache_key(args) -> Tuple:
    return (
        tuple(sorted(args.get("sports", []))),
        bool(args.get("props")),
        bool(args.get("today")),
        round(float(args.get("min_edge", 0.01)), 4),
        int(args.get("min_books", 3)),
    )


def _scan(args) -> Tuple[List[Pick], List[Parlay], Optional[str]]:
    key = _cache_key(args)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SEC:
        return cached[1], cached[2], None

    try:
        api = OddsAPI()
    except OddsAPIError as e:
        return [], [], str(e)

    try:
        picks = scan_all(
            api,
            include_props=args.get("props", False),
            min_books=args.get("min_books", 3),
            min_edge=args.get("min_edge", 0.01),
            sports_filter=args.get("sports") or None,
        )
        if args.get("today"):
            picks = only_today(picks)
        parlays = build_parlays(picks)
    except OddsAPIError as e:
        return [], [], str(e)

    _CACHE[key] = (now, picks, parlays)
    return picks, parlays, None


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Today's Top Picks</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, system-ui, Segoe UI, Roboto, sans-serif;
         background:#0d1117; color:#c9d1d9; margin:0; padding:24px; }
  h1   { margin:0 0 4px 0; font-size:22px; }
  .sub { color:#8b949e; margin-bottom:18px; font-size:13px; }
  form { background:#161b22; padding:14px; border:1px solid #30363d;
         border-radius:8px; margin-bottom:18px; display:flex; flex-wrap:wrap; gap:14px; align-items:end; }
  form label { display:flex; flex-direction:column; font-size:12px; color:#8b949e; gap:4px; }
  form input, form select { background:#0d1117; color:#c9d1d9; border:1px solid #30363d;
                            border-radius:6px; padding:6px 8px; min-width:120px; }
  form button { background:#238636; color:white; border:0; border-radius:6px;
                padding:8px 14px; font-weight:600; cursor:pointer; }
  form button:hover { background:#2ea043; }
  .err  { background:#3b1d1d; border:1px solid #6e2828; color:#ffa198; padding:12px; border-radius:8px; }
  table { width:100%; border-collapse:collapse; background:#161b22; border:1px solid #30363d; border-radius:8px; overflow:hidden; }
  th, td { padding:9px 12px; text-align:left; border-bottom:1px solid #21262d; font-size:13px; vertical-align:top; }
  th { background:#21262d; color:#8b949e; font-weight:600; text-transform:uppercase; font-size:11px; letter-spacing:.05em; }
  tr:last-child td { border-bottom:0; }
  .edge { color:#3fb950; font-weight:700; font-variant-numeric: tabular-nums; }
  .price { font-variant-numeric: tabular-nums; color:#d2a8ff; }
  .muted { color:#8b949e; font-size:12px; }
  h2 { margin:28px 0 8px 0; font-size:16px; color:#c9d1d9; }
  details { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px 14px; margin-bottom:8px; }
  details summary { cursor:pointer; font-weight:600; }
  details ul { margin:8px 0 0 18px; padding:0; color:#c9d1d9; font-size:13px; }
  .pill { display:inline-block; background:#21262d; color:#8b949e; padding:2px 6px;
          border-radius:10px; font-size:11px; margin-right:4px; }
  .empty { color:#8b949e; padding:14px; text-align:center; }
  .footer { margin-top:24px; color:#8b949e; font-size:11px; }
  .qr { float:right; margin-left:14px; background:#161b22; border:1px solid #30363d;
        border-radius:8px; padding:10px; text-align:center; font-size:11px; color:#8b949e; }
  .qr img { display:block; width:130px; height:130px; background:#fff; border-radius:4px; }
  @media (max-width: 700px) { .qr { display:none; } }
</style>
</head>
<body>
  <div class="qr">
    <img src="https://api.qrserver.com/v1/create-qr-code/?size=260x260&margin=8&data={{ this_url|urlencode }}" alt="Scan to open on phone">
    Scan to open<br>on your phone
  </div>
  <h1>Today's Top Picks</h1>
  <div class="sub">+EV scanner across all in-season sports. Cached for {{ ttl }}s.</div>

  <form method="get">
    <label>Sports
      <input type="text" name="sports" value="{{ sports_str }}" placeholder="basketball_nba baseball_mlb (blank = all)">
    </label>
    <label>Min edge %
      <input type="number" step="0.1" name="min_edge_pct" value="{{ min_edge_pct }}">
    </label>
    <label>Min books
      <input type="number" name="min_books" value="{{ min_books }}" min="1" max="20">
    </label>
    <label>Top N
      <input type="number" name="top" value="{{ top }}" min="1" max="100">
    </label>
    <label>Today only
      <select name="today"><option value="1" {% if today %}selected{% endif %}>Yes</option>
                          <option value="0" {% if not today %}selected{% endif %}>No</option></select>
    </label>
    <label>Player props
      <select name="props"><option value="0" {% if not props %}selected{% endif %}>No (cheap)</option>
                          <option value="1" {% if props %}selected{% endif %}>Yes (more credits)</option></select>
    </label>
    <button type="submit">Scan</button>
  </form>

  {% if error %}
    <div class="err"><strong>Error:</strong> {{ error }}</div>
  {% else %}

    <h2>Singles &middot; <span class="muted">top {{ singles|length }} of {{ total_singles }}</span></h2>
    {% if singles %}
    <table>
      <thead><tr>
        <th>#</th><th>Edge</th><th>Price</th><th>Fair %</th><th>Kelly ¼</th>
        <th>Sport</th><th>Selection</th><th>Event</th><th>Book</th>
      </tr></thead>
      <tbody>
      {% for p in singles %}
        <tr>
          <td class="muted">{{ loop.index }}</td>
          <td class="edge">{{ '%.2f'|format(p.edge*100) }}%</td>
          <td class="price">{{ '%+d'|format(p.best_price) }}</td>
          <td>{{ '%.1f'|format(p.fair_prob*100) }}%</td>
          <td>{{ '%.2f'|format(p.kelly_frac*100) }}%</td>
          <td><span class="pill">{{ p.sport }}</span></td>
          <td><strong>{{ p.selection }}</strong> <span class="muted">{{ p.market }}</span></td>
          <td class="muted">{{ p.event }}<br><span class="muted">{{ p.commence_time }}</span></td>
          <td class="muted">{{ p.best_book }} ({{ p.books_count }} books)</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    {% else %}<div class="empty">No picks cleared the filters.</div>{% endif %}

    <h2>Parlays <span class="muted">(uncorrelated 2–3 leg combos from top singles)</span></h2>
    {% if parlays %}
      {% for par in parlays %}
        <details {% if loop.first %}open{% endif %}>
          <summary>
            <span class="price">{{ '%+d'|format(par.combined_american) }}</span>
            &middot; <span class="edge">edge {{ '%.2f'|format(par.edge*100) }}%</span>
            &middot; <span class="muted">hits {{ '%.2f'|format(par.fair_prob*100) }}% of the time</span>
          </summary>
          <ul>
            {% for leg in par.legs %}
              <li><strong>{{ leg.selection }}</strong>
                  <span class="muted">{{ leg.market }}</span>
                  <span class="price">{{ '%+d'|format(leg.best_price) }}</span>
                  <span class="muted">[{{ leg.best_book }}] — {{ leg.event }}</span></li>
            {% endfor %}
          </ul>
        </details>
      {% endfor %}
    {% else %}<div class="empty">No +EV parlays found.</div>{% endif %}

  {% endif %}

  <div class="footer">
    Edges are pricing-only (no sharp/public splits, no injury data). Bet responsibly.
    Don't chase lottery-ticket parlays — high "edge" on a 2% hit-rate is still mostly losing.
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    raw_sports = (request.args.get("sports") or "").strip()
    sports = raw_sports.split() if raw_sports else []
    min_edge_pct = float(request.args.get("min_edge_pct", "1.0"))
    min_books = int(request.args.get("min_books", "3"))
    top = int(request.args.get("top", "20"))
    today = request.args.get("today", "1") == "1"
    props = request.args.get("props", "0") == "1"

    args = {
        "sports": sports,
        "min_edge": min_edge_pct / 100.0,
        "min_books": min_books,
        "today": today,
        "props": props,
    }

    picks, parlays, error = _scan(args)

    return render_template_string(
        PAGE,
        ttl=_CACHE_TTL_SEC,
        this_url=request.url_root.rstrip("/"),
        sports_str=raw_sports,
        min_edge_pct=min_edge_pct,
        min_books=min_books,
        top=top,
        today=today,
        props=props,
        singles=[asdict(p) for p in picks[:top]],
        total_singles=len(picks),
        parlays=[
            {
                "combined_american": par.combined_american,
                "edge": par.edge,
                "fair_prob": par.fair_prob,
                "legs": [asdict(l) for l in par.legs],
            }
            for par in parlays
        ],
        error=error,
    )


@app.route("/healthz")
def healthz():
    return {"ok": True}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
