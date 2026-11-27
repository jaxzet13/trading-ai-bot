"""Do the search's best strategies add anything to the live model? One contract per market, no double bets.

Each test day: the top K strategies by their record on EARLIER days only; their signals that day are pooled, one bet
per market (the earliest minute). Portfolios compared on the same days:
  model        the live model as it runs (4c bar, live coins)
  search K     the pooled top-K strategies alone
  model + K    the model's bets plus the search's bets on markets the model did not bet

    python3 research/crypto_search/combine.py
"""
import json
import math
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "research/crypto_search")
from kalshi15m import edge as E                                 # noqa: E402
import search as S                                              # noqa: E402

WARM = 14


def mask_of(name, c):
    parts = name.split("|")
    fam = parts[0]
    R = c["R"]
    if fam == "F":
        _, feat, side, m, coin, band, _, g = parts
        f = E.FEATURES.index(feat)
        sd = int(side[4:])
        lo, hi = c["bands"][int(band[4:])]
        price = c["priceY"] if sd == 1 else c["priceN"]
        mk = c["min_mask"][int(m[1:])] & c["coin_mask"][coin] & (price >= lo) & (price <= hi) & (c["dec"][:, f] == int(g))
        return mk, (c["payY"] if sd == 1 else c["payN"])
    thr = float(parts[1][3:])
    ok = np.isfinite(c["p"])
    selY = ok & (c["edgeY"] >= thr) & (R["ya"] >= 0.05) & (R["ya"] <= 0.95)
    selN = ok & (c["edgeN"] >= thr) & (1 - R["yb"] >= 0.05) & (1 - R["yb"] <= 0.95) & ~selY
    pay = np.where(selY, c["payY"], c["payN"])
    price = np.where(selY, c["priceY"], c["priceN"])
    sel = selY | selN
    if fam == "M":
        _, _, m, coin, band = parts
        lo, hi = c["bands"][int(band[4:])]
        return sel & c["min_mask"][int(m[1:])] & c["coin_mask"][coin] & (price >= lo) & (price <= hi), pay
    if fam == "C":
        _, _, feat, m, coin, _, g = parts
        f = E.FEATURES.index(feat)
        return sel & c["min_mask"][int(m[1:])] & c["coin_mask"][coin] & (c["qui"][:, f] == int(g)), pay
    _, _, m, coin, _, g = parts
    return sel & c["min_mask"][int(m[1:])] & c["coin_mask"][coin] & (c["hour_block"] == int(g)), pay


def stats(dd, n):
    dd = np.asarray(dd)
    return {"usd_per_day": round(float(dd.mean()), 3), "t": round(float(dd.mean() / dd.std(ddof=1) * math.sqrt(len(dd))), 2),
            "days_up": int((dd > 0).sum()), "days": len(dd), "bets_per_day": round(n / len(dd), 1),
            "cents_per_bet": round(100 * float(dd.sum()) / max(n, 1), 2),
            "halves": [round(float(dd[:len(dd) // 2].mean()), 3), round(float(dd[len(dd) // 2:].mean()), 3)]}


def main():
    c = S.build()
    R, tdays, D = c["R"], c["tdays"], c["D"]
    live = json.load(open(E.MODEL))["live_coins"]
    b = E.bets(R, c["p"], 0.04)
    b = E._sub(b, np.isin(b["coin"], live))
    model_day = {}
    for i in range(len(b["pnl"])):
        model_day.setdefault(int(b["day"][i]), {})[(b["coin"][i], int(b["ots"][i]))] = float(b["pnl"][i])
    cP, cN, cQ = np.cumsum(c["P"], 1), np.cumsum(c["N"], 1), np.cumsum(c["Q"], 1)
    cache = {}
    out = {}
    for K in (5, 20, 100):
        dm, ds, du, nm, ns, nu = [], [], [], 0, 0, 0
        for i in range(WARM, D):
            t = S.tstat(cP[:, i - 1], cN[:, i - 1], cQ[:, i - 1])
            top = [j for j in np.argsort(-t)[:K] if np.isfinite(t[j])]
            day = tdays[i]
            dayrows = R["day"] == day
            cand = {}
            for j in top:
                nmj = c["names"][j]
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
        out[f"K{K}"] = {"model": stats(dm, nm), "search_alone": stats(ds, ns), "model_plus_search": stats(du, nu)}
        print(K, json.dumps(out[f"K{K}"]), flush=True)
    json.dump(out, open("research/crypto_search/combine_results.json", "w"), indent=1)


if __name__ == "__main__":
    main()
