"""Crypto 15-minute markets: search ~100,000 strategies, judged honestly (Nov 27 2026).

Account holder: "do a overhaul of the crypto and backtest 100,000 different strategies and find me even better
strategies than we are using right now".

Data: every 15-minute market of the 9 coins since Aug 31 (kalshi15m edge rows: one row per market x minute with the
21 model features, the quotes and the result). Fills at the ask, Kalshi's taker fee, one contract.

Strategy families (each strategy bets at one fixed minute of the market, so one bet per market):
  F  feature rules: feature f in decile d (deciles from the 28 days BEFORE the test period: no look-ahead) -> buy YES
     or NO, at minute 4/7/10/13, in one of 5 price bands, on one coin or all coins.   21 x 10 x 2 x 4 x 5 x 10
  M  model rules: the live model's out-of-sample edge >= x (2..10c) at minute m (1..14), price band, coin.
  C  model + feature: model edge >= 3c AND feature f in quintile q, minute 4/7/10/13, coin.
  H  model + time of day: model edge >= x in one 4-hour UTC block, minute, coin.

Honest scoring:
  * walk-forward: every test day bets the top 1 / 5 / 20 / 100 strategies ranked on EARLIER days only (t-stat,
    >= 30 bets). This is what "using the best strategies" would really have earned.
  * hold-out: rank on the first two thirds of the test days, score the top 1 / 5 / 20 / 100 on the last third.
  * baseline: the live model as it runs (4c bar, first qualifying minute 4-13), same days.

    python3 research/crypto_search/search.py   -> research/crypto_search/results.json
"""
import json
import math
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from kalshi15m import edge as E                                  # noqa: E402

T0 = time.time()
OUT = "research/crypto_search/results.json"


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def fee(p):
    return 0.07 * p * (1 - p)


def build():
    log("loading rows")
    R = E.rows(E.load_panels(log=lambda *a: None))
    p, tdays = E.walk_predict(R)
    tdays = np.asarray(tdays)
    D = len(tdays)
    test = np.isin(R["day"], tdays)
    pre = R["day"] < tdays[0]
    dix = np.searchsorted(tdays, R["day"])
    log(f"{len(R['y'])} rows, {D} test days, {pre.sum()} warm-up rows")

    ya, yb, y = R["ya"], R["yb"], R["y"]
    na = 1 - yb
    payY = y - ya - fee(ya)
    payN = (1 - y) - na - fee(na)
    priceY, priceN = ya, na
    edgeY = p - ya - fee(ya)
    edgeN = (1 - p) - na - fee(na)
    coins = sorted(set(R["coin"]))
    coin_opts = ["all"] + coins
    bands = [(0.05, 0.95), (0.15, 0.85), (0.30, 0.70), (0.05, 0.40), (0.60, 0.95)]
    mins = [4, 7, 10, 13]
    hour_block = ((R["ots"] % 86400) // 3600 // 4).astype(int)
    X = R["X"]
    F = X.shape[1]
    # deciles / quintiles from the warm-up period only
    qs10 = np.nanquantile(X[pre], np.linspace(0, 1, 11)[1:-1], axis=0)          # 9 x F
    qs5 = np.nanquantile(X[pre], np.linspace(0, 1, 6)[1:-1], axis=0)
    dec = np.zeros(X.shape, np.int8)
    qui = np.zeros(X.shape, np.int8)
    for f in range(F):
        dec[:, f] = np.searchsorted(qs10[:, f], X[:, f])
        qui[:, f] = np.searchsorted(qs5[:, f], X[:, f])

    names, Ps, Ns, Qs = [], [], [], []

    def add(name, mask, pay):
        m = mask & test
        if m.sum() < 30:
            return
        d = dix[m]
        names.append(name)
        Ps.append(np.bincount(d, pay[m], D).astype(np.float32))
        Ns.append(np.bincount(d, None, D).astype(np.float32))
        Qs.append(np.bincount(d, pay[m] ** 2, D).astype(np.float32))

    def add_grouped(prefix, base_mask, groups, ng, pay):
        """groups: int array (bucket id per row); adds ng strategies at once."""
        m = base_mask & test
        idx = np.nonzero(m)[0]
        if len(idx) < 30:
            return
        key = groups[idx].astype(np.int64) * D + dix[idx]
        P = np.bincount(key, pay[idx], ng * D).reshape(ng, D)
        N = np.bincount(key, None, ng * D).reshape(ng, D)
        Q = np.bincount(key, pay[idx] ** 2, ng * D).reshape(ng, D)
        for g in range(ng):
            if N[g].sum() >= 30:
                names.append(f"{prefix}|{g}")
                Ps.append(P[g].astype(np.float32)); Ns.append(N[g].astype(np.float32)); Qs.append(Q[g].astype(np.float32))

    coin_mask = {"all": np.ones(len(y), bool)}
    for c in coins:
        coin_mask[c] = R["coin"] == c
    min_mask = {j: R["j"] == j for j in range(1, 15)}

    # F: feature deciles
    log("family F")
    nF = 0
    for j in mins:
        for c in coin_opts:
            cm = min_mask[j] & coin_mask[c]
            for side, pay, price in ((1, payY, priceY), (-1, payN, priceN)):
                for bi, (lo, hi) in enumerate(bands):
                    bm = cm & (price >= lo) & (price <= hi)
                    for f in range(F):
                        before = len(names)
                        add_grouped(f"F|{E.FEATURES[f]}|side{side}|m{j}|{c}|band{bi}|dec", bm, dec[:, f], 10, pay)
                        nF += len(names) - before
    log(f"  F strategies kept (>=30 bets): {nF}")

    # M: model edge
    log("family M")
    ok = np.isfinite(p)
    for thr in (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10):
        selY = ok & (edgeY >= thr) & (ya >= 0.05) & (ya <= 0.95)
        selN = ok & (edgeN >= thr) & (na >= 0.05) & (na <= 0.95) & ~selY
        pay = np.where(selY, payY, payN)
        price = np.where(selY, priceY, priceN)
        sel = selY | selN
        for j in range(1, 15):
            for c in coin_opts:
                for bi, (lo, hi) in enumerate(bands):
                    add(f"M|thr{thr}|m{j}|{c}|band{bi}", sel & min_mask[j] & coin_mask[c] & (price >= lo) & (price <= hi), pay)
        # C: model + feature quintile
        if thr == 0.03:
            log("family C")
            for j in mins:
                for c in coin_opts:
                    for f in range(F):
                        add_grouped(f"C|thr{thr}|{E.FEATURES[f]}|m{j}|{c}|qui", sel & min_mask[j] & coin_mask[c], qui[:, f], 5, pay)
        # H: model + hour block
        for j in mins:
            for c in coin_opts:
                add_grouped(f"H|thr{thr}|m{j}|{c}|block", sel & min_mask[j] & coin_mask[c], hour_block, 6, pay)
    S = len(names)
    log(f"total strategies: {S}")
    P, N, Q = np.array(Ps), np.array(Ns), np.array(Qs)
    return dict(R=R, p=p, tdays=tdays, D=D, dix=dix, test=test, payY=payY, payN=payN, priceY=priceY, priceN=priceN,
                edgeY=edgeY, edgeN=edgeN, bands=bands, dec=dec, qui=qui, hour_block=hour_block, coin_mask=coin_mask,
                min_mask=min_mask, names=names, P=P, N=N, Q=Q, S=S)


def tstat(p_, n_, q_):
    mu = np.divide(p_, n_, out=np.zeros_like(p_), where=n_ > 0)
    var = np.divide(q_ - n_ * mu * mu, n_ - 1, out=np.zeros_like(p_), where=n_ > 1)
    return np.where((n_ >= 30) & (var > 0), mu / np.sqrt(np.where(var > 0, var, 1) / np.where(n_ > 0, n_, 1)), -np.inf)


def main():
    ctx = build()
    R, p, tdays, D, names, P, N, Q, S = (ctx[k] for k in ("R", "p", "tdays", "D", "names", "P", "N", "Q", "S"))

    def tstat(p_, n_, q_):
        mu = np.divide(p_, n_, out=np.zeros_like(p_), where=n_ > 0)
        var = np.divide(q_ - n_ * mu * mu, n_ - 1, out=np.zeros_like(p_), where=n_ > 1)
        return np.where((n_ >= 30) & (var > 0), mu / np.sqrt(np.where(var > 0, var, 1) / np.where(n_ > 0, n_, 1)), -np.inf)

    # baseline: the live model as it runs
    b = E.bets(R, p, 0.04)
    live = json.load(open(E.MODEL))["live_coins"]
    b = E._sub(b, np.isin(b["coin"], live))
    base = np.array([b["pnl"][b["day"] == d].sum() for d in tdays])

    def dstats(dd, bets=None):
        dd = np.asarray(dd, float)
        cum = np.cumsum(dd)
        return {"usd_per_day": round(float(dd.mean()), 3), "t": round(float(dd.mean() / dd.std(ddof=1) * math.sqrt(len(dd))) if dd.std() > 0 else 0, 2),
                "days_up": int((dd > 0).sum()), "days": len(dd), "halves": [round(float(dd[:len(dd) // 2].mean()), 3), round(float(dd[len(dd) // 2:].mean()), 3)],
                "max_drawdown": round(float((np.maximum.accumulate(np.maximum(cum, 0)) - cum).max()), 2),
                **({"cents_per_bet": round(100 * float(dd.sum() / bets), 2), "bets": int(bets)} if bets else {})}

    res = {"strategies": S, "test_days": D, "first_test_day": time.strftime("%Y-%m-%d", time.gmtime(int(tdays[0]) * 86400))}
    WARM = 14
    res["baseline_live_model_4c"] = dstats(base[WARM:], len(b["pnl"][np.isin(b["day"], tdays[WARM:])]))
    log("baseline", res["baseline_live_model_4c"])
    cP, cN, cQ = np.cumsum(P, 1), np.cumsum(N, 1), np.cumsum(Q, 1)
    picks_log = {}
    for K in (1, 5, 20, 100):
        dd, nb = [], 0
        for i in range(WARM, D):
            t = tstat(cP[:, i - 1], cN[:, i - 1], cQ[:, i - 1])
            top = np.argsort(-t)[:K]
            top = top[np.isfinite(t[top])]
            dd.append(float(P[top, i].sum()) / max(K, 1))           # $ per day per strategy slot (1 contract each)
            nb += int(N[top, i].sum())
            if K == 5:
                for j in top:
                    picks_log[names[j]] = picks_log.get(names[j], 0) + 1
        res[f"walk_forward_top{K}"] = dstats(dd, nb / max(K, 1))
        log(f"walk-forward top {K}", res[f"walk_forward_top{K}"])
    res["walk_forward_top5_most_picked"] = sorted(picks_log.items(), key=lambda x: -x[1])[:15]
    cut = WARM + int((D - WARM) * 2 / 3)
    t_sel = tstat(P[:, :cut].sum(1), N[:, :cut].sum(1), Q[:, :cut].sum(1))
    order = np.argsort(-t_sel)
    res["holdout_baseline"] = dstats(base[cut:])
    for K in (1, 5, 20, 100):
        top = order[:K]
        dd = P[top, cut:].sum(0) / K
        res[f"holdout_top{K}"] = dstats(dd, N[top, cut:].sum() / K)
        res[f"holdout_top{K}_names"] = [names[j] for j in top[:10]]
    log("holdout baseline", res["holdout_baseline"])
    for K in (1, 5, 20, 100):
        log(f"holdout top {K}", res[f"holdout_top{K}"])
    t_all = tstat(P.sum(1), N.sum(1), Q.sum(1))
    best = np.argsort(-t_all)[:20]
    res["in_sample_top20_not_a_result"] = [(names[j], round(float(t_all[j]), 2), int(N[j].sum()),
                                            round(100 * float(P[j].sum() / N[j].sum()), 2)) for j in best]
    res["expected_best_t_by_luck"] = round(float(np.sqrt(2 * np.log(S))), 2)
    json.dump(res, open(OUT, "w"), indent=1, default=float)
    log("in-sample best t", res["in_sample_top20_not_a_result"][0], "luck alone ~", res["expected_best_t_by_luck"])
    log("done")


if __name__ == "__main__":
    main()
