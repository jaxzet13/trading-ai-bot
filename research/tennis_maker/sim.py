"""Tennis resting bids replayed against the trade tape (Challenger favourites before the scheduled start).

For each market whose mid is in the band at decision minute M: rest a 1-contract YES bid from M until the scheduled
start (or for `rest` minutes), at the bid (join) or one cent above it when the spread allows (improve).
Fill rules, read off real trades by takers selling YES:
  certain   a trade printed below the bid: filled whatever the queue (worst selection)
  touch     a trade printed at or below the bid: assumes first in the queue (best case)
  improve   a bid alone at its price is hit by any sale at or below it
No fee on fills (tennis series charge takers only). Compared with buying at the ask at M (fee included).

    python3 research/tennis_maker/sim.py <rows.pkl> <tape.pkl> [out.json]
"""
import json
import math
import pickle
import sys
from collections import defaultdict

import numpy as np


def fee(p):
    return 0.07 * p * (1 - p)


def tstat(pnl, day):
    by = defaultdict(float)
    for p, d in zip(pnl, day):
        by[d] += p
    w = np.array(list(by.values()))
    return float(w.mean() / w.std(ddof=1) * math.sqrt(len(w))) if len(w) > 2 and w.std() > 0 else 0.0


def sells(tp, t0, t1):
    m = (tp["t"] > t0) & (tp["t"] <= t1) & ~tp["buy_yes"]
    return tp["yes"][m]


def run(R, tape, M, lo, hi, rest):
    out = []
    k = np.nonzero((R["tour"] == "chal") & (R["M"] == M) & (R["mid"] >= lo) & (R["mid"] < hi))[0]
    for i in k:
        tp = tape.get(R["tk"][i])
        if tp is None:
            continue
        T, end = tp["start"] + 60 * M, tp["start"] + 60 * min(M + rest, 0)
        b, a, v = float(R["bid"][i]), float(R["ask"][i]), float(R["v"][i])
        s = sells(tp, T + 5, end)
        imp = round(b + 0.01, 4) if a - b >= 0.0199 else b
        out.append({"day": int(R["day"][i]), "v": v, "bid": b, "ask": a, "taker": v - a - fee(a),
                    "certain": bool((s < b - 1e-6).any()), "touch": bool((s <= b + 1e-6).any()),
                    "imp_px": imp, "improve": bool((s <= imp + 1e-6).any()), "n_sells": int(len(s))})
    return out


def line(name, rows, flag, px):
    f = [r for r in rows if r[flag]] if flag else rows
    if len(f) < 15:
        return f"  {name:24s} n={len(f)}"
    pnl = np.array([r["v"] - r[px] for r in f]) if px != "taker" else np.array([r["taker"] for r in f])
    day = np.array([r["day"] for r in f])
    half = day <= np.median(day)
    un = [r for r in rows if not r[flag]] if flag else []
    s = (f"  {name:24s} fills {len(f) / len(rows):4.0%}  {100 * pnl.mean():+6.2f}c a fill  t {tstat(pnl, day):+5.2f}  "
         f"win {np.mean([r['v'] for r in f]):.3f} at {np.mean([r[px] if px != 'taker' else r['ask'] for r in f]):.3f}  "
         f"halves {100 * pnl[half].mean():+.1f} / {100 * pnl[~half].mean():+.1f}  "
         f"per signal {100 * pnl.sum() / len(rows):+.2f}c")
    if un and px != "taker":
        s += f"  | unfilled {len(un)}: would earn {100 * np.mean([r['v'] - r[px] for r in un]):+.1f}c"
    return s


def main():
    R = pickle.load(open(sys.argv[1], "rb"))
    tape = pickle.load(open(sys.argv[2], "rb"))
    print(len(tape), "markets with tape")
    res = {}
    for M in (-120, -60, -30):
        for lo, hi in ((0.80, 0.96), (0.80, 0.90), (0.90, 0.96)):
            for rest in (9999, 30):
                rows = run(R, tape, M, lo, hi, rest)
                if len(rows) < 40:
                    continue
                print(f"\nM {M} min, mid {lo:.2f}-{hi:.2f}, rest {'until the start' if rest == 9999 else str(rest) + ' min'}: "
                      f"{len(rows)} signals over {len({r['day'] for r in rows})} days, "
                      f"median sales to a resting bid {int(np.median([r['n_sells'] for r in rows]))}")
                print(line("buy at the ask (taker)", rows, None, "taker"))
                print(line("bid, if all filled", rows, None, "bid"))
                print(line("bid, certain fills", rows, "certain", "bid"))
                print(line("bid, touch fills", rows, "touch", "bid"))
                print(line("bid + 1c, any sale", rows, "improve", "imp_px"))
                res[f"{M}/{lo}-{hi}/{rest}"] = {
                    "signals": len(rows),
                    **{n: round(100 * float(np.mean([r["v"] - r[p] for r in rows if r[f]])), 2) if any(r[f] for r in rows) else None
                       for n, f, p in (("certain_c", "certain", "bid"), ("touch_c", "touch", "bid"), ("improve_c", "improve", "imp_px"))},
                    "taker_c": round(100 * float(np.mean([r["taker"] for r in rows])), 2)}
    if len(sys.argv) > 3:
        json.dump(res, open(sys.argv[3], "w"), indent=1)


if __name__ == "__main__":
    main()
