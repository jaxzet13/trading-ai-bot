"""Can the live edge model be tuned to earn more? Honest sweep, Nov 27 2026.

Account holder: "just do anything you can to improve it ... we've been on a plateau".

Two kinds of change, both judged on unseen days only:
  A  model settings that need a refit: training window (ROLL_DAYS), shrinkage (LAM_POOL, LAM_COIN), refit cadence.
     Each variant re-runs the full walk-forward (the model for day d is fitted on days before d only).
  B  entry rules on top of the out-of-sample predictions: edge bar, minutes of the window, price band, per-coin bar.
     Picking the best rule on the same days it is scored on would flatter it, so rules are chosen WALK-FORWARD too:
     for each test day the rule with the best record on earlier days (at least 14 of them) is the one applied.

Live coins = the coins live now. Results are per 1 contract, Kalshi fee included, filled at the ask.

    python3 research/edge_tune/sweep.py [out.json]
"""
import itertools
import json
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from kalshi15m import edge as E                       # noqa: E402

T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def live_set():
    return set(json.load(open(E.MODEL)).get("live_coins", []))


def score(b, days, live):
    return E.summary(E._sub(b, np.isin(b["coin"], list(live))), days)


def model_variant(R, **kw):
    old = {k: getattr(E, k) for k in kw}
    for k, v in kw.items():
        setattr(E, k, v)
    try:
        p, days = E.walk_predict(R)
    finally:
        for k, v in old.items():
            setattr(E, k, v)
    return p, days


def rule_bets(R, p, thr, start, end, pmin, pmax, coin_thr=None):
    old = (E.PMIN, E.PMAX)
    E.PMIN, E.PMAX = pmin, pmax
    try:
        if coin_thr is None:
            return E.bets(R, p, thr, start, end)
        parts = []
        for c, t in coin_thr.items():
            m = R["coin"] == c
            sub = {k: (v[m] if hasattr(v, "__len__") and len(v) == len(m) else v) for k, v in R.items()}
            parts.append(E.bets(sub, p[m], t, start, end))
        return {k: np.concatenate([b[k] for b in parts]) for k in parts[0]}
    finally:
        E.PMIN, E.PMAX = old


def daily(b, days):
    return np.array([b["pnl"][b["day"] == d].sum() for d in days])


def walk_select(R, p, days, live, grid, warm=14):
    """Each test day uses the grid rule with the best total on earlier test days -> (daily pnl, picks)."""
    rows = []
    for g in grid:
        b = rule_bets(R, p, *g)
        b = E._sub(b, np.isin(b["coin"], list(live)))
        rows.append(daily(b, days))
    M = np.array(rows)                                   # rules x days
    cum = np.cumsum(M, axis=1)
    out, picks = [], []
    for i in range(warm, len(days)):
        k = int(np.argmax(cum[:, i - 1]))
        out.append(M[k, i])
        picks.append(grid[k])
    return np.array(out), picks, M


def stats(dd):
    dd = np.asarray(dd)
    cum = np.cumsum(dd)
    return {"usd_per_day": round(float(dd.mean()), 3), "t": round(E._t(dd), 2), "days_up": int((dd > 0).sum()),
            "days": int(len(dd)), "max_drawdown": round(float((np.maximum.accumulate(np.maximum(cum, 0)) - cum).max()), 2),
            "halves": [round(float(dd[:len(dd) // 2].mean()), 3), round(float(dd[len(dd) // 2:].mean()), 3)]}


def main():
    res = {}
    live = live_set()
    log("loading panels")
    R = E.rows(E.load_panels(log=lambda *a: None))
    log(f"{len(R['y'])} rows, live coins {sorted(live)}")

    # ---- A: model settings
    variants = [("current", {}),
                ("roll 21", {"ROLL_DAYS": 21}), ("roll 49", {"ROLL_DAYS": 49}),
                ("lam_coin 100", {"LAM_COIN": 100.0}), ("lam_coin 1000", {"LAM_COIN": 1000.0}),
                ("lam_pool 5", {"LAM_POOL": 5.0}), ("lam_pool 80", {"LAM_POOL": 80.0}),
                ("refit daily", {"REFIT_DAYS": 1})]
    preds = {}
    for name, kw in variants:
        p, days = model_variant(R, **kw)
        preds[name] = (p, days)
        b = E.bets(R, p)
        s = score(b, days, live)
        res[f"A {name}"] = s
        log(f"A {name:14s} {s['per_day']:5.1f}/day {s['cents_per_bet']:+5.2f}c ${s['usd_per_day']:+.2f}/day t {s['t']:.2f} "
            f"up {s['days_up']}/{s['days']} maxDD {s['max_drawdown']:.2f}")
    # all variants share the same test days only if ROLL/WARM agree; compare on the common tail
    p0, days0 = preds["current"]

    # ---- B: entry rules on the current model's out-of-sample predictions, chosen walk-forward
    thrs = (0.03, 0.04, 0.05, 0.06, 0.08)
    windows = ((4, 13), (2, 13), (6, 13), (4, 10), (8, 14), (1, 14))
    bands = ((0.05, 0.95), (0.10, 0.90), (0.20, 0.80), (0.05, 0.60))
    grid = [(t, s, e, lo, hi) for t in thrs for (s, e) in windows for (lo, hi) in bands]
    log(f"B grid: {len(grid)} rules")
    fixed = rule_bets(R, p0, 0.05, 4, 13, 0.05, 0.95)
    base_dd = daily(E._sub(fixed, np.isin(fixed["coin"], list(live))), days0)
    wf, picks, M = walk_select(R, p0, days0, live, grid)
    res["B current rule (same days)"] = stats(base_dd[14:])
    res["B walk-forward chosen rule"] = stats(wf)
    top = {}
    for g in picks:
        top[str(g)] = top.get(str(g), 0) + 1
    res["B picks"] = sorted(top.items(), key=lambda x: -x[1])[:6]
    # in-sample best, for the record only
    tot = M.sum(1)
    best = np.argsort(-tot)[:5]
    res["B in-sample top (not a result)"] = [(str(grid[i]), round(float(tot[i] / M.shape[1]), 3)) for i in best]
    log("B current", res["B current rule (same days)"])
    log("B walk-forward", res["B walk-forward chosen rule"], res["B picks"][:3])
    log("B in-sample top", res["B in-sample top (not a result)"])

    # ---- C: per-coin edge bar, chosen walk-forward per coin
    coins = sorted(live)
    per = {}
    for c in coins:
        rowsc = []
        for t in thrs:
            b = rule_bets(R, p0, t, 4, 13, 0.05, 0.95)
            b = E._sub(b, b["coin"] == c)
            rowsc.append(daily(b, days0))
        per[c] = np.array(rowsc)
    wfc = np.zeros(len(days0) - 14)
    pk = {c: {} for c in coins}
    for i in range(14, len(days0)):
        for c in coins:
            k = int(np.argmax(per[c][:, :i].sum(1)))
            wfc[i - 14] += per[c][k, i]
            pk[c][thrs[k]] = pk[c].get(thrs[k], 0) + 1
    res["C per-coin bar, walk-forward"] = stats(wfc)
    res["C picks"] = {c: v for c, v in pk.items()}
    log("C per-coin walk-forward", res["C per-coin bar, walk-forward"], res["C picks"])

    # ---- D: model variants x threshold 0.04/0.05 on common days
    common = days0[14:]
    for name, (p, days) in preds.items():
        for t in (0.04, 0.05):
            b = rule_bets(R, p, t, 4, 13, 0.05, 0.95)
            dd = daily(E._sub(b, np.isin(b["coin"], list(live))), common)
            res[f"D {name} thr {t}"] = stats(dd)
    log("D done")
    for k, v in res.items():
        if k.startswith("D "):
            log(k, v)
    if len(sys.argv) > 1:
        json.dump(res, open(sys.argv[1], "w"), indent=1, default=str)
    log("done")


if __name__ == "__main__":
    main()
