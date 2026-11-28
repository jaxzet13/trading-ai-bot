"""La Liga deep dive (Nov 28 2026): is the walk-forward "+11c" real?

Account holder: "Go way deeper on La Liga ... it says +11 which isn't bad honestly, try to get it better though".

Reproduces the per-sport study's La Liga top-5 walk-forward (same grid, same fills, corrected kickoff clock), then asks
four questions about it:
  1. How concentrated is it? (bets, distinct games, share of the profit from the best 3 / 5 games)
  2. How wide is the error bar? (bootstrap over GAMES, since bets in one game are not independent)
  3. Does it survive leaving the best few games out?
  4. Transfer: do the strategies La Liga's search liked make money on the OTHER soccer leagues, games that never
     influenced the choice? (EPL, Champions League, Bundesliga, MLS, Liga MX; thousands of markets.)

    python3 research/soccer_focus/laliga_deep.py   -> research/soccer_focus/laliga_deep.json
"""
import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from tennis import lab                                         # noqa: E402

DATA = Path("data/sports_fixed")
WARM = 14
K = 5
OTHERS = ["KXEPLGAME", "KXUCLGAME", "KXBUNDESLIGAGAME", "KXMLSGAME", "KXLIGAMXGAME"]


def arrays_for(ms, strats, rows):
    """(mask, pay) per requested strategy row, same definitions as lab.score_matrix."""
    out = {}
    scope = lab._scope_masks(ms)
    cache = {}
    for r in rows:
        s = strats[r]
        sc = scope[s.get("scope", "all")]
        if s["fam"] == "band":
            if ("b", s["M"]) not in cache:
                cache[("b", s["M"])] = lab._band_arrays(ms, s["M"])
            ok, mid, _, pay = cache[("b", s["M"])]
            out[r] = (ok & (mid >= s["lo"]) & (mid < s["hi"]) & sc, pay)
        elif s["fam"] == "drift":
            key = ("d", s["M"], s["L"])
            if key not in cache:
                cache[key] = lab._drift_arrays(ms, s["M"], s["L"])
            mid_i, ch, ok_y, pay_y, ok_n, pay_n = cache[key]
            with np.errstate(invalid="ignore"):
                band = (mid_i >= 0.10) & (mid_i <= 0.90)
                moved = (ch >= s["d"]) if s["dir"] == "up" else (ch <= -s["d"])
            back = (s["dir"] == "up") == (s["act"] == "mom")
            out[r] = (band & moved & (ok_y if back else ok_n) & sc, pay_y if back else pay_n)
        else:
            key = ("s", s["phase"], s["w"], s["d"], s["dir"])
            if key not in cache:
                cache[key] = lab._swing_arrays(ms, s["phase"], s["w"], s["d"], s["dir"])
            ok_y, pay_y, ok_n, pay_n = cache[key]
            back = (s["dir"] == "down") == (s["act"] == "rev")
            out[r] = ((ok_y if back else ok_n) & sc, pay_y if back else pay_n)
    return out


def t_of(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def main():
    ms = lab.load(DATA / "KXLALIGAGAME.jsonl")
    strats = [s for s in lab.strategies() if s.get("scope", "all") == "all"]
    days, P, N, Q = lab.score_matrix(ms, strats, log=lambda *a: None)
    D = len(days)
    day_of = np.array([m["day"] for m in ms])
    di = np.searchsorted(days, day_of)
    ev = np.array([m["event"] for m in ms])
    cP, cN, cQ = np.cumsum(P, 1), np.cumsum(N, 1), np.cumsum(Q, 1)
    picks = {}
    for i in range(WARM, D):
        n, p, q = cN[:, i - 1], cP[:, i - 1], cQ[:, i - 1]
        mu = np.divide(p, n, out=np.zeros_like(p), where=n > 0)
        var = np.divide(q - n * mu * mu, n - 1, out=np.zeros_like(p), where=n > 1)
        t = np.where((n >= lab.MIN_BETS) & (var > 0), mu / np.sqrt(np.where(var > 0, var, 1) / np.where(n > 0, n, 1)), -np.inf)
        picks[i] = [int(j) for j in np.argsort(-t)[:K] if np.isfinite(t[j])]
    rows_needed = sorted({j for v in picks.values() for j in v})
    arr = arrays_for(ms, strats, rows_needed)
    recs = []                                   # (day index, event, pnl, strategy row)
    for i, js in picks.items():
        for j in js:
            mask, pay = arr[j]
            for k in np.nonzero(mask & (di == i))[0]:
                recs.append((i, ev[k], float(pay[k]), j))
    res = {"markets": len(ms), "games": len(set(ev)), "days": int(D), "test_days": int(D - WARM)}
    pnl = np.array([r[2] for r in recs])
    res["walk_top5"] = {"bets": len(recs), "cents_per_bet": round(100 * float(pnl.mean()), 2) if len(recs) else 0,
                        "total_pnl": round(float(pnl.sum()), 2)}
    # 1. concentration
    by_game = collections.defaultdict(float)
    nb_game = collections.Counter()
    for _, e, p, _ in recs:
        by_game[e] += p
        nb_game[e] += 1
    g = np.array(sorted(by_game.values(), reverse=True))
    res["distinct_games"] = len(g)
    res["bets_per_game"] = round(len(recs) / max(len(g), 1), 2)
    res["best_games_pnl"] = [round(float(x), 2) for x in g[:5]]
    res["share_of_profit_from_best_3_games"] = round(float(g[:3].sum() / max(g.sum(), 1e-9)), 2) if g.sum() > 0 else None
    # 2. bootstrap over games
    rng = np.random.default_rng(1)
    games = list(by_game)
    gp = np.array([by_game[x] for x in games])
    gn = np.array([nb_game[x] for x in games])
    boots = []
    for _ in range(5000):
        idx = rng.integers(0, len(games), len(games))
        boots.append(100 * gp[idx].sum() / max(gn[idx].sum(), 1))
    res["bootstrap_cents_per_bet_90pct_interval"] = [round(float(np.percentile(boots, 5)), 2), round(float(np.percentile(boots, 95)), 2)]
    res["bootstrap_share_of_runs_below_zero"] = round(float(np.mean(np.array(boots) < 0)), 3)
    # 3. leave the best games out
    for drop in (1, 3, 5):
        keep = np.argsort(-gp)[drop:]
        res[f"cents_per_bet_without_best_{drop}_games"] = round(100 * float(gp[keep].sum() / max(gn[keep].sum(), 1)), 2)
    # 4. transfer to the other leagues
    picked_count = collections.Counter(j for _, _, _, j in recs)
    favourites = [j for j, _ in collections.Counter({j: sum(1 for v in picks.values() if j in v) for j in rows_needed}).most_common(10)]
    res["most_picked_strategies"] = [strats[j]["id"] for j in favourites]
    tr = {}
    allp, alln = [], []
    for s in OTHERS:
        p2 = DATA / f"{s}.jsonl"
        if not p2.exists():
            continue
        m2 = lab.load(p2)
        a2 = arrays_for(m2, strats, favourites)
        d2 = np.array([m["day"] for m in m2])
        pays = []
        for j in favourites:
            mask, pay = a2[j]
            pays.append((mask, pay))
        # one entry per (strategy, market): the same market can be bet by several of the 10; report per-strategy average
        per = []
        for mask, pay in pays:
            x = pay[mask]
            per.append((len(x), float(x.sum())))
        nb = sum(n for n, _ in per)
        pl = sum(p for _, p in per)
        # daily series for a t-stat: average of the strategies' daily P&L
        dd = collections.defaultdict(float)
        for mask, pay in pays:
            for k in np.nonzero(mask)[0]:
                dd[d2[k]] += float(pay[k]) / len(favourites)
        series = np.array(list(dd.values()))
        tr[s] = {"markets": len(m2), "bets": nb, "cents_per_bet": round(100 * pl / max(nb, 1), 2), "t_by_day": round(t_of(series), 2)}
        allp.append(pl); alln.append(nb)
    res["transfer_to_other_leagues"] = tr
    res["transfer_pooled_cents_per_bet"] = round(100 * sum(allp) / max(sum(alln), 1), 2)
    json.dump(res, open("research/soccer_focus/laliga_deep.json", "w"), indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
