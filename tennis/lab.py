"""Tennis strategy lab (python -m tennis lab): thousands of value strategies scored on every settled match.

Same honesty rules as the crypto lab:
  * A bet is decided from one minute's prices and filled in the NEXT minute at that minute's worst price
    (YES at its ask high, NO at 1 - its bid low): the bot's delay and no lucky fills.
  * It pays what Kalshi actually settled (1, 0, or the fair price of a match never played), minus Kalshi's fee.
  * Strategies are ranked only on days before the day they are judged on (walk-forward), so a leaderboard
    position is never a peek at the future.

Families (each match has one market per player; backing a player = YES on their market):
  band   at minute M of the match clock (M < 0 = before the start), back a player whose mid price is in [lo, hi)
  swing  in play, when a player's mid moves by d or more within w minutes: back the bounce (rev) or the move (mom)
Every rule bets at most once per market.
"""
from __future__ import annotations

import json
import math
import random
import time
from collections import defaultdict

import numpy as np

from . import api
from .history import STORE

MINUTES = [-120, -60, -30, -10, 0, 15, 30, 60, 90, 120]
WIDTHS = [0.10, 0.15, 0.20]
LOS = [round(0.05 * i, 2) for i in range(1, 19)]
SWING_W = [5, 10, 20, 30]
SWING_D = [0.05, 0.10, 0.15, 0.20, 0.25]
PHASES = {"early": (0, 60), "late": (60, 240), "all": (0, 240)}
MIN_BETS = 30


def load(path=STORE):
    ms = []
    for ln in open(path):
        m = json.loads(ln)
        b = np.array([[x if x is not None else np.nan for x in r] for r in m["bars"]], float) if m["bars"] else np.zeros((0, 6))
        if len(b) < 10:
            continue
        v = m.get("value")
        if v is None:
            v = 1.0 if m.get("result") == "yes" else 0.0 if m.get("result") == "no" else None
        if v is None:
            continue
        rel = (b[:, 0] - m["start"]) / 60.0
        bid, bidlo, ask, askhi = b[:, 1], b[:, 2], b[:, 3], b[:, 4]
        mid = np.where(np.isfinite(bid) & np.isfinite(ask), (bid + ask) / 2, np.nan)
        ms.append({"ticker": m["ticker"], "event": m["event"], "series": m["series"], "player": m.get("player"),
                   "day": int(m["start"] // 86400), "start": m["start"], "value": float(v),
                   "rel": rel, "mid": mid, "bidlo": bidlo, "askhi": askhi})
    return ms


def strategies():
    out = []
    for M in MINUTES:
        for w in WIDTHS:
            for lo in LOS:
                hi = round(lo + w, 2)
                if hi <= 0.98:
                    out.append({"id": f"band:m{M}:{lo:.2f}-{hi:.2f}", "fam": "band", "M": M, "lo": lo, "hi": hi})
    for ph in PHASES:
        for w in SWING_W:
            for d in SWING_D:
                for direction in ("down", "up"):
                    for act in ("rev", "mom"):
                        out.append({"id": f"swing:{ph}:{direction}{d:.2f}/{w}m:{act}", "fam": "swing", "phase": ph,
                                    "w": w, "d": d, "dir": direction, "act": act})
    return out


def _fill(m, i, side):
    """Fill in the bar after index i (within 3 minutes): YES at ask high, NO at 1 - bid low -> price or None."""
    j = i + 1
    if j >= len(m["rel"]) or m["rel"][j] - m["rel"][i] > 3.01:
        return None
    p = m["askhi"][j] if side == "yes" else (1 - m["bidlo"][j] if np.isfinite(m["bidlo"][j]) else np.nan)
    return float(p) if np.isfinite(p) and 0.02 <= p <= 0.98 else None


def _pay(m, side, p):
    win = m["value"] if side == "yes" else 1 - m["value"]
    return win - p - api.fee(p, 1)


def bet(m, s):
    """The one bet strategy s makes on market m -> (side, price, pnl, minute) or None."""
    rel, mid = m["rel"], m["mid"]
    if s["fam"] == "band":
        idx = np.nonzero(rel <= s["M"])[0]
        if not len(idx):
            return None
        i = idx[-1]
        if s["M"] - rel[i] > 10 or not np.isfinite(mid[i]) or not (s["lo"] <= mid[i] < s["hi"]):
            return None
        p = _fill(m, i, "yes")
        return None if p is None else ("yes", p, _pay(m, "yes", p), float(rel[i]))
    a, b = PHASES[s["phase"]]
    w, d = s["w"], s["d"]
    sel = np.nonzero((rel >= a) & (rel < b))[0]
    for i in sel:
        if not np.isfinite(mid[i]) or not (0.10 <= mid[i] <= 0.90):
            continue
        past = np.nonzero((rel >= rel[i] - w) & (rel < rel[i]))[0]
        if not len(past):
            continue
        ref = mid[past[0]]
        if not np.isfinite(ref):
            continue
        ch = mid[i] - ref
        if (s["dir"] == "down" and ch <= -d) or (s["dir"] == "up" and ch >= d):
            back = (s["dir"] == "down") == (s["act"] == "rev")     # back this player?
            side = "yes" if back else "no"
            p = _fill(m, i, side)
            return None if p is None else (side, p, _pay(m, side, p), float(rel[i]))
    return None


def score(ms, strats, log=print):
    """-> {strategy id: {day: [pnl, n, sumsq]}} over every market."""
    t0 = time.time()
    daily = {s["id"]: defaultdict(lambda: [0.0, 0, 0.0]) for s in strats}
    for k, m in enumerate(ms):
        for s in strats:
            r = bet(m, s)
            if r:
                c = daily[s["id"]][m["day"]]
                c[0] += r[2]; c[1] += 1; c[2] += r[2] ** 2
    log(f"  scored {len(strats)} strategies on {len(ms)} markets ({time.time() - t0:.0f}s)")
    return {k: dict(v) for k, v in daily.items()}


def _t(n, s, q):
    if n < 3:
        return -9.0
    mu = s / n
    var = (q - n * mu * mu) / (n - 1)
    return mu / math.sqrt(var / n) if var > 0 else -9.0


def stats(daily, days=None):
    n = s = q = 0.0
    for d, (ps, pn, pq) in daily.items():
        if days is None or d in days:
            s += ps; n += pn; q += pq
    return n, s, _t(n, s, q)


def walk(daily, warmup=7, ks=(1, 5, 20)):
    """Walk-forward test of 'trust the leaderboard': on each day, rank strategies on the days before it only
    (>= MIN_BETS bets, by t), back the top K that day, and compare with backing every eligible strategy."""
    days = sorted({d for v in daily.values() for d in v})
    res = {k: [] for k in ks}
    base = []
    for i, d in enumerate(days):
        if i < warmup:
            continue
        prior = set(days[:i])
        ranked = []
        for sid, v in daily.items():
            n, s, t = stats(v, prior)
            if n >= MIN_BETS:
                ranked.append((t, sid))
        if not ranked:
            continue
        ranked.sort(reverse=True)
        per_bet = lambda ids: (sum(daily[x].get(d, [0, 0, 0])[0] for x in ids), sum(daily[x].get(d, [0, 0, 0])[1] for x in ids))
        for k in ks:
            p, n = per_bet([x for _, x in ranked[:k]])
            res[k].append((p, n))
        p, n = per_bet([x for _, x in ranked])
        base.append((p, n))
    agg = lambda xs: (round(sum(p for p, _ in xs) / max(sum(n for _, n in xs), 1), 4), int(sum(n for _, n in xs)), len(xs))
    return {"days": len(days), "test_days": len(base), "top": {k: agg(v) for k, v in res.items()}, "all": agg(base)}


def mutate(s, rng):
    """A nearby variant of strategy s (the breeding step of the learning loop)."""
    c = dict(s)
    if s["fam"] == "band":
        c["M"] = int(s["M"] + rng.choice([-15, -5, 5, 15]))
        lo = round(min(0.9, max(0.02, s["lo"] + rng.choice([-0.03, -0.02, 0.02, 0.03]))), 2)
        hi = round(min(0.98, max(lo + 0.04, s["hi"] + rng.choice([-0.03, -0.02, 0.02, 0.03]))), 2)
        c.update(lo=lo, hi=hi, id=f"band:m{c['M']}:{lo:.2f}-{hi:.2f}")
    else:
        c["w"] = int(max(2, s["w"] + rng.choice([-5, -2, 2, 5])))
        c["d"] = round(max(0.03, s["d"] + rng.choice([-0.03, -0.02, 0.02, 0.03])), 2)
        c["id"] = f"swing:{c['phase']}:{c['dir']}{c['d']:.2f}/{c['w']}m:{c['act']}"
    return c
