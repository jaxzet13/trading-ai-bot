"""Shared loading for the index study: Kalshi quotes on a minute grid, index level (Yahoo / implied), scoring."""
import json
import math
import os
from collections import defaultdict

import numpy as np

DATA = "data/index"
WIN = 450                                   # minutes before the close that were downloaded
INDEX = {"KXINX": "GSPC", "KXINXU": "GSPC", "KXNASDAQ100": "NDX", "KXNASDAQ100U": "NDX"}
FAMILY = {"KXINX": "range", "KXNASDAQ100": "range", "KXINXU": "above", "KXNASDAQ100U": "above"}
STALE = 10                                  # a quote is carried forward at most this many minutes


def fee(p):
    return 0.07 * p * (1 - p)


def tstat(pnl, day):
    """t statistic of the mean with days as the independent unit (sum per day, like the other studies)."""
    by = defaultdict(float)
    for p, d in zip(pnl, day):
        by[d] += p
    w = np.array(list(by.values()))
    return float(w.mean() / w.std(ddof=1) * math.sqrt(len(w))) if len(w) > 2 and w.std() > 0 else 0.0


def halves(pnl, day, alldays):
    """Mean pnl in the first / second half of the calendar of days (split fixed by the calendar, not by bets)."""
    cut = sorted(alldays)[len(alldays) // 2]
    a, b = pnl[day < cut], pnl[day >= cut]
    return (100 * a.mean() if len(a) else float("nan")), (100 * b.mean() if len(b) else float("nan"))


def grid(bars, close):
    """bid / ask arrays on the minute grid: index i = minutes after (close - WIN), i = WIN is the close itself."""
    bid, ask, vol = np.full(WIN + 1, np.nan), np.full(WIN + 1, np.nan), np.zeros(WIN + 1)
    age = np.full(WIN + 1, 10 ** 6)
    t0 = close - WIN * 60
    for r in bars:
        i = (r[0] - t0) // 60
        if 0 <= i <= WIN:
            bid[i] = np.nan if r[1] is None else r[1]
            ask[i] = np.nan if r[2] is None else r[2]
            vol[i] = r[5] or 0
            age[i] = 0
    for i in range(1, WIN + 1):                 # carry the last quote forward, at most STALE minutes
        if age[i] > 0 and age[i - 1] < STALE:
            bid[i], ask[i], age[i] = bid[i - 1], ask[i - 1], age[i - 1] + 1
    return bid, ask, vol


def load(series):
    """Events of one series: {day, close, exp, series, markets: [{tk, floor, cap, type, v, volume, bid, ask, vol}]}"""
    ev = {}
    path = f"{DATA}/{series}.jsonl"
    if not os.path.exists(path):
        return []
    for ln in open(path):
        m = json.loads(ln)
        if m["result"] not in ("yes", "no") or not m["event"].endswith("H1600"):
            continue
        e = ev.setdefault(m["event"], {"event": m["event"], "day": m["close"] // 86400, "close": m["close"],
                                       "exp": m["exp"], "series": series, "markets": []})
        bid, ask, vol = grid(m["bars"], m["close"])
        e["markets"].append({"tk": m["ticker"], "floor": m["floor"], "cap": m["cap"], "type": m["type"],
                             "v": 1.0 if m["result"] == "yes" else 0.0, "volume": m["volume"] or 0,
                             "bid": bid, "ask": ask, "vol": vol})
    out = sorted(ev.values(), key=lambda e: e["close"])
    for e in out:
        e["markets"].sort(key=lambda m: (m["floor"] if m["floor"] is not None else -1))
    return out


def two_sided(bid, ask):
    return np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask < 1) & (ask > bid)


def implied_level(event):
    """Index level implied by an "X or above" ladder at every minute: the strike where the mid crosses 50c
    (linear between the two neighbouring strikes that have a two-sided quote no wider than 20c)."""
    ms = [m for m in event["markets"] if m["type"] in ("greater", "greater_or_equal") and m["floor"] is not None]
    K = np.array([m["floor"] for m in ms])
    B, A = np.array([m["bid"] for m in ms]), np.array([m["ask"] for m in ms])
    ok = two_sided(B, A) & (A - B <= 0.20)
    mid = np.where(ok, (A + B) / 2, np.nan)
    out = np.full(WIN + 1, np.nan)
    for i in range(WIN + 1):
        j = np.where(ok[:, i])[0]
        if len(j) < 2:
            continue
        k, p = K[j], mid[j, i]
        hi = np.where(p >= 0.5)[0]
        lo = np.where(p < 0.5)[0]
        if not len(hi) or not len(lo):
            continue
        a, b = hi[-1], lo[0]                   # highest strike still >= 50c, lowest strike below 50c
        if b != a + 1 or k[b] - k[a] > 0.004 * k[a]:   # non-monotonic quotes or a hole in the ladder
            continue
        out[i] = k[a] + (p[a] - 0.5) / (p[a] - p[b]) * (k[b] - k[a])
    return out


def yahoo(sym, interval="5m"):
    path = f"{DATA}/yahoo_{sym}_{interval}.json"
    if not os.path.exists(path):
        return {}
    return {int(k): v[3] for k, v in json.load(open(path)).items()}       # bar start ts -> close


def yahoo_level(bars5, close):
    """Yahoo index level on the minute grid, known at that minute: the close of the 5-minute bar that ENDED
    at or before it (only filled on 5-minute boundaries of the regular session)."""
    out = np.full(WIN + 1, np.nan)
    t0 = close - WIN * 60
    for i in range(WIN + 1):
        t = t0 + i * 60
        if (close - t) % 300 == 0 and close - t <= 385 * 60:
            v = bars5.get(t - 300)
            if v is not None:
                out[i] = v
    return out
