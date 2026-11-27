"""Sports: search ~17,000 strategies per sport (100,000+ in total), judged honestly (Nov 27 2026).

Account holder: "go above and beyond to find the best strategies ... backtest 100,000 different strategies ... And
for sportsbetting do the same".

Sports = each tennis tier (ATP, WTA, Challenger ATP/WTA, ITF men/women) and each downloaded league
(data/sports/<series>.jsonl). Same honest fills as the tennis lab (decided on one minute's mid, filled the next
minute at that minute's worst ask, Kalshi's fee).

Strategies per sport (a finer grid than the tennis lab's):
  band   back a side priced in [lo, lo + w) at minute M; M every 5 min from 4 h before to 3 h in (85 minutes),
         lo every 2c, w 4/8/12/20c
  swing  in play, a move of >= d within w minutes: back the bounce or the move (3 phases, 6 windows, 7 sizes)
  drift  before the start, a move of >= d over L minutes up to minute M: follow or fade it
Honest scoring per sport:
  * walk-forward: each test day bets the top 1 / 5 / 20 strategies ranked on EARLIER days only (t, >= 30 bets)
  * hold-out: rank on the first two thirds of the days, score on the last third
  * pooled: the same over all sports together (the best strategies across every sport)

    python3 research/sports_study/search.py [series ...]  -> research/sports_study/search_results.json
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from tennis import lab                                         # noqa: E402
from tennis.history import STORE                               # noqa: E402

T0 = time.time()
OUT = Path("research/sports_study/search_results.json")
TENNIS = ["KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXITFMATCH", "KXITFWMATCH"]
WARM = 14


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def grid():
    out = []
    for M in range(-240, 181, 5):
        for w in (0.04, 0.08, 0.12, 0.20):
            for k in range(2, 48):
                lo = round(0.02 * k, 2)
                hi = round(lo + w, 2)
                if hi <= 0.98:
                    out.append({"id": f"band:m{M}:{lo:.2f}-{hi:.2f}", "fam": "band", "M": M, "lo": lo, "hi": hi, "scope": "all"})
    for ph in lab.PHASES:
        for w in (5, 10, 15, 20, 30, 45):
            for d in (0.04, 0.08, 0.12, 0.16, 0.20, 0.25, 0.30):
                for dr in ("down", "up"):
                    for act in ("rev", "mom"):
                        out.append({"id": f"swing:{ph}:{dr}{d:.2f}/{w}m:{act}", "fam": "swing", "phase": ph, "w": w, "d": d,
                                    "dir": dr, "act": act, "scope": "all"})
    for M in (-180, -120, -90, -60, -30, -10, 0):
        for L in (15, 30, 60, 120, 240):
            for d in (0.02, 0.03, 0.05, 0.08, 0.10, 0.12, 0.15):
                for dr in ("down", "up"):
                    for act in ("rev", "mom"):
                        out.append(lab._drift(M, L, d, dr, act, "all"))
    return out


def tstat(p, n, q):
    mu = np.divide(p, n, out=np.zeros_like(p), where=n > 0)
    var = np.divide(q - n * mu * mu, n - 1, out=np.zeros_like(p), where=n > 1)
    return np.where((n >= 30) & (var > 0), mu / np.sqrt(np.where(var > 0, var, 1) / np.where(n > 0, n, 1)), -np.inf)


def dstats(dd, bets=None):
    dd = np.asarray(dd, float)
    if len(dd) < 3:
        return {"days": len(dd)}
    return {"usd_per_day": round(float(dd.mean()), 3),
            "t": round(float(dd.mean() / dd.std(ddof=1) * math.sqrt(len(dd))) if dd.std() > 0 else 0.0, 2),
            "days_up": int((dd > 0).sum()), "days": len(dd),
            "halves": [round(float(dd[:len(dd) // 2].sum()), 2), round(float(dd[len(dd) // 2:].sum()), 2)],
            **({"bets": int(bets), "cents_per_bet": round(100 * float(dd.sum()) / max(bets, 1), 2)} if bets is not None else {})}


def evaluate(P, N, Q, names):
    D = P.shape[1]
    cP, cN, cQ = np.cumsum(P, 1), np.cumsum(N, 1), np.cumsum(Q, 1)
    out = {}
    for K in (1, 5, 20):
        dd, nb, picks = [], 0, {}
        for i in range(WARM, D):
            t = tstat(cP[:, i - 1], cN[:, i - 1], cQ[:, i - 1])
            top = np.argsort(-t)[:K]
            top = top[np.isfinite(t[top])]
            dd.append(float(P[top, i].sum()) / K)
            nb += int(N[top, i].sum())
            for j in top:
                picks[names[j]] = picks.get(names[j], 0) + 1
        out[f"walk_top{K}"] = dstats(dd, nb / K)
        out[f"walk_top{K}_picked"] = sorted(picks.items(), key=lambda x: -x[1])[:5]
    cut = WARM + int((D - WARM) * 2 / 3)
    order = np.argsort(-tstat(P[:, :cut].sum(1), N[:, :cut].sum(1), Q[:, :cut].sum(1)))
    for K in (1, 5, 20):
        top = order[:K]
        out[f"holdout_top{K}"] = dstats(P[top, cut:].sum(0) / K, N[top, cut:].sum() / K)
    out["holdout_top5_names"] = [names[j] for j in order[:5]]
    t_all = tstat(P.sum(1), N.sum(1), Q.sum(1))
    j = int(np.argmax(t_all))
    out["in_sample_best_not_a_result"] = (names[j], round(float(t_all[j]), 2), int(N[j].sum()), round(100 * float(P[j].sum() / N[j].sum()), 2))
    return out


def load_sport(series):
    if series in TENNIS:
        return [m for m in lab.load(STORE) if m["series"] == series]
    return lab.load(Path("data/sports") / f"{series}.jsonl")


def main():
    strats = grid()
    log(f"{len(strats)} strategies per sport")
    series = sys.argv[1:] or (TENNIS + sorted(p.stem for p in Path("data/sports").glob("KX*.jsonl")))
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    pooled = {}
    total = 0
    for s in series:
        ms = load_sport(s)
        if len(ms) < 200:
            log(f"{s}: {len(ms)} markets, skipped")
            continue
        days, P, N, Q = lab.score_matrix(ms, strats, log=lambda *a: None)
        keep = N.sum(1) >= 30
        names = [f"{s}|{strats[i]['id']}" for i in np.nonzero(keep)[0]]
        P, N, Q = P[keep], N[keep], Q[keep]
        total += len(names)
        r = evaluate(P, N, Q, names)
        r.update(series=s, markets=len(ms), days=len(days), strategies=len(names))
        res[s] = r
        w = r["walk_top5"]
        log(f"{s:24s} {len(ms):6d} mkts {len(days):3d} d {len(names):6d} strats | walk top5 {w.get('usd_per_day', 0):+.3f}$/d "
            f"t {w.get('t', 0):+.2f} {w.get('cents_per_bet', 0):+.2f}c halves {w.get('halves')} | holdout top5 "
            f"{r['holdout_top5'].get('usd_per_day', 0):+.3f}$/d t {r['holdout_top5'].get('t', 0):+.2f}")
        for d_, i in zip(days, range(len(days))):
            pooled.setdefault(int(d_), None)
        pooled[s] = (days, P, N, Q, names)
        OUT.write_text(json.dumps(res, indent=1, default=float))
    # pooled across sports on a common day axis
    alld = np.array(sorted({int(d) for k, v in pooled.items() if isinstance(v, tuple) for d in v[0]}))
    Ps, Ns, Qs, names = [], [], [], []
    for k, v in pooled.items():
        if not isinstance(v, tuple):
            continue
        days, P, N, Q, nm = v
        ix = np.searchsorted(alld, days)
        for M_, L_ in ((P, Ps), (N, Ns), (Q, Qs)):
            Z = np.zeros((M_.shape[0], len(alld)), np.float32)
            Z[:, ix] = M_
            L_.append(Z)
        names += nm
    if Ps:
        r = evaluate(np.vstack(Ps), np.vstack(Ns), np.vstack(Qs), names)
        r.update(strategies=len(names), days=len(alld))
        res["POOLED"] = r
        w = r["walk_top5"]
        log(f"POOLED {len(names)} strategies | walk top5 {w.get('usd_per_day', 0):+.3f}$/d t {w.get('t', 0):+.2f} "
            f"{w.get('cents_per_bet', 0):+.2f}c | holdout top5 {r['holdout_top5']}")
    res["total_strategies"] = total
    OUT.write_text(json.dumps(res, indent=1, default=float))
    log("done")


if __name__ == "__main__":
    main()
