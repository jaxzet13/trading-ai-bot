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
  drift  before the start (or at it), when a player's mid moved by d or more over the L minutes up to minute M:
         back the move (mom: follow the money) or fade it (rev); one bet at minute M
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

MINUTES = list(range(-180, 181, 10))           # match clock, every 10 min from 3 h before to 3 h into play
WIDTHS = [0.05, 0.10, 0.15, 0.20]
LOS = [round(0.05 * i, 2) for i in range(1, 19)]
# tour filter: a strategy can be limited to one kind of tennis ("all" keeps the old ids unchanged)
SCOPES = {"all": None, "atp": {"KXATPMATCH"}, "wta": {"KXWTAMATCH"},
          "chal": {"KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH"}, "itf": {"KXITFMATCH", "KXITFWMATCH"}}
SCOPE_NAME = {"all": "", "atp": "ATP", "wta": "WTA", "chal": "Challenger", "itf": "ITF"}
SWING_W = [5, 10, 20, 30]
SWING_D = [0.05, 0.10, 0.15, 0.20, 0.25]
PHASES = {"early": (0, 60), "late": (60, 240), "all": (0, 240)}
DRIFT_M = [-120, -60, -30, -10, 0]
DRIFT_L = [30, 60, 120, 240]
DRIFT_D = [0.03, 0.05, 0.08, 0.12]
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


def _sid(base, scope):
    return base if scope == "all" else f"{base}:{scope}"


def strategies():
    out = []
    for scope in SCOPES:
        for M in MINUTES:
            for w in WIDTHS:
                for lo in LOS:
                    hi = round(lo + w, 2)
                    if hi <= 0.98:
                        out.append({"id": _sid(f"band:m{M}:{lo:.2f}-{hi:.2f}", scope), "fam": "band", "M": M,
                                    "lo": lo, "hi": hi, "scope": scope})
        for ph in PHASES:
            for w in SWING_W:
                for d in SWING_D:
                    for direction in ("down", "up"):
                        for act in ("rev", "mom"):
                            out.append({"id": _sid(f"swing:{ph}:{direction}{d:.2f}/{w}m:{act}", scope), "fam": "swing",
                                        "phase": ph, "w": w, "d": d, "dir": direction, "act": act, "scope": scope})
        for M in DRIFT_M:
            for L in DRIFT_L:
                for d in DRIFT_D:
                    for direction in ("down", "up"):
                        for act in ("rev", "mom"):
                            out.append(_drift(M, L, d, direction, act, scope))
    return out


def _drift(M, L, d, direction, act, scope):
    return {"id": _sid(f"drift:m{M}:{direction}{d:.2f}/{L}m:{act}", scope), "fam": "drift", "M": M, "L": L,
            "d": d, "dir": direction, "act": act, "scope": scope}


def _bar_at(rel, t):
    """Index of the last bar at or before minute t, if it is within 10 minutes of t, else None."""
    i = int(np.searchsorted(rel, t, side="right")) - 1
    return i if i >= 0 and t - rel[i] <= 10 else None


def in_scope(m, s):
    sc = SCOPES.get(s.get("scope", "all"))
    return sc is None or m["series"] in sc


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
    if not in_scope(m, s):
        return None
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
    if s["fam"] == "drift":
        i, j = _bar_at(rel, s["M"]), _bar_at(rel, s["M"] - s["L"])
        if i is None or j is None or j >= i or not (np.isfinite(mid[i]) and np.isfinite(mid[j])):
            return None
        if not 0.10 <= mid[i] <= 0.90:
            return None
        ch = mid[i] - mid[j]
        if not ((s["dir"] == "up" and ch >= s["d"]) or (s["dir"] == "down" and ch <= -s["d"])):
            return None
        side = "yes" if (s["dir"] == "up") == (s["act"] == "mom") else "no"
        p = _fill(m, i, side)
        return None if p is None else (side, p, _pay(m, side, p), float(rel[i]))
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
        c.update(lo=lo, hi=hi, id=_sid(f"band:m{c['M']}:{lo:.2f}-{hi:.2f}", s.get("scope", "all")))
    elif s["fam"] == "drift":
        M = int(min(0, s["M"] + rng.choice([-10, -5, 5, 10])))
        L = int(max(10, s["L"] + rng.choice([-30, -15, 15, 30])))
        d = round(max(0.02, s["d"] + rng.choice([-0.02, -0.01, 0.01, 0.02])), 2)
        c = _drift(M, L, d, s["dir"], s["act"], s.get("scope", "all"))
    else:
        c["w"] = int(max(2, s["w"] + rng.choice([-5, -2, 2, 5])))
        c["d"] = round(max(0.03, s["d"] + rng.choice([-0.03, -0.02, 0.02, 0.03])), 2)
        c["id"] = _sid(f"swing:{c['phase']}:{c['dir']}{c['d']:.2f}/{c['w']}m:{c['act']}", s.get("scope", "all"))
    return c


# ---------------------------------------------------------------------------------------------------------------
# Fast scoring: the same rules as bet(), computed for every market at once so thousands of strategies fit in a
# round. tests/test_tennis.py checks that score_matrix() gives exactly what bet() gives, bet by bet.

def _fee_vec(p):
    return np.ceil(api.TAKER_RATE * p * (1 - p) * 100 - 1e-9) / 100


def _scope_masks(ms):
    series = np.array([m["series"] for m in ms])
    return {k: (np.ones(len(ms), bool) if v is None else np.isin(series, list(v))) for k, v in SCOPES.items()}


def _band_arrays(ms, M):
    """Per market, what a band rule at minute M sees: (ok, mid at the decision bar, fill price, pnl backing YES)."""
    n = len(ms)
    ok = np.zeros(n, bool); mid = np.full(n, np.nan); price = np.full(n, np.nan); pay = np.zeros(n)
    for k, m in enumerate(ms):
        rel = m["rel"]
        i = np.searchsorted(rel, M, side="right") - 1
        if i < 0 or M - rel[i] > 10 or not np.isfinite(m["mid"][i]):
            continue
        j = i + 1
        if j >= len(rel) or rel[j] - rel[i] > 3.01:
            continue
        p = m["askhi"][j]
        if not (np.isfinite(p) and 0.02 <= p <= 0.98):
            continue
        ok[k], mid[k], price[k] = True, m["mid"][i], p
        pay[k] = m["value"] - p - _fee_vec(p)
    return ok, mid, price, pay


def _swing_arrays(ms, phase, w, d, direction):
    """Per market, the first in-play trigger of a swing rule and the pnl of backing (yes) / opposing (no) it."""
    a, b = PHASES[phase]
    n = len(ms)
    ok_y = np.zeros(n, bool); ok_n = np.zeros(n, bool); pay_y = np.zeros(n); pay_n = np.zeros(n)
    for k, m in enumerate(ms):
        rel, mid = m["rel"], m["mid"]
        idx = np.arange(len(rel))
        j = np.searchsorted(rel, rel - w, side="left")
        refok = (j < idx) & np.isfinite(mid[np.minimum(j, len(rel) - 1)])
        ch = mid - mid[np.minimum(j, len(rel) - 1)]
        cond = ((rel >= a) & (rel < b) & np.isfinite(mid) & (mid >= 0.10) & (mid <= 0.90) & refok
                & ((ch <= -d) if direction == "down" else (ch >= d)))
        hit = np.nonzero(cond)[0]
        if not len(hit):
            continue
        i = hit[0]
        if i + 1 >= len(rel) or rel[i + 1] - rel[i] > 3.01:
            continue
        py = m["askhi"][i + 1]
        if np.isfinite(py) and 0.02 <= py <= 0.98:
            ok_y[k], pay_y[k] = True, m["value"] - py - _fee_vec(py)
        bl = m["bidlo"][i + 1]
        pn = 1 - bl if np.isfinite(bl) else np.nan
        if np.isfinite(pn) and 0.02 <= pn <= 0.98:
            ok_n[k], pay_n[k] = True, (1 - m["value"]) - pn - _fee_vec(pn)
    return ok_y, pay_y, ok_n, pay_n


def _drift_arrays(ms, M, L):
    """Per market, what a drift rule (M, L) sees: (mid at M, change over L, ok/pnl backing yes, ok/pnl backing no)."""
    n = len(ms)
    mid_i = np.full(n, np.nan); ch = np.full(n, np.nan)
    ok_y = np.zeros(n, bool); ok_n = np.zeros(n, bool); pay_y = np.zeros(n); pay_n = np.zeros(n)
    for k, m in enumerate(ms):
        rel, mid = m["rel"], m["mid"]
        i, j = _bar_at(rel, M), _bar_at(rel, M - L)
        if i is None or j is None or j >= i or not (np.isfinite(mid[i]) and np.isfinite(mid[j])):
            continue
        mid_i[k], ch[k] = mid[i], mid[i] - mid[j]
        if i + 1 >= len(rel) or rel[i + 1] - rel[i] > 3.01:
            continue
        py = m["askhi"][i + 1]
        if np.isfinite(py) and 0.02 <= py <= 0.98:
            ok_y[k], pay_y[k] = True, m["value"] - py - _fee_vec(py)
        bl = m["bidlo"][i + 1]
        pn = 1 - bl if np.isfinite(bl) else np.nan
        if np.isfinite(pn) and 0.02 <= pn <= 0.98:
            ok_n[k], pay_n[k] = True, (1 - m["value"]) - pn - _fee_vec(pn)
    return mid_i, ch, ok_y, pay_y, ok_n, pay_n


def score_matrix(ms, strats, log=print):
    """-> (days, P, N, Q): per strategy (rows, in strats order) and day (columns) the P&L, bets and P&L^2."""
    t0 = time.time()
    days = np.array(sorted({m["day"] for m in ms}))
    dix = np.searchsorted(days, np.array([m["day"] for m in ms]))
    D, S = len(days), len(strats)
    P, N, Q = np.zeros((S, D)), np.zeros((S, D)), np.zeros((S, D))
    scope = _scope_masks(ms)
    by_m, by_sw, by_dr = defaultdict(list), defaultdict(list), defaultdict(list)
    for r, s in enumerate(strats):
        if s["fam"] == "band":
            by_m[s["M"]].append(r)
        elif s["fam"] == "drift":
            by_dr[(s["M"], s["L"])].append(r)
        else:
            by_sw[(s["phase"], s["w"], s["d"], s["dir"])].append(r)
    def put(r, mask, pay):
        P[r] = np.bincount(dix[mask], pay[mask], D)
        N[r] = np.bincount(dix[mask], None, D)
        Q[r] = np.bincount(dix[mask], pay[mask] ** 2, D)
    for M, rows in by_m.items():
        ok, mid, _, pay = _band_arrays(ms, M)
        for r in rows:
            s = strats[r]
            put(r, ok & (mid >= s["lo"]) & (mid < s["hi"]) & scope[s.get("scope", "all")], pay)
    for (ph, w, d, dr), rows in by_sw.items():
        ok_y, pay_y, ok_n, pay_n = _swing_arrays(ms, ph, w, d, dr)
        for r in rows:
            s = strats[r]
            back = (dr == "down") == (s["act"] == "rev")
            sc = scope[s.get("scope", "all")]
            put(r, (ok_y if back else ok_n) & sc, pay_y if back else pay_n)
    for (M, L), rows in by_dr.items():
        mid_i, ch, ok_y, pay_y, ok_n, pay_n = _drift_arrays(ms, M, L)
        with np.errstate(invalid="ignore"):
            band = (mid_i >= 0.10) & (mid_i <= 0.90)
            for r in rows:
                s = strats[r]
                moved = (ch >= s["d"]) if s["dir"] == "up" else (ch <= -s["d"])
                back = (s["dir"] == "up") == (s["act"] == "mom")
                put(r, band & moved & (ok_y if back else ok_n) & scope[s.get("scope", "all")], pay_y if back else pay_n)
    log(f"  scored {S} strategies on {len(ms)} markets ({time.time() - t0:.0f}s)")
    return days, P, N, Q


def metrics(days, P, N, Q, hold_frac=1 / 3):
    """Consistency of every strategy: totals, t, days up, worst drawdown, and history vs hold-out (the last third
    of the days, which the leaderboard ranking never uses)."""
    D = len(days)
    cut = int(round(D * (1 - hold_frac)))
    def t_of(p, n, q):
        mu = np.divide(p, n, out=np.zeros_like(p), where=n > 0)
        var = np.divide(q - n * mu * mu, n - 1, out=np.zeros_like(p), where=n > 1)
        se = np.sqrt(np.divide(var, n, out=np.full_like(p, np.inf), where=n > 0))
        return np.where((n >= 3) & (var > 0), mu / np.where(se > 0, se, np.inf), -9.0)
    n, p, q = N.sum(1), P.sum(1), Q.sum(1)
    ns, ps, qs = N[:, :cut].sum(1), P[:, :cut].sum(1), Q[:, :cut].sum(1)
    nh, ph, qh = N[:, cut:].sum(1), P[:, cut:].sum(1), Q[:, cut:].sum(1)
    cum = np.cumsum(P, 1)
    dd = (np.maximum.accumulate(np.maximum(cum, 0), 1) - cum).max(1)
    return {"n": n, "pnl": p, "t": t_of(p, n, q), "days_up": (P > 0).sum(1), "days_active": (N > 0).sum(1),
            "max_dd": dd, "n_hist": ns, "pnl_hist": ps, "t_hist": t_of(ps, ns, qs),
            "n_hold": nh, "pnl_hold": ph, "t_hold": t_of(ph, nh, qh), "cut_day": int(days[cut]) if cut < D else None}


def walk_matrix(P, N, Q, warmup=7, ks=(1, 5, 20, 50)):
    """Vectorized lab.walk(): on each day rank strategies on the days before it only (>= MIN_BETS bets, by t),
    back the top K that day, compare with backing every eligible strategy."""
    D = P.shape[1]
    cP, cN, cQ = np.cumsum(P, 1), np.cumsum(N, 1), np.cumsum(Q, 1)
    res = {k: [0.0, 0.0] for k in ks}
    base = [0.0, 0.0]
    tdays = 0
    for i in range(warmup, D):
        n, p, q = cN[:, i - 1], cP[:, i - 1], cQ[:, i - 1]
        elig = n >= MIN_BETS
        if not elig.any():
            continue
        mu = np.divide(p, n, out=np.zeros_like(p), where=n > 0)
        var = np.divide(q - n * mu * mu, n - 1, out=np.zeros_like(p), where=n > 1)
        t = np.where(elig & (var > 0), mu / np.sqrt(np.where(var > 0, var, 1) / np.where(n > 0, n, 1)), -np.inf)
        order = np.argsort(-t)
        tdays += 1
        for k in ks:
            top = order[:k]
            top = top[np.isfinite(t[top])]
            res[k][0] += P[top, i].sum(); res[k][1] += N[top, i].sum()
        base[0] += P[elig, i].sum(); base[1] += N[elig, i].sum()
    agg = lambda x: (round(x[0] / max(x[1], 1), 4), int(x[1]))
    return {"test_days": tdays, "top": {k: agg(v) for k, v in res.items()}, "all": agg(base)}
