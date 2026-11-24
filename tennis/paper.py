"""Tennis practice runner (python -m tennis paper): the lab's own decision code on live matches, no money.

Every minute it rebuilds each open match's minute bars from the recorder's 15-second books (bid close, bid low,
ask close, ask high per minute) and asks lab.bet(), the exact function the lab scores with, whether each strategy
would bet. A practice bet is logged once its fill minute has closed, at that minute's worst price, as in the lab.
When the match settles the bet is paid from results.jsonl, and once its official candlesticks are in the history
the same strategy is replayed there (parity): same side and a price within PARITY_C cents means the live runner
and the lab agree. The real-money runner will reuse this path unchanged.

Strategies run: every one that passed its forward test, else the 5 best by forward t (marked practice-only), so
the pipeline is exercised before anything passes.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from collections import defaultdict

import numpy as np

from . import lab
from .collect import BOOKS, DATA, RESULTS
from .history import STORE

LOG = DATA / "paper_bets.jsonl"
PARITY_C = 2.0
CLOSE_LAG_S = 20
FALLBACK_N = 50


def _strategies():
    fp = DATA / "report" / "forward.json"
    rows = json.loads(fp.read_text()) if fp.exists() else []
    passed = [r for r in rows if r.get("passed")]
    by_id, latest = {}, []
    for bp in sorted((DATA / "forward").glob("batch_*.json")):
        latest = json.loads(bp.read_text())["strategies"]
        for s in latest:
            by_id[s["id"]] = s
    if passed:
        return [by_id[r["code"]] for r in passed if r["code"] in by_id], True
    # nothing passed yet: run the newest frozen batch's top FALLBACK_N (frozen in leaderboard order), practice only
    return latest[:FALLBACK_N], False


def _start_times():
    """Scheduled start per event from the open markets (occurrence_datetime), cached per call."""
    from . import api
    out = {}
    for s in api.MATCH_SERIES:
        try:
            for m in api.open_markets(s):
                if m.get("occurrence_datetime"):
                    out[m["ticker"]] = int(dt.datetime.fromisoformat(m["occurrence_datetime"].replace("Z", "+00:00")).timestamp())
        except Exception:
            continue
    return out


def live_markets(starts, now):
    """Minute bars per open market from today's (and yesterday's) recorded books."""
    rows = defaultdict(list)
    for p in sorted(BOOKS.glob("*.jsonl"))[-2:]:
        for ln in open(p):
            r = json.loads(ln)
            if r["ticker"] in starts and r.get("yes_bid") and r.get("yes_ask"):
                rows[r["ticker"]].append((r["ts"], r["yes_bid"], r["yes_ask"], r["event"], r.get("series")))
    out = []
    for tk, rs in rows.items():
        rs.sort()
        cur_min = int(now // 60)
        last = rs[-1]
        ts_ = [r[0] for r in rs]
        # Kalshi's official 1-minute bar ends at the minute boundary and closes at the price THERE. The recorder
        # samples every 15 s, so the last sample inside a minute can miss a move in its final seconds (Nov 24
        # parity check: a drop from 0.19 to 0.11 at 79:55 made the live runner bet where the lab would not).
        # So a minute's close is the first sample at or after its end (within CLOSE_LAG_S), else the last one
        # inside it; its low/high cover every sample from the previous close through this one.
        import bisect
        full, prev = [], None
        first_min = int(rs[0][0] // 60)
        for m_ in range(first_min, cur_min):
            end = (m_ + 1) * 60
            k = bisect.bisect_left(ts_, end)
            if k < len(rs) and rs[k][0] - end <= CLOSE_LAG_S:
                close = rs[k]
            elif k > 0 and rs[k - 1][0] >= end - 60:
                close = rs[k - 1]
            else:
                close = None
            lo_i = bisect.bisect_left(ts_, end - 60)
            hi_i = (k + 1) if (k < len(rs) and close is rs[k]) else k
            span = rs[lo_i:hi_i] or ([close] if close else [])
            if close:
                prev = (close[1], min(x[1] for x in span), close[2], max(x[2] for x in span))
            elif prev:
                prev = (prev[0], prev[0], prev[2], prev[2])          # unchanged book: the recorder logs changes only
            if prev and end <= now - CLOSE_LAG_S:
                full.append((end, *prev))
        if len(full) < 2:
            continue
        b = np.array(full, float)
        start = starts[tk]
        rel = (b[:, 0] - start) / 60.0
        out.append({"ticker": tk, "event": last[3], "series": last[4], "day": int(start // 86400), "start": start,
                    "value": np.nan, "rel": rel, "mid": (b[:, 1] + b[:, 3]) / 2, "bidlo": b[:, 2], "askhi": b[:, 4]})
    return out


def _logged():
    if not LOG.exists():
        return {}
    return {(r["ticker"], r["strategy"]): r for r in (json.loads(ln) for ln in open(LOG) if ln.strip())}


def step(log=print):
    strats, passed = _strategies()
    if not strats:
        return 0
    now = time.time()
    starts = _start_times()
    done = _logged()
    n = 0
    with open(LOG, "a") as f:
        for m in live_markets(starts, now):
            for s in strats:
                if (m["ticker"], s["id"]) in done:
                    continue
                m2 = dict(m, value=0.0)               # value is unknown live; bet() needs it only for the pnl
                r = lab.bet(m2, s)
                if not r:
                    continue
                side, price, _, minute = r
                rec = {"ts": round(now, 1), "ticker": m["ticker"], "event": m["event"], "series": m["series"],
                       "strategy": s["id"], "practice_only": not passed, "side": side, "price": round(price, 4),
                       "minute": round(minute, 1)}
                f.write(json.dumps(rec) + "\n")
                done[(m["ticker"], s["id"])] = rec
                n += 1
                log(f"  practice bet: {m['ticker']} {side} @ {price:.2f} ({s['id']})")
    return n


def settle_and_check():
    """Pay practice bets from results.jsonl and replay them on official candlesticks -> summary rows."""
    bets = list(_logged().values())
    res = {}
    if RESULTS.exists():
        for ln in open(RESULTS):
            r = json.loads(ln)
            res[r["ticker"]] = r
    hist = {}
    if STORE.exists() and bets:
        want = {b["ticker"] for b in bets}
        for m in lab.load():
            if m["ticker"] in want:
                hist[m["ticker"]] = m
    strat_by_id = {}
    for bp in sorted((DATA / "forward_old").glob("batch_*.json")) + sorted((DATA / "forward").glob("batch_*.json")):
        for s in json.loads(bp.read_text())["strategies"]:
            strat_by_id[s["id"]] = s
    from . import api
    out = []
    for b in bets:
        r = res.get(b["ticker"])
        pnl = None
        if r and r.get("result") in ("yes", "no"):
            v = 1.0 if r["result"] == "yes" else 0.0
            win = v if b["side"] == "yes" else 1 - v
            pnl = round(win - b["price"] - api.fee(b["price"], 1), 4)
        parity = None
        if b["ticker"] in hist and b["strategy"] in strat_by_id:
            rr = lab.bet(hist[b["ticker"]], strat_by_id[b["strategy"]])
            parity = bool(rr and rr[0] == b["side"] and round(abs(rr[1] - b["price"]) * 100, 6) <= PARITY_C)
        out.append({**b, "pnl": pnl, "parity": parity})
    return out
