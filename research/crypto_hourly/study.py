"""Backtest of Kalshi's hourly crypto "above $X" markets with the live 15-minute bot's method (Nov 27 2026).

Data: research/crypto_hourly/download.py (Kalshi 1-minute quotes, last hour of each event) + the 1-minute spot
files the 15-minute bot already keeps (data/kalshi15m/fwd/<coin>_spot.csv, from Oct 20).

Each strike is looked at L minutes before the close (L in LS). Inputs, like kalshi15m/edge.py:
  dl      logit(spot model) - logit(market mid), spot model = N(log(S/K) / (vol60 * sqrt(L)))   (and with vol240)
  r5z r15z r60z   recent spot moves in vol units;  z = log(S/K)/(vol60*sqrt(L));  interactions with L <= 10, L >= 40
Fit: ridge logistic with logit(mid) as offset, pooled + per coin (edge.fit_all), trained only on the ROLL days before
each test day, refit every 3 days, first WARM days are training only. Bet: decide on minute t's quotes, buy at minute
t+1's ask (YES) or 1 - bid (NO), pay Kalshi's taker fee; net edge >= thr; one bet per market (first chance); price
5-95c. Also scored: the raw spot model with no fitting at all, and every (L, price band, side) rule picked
walk-forward. Results -> research/crypto_hourly/results.json.

    python3 research/crypto_hourly/study.py
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

sys.path.insert(0, ".")
from kalshi15m import edge as E                                   # noqa: E402

DATA = Path("data/crypto_hourly")
SPOT = Path("data/kalshi15m/fwd")
COINS = {"KXBTCD": "KXBTC15M", "KXETHD": "KXETH15M", "KXSOLD": "KXSOL15M", "KXXRPD": "KXXRP15M"}
LS = [55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 7, 5, 3]
FEATS = ["dl", "dl240", "r5z", "r15z", "r60z", "z", "dl_late", "dl_early", "r5z_late", "r15z_late"]
WARM, ROLL, REFIT = 14, 35, 3
OUT = Path("research/crypto_hourly/results.json")
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:5.0f}s]", *a, flush=True)


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


class Spot:
    def __init__(self, path):
        sp = pd.read_csv(path).drop_duplicates("ts").sort_values("ts")
        self.t0 = int(sp.ts.iloc[0])
        grid = self.t0 + 60 * np.arange(int((int(sp.ts.iloc[-1]) - self.t0) // 60) + 1, dtype=np.int64)
        c = sp.set_index("ts").reindex(grid).close.ffill().to_numpy(float)
        self.lc = np.log(c)
        lr = pd.Series(np.r_[np.nan, np.diff(self.lc)])
        self.v60 = lr.rolling(60, min_periods=30).std().to_numpy()
        self.v240 = lr.rolling(240, min_periods=120).std().to_numpy()

    def at(self, arr, t):
        """Value for the bar that ENDS at time t (starts at t - 60)."""
        i = (int(t) - 60 - self.t0) // 60
        return arr[i] if 0 <= i < len(arr) else np.nan


def rows():
    cols = {k: [] for k in ["coin", "ev", "m", "L", "day", "y", "ya", "yb", "fa", "fb", "off", "q"] + FEATS}
    for ser, sc in COINS.items():
        p = DATA / f"{ser}.jsonl"
        if not p.exists():
            log(f"{ser}: no data yet")
            continue
        sp = Spot(SPOT / f"{sc}_spot.csv")
        n = 0
        for ln in open(p):
            e = json.loads(ln)
            C = int(e["close"])
            if sp.at(sp.lc, C - 3600 - 3600) != sp.at(sp.lc, C - 3600 - 3600):     # spot history needed (NaN check)
                continue
            for tk, mk in e["markets"].items():
                K = mk.get("strike")
                if not K or mk.get("result") not in ("yes", "no"):
                    continue
                bars = sorted(mk["bars"])
                bt = np.array([b[0] for b in bars])
                for L in LS:
                    t = C - 60 * L
                    i = np.searchsorted(bt, t, "right") - 1               # last quote at or before t
                    j = np.searchsorted(bt, t + 60, "right") - 1          # the quote one minute later (the fill)
                    if i < 0:
                        continue
                    yb, ya = bars[i][1], bars[i][2]
                    fb, fa = bars[j][1], bars[j][2]
                    if None in (ya, yb, fa, fb):
                        continue
                    mid = (ya + yb) / 2
                    if not 0.04 <= mid <= 0.96:
                        continue
                    S, v, v240 = math.exp(sp.at(sp.lc, t)), sp.at(sp.v60, t), sp.at(sp.v240, t)
                    if not (np.isfinite(S) and v > 0 and v240 > 0):
                        continue
                    x = math.log(S / float(K))
                    q, q240 = ndtr(x / (v * math.sqrt(L))), ndtr(x / (v240 * math.sqrt(L)))
                    off = float(logit(mid))
                    c4 = lambda a: float(np.clip(a, -4, 4))
                    r = lambda k: c4((sp.at(sp.lc, t) - sp.at(sp.lc, t - 60 * k)) / (v * math.sqrt(k)))
                    f = {"dl": float(np.clip(logit(q) - off, -3, 3)), "dl240": float(np.clip(logit(q240) - off, -3, 3)),
                         "r5z": r(5), "r15z": r(15), "r60z": r(60), "z": c4(x / (v * math.sqrt(L)))}
                    late, early = float(L <= 10), float(L >= 40)
                    f.update(dl_late=f["dl"] * late, dl_early=f["dl"] * early, r5z_late=f["r5z"] * late,
                             r15z_late=f["r15z"] * late)
                    if not all(np.isfinite(list(f.values()))):
                        continue
                    for k, val in (("coin", ser), ("ev", e["event"]), ("m", tk), ("L", L), ("day", C // 86400),
                                   ("y", float(mk["result"] == "yes")), ("ya", ya), ("yb", yb), ("fa", fa), ("fb", fb),
                                   ("off", off), ("q", q)):
                        cols[k].append(val)
                    for k in FEATS:
                        cols[k].append(f[k])
                    n += 1
        log(f"{ser}: {n:,} rows")
    R = {k: np.asarray(v) for k, v in cols.items()}
    R["X"] = np.column_stack([R[k] for k in FEATS]).astype(float)
    return R


def walk(R):
    days = np.unique(R["day"])
    p = np.full(len(R["y"]), np.nan)
    bc = None
    for i, d in enumerate(days):
        if i < WARM:
            continue
        if bc is None or (i - WARM) % REFIT == 0:
            tr = (R["day"] < d) & (R["day"] >= d - ROLL)
            _, bc = E.fit_all(R["X"][tr], R["y"][tr], R["off"][tr], R["coin"][tr])
        te = R["day"] == d
        for c, b in bc.items():
            mk = te & (R["coin"] == c)
            p[mk] = E.prob(R["off"][mk], R["X"][mk], b)
    return p, days[WARM:]


def bets(R, p, thr, lmin=0, lmax=99):
    side, price, q, e = E.pick(p, R["fa"], R["fb"], thr)            # filled one minute after the decision
    idx = np.nonzero((side != 0) & np.isfinite(p) & (R["L"] >= lmin) & (R["L"] <= lmax))[0]
    idx = idx[np.lexsort((-R["L"][idx], R["m"][idx]))]               # earliest chance first within each market
    _, first = np.unique(R["m"][idx], return_index=True)
    idx = idx[np.sort(first)]
    win = np.where(side[idx] == 1, R["y"][idx], 1 - R["y"][idx])
    return {"coin": R["coin"][idx], "day": R["day"][idx], "L": R["L"][idx], "price": price[idx], "win": win,
            "pnl": win - price[idx] - E.fee(price[idx]), "ev": R["ev"][idx]}


def halves(b, days):
    h = len(days) // 2
    return [E.summary(b, days[:h])["cents_per_bet"], E.summary(b, days[h:])["cents_per_bet"]]


def band_rules(R, tdays):
    """Every (L, 10c ask band, side) rule; each test day bets the top-K rules by t on earlier days only."""
    days = np.unique(R["day"])
    rules = []
    for L in LS:
        for lo in np.arange(0.05, 0.95, 0.05):
            for sd in (1, -1):
                pr = R["fa"] if sd == 1 else 1 - R["fb"]
                mk = (R["L"] == L) & (pr >= lo) & (pr < lo + 0.10)
                win = R["y"] if sd == 1 else 1 - R["y"]
                rules.append((f"L{L}|{lo:.2f}|{'YES' if sd == 1 else 'NO'}", mk, win - pr - E.fee(pr)))
    D = len(days)
    P = np.zeros((len(rules), D)); N = np.zeros((len(rules), D)); Q = np.zeros((len(rules), D))
    di = np.searchsorted(days, R["day"])
    for k, (_, mk, pnl) in enumerate(rules):
        P[k] = np.bincount(di[mk], pnl[mk], D); N[k] = np.bincount(di[mk], None, D); Q[k] = np.bincount(di[mk], pnl[mk] ** 2, D)
    cP, cN, cQ = P.cumsum(1), N.cumsum(1), Q.cumsum(1)
    out = {"rules": len(rules)}
    for K in (1, 5):
        dd, nb = [], 0
        for i in range(WARM, D):
            n = np.maximum(cN[:, i - 1], 1)
            m = cP[:, i - 1] / n
            sd = np.sqrt(np.maximum(cQ[:, i - 1] / n - m * m, 1e-9))
            t = np.where(cN[:, i - 1] >= 30, m / sd * np.sqrt(n), -np.inf)
            top = np.argsort(-t)[:K]
            dd.append(P[top, i].sum() / K); nb += int(N[top, i].sum())
        dd = np.array(dd)
        out[f"top{K}"] = {"usd_per_day": round(float(dd.mean()), 3), "t": round(E._t(dd), 2), "bets": nb,
                          "cents_per_bet": round(100 * float(dd.sum() * K / max(nb, 1)), 2)}
    return out


def main():
    R = rows()
    if not len(R["y"]):
        return
    log(f"{len(R['y']):,} rows, {len(np.unique(R['ev']))} events, {len(np.unique(R['day']))} days")
    res = {"updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "rows": int(len(R["y"])),
           "events": int(len(np.unique(R["ev"]))), "days": int(len(np.unique(R["day"])))}
    # calibration check: does the market or the raw spot model predict better?
    mid = 1 / (1 + np.exp(-R["off"]))
    ll = lambda pp: float(-np.mean(R["y"] * np.log(np.clip(pp, 1e-4, 1)) + (1 - R["y"]) * np.log(np.clip(1 - pp, 1e-4, 1))))
    res["logloss"] = {"market_mid": round(ll(mid), 4), "spot_model_raw": round(ll(R["q"]), 4)}
    log("log loss", res["logloss"])
    p, tdays = walk(R)
    res["test_days"] = int(len(tdays))
    tmask = np.isin(R["day"], tdays)
    res["logloss"]["fitted_model_test_days"] = round(ll(np.where(tmask, p, mid)[tmask]) if False else float(
        -np.mean(R["y"][tmask] * np.log(p[tmask]) + (1 - R["y"][tmask]) * np.log(1 - p[tmask]))), 4)
    res["logloss"]["market_mid_test_days"] = round(float(-np.mean(R["y"][tmask] * np.log(mid[tmask]) + (1 - R["y"][tmask]) * np.log(1 - mid[tmask]))), 4)
    log("log loss on test days", res["logloss"])
    for thr in (0.03, 0.04, 0.05, 0.08):
        b = bets(R, p, thr)
        s = E.summary(b, tdays)
        s["halves_cents"] = halves(b, tdays)
        s["per_coin"] = {c: E.summary({k: v[b["coin"] == c] for k, v in b.items()}, tdays) for c in COINS}
        res[f"model_thr{thr}"] = s
        log(f"fitted model thr {thr}", {k: s[k] for k in ("bets", "per_day", "cents_per_bet", "usd_per_day", "t", "days_up", "days", "max_drawdown")}, "halves", s["halves_cents"])
        for c in COINS:
            log("   ", c, {k: s["per_coin"][c][k] for k in ("bets", "cents_per_bet", "usd_per_day", "t")})
    for thr in (0.04, 0.08):
        for lmin, lmax in ((3, 10), (15, 30), (35, 55)):
            b = bets(R, p, thr, lmin, lmax)
            s = E.summary(b, tdays)
            res[f"model_thr{thr}_L{lmin}-{lmax}"] = s
            log(f"  thr {thr} minutes-left {lmin}-{lmax}", {k: s[k] for k in ("bets", "cents_per_bet", "usd_per_day", "t")})
    for thr in (0.04, 0.08, 0.15):
        b = bets(R, R["q"], thr)
        s = E.summary(b, tdays)
        res[f"raw_spot_model_thr{thr}"] = s
        log(f"raw spot model (no fit) thr {thr}", {k: s[k] for k in ("bets", "cents_per_bet", "usd_per_day", "t")})
    res["band_rules"] = band_rules(R, tdays)
    log("band rules", res["band_rules"])
    json.dump(res, open(OUT, "w"), indent=1, default=float)
    log("done")


if __name__ == "__main__":
    main()
