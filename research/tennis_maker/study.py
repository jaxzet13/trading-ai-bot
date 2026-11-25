"""Tennis: would resting bids on pre-match favourites earn what buying at the ask does not?

Known (Nov 24 pooled test): favourites win a little more often than their mid price says, but buying at the ask
(spread + fee) gives it back. A resting bid pays no fee and no spread, but only fills when somebody sells to it.

From the stored 1-minute candles of every settled match (data/tennis/hist/markets.jsonl), for each market and each
decision minute M before the start:
  taker   buy YES at the ask close: value - ask - fee
  maker   rest a YES bid at the bid close until the match starts (or for `rest` minutes):
            if all filled   value - bid          (no selection: an upper bound)
            through         filled only if the bid later trades BELOW our price (certain fill, worst selection)
Day-clustered t statistics; one row per market and M, matches of a day are not independent.

    python3 research/tennis_maker/study.py [out.pkl]
"""
import json
import math
import pickle
import sys
from collections import defaultdict

import numpy as np

STORE = "data/tennis/hist/markets.jsonl"
TOUR = {"KXATPMATCH": "atp", "KXWTAMATCH": "wta", "KXATPCHALLENGERMATCH": "chal", "KXWTACHALLENGERMATCH": "chal",
        "KXITFMATCH": "itf", "KXITFWMATCH": "itf"}
MS = [-240, -180, -120, -90, -60, -30, -10]
RESTS = [30, 60, 9999]                      # minutes a bid rests (9999 = until the scheduled start)


def fee(p):
    return 0.07 * p * (1 - p)


def rows():
    out = []
    for ln in open(STORE):
        m = json.loads(ln)
        if not m["bars"] or len(m["bars"]) < 10:
            continue
        v = m.get("value")
        if v is None:
            v = 1.0 if m.get("result") == "yes" else 0.0 if m.get("result") == "no" else None
        if v is None:
            continue
        b = np.array([[x if x is not None else np.nan for x in r] for r in m["bars"]], float)
        rel = (b[:, 0] - m["start"]) / 60.0
        bid, bidlo, ask, vol = b[:, 1], b[:, 2], b[:, 3], b[:, 5]
        for M in MS:
            i = int(np.searchsorted(rel, M, side="right")) - 1
            if i < 0 or M - rel[i] > 10:
                continue
            bb, aa = bid[i], ask[i]
            if not (np.isfinite(bb) and np.isfinite(aa) and 0.02 < bb < aa < 0.98):
                continue
            r = {"tk": m["ticker"], "ev": m["event"], "tour": TOUR.get(m["series"], "?"), "day": int(m["start"] // 86400),
                 "M": M, "bid": bb, "ask": aa, "v": float(v)}
            for rest in RESTS:
                j = (rel > M) & (rel <= min(M + rest, 0))
                r[f"thr{rest}"] = bool(np.any(bidlo[j] < bb - 1e-9)) if j.any() else False
                r[f"vol{rest}"] = float(np.nansum(vol[j])) if j.any() else 0.0
            out.append(r)
    return out


def tstat(pnl, day):
    by = defaultdict(float)
    for p, d in zip(pnl, day):
        by[d] += p
    w = np.array(list(by.values()))
    return float(w.mean() / w.std(ddof=1) * math.sqrt(len(w))) if len(w) > 2 and w.std() > 0 else 0.0


def table(R, title, mask):
    print(f"\n{title}")
    print("  band        n   win-mid   taker        all-filled   | through fills (certain): rate, earn, t "
          "| filled first half / second half")
    for lo, hi in ((0.05, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 0.9), (0.9, 0.96), (0.8, 0.96)):
        k = mask & (R["mid"] >= lo) & (R["mid"] < hi)
        if k.sum() < 50:
            continue
        v, bid, ask, day = R["v"][k], R["bid"][k], R["ask"][k], R["day"][k]
        tk = v - ask - fee(ask)
        mk = v - bid
        line = (f"  {lo:.2f}-{hi:.2f} {k.sum():6d}  {100 * (v - R['mid'][k]).mean():+6.2f}c  {100 * tk.mean():+6.2f}c (t {tstat(tk, day):+5.2f})"
                f"  {100 * mk.mean():+6.2f}c (t {tstat(mk, day):+5.2f}) |")
        for rest in (60, 9999):
            f = R[f"thr{rest}"][k]
            if f.sum() >= 20:
                half = day[f] <= np.median(day[f])
                line += (f" {'start' if rest == 9999 else str(rest) + 'm'}: {f.mean():.0%} {100 * mk[f].mean():+6.2f}c t {tstat(mk[f], day[f]):+5.2f}"
                         f" [{100 * mk[f][half].mean():+.1f} / {100 * mk[f][~half].mean():+.1f}] |")
        print(line)


def main():
    rs = rows()
    R = {k: np.array([r[k] for r in rs]) for k in rs[0]}
    R["mid"] = (R["bid"] + R["ask"]) / 2
    if len(sys.argv) > 1:
        pickle.dump(R, open(sys.argv[1], "wb"))
    print(len(rs), "market x minute rows,", len(set(R["tk"])), "markets,", len(set(R["day"])), "days; spread mean",
          {t: round(100 * float((R["ask"] - R["bid"])[R["tour"] == t].mean()), 2) for t in ("atp", "wta", "chal", "itf")})
    for t in ("chal", "itf", "atp", "wta"):
        table(R, f"{t}: decision 60 min before the start", (R["tour"] == t) & (R["M"] == -60))
    table(R, "chal: decision 120 min before", (R["tour"] == "chal") & (R["M"] == -120))
    table(R, "chal: decision 240 min before", (R["tour"] == "chal") & (R["M"] == -240))
    table(R, "chal: decision 30 min before", (R["tour"] == "chal") & (R["M"] == -30))


if __name__ == "__main__":
    main()
