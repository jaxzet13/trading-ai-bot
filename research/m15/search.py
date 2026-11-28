"""Millions of strategies on every Kalshi 15-minute market, judged honestly (Nov 28 2026).

Account holder: "Backtest all those 15m coins, and backtest with millions of strategies and find the most profitable".

Data: for the 9 crypto coins the stored quote panels (kalshi15m), for the other 19 series (gold, oil, metals, currencies, S&P,
Treasury yields) data/m15 from download.py. Only Kalshi's OWN quote path inside the 15-minute window is used (no outside price
feed exists for most of them), so these are "market behaviour" strategies, not the live crypto model's spot-price edge.

Every decision is taken on minute j's quotes (j = 1..13) and filled the NEXT minute at the ask (YES) or 1 - bid (NO), price 5-95c,
Kalshi's fee. Inputs at minute j: mid, spread, mid change over 1/3/5 minutes, drift since the window opened, distance from 50c,
range so far, acceleration (9 of them). A strategy = (group, minute, side, one input in a decile) or (two inputs in two deciles)
= 90 + 3,600 cells per group, minute and side. Groups: each series, five sectors, everything pooled.

Judged like the crypto and tennis searches:
  * walk-forward: each test day bets the top K (1/5/20) strategies by t on EARLIER days only (>= 30 bets), deciles from the
    first WARM days; the merged "best of everything" version too
  * hold-out: rank on the first two thirds of the days, score the last third
  * the luck benchmark: with S strategies the best t by chance alone is about sqrt(2 ln S)

    python3 research/m15/search.py   -> research/m15/results.json
"""
import collections
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")

D = Path("data/m15")
import os as _os
OUT = Path(_os.environ.get("M15_OUT", "research/m15/results.json"))
WARM = 14
FEATS = ["mid", "spr", "d1", "d3", "d5", "drift", "ext", "rng", "acc"]
NF = len(FEATS)
PAIRS = [(a, b) for a in range(NF) for b in range(a + 1, NF)]
TRIPLES = [(a, b, c) for a in range(NF) for b in range(a + 1, NF) for c in range(b + 1, NF)]
NCELL = NF * 10 + len(PAIRS) * 100 + len(TRIPLES) * 27
JS = list(range(1, 14))
SECTORS = {
    "METALS": ["KXGOLD15M", "KXSILVER15M", "KXCOPPER15M", "KXPLATINUM15M", "KXPALLADIUM15M"],
    "ENERGY": ["KXWTI15M", "KXBRENT15M", "KXNATGAS15M"],
    "FX": ["KXUSDJPY15M", "KXEURUSD15M", "KXAUDUSD15M", "KXGBPUSD15M", "KXUSDCAD15M", "KXUSDMXN15M"],
    "RATES": ["KX2YRRATE15M", "KX5YRRATE15M", "KX10YRRATE15M", "KX30YRRATE15M"],
    "CRYPTO": ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M", "KXNEAR15M", "KXHYPE15M", "KXZEC15M", "KXBNB15M"],
}
T0 = time.time()
DAYS = {}
GEN = [0]


def log(*a):
    print(f"[{time.time() - T0:5.0f}s]", *a, flush=True)


def fee(p):
    return 0.07 * p * (1 - p)


def load_series():
    """series -> (bid[W,15], ask[W,15], y[W], day[W]) with minute index j = 0..14 holding the quote at open + 60 j (NaN if none)."""
    out = {}
    for p in sorted(D.glob("*.jsonl")):
        seen, recs = set(), []
        for ln in open(p):
            r = json.loads(ln)
            if r["bars"] and r["t"] not in seen:          # two downloaders can overlap: keep each window once
                seen.add(r["t"]); recs.append(r)
        W = len(recs)
        bid = np.full((W, 15), np.nan); ask = np.full((W, 15), np.nan)
        y = np.zeros(W); day = np.zeros(W, dtype=np.int64)
        for i, r in enumerate(recs):
            open_ts = r["close"] - 900
            for e, b, a, v in r["bars"]:
                j = (e - open_ts) // 60
                if 0 <= j <= 14 and (e - open_ts) % 60 == 0:
                    bid[i, j], ask[i, j] = b, a
            y[i] = float(r["result"] == "yes")
            day[i] = open_ts // 86400
        out[p.stem] = (bid, ask, y, day)
        log(f"{p.stem}: {W} windows")
    import os
    if os.environ.get("SKIP_CRYPTO"):
        return out
    try:
        from kalshi15m import edge as E
        R = E.rows(E.load_panels(log=lambda *a: None))
        for c in sorted(set(R["coin"])):
            m = R["coin"] == c
            ots = R["ots"][m]; j = R["j"][m]
            uo, inv = np.unique(ots, return_inverse=True)
            bid = np.full((len(uo), 15), np.nan); ask = np.full((len(uo), 15), np.nan)
            bid[inv, j] = R["yb"][m]; ask[inv, j] = R["ya"][m]
            y = np.zeros(len(uo)); y[inv] = R["y"][m]
            out[str(c)] = (bid, ask, y, (uo // 86400).astype(np.int64))
            log(f"{c}: {len(uo)} windows (crypto panel)")
    except Exception as e:
        log("crypto panels unavailable:", repr(e))
    return out


def features(bid, ask, j):
    """Inputs at minute j for every window: dict name -> array (NaN where unavailable)."""
    mid = (bid + ask) / 2
    spr = ask - bid
    g = lambda k: mid[:, j - k] if j - k >= 0 else np.full(len(mid), np.nan)
    f = {"mid": mid[:, j], "spr": spr[:, j], "d1": mid[:, j] - g(1), "d3": mid[:, j] - g(3), "d5": mid[:, j] - g(5),
         "drift": mid[:, j] - mid[:, 1], "ext": np.abs(mid[:, j] - 0.5),
         "rng": np.nanmax(mid[:, 1:j + 1], 1) - np.nanmin(mid[:, 1:j + 1], 1) if j >= 2 else np.zeros(len(mid)),
         "acc": (mid[:, j] - g(1)) - (g(1) - g(2))}
    return f


def build_group(members, data):
    """Concatenate member series into per-minute row sets for one group."""
    per_j = {}
    for j in JS:
        parts = []
        for s in members:
            if s not in data:
                continue
            bid, ask, y, day = data[s]
            with np.errstate(all="ignore"):
                f = features(bid, ask, j)
                ok = np.isfinite(bid[:, j]) & np.isfinite(ask[:, j]) & np.isfinite(bid[:, j + 1]) & np.isfinite(ask[:, j + 1])
                ok &= (ask[:, j] - bid[:, j] <= 0.30) & (f["mid"] >= 0.03) & (f["mid"] <= 0.97)
                pa = ask[:, j + 1]; pn = 1 - bid[:, j + 1]
                pay_y = np.where((pa >= 0.05) & (pa <= 0.95), y - pa - fee(pa), np.nan)
                pay_n = np.where((pn >= 0.05) & (pn <= 0.95), (1 - y) - pn - fee(pn), np.nan)
            parts.append((day[ok], np.column_stack([f[k][ok] for k in FEATS]), pay_y[ok], pay_n[ok]))
        if not parts:
            continue
        per_j[j] = (np.concatenate([p[0] for p in parts]), np.vstack([p[1] for p in parts]),
                    np.concatenate([p[2] for p in parts]), np.concatenate([p[3] for p in parts]))
    return per_j


def tstat(p, n, q):
    with np.errstate(all="ignore"):
        m = p / n
        v = np.maximum(q / n - m * m, 1e-12) * n / np.maximum(n - 1, 1)
        t = m / np.sqrt(v / n)
    return np.where(n >= 30, t, -np.inf)


def run_group(name, members, data, days_all):
    per_j = build_group(members, data)
    if not per_j:
        return None
    days = np.array(sorted({d for j in per_j for d in np.unique(per_j[j][0])}))
    Dn = len(days)
    if Dn < WARM + 6:
        return {"name": name, "note": f"only {Dn} days"}
    DAYS[name] = [int(d) for d in days[WARM:]]
    ncell_all = []
    P = np.zeros((len(JS) * 2 * NCELL, Dn)); N = np.zeros_like(P); Q = np.zeros_like(P)
    labels = []
    for ji, j in enumerate(JS):
        if j not in per_j:
            continue
        dd, F, py, pn = per_j[j]
        di = np.searchsorted(days, dd)
        warm = di < WARM
        # deciles from warm-up days only
        dec = np.full(F.shape, -1, dtype=np.int64)
        for k in range(NF):
            col = F[:, k]
            ok = np.isfinite(col)
            if (ok & warm).sum() < 50:
                continue
            edges = np.unique(np.quantile(col[ok & warm], np.linspace(0.1, 0.9, 9)))
            b = np.searchsorted(edges, col, side="right")
            dec[:, k] = np.where(ok, np.minimum(b, 9), -1)
        dec3 = np.where(dec < 0, -1, (dec >= 3).astype(np.int64) + (dec >= 7).astype(np.int64))
        for si, pay in enumerate((py, pn)):
            valid = np.isfinite(pay)
            base = (ji * 2 + si) * NCELL
            pv = np.where(valid, pay, 0.0)
            for k in range(NF):
                m = valid & (dec[:, k] >= 0)
                key = dec[m, k] * Dn + di[m]
                sl = slice(base + k * 10, base + k * 10 + 10)
                P[sl] = np.bincount(key, pv[m], 10 * Dn).reshape(10, Dn)
                N[sl] = np.bincount(key, None, 10 * Dn).reshape(10, Dn)
                Q[sl] = np.bincount(key, pv[m] ** 2, 10 * Dn).reshape(10, Dn)
            for pi, (a, b) in enumerate(PAIRS):
                m = valid & (dec[:, a] >= 0) & (dec[:, b] >= 0)
                key = (dec[m, a] * 10 + dec[m, b]) * Dn + di[m]
                sl = slice(base + NF * 10 + pi * 100, base + NF * 10 + pi * 100 + 100)
                P[sl] = np.bincount(key, pv[m], 100 * Dn).reshape(100, Dn)
                N[sl] = np.bincount(key, None, 100 * Dn).reshape(100, Dn)
                Q[sl] = np.bincount(key, pv[m] ** 2, 100 * Dn).reshape(100, Dn)
            for ti, (a, b, c) in enumerate(TRIPLES):
                m = valid & (dec3[:, a] >= 0) & (dec3[:, b] >= 0) & (dec3[:, c] >= 0)
                key = (dec3[m, a] * 9 + dec3[m, b] * 3 + dec3[m, c]) * Dn + di[m]
                o = base + NF * 10 + len(PAIRS) * 100 + ti * 27
                P[o:o + 27] = np.bincount(key, pv[m], 27 * Dn).reshape(27, Dn)
                N[o:o + 27] = np.bincount(key, None, 27 * Dn).reshape(27, Dn)
                Q[o:o + 27] = np.bincount(key, pv[m] ** 2, 27 * Dn).reshape(27, Dn)
    keep = N.sum(1) >= 30
    S = int(keep.sum())
    GEN[0] += len(JS) * 2 * NCELL
    cP, cN, cQ = np.cumsum(P, 1), np.cumsum(N, 1), np.cumsum(Q, 1)
    res = {"name": name, "members": len(members), "days": int(Dn), "strategies_scored": S,
           "luck_best_t": round(math.sqrt(2 * math.log(max(S, 2))), 2)}
    cand = []                                              # per test day: top-20 (t, cell, P_i, N_i)
    walk = {1: [], 5: [], 20: []}
    nb = {1: 0, 5: 0, 20: 0}
    for i in range(WARM, Dn):
        t = tstat(cP[:, i - 1], cN[:, i - 1], cQ[:, i - 1])
        top = np.argpartition(-t, 20)[:20]
        top = top[np.argsort(-t[top])]
        top = [int(c) for c in top if np.isfinite(t[c])]
        cand.append([(float(t[c]), c, float(P[c, i]), float(N[c, i])) for c in top])
        for K in (1, 5, 20):
            sel = top[:K]
            walk[K].append(float(P[sel, i].sum()) / max(len(sel), 1) if sel else 0.0)
            nb[K] += int(N[sel, i].sum()) if sel else 0
    for K in (1, 5, 20):
        d = np.array(walk[K])
        tt = float(d.mean() / d.std(ddof=1) * math.sqrt(len(d))) if len(d) > 2 and d.std(ddof=1) > 0 else 0.0
        res[f"walk_top{K}"] = {"usd_per_day_per_strategy": round(float(d.mean()), 3), "t": round(tt, 2), "bets": nb[K],
                               "cents_per_bet": round(100 * float(d.sum() * K / max(nb[K], 1)), 2), "days": len(d), "days_up": int((d > 0).sum()),
                               "halves": [round(float(d[:len(d) // 2].mean()), 3), round(float(d[len(d) // 2:].mean()), 3)]}
    cut = WARM + int((Dn - WARM) * 2 / 3)
    t1 = tstat(P[:, :cut].sum(1), N[:, :cut].sum(1), Q[:, :cut].sum(1))
    best = int(np.argmax(t1))
    nh = N[best, cut:].sum()
    res["holdout_best"] = {"history_t": round(float(t1[best]), 2), "history_bets": int(N[best, :cut].sum()),
                           "history_cents": round(100 * float(P[best, :cut].sum() / max(N[best, :cut].sum(), 1)), 2),
                           "holdout_bets": int(nh), "holdout_cents": round(100 * float(P[best, cut:].sum() / nh), 2) if nh else None}
    ta = tstat(P.sum(1), N.sum(1), Q.sum(1))
    top = np.argsort(-ta)[:3]
    res["in_sample_best_not_a_result"] = [{"t": round(float(ta[c]), 2), "bets": int(N[c].sum()), "cents": round(100 * float(P[c].sum() / N[c].sum()), 2),
                                           "desc": describe(int(c), name)} for c in top]
    return res, cand


def describe(c, group):
    ji, r = divmod(c, 2 * NCELL)
    si, cell = divmod(r, NCELL)
    j = JS[ji] if False else JS[c // (2 * NCELL)]
    side = "YES" if (c % (2 * NCELL)) // NCELL == 0 else "NO"
    cell = c % NCELL
    if cell < NF * 10:
        f, d = divmod(cell, 10)
        rule = f"{FEATS[f]} in decile {d}"
    elif cell < NF * 10 + len(PAIRS) * 100:
        pi, ab = divmod(cell - NF * 10, 100)
        a, b = PAIRS[pi]
        rule = f"{FEATS[a]} decile {ab // 10} and {FEATS[b]} decile {ab % 10}"
    else:
        ti, abc = divmod(cell - NF * 10 - len(PAIRS) * 100, 27)
        a, b, c = TRIPLES[ti]
        nm = ["low", "middle", "high"]
        rule = f"{FEATS[a]} {nm[abc // 9]}, {FEATS[b]} {nm[(abc // 3) % 3]}, {FEATS[c]} {nm[abc % 3]}"
    return f"{group}: minute {j}, buy {side} when {rule}"


def main():
    data = load_series()
    groups = [(s, [s]) for s in sorted(data)]
    groups += [(k, v) for k, v in SECTORS.items()]
    groups.append(("ALL", sorted(data)))
    results, allcand = {}, {}
    total = 0
    for name, members in groups:
        out = run_group(name, members, data, None)
        if out is None:
            continue
        if isinstance(out, dict):
            results[name] = out
            continue
        r, cand = out
        results[name] = r
        allcand[name] = cand
        total += r["strategies_scored"]
        w = r["walk_top5"]
        log(f"{name:16} {r['strategies_scored']:>9,} strategies | walk top5 ${w['usd_per_day_per_strategy']:+.3f}/d {w['cents_per_bet']:+.2f}c t {w['t']:+.2f} ({w['bets']} bets) | holdout best {r['holdout_best']['holdout_cents']}c on {r['holdout_best']['holdout_bets']} bets")
    # best of everything: each test day, the top K by t across all groups
    ndays = max(len(c) for c in allcand.values())
    day_numbers = {g: [] for g in allcand}
    glob = {1: [], 5: [], 20: []}
    gb = {1: 0, 5: 0, 20: 0}
    for i in range(ndays):
        pool = []
        for g, cand in allcand.items():
            if i < len(cand):
                pool += [(t, p, n) for t, c, p, n in cand[i]]
        pool.sort(key=lambda x: -x[0])
        for K in (1, 5, 20):
            sel = pool[:K]
            glob[K].append(sum(p for _, p, _ in sel) / max(len(sel), 1) if sel else 0.0)
            gb[K] += int(sum(n for _, _, n in sel))
    dates = DAYS.get("ALL") or max(DAYS.values(), key=len)
    res_g = {"dates_utc_day_number": dates, "total_strategies_generated": GEN[0], "total_strategies_scored": total, "luck_best_t": round(math.sqrt(2 * math.log(max(total, 2))), 2)}
    for K in (1, 5, 20):
        d = np.array(glob[K])
        tt = float(d.mean() / d.std(ddof=1) * math.sqrt(len(d))) if len(d) > 2 and d.std(ddof=1) > 0 else 0.0
        res_g[f"daily_top{K}"] = [round(float(x), 4) for x in d]
        res_g[f"walk_top{K}"] = {"usd_per_day_per_strategy": round(float(d.mean()), 3), "t": round(tt, 2), "bets": gb[K],
                                 "cents_per_bet": round(100 * float(d.sum() * K / max(gb[K], 1)), 2), "days": len(d),
                                 "halves": [round(float(d[:len(d) // 2].mean()), 3), round(float(d[len(d) // 2:].mean()), 3)]}
    results["_best_of_everything"] = res_g
    log("BEST OF EVERYTHING", json.dumps(res_g))
    json.dump({"updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "results": results}, open(OUT, "w"), indent=1, default=float)
    log("done")


if __name__ == "__main__":
    main()
