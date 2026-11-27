"""Crypto: one million+ strategies (Nov 27 2026). Account holder: "research 1 million strategies for crypto 15m".

The 95k strategies of search.py plus family F2: two-feature rules (feature f in decile a AND feature g in decile b,
deciles from the warm-up days only) -> buy YES or NO at minute 4/7/10/13, on one coin or all, full price band.
210 feature pairs x 100 decile pairs x 2 sides x 4 minutes x 10 coin options = 1.68 million candidates; the ones with
>= 30 bets are scored. Judged exactly like search.py (walk-forward top-K, hold-out third) and by whether the top
strategies add profit on markets the live model does not bet (combine.py logic).

    python3 research/crypto_search/search2.py
"""
import json
import math
import sys
import time

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "research/crypto_search")
from kalshi15m import edge as E                                   # noqa: E402
import search as S                                                # noqa: E402
import combine as C                                               # noqa: E402

T0 = time.time()
WARM = 14


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def mask_of(name, c):
    if not name.startswith("F2|"):
        return C.mask_of(name, c)
    _, f, g, side, m, coin, grp = name.split("|")
    fi, gi = E.FEATURES.index(f), E.FEATURES.index(g)
    sd = int(side[4:])
    a, b = divmod(int(grp), 10)
    price = c["priceY"] if sd == 1 else c["priceN"]
    mk = (c["min_mask"][int(m[1:])] & c["coin_mask"][coin] & (c["dec"][:, fi] == a) & (c["dec"][:, gi] == b)
          & (price >= 0.05) & (price <= 0.95))
    return mk, (c["payY"] if sd == 1 else c["payN"])


def main():
    c = S.build()
    R, D, dix, test = c["R"], c["D"], c["dix"], c["test"]
    names, P, N, Q = list(c["names"]), [c["P"]], [c["N"]], [c["Q"]]
    F = len(E.FEATURES)
    gen = 0
    log("family F2")
    for j in (4, 7, 10, 13):
        for coin in ["all"] + sorted(set(R["coin"])):
            base = c["min_mask"][j] & c["coin_mask"][coin] & test
            idx = np.nonzero(base)[0]
            d = dix[idx]
            for side, pay, price in ((1, c["payY"], c["priceY"]), (-1, c["payN"], c["priceN"])):
                okp = (price[idx] >= 0.05) & (price[idx] <= 0.95)       # same price band as every other family
                pv = np.where(okp, pay[idx], 0.0)
                Pb, Nb, Qb, nb = [], [], [], []
                for f in range(F):
                    for g in range(f + 1, F):
                        gen += 100
                        key = (c["dec"][idx, f].astype(np.int64) * 10 + c["dec"][idx, g]) * D + d
                        Pk = np.bincount(key, pv, 100 * D).reshape(100, D)
                        Nk = np.bincount(key, okp.astype(float), 100 * D).reshape(100, D)
                        keep = np.nonzero(Nk.sum(1) >= 30)[0]
                        if not len(keep):
                            continue
                        Qk = np.bincount(key, pv * pv, 100 * D).reshape(100, D)
                        Pb.append(Pk[keep].astype(np.float32)); Nb.append(Nk[keep].astype(np.float32)); Qb.append(Qk[keep].astype(np.float32))
                        nb += [f"F2|{E.FEATURES[f]}|{E.FEATURES[g]}|side{side}|m{j}|{coin}|{k}" for k in keep]
                if Pb:
                    P.append(np.vstack(Pb)); N.append(np.vstack(Nb)); Q.append(np.vstack(Qb)); names += nb
        log(f"  minute {j} done, {gen:,} generated, {len(names):,} kept")
    P, N, Q = np.vstack(P), np.vstack(N), np.vstack(Q)
    total_generated = gen + 95000
    log(f"strategies generated ~{total_generated:,}; scored (>= 30 bets): {len(names):,}")
    tdays = c["tdays"]
    live = json.load(open(E.MODEL))["live_coins"]
    b = E.bets(R, c["p"], 0.04)
    b = E._sub(b, np.isin(b["coin"], live))
    model_day = {}
    for i in range(len(b["pnl"])):
        model_day.setdefault(int(b["day"][i]), {})[(b["coin"][i], int(b["ots"][i]))] = float(b["pnl"][i])
    cP, cN, cQ = np.cumsum(P, 1), np.cumsum(N, 1), np.cumsum(Q, 1)
    res = {"generated": total_generated, "scored": len(names), "expected_best_t_by_luck": round(math.sqrt(2 * math.log(len(names))), 2)}
    t_all = S.tstat(P.sum(1), N.sum(1), Q.sum(1))
    top_all = np.argsort(-t_all)[:10]
    res["in_sample_top10_not_a_result"] = [(names[j], round(float(t_all[j]), 2), int(N[j].sum())) for j in top_all]
    log("in-sample best", res["in_sample_top10_not_a_result"][:3], "luck alone ~", res["expected_best_t_by_luck"])
    cache = {}
    for K in (1, 5, 20):
        dm, ds, du, nm, ns, nu, picks = [], [], [], 0, 0, 0, {}
        for i in range(WARM, D):
            t = S.tstat(cP[:, i - 1], cN[:, i - 1], cQ[:, i - 1])
            top = [j for j in np.argpartition(-t, K)[:K] if np.isfinite(t[j])]
            day = tdays[i]
            dayrows = R["day"] == day
            cand = {}
            for j in top:
                nmj = names[j]
                picks[nmj] = picks.get(nmj, 0) + 1
                if nmj not in cache:
                    cache[nmj] = mask_of(nmj, c)
                mk, pay = cache[nmj]
                for r in np.nonzero(mk & dayrows)[0]:
                    key = (R["coin"][r], int(R["ots"][r]))
                    if key not in cand or R["j"][r] < cand[key][0]:
                        cand[key] = (int(R["j"][r]), float(pay[r]))
            mday = model_day.get(int(day), {})
            dm.append(sum(mday.values())); nm += len(mday)
            ds.append(sum(v[1] for v in cand.values())); ns += len(cand)
            extra = {k: v for k, v in cand.items() if k not in mday}
            du.append(sum(mday.values()) + sum(v[1] for v in extra.values())); nu += len(mday) + len(extra)
        res[f"K{K}"] = {"model": C.stats(dm, nm), "search_alone": C.stats(ds, ns), "model_plus_search": C.stats(du, nu),
                        "most_picked": sorted(picks.items(), key=lambda x: -x[1])[:5]}
        log(f"K{K}", json.dumps({k: v for k, v in res[f'K{K}'].items() if k != 'most_picked'}))
    cut = WARM + int((D - WARM) * 2 / 3)
    order = np.argsort(-S.tstat(P[:, :cut].sum(1), N[:, :cut].sum(1), Q[:, :cut].sum(1)))
    for K in (1, 5, 20):
        top = order[:K]
        dd = P[top, cut:].sum(0) / K
        res[f"holdout_top{K}"] = {"usd_per_day_per_strategy": round(float(dd.mean()), 3),
                                  "cents_per_bet": round(100 * float(P[top, cut:].sum() / max(N[top, cut:].sum(), 1)), 2),
                                  "bets": int(N[top, cut:].sum()), "names": [names[j] for j in top[:5]]}
        log(f"holdout top {K}", res[f"holdout_top{K}"])
    json.dump(res, open("research/crypto_search/search2_results.json", "w"), indent=1, default=float)
    log("done")


if __name__ == "__main__":
    main()
