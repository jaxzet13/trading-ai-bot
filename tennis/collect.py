"""24/7 recorder of the top of book of every open tennis match market (python -m tennis collect).

Kalshi keeps every trade but not past order books, and a risk-free arb needs both players' prices at the same
moment, so arbs can only be tested on books we record ourselves. Every POLL_S seconds this reads all open markets of
the match-winner series (one request per series) and appends a row for every market whose top of book changed to
data/tennis/books/YYYY-MM-DD.jsonl. Results (which player won, and matches settled some other way) are appended to
data/tennis/results.jsonl as matches settle. Read-only: places nothing.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import api

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "tennis"
BOOKS = DATA / "books"
RESULTS = DATA / "results.jsonl"
POLL_S = 15
RESULT_EVERY_S = 1800
KEYS = ("yes_ask", "yes_ask_size", "yes_bid", "yes_bid_size", "no_ask", "no_bid")


def snapshot(session=None):
    rows = []
    for s in api.MATCH_SERIES:
        try:
            ms = api.open_markets(s, session=session) if session else api.open_markets(s)
        except Exception as e:                       # one series failing must not stop the others
            print(f"  {s}: {e!r}", flush=True)
            continue
        for m in ms:
            r = api.top_of_book(m)
            r["series"] = s
            rows.append(r)
    return rows


def record_results(seen, log=print):
    """Append newly settled match markets (result yes/no, settle time) to results.jsonl."""
    new = 0
    with open(RESULTS, "a") as f:
        for s in api.MATCH_SERIES:
            try:
                d = api.get("/markets", {"series_ticker": s, "status": "settled", "limit": 1000})
            except Exception:
                continue
            for m in d.get("markets", []):
                if m["ticker"] in seen:
                    continue
                seen.add(m["ticker"])
                f.write(json.dumps({"ticker": m["ticker"], "event": m["event_ticker"], "series": s,
                                    "player": m.get("yes_sub_title"), "result": m.get("result"),
                                    "settled": m.get("settlement_ts") or m.get("close_time"),
                                    "volume": api._f(m.get("volume_fp"))}) + "\n")
                new += 1
    if new:
        log(f"  results: +{new} settled markets")


def run(once=False, log=print):
    BOOKS.mkdir(parents=True, exist_ok=True)
    last, seen = {}, set()
    if RESULTS.exists():
        seen = {json.loads(ln)["ticker"] for ln in open(RESULTS) if ln.strip()}
    next_results = 0.0
    while True:
        t0 = time.time()
        rows = snapshot()
        path = BOOKS / time.strftime("%Y-%m-%d.jsonl", time.gmtime(t0))
        changed = 0
        with open(path, "a") as f:
            for r in rows:
                key = tuple(r.get(k) for k in KEYS)
                if last.get(r["ticker"]) == key:
                    continue
                last[r["ticker"]] = key
                r["ts"] = round(t0, 1)
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
                changed += 1
        if t0 >= next_results:
            record_results(seen, log)
            next_results = t0 + RESULT_EVERY_S
            log(f"{time.strftime('%H:%M:%S', time.gmtime(t0))} {len(rows)} open match markets, {changed} changed")
        if once:
            return rows
        time.sleep(max(1.0, POLL_S - (time.time() - t0)))
