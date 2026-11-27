"""Per-sport backtest: is there a strategy that makes money on games it never saw? (Nov 27 2026)

Account holder: "expanding into other sports and doing separate backtests for each sport like how we do separate
backtests for different crypto", then "Do it ... make a separate artifact for it ... if we should start using them
with real money".

For every sport (one Kalshi game-winner series), with the tennis lab's code and honest fills (decided on one
minute's mid, filled the next minute at that minute's worst ask, Kalshi's taker fee):
  1. Calibration 60 minutes before the scheduled start: in each price band, how often does the team at that price win,
     minus what it costs (price + fee)? Positive = buying at that price made money.
  2. Strategy search, walk-forward: the lab's ~3,000 rules (price bands at every 10 minutes from 3 h before to 3 h
     into the game; in-play swing rules; pre-game drift rules). On each test day the 1 / 5 / 20 rules with the best
     record on EARLIER days only (>= 30 bets, ranked by t) are the ones bet that day. That is the result that counts.
  3. Hold-out: the single best rule on the first two thirds of the days, scored on the last third.
Result per sport: per $1 contract, Kalshi fee included.

    python3 research/sports_study/study.py [series ...]   -> research/sports_study/results.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from tennis import api, lab                                  # noqa: E402

DATA = Path("data/sports")
OUT = Path("research/sports_study/results.json")
WARM = 14
NAMES = {"KXNBAGAME": "NBA", "KXNFLGAME": "NFL", "KXNCAAFGAME": "College football", "KXNCAAMBGAME": "Men's college basketball",
         "KXNHLGAME": "NHL", "KXEPLGAME": "Premier League", "KXUCLGAME": "Champions League", "KXLALIGAGAME": "La Liga",
         "KXCS2GAME": "Counter-Strike 2", "KXUFCFIGHT": "UFC", "KXNCAAWBGAME": "Women's college basketball",
         "KXLIGAMXGAME": "Liga MX", "KXMLSGAME": "MLS", "KXBUNDESLIGAGAME": "Bundesliga", "KXLOLGAME": "League of Legends",
         "KXDOTA2GAME": "Dota 2"}


def t_of(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def calibration(ms, M=-60):
    ok, mid, price, pay = lab._band_arrays(ms, M)
    rows = []
    for lo, hi in ((0.05, 0.20), (0.20, 0.40), (0.40, 0.60), (0.60, 0.80), (0.80, 0.90), (0.90, 0.97)):
        m = ok & (mid >= lo) & (mid < hi)
        n = int(m.sum())
        if n >= 20:
            rows.append({"band": f"{int(lo * 100)}-{int(hi * 100)}c", "n": n, "cents_per_bet": round(100 * float(pay[m].mean()), 2),
                         "t": round(float(pay[m].mean() / (pay[m].std(ddof=1) / math.sqrt(n))), 2) if n > 2 else 0.0})
    return rows


def walk(P, N, Q, ks=(1, 5, 20)):
    D = P.shape[1]
    cP, cN, cQ = np.cumsum(P, 1), np.cumsum(N, 1), np.cumsum(Q, 1)
    daily = {k: [] for k in ks}
    bets = {k: 0 for k in ks}
    for i in range(WARM, D):
        n, p, q = cN[:, i - 1], cP[:, i - 1], cQ[:, i - 1]
        elig = n >= lab.MIN_BETS
        mu = np.divide(p, n, out=np.zeros_like(p), where=n > 0)
        var = np.divide(q - n * mu * mu, n - 1, out=np.zeros_like(p), where=n > 1)
        t = np.where(elig & (var > 0), mu / np.sqrt(np.where(var > 0, var, 1) / np.where(n > 0, n, 1)), -np.inf)
        order = np.argsort(-t)
        for k in ks:
            top = [j for j in order[:k] if np.isfinite(t[j])]
            daily[k].append(float(P[top, i].sum()) if top else 0.0)
            bets[k] += int(N[top, i].sum()) if top else 0
    out = {}
    for k in ks:
        d = np.array(daily[k])
        out[k] = {"bets": bets[k], "pnl": round(float(d.sum()), 2), "cents_per_bet": round(100 * float(d.sum()) / max(bets[k], 1), 2),
                  "t": round(t_of(d), 2), "days": len(d), "days_up": int((d > 0).sum()),
                  "halves_pnl": [round(float(d[:len(d) // 2].sum()), 2), round(float(d[len(d) // 2:].sum()), 2)]}
    return out


def holdout(P, N, Q, strats):
    D = P.shape[1]
    cut = int(D * 2 / 3)
    n, p, q = N[:, :cut].sum(1), P[:, :cut].sum(1), Q[:, :cut].sum(1)
    mu = np.divide(p, n, out=np.zeros_like(p), where=n > 0)
    var = np.divide(q - n * mu * mu, n - 1, out=np.zeros_like(p), where=n > 1)
    t = np.where((n >= lab.MIN_BETS) & (var > 0), mu / np.sqrt(np.where(var > 0, var, 1) / np.where(n > 0, n, 1)), -np.inf)
    j = int(np.argmax(t))
    nh, ph = N[j, cut:].sum(), P[j, cut:].sum()
    return {"rule": strats[j]["id"], "history_t": round(float(t[j]), 2), "history_bets": int(n[j]),
            "history_cents": round(100 * float(mu[j]), 2), "holdout_bets": int(nh),
            "holdout_cents": round(100 * float(ph / nh), 2) if nh else None, "holdout_pnl": round(float(ph), 2)}


def study(series):
    path = DATA / f"{series}.jsonl"
    ms = lab.load(path)
    if len(ms) < 100:
        return {"series": series, "name": NAMES.get(series, series), "markets": len(ms), "note": "too few settled markets"}
    days = sorted({m["day"] for m in ms})
    strats = [s for s in lab.strategies() if s.get("scope", "all") == "all"]
    _, P, N, Q = lab.score_matrix(ms, strats, log=lambda *a: None)
    vol = [m.get("volume") or 0 for m in map(json.loads, open(path))]
    res = {"series": series, "name": NAMES.get(series, series), "markets": len(ms),
           "games": len({m["event"] for m in ms}), "days": len(days),
           "median_volume": round(float(np.median(vol)), 0) if vol else 0,
           "calibration_60min": calibration(ms), "walk_forward": walk(P, N, Q), "holdout": holdout(P, N, Q, strats)}
    w = res["walk_forward"][5]
    res["verdict"] = ("edge" if w["t"] >= 2.5 and w["cents_per_bet"] > 1 and min(w["halves_pnl"]) > 0
                      else "maybe" if w["t"] >= 1.5 and w["cents_per_bet"] > 0 else "no edge")
    return res


def main():
    series = sys.argv[1:] or sorted(p.stem for p in DATA.glob("*.jsonl"))
    allres = json.load(open(OUT)) if OUT.exists() else {}
    for s in series:
        r = study(s)
        allres[s] = r
        w = r.get("walk_forward", {}).get(5, {})
        print(f"{r['name']:28s} {r.get('games', 0):5d} games {r.get('days', 0):3d} days | top-5 walk-forward: "
              f"{w.get('bets', 0):5d} bets {w.get('cents_per_bet', 0):+6.2f}c t {w.get('t', 0):+5.2f} "
              f"halves {w.get('halves_pnl')} -> {r.get('verdict', r.get('note'))}", flush=True)
        OUT.write_text(json.dumps(allres, indent=1, default=float))


if __name__ == "__main__":
    main()
