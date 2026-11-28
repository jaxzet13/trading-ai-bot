"""Step 3 of the whole-sports scan: is ANY kind of Kalshi sports market, at any price, mispriced? (Nov 28 2026)

Rows: every traded settled market at 3.5 / 5 / 8 hours before its expected expiration (game markets: ~30 min / 2 h / 5 h
before kickoff), using the hourly quote at that time, a 1c slip on top of the ask (the next-minute fill the other tests
use is not available on hourly bars), and Kalshi's fee. Needs some trading beforehand (>= 10 contracts) and a spread <= 8c.

Strategies = (group, side, price band, hours before): group is the exact series (player points, 1st-half spread, both
teams to score, corners, ...), the market TYPE across all sports (every totals market, every BTTS market ...) or the sport
across all types. Price bands are 10c wide every 5c. Judged honestly, like the crypto and tennis searches:
  * walk-forward: each test day bets the top K (1/5/20) strategies ranked by t on EARLIER days only (>= 30 bets)
  * hold-out: rank on the first two thirds of the days, score the last third
  * the luck benchmark: with S strategies the best t by chance alone is about sqrt(2 ln S)
Also the plain pooled calibration of the biggest market types (win rate minus cost, by price), which is the least
fishy number here.

    python3 research/sports_universe/analyze.py            -> research/sports_universe/results.json
"""
import collections
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np

D = Path("data/sports_universe")
OUT = Path("research/sports_universe/results.json")
HS = (3.5, 5.0, 8.0)
WARM = 8
T0 = time.time()
TYPES = ["GAME", "SPREAD", "TOTAL", "BTTS", "PTS", "REB", "AST", "3PT", "STL", "BLK", "PRA", "MATCH", "1HSPREAD", "1HTOTAL",
         "1HBTTS", "2HSPREAD", "2HTOTAL", "TCORNERS", "CORNERS", "FTTS", "MOV", "ML", "WINNER", "FIGHT", "H2H", "MAP", "ROUND"]


def log(*a):
    print(f"[{time.time() - T0:5.0f}s]", *a, flush=True)


def fee(p):
    return 0.07 * p * (1 - p)


def split(series):
    """KXNBAPTS -> ('NBA', 'PTS'); unknown suffix -> (series without KX, 'OTHER')."""
    s = series[2:] if series.startswith("KX") else series
    for t in sorted(TYPES, key=len, reverse=True):
        if s.endswith(t) and len(s) > len(t):
            return s[:-len(t)], t
    return s, "OTHER"


def main():
    meta = {}
    for ln in open(D / "markets.jsonl"):
        m = json.loads(ln)
        meta[m["t"]] = m
    names, rows = {}, collections.defaultdict(list)
    ser_ids, typ_ids, sport_ids = {}, {}, {}
    R = {k: [] for k in ("ser", "typ", "sport", "h", "bid", "ask", "y", "day")}
    n_mk = 0
    for ln in open(D / "prices.jsonl"):
        p = json.loads(ln)
        m = meta.get(p["t"])
        if not m or not p["b"]:
            continue
        n_mk += 1
        sport, typ = split(m["s"])
        sid = ser_ids.setdefault(m["s"], len(ser_ids))
        tid = typ_ids.setdefault(typ, len(typ_ids))
        spid = sport_ids.setdefault(sport, len(sport_ids))
        x = p["x"]
        b = p["b"]
        for hi, h in enumerate(HS):
            tref = x - h * 3600
            k = -1
            for j, bar in enumerate(b):
                if bar[0] <= tref:
                    k = j
            if k < 0 or x - b[k][0] > (h + 3) * 3600:
                continue
            bid, ask = b[k][1], b[k][2]
            if ask - bid > 0.08 or sum(bar[3] for bar in b[:k + 1]) < 10:
                continue
            for key, val in (("ser", sid), ("typ", tid), ("sport", spid), ("h", hi), ("bid", bid), ("ask", ask),
                             ("y", float(m["r"] == "yes")), ("day", x // 86400)):
                R[key].append(val)
    R = {k: np.array(v) for k, v in R.items()}
    inv = lambda d: {v: k for k, v in d.items()}
    sname, tname, spname = inv(ser_ids), inv(typ_ids), inv(sport_ids)
    days = np.unique(R["day"])
    D_ = len(days)
    di = np.searchsorted(days, R["day"])
    log(f"{n_mk:,} markets, {len(R['y']):,} rows, {len(ser_ids)} series, {len(typ_ids)} types, {len(sport_ids)} sports, {D_} days")

    # entries: (row, side) -> price, pnl
    ent = []
    for side in (1, -1):
        price = np.minimum((R["ask"] if side == 1 else 1 - R["bid"]) + 0.01, 0.99)
        win = R["y"] if side == 1 else 1 - R["y"]
        pnl = win - price - fee(price)
        for off in (0.0, 0.05):                          # two overlapping 10c grids
            lo = np.floor((price - off) / 0.10) * 0.10 + off
            ok = (price >= 0.05) & (price <= 0.95)
            ent.append((side, lo, pnl, ok))
    strat = {}                                            # key -> [P(D), N(D), Q(D)]
    groups = (("ser", R["ser"], sname, "S"), ("typ", R["typ"], tname, "T"), ("sport", R["sport"], spname, "P"))
    for gname, gid, gnames, tag in groups:
        for side, lo, pnl, ok in ent:
            band = np.round(lo * 100).astype(int)
            key = ((gid.astype(np.int64) * 2 + (side == 1)) * 100 + band) * 3 + R["h"]
            key = np.where(ok, key, -1)
            uk, inv_k = np.unique(key[key >= 0], return_inverse=True)
            sel = np.nonzero(key >= 0)[0]
            idx = inv_k * D_ + di[sel]
            P = np.bincount(idx, pnl[sel], len(uk) * D_).reshape(len(uk), D_)
            N = np.bincount(idx, None, len(uk) * D_).reshape(len(uk), D_)
            Q = np.bincount(idx, pnl[sel] ** 2, len(uk) * D_).reshape(len(uk), D_)
            for i, k in enumerate(uk):
                if N[i].sum() < 30:
                    continue
                h = int(k % 3); r = k // 3; bnd = int(r % 100); r //= 100; sd = int(r % 2); g = int(r // 2)
                name = f"{tag}|{gnames[g]}|{'YES' if sd else 'NO'}|{bnd}-{bnd + 10}c|{HS[h]}h"
                a = strat.setdefault(name, [np.zeros(D_), np.zeros(D_), np.zeros(D_)])
                a[0] += P[i]; a[1] += N[i]; a[2] += Q[i]
    names = list(strat)
    P = np.array([strat[n][0] for n in names]); N = np.array([strat[n][1] for n in names]); Q = np.array([strat[n][2] for n in names])
    log(f"{len(names):,} strategies with >= 30 bets")

    def tstat(p, n, q):
        with np.errstate(all="ignore"):
            m = p / n
            v = np.maximum(q / n - m * m, 1e-9)
            t = m / np.sqrt(v) * np.sqrt(n)
        return np.where(n >= 30, t, -np.inf)

    res = {"markets": n_mk, "rows": int(len(R["y"])), "days": int(D_), "strategies": len(names),
           "luck_best_t": round(math.sqrt(2 * math.log(len(names))), 2)}
    t_all = tstat(P.sum(1), N.sum(1), Q.sum(1))
    order = np.argsort(-t_all)[:25]
    res["in_sample_top25_not_a_result"] = [(names[j], round(float(t_all[j]), 2), int(N[j].sum()), round(100 * float(P[j].sum() / N[j].sum()), 2)) for j in order]
    log("in-sample best (NOT a result):", res["in_sample_top25_not_a_result"][:5], "| luck alone ~", res["luck_best_t"])
    cP, cN, cQ = np.cumsum(P, 1), np.cumsum(N, 1), np.cumsum(Q, 1)
    for K in (1, 5, 20):
        dd, nb = [], 0
        for i in range(WARM, D_):
            t = tstat(cP[:, i - 1], cN[:, i - 1], cQ[:, i - 1])
            top = np.argpartition(-t, K)[:K]
            top = [j for j in top if np.isfinite(t[j])]
            if not top:
                dd.append(0.0); continue
            dd.append(P[top, i].sum() / K); nb += int(N[top, i].sum())
        dd = np.array(dd)
        tt = float(dd.mean() / dd.std(ddof=1) * math.sqrt(len(dd))) if dd.std(ddof=1) > 0 else 0.0
        res[f"walk_top{K}"] = {"usd_per_day_per_strategy": round(float(dd.mean()), 3), "t": round(tt, 2), "bets": nb,
                               "days": int(len(dd)), "cents_per_bet": round(100 * float(dd.sum() * K / max(nb, 1)), 2),
                               "halves": [round(float(dd[:len(dd) // 2].mean()), 3), round(float(dd[len(dd) // 2:].mean()), 3)]}
        log(f"walk-forward top {K}:", res[f"walk_top{K}"])
    cut = WARM + int((D_ - WARM) * 2 / 3)
    best = np.argsort(-tstat(P[:, :cut].sum(1), N[:, :cut].sum(1), Q[:, :cut].sum(1)))[:5]
    res["holdout_top5"] = [(names[j], int(N[j, cut:].sum()), round(100 * float(P[j, cut:].sum() / max(N[j, cut:].sum(), 1)), 2)) for j in best]
    log("hold-out (rank on first two thirds, score the last third):", res["holdout_top5"])
    # pooled calibration by market type: the plain evidence
    cal = []
    for n_, i in ((n, i) for i, n in enumerate(names)):
        if n_.startswith("T|") and N[i].sum() >= 300:
            cal.append((n_, int(N[i].sum()), round(100 * float(P[i].sum() / N[i].sum()), 2), round(float(tstat(P[i:i + 1].sum(1), N[i:i + 1].sum(1), Q[i:i + 1].sum(1))[0]), 2)))
    cal.sort(key=lambda r: -r[3])
    res["type_calibration_top"] = cal[:20]
    res["type_calibration_bottom"] = cal[-10:]
    json.dump(res, open(OUT, "w"), indent=1, default=float)
    log("done")


if __name__ == "__main__":
    main()
