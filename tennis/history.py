"""Settled tennis matches with their minute-by-minute prices (python -m tennis history [days]).

For every settled match-winner market: its scheduled start (occurrence_datetime), result and settlement value,
and Kalshi's 1-minute candlesticks (yes bid/ask open/high/low/close, volume) from 6 hours before the start to
settlement (at most 12 hours). Stored per market in data/tennis/hist/markets.jsonl (one line each), appended as
new matches settle, so the learning loop can rerun it cheaply.
"""
from __future__ import annotations

import datetime as dt
import json
import time

from . import api
from .collect import DATA

HIST = DATA / "hist"
STORE = HIST / "markets.jsonl"
SERIES = ["KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXITFWMATCH", "KXITFMATCH"]
PRE_S, MAX_S = 6 * 3600, 12 * 3600


def _ts(s):
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()) if s else None


def _f(x, k):
    try:
        return round(float(x[k]), 4)
    except (KeyError, TypeError, ValueError):
        return None


def settled(series, since_ts):
    out, cursor = [], None
    while True:
        p = {"series_ticker": series, "status": "settled", "limit": 1000, "min_close_ts": since_ts}
        if cursor:
            p["cursor"] = cursor
        d = api.get("/markets", p)
        out += d.get("markets", [])
        cursor = d.get("cursor")
        if not cursor or not d.get("markets"):
            return out


def bars(series, ticker, start, end):
    d = api.get(f"/series/{series}/markets/{ticker}/candlesticks",
                {"start_ts": start, "end_ts": end, "period_interval": 1})
    rows = []
    for c in d.get("candlesticks", []):
        a, b = c.get("yes_ask") or {}, c.get("yes_bid") or {}
        rows.append([int(c["end_period_ts"]), _f(b, "close_dollars"), _f(b, "low_dollars"), _f(a, "close_dollars"),
                     _f(a, "high_dollars"), round(float(c.get("volume_fp") or 0), 2)])
    return rows                        # [minute end ts, bid close, bid low, ask close, ask high, volume]


def update(days=60, log=print, max_s=None):
    HIST.mkdir(parents=True, exist_ok=True)
    have = set()
    if STORE.exists():
        have = {json.loads(ln)["ticker"] for ln in open(STORE) if ln.strip()}
    since = int(time.time()) - days * 86400
    t_end = time.time() + max_s if max_s else None
    new = 0
    with open(STORE, "a") as f:
        for s in SERIES:
            try:
                ms = settled(s, since)
            except Exception as e:
                log(f"  {s}: {e!r}")
                continue
            todo = [m for m in ms if m["ticker"] not in have and m.get("occurrence_datetime")]
            log(f"  {s}: {len(ms)} settled since {days} d ago, {len(todo)} new")
            for m in todo:
                if t_end and time.time() > t_end:
                    break
                start, end = _ts(m["occurrence_datetime"]), _ts(m.get("settlement_ts") or m["close_time"])
                if not start or not end:
                    continue
                try:
                    b = bars(s, m["ticker"], start - PRE_S, min(end, start + MAX_S))
                except Exception as e:
                    log(f"  {m['ticker']}: {e!r}")
                    continue
                f.write(json.dumps({"ticker": m["ticker"], "event": m["event_ticker"], "series": s,
                                    "player": m.get("yes_sub_title"), "start": start, "settled": end,
                                    "result": m.get("result"), "value": _f(m, "settlement_value_dollars"),
                                    "volume": _f(m, "volume_fp"), "bars": b}, separators=(",", ":")) + "\n")
                have.add(m["ticker"])
                new += 1
                if new % 200 == 0:
                    f.flush()
                    log(f"    {new} markets downloaded")
    log(f"history: +{new} markets, {len(have)} stored" + (" (time budget reached, more next round)" if t_end and time.time() > t_end else ""))
    return new
