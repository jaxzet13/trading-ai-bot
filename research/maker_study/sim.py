"""Step 3 of the resting-bid (maker) study: replay resting bids against Kalshi's trade tape.

A resting bid pays no Kalshi fee and does not pay the spread, but it only fills when somebody sells to it, which
happens more often when the price is about to move against it. The tape answers whether what is saved is worth more
than what that costs.

Every minute 4-13 of a market (one bet per market, like the live bot):
  taker   buy at the ask when the model's edge after the fee is >= 5c (today's rule; the scorecard assumes it fills)
  maker   rest a bid for LIFE seconds when the model's probability is >= thr above the bid price:
            join     at the best bid on that side
            improve  one cent above the best bid when the spread is 2c or more (else join)
          fill rules, both read off the tape between T+DELAY and T+LIFE:
            through  a trade printed below the bid: certain fill, whatever the queue (worst case for what follows)
            touch    a trade printed at or below the bid: assumes we are first in the queue (best case)
          a bid improved by a cent is alone at its price, so any sale at or below it fills it
  hybrid  taker when its rule fires, else a resting bid

    python3 research/maker_study/sim.py <rows.pkl> <tape.pkl> [out.json]
"""
import json
import math
import pickle
import sys
from collections import defaultdict

import numpy as np

PMIN, PMAX, TAKER_THR, START, END = 0.05, 0.95, 0.05, 4, 13
DELAY, LIFE = 1.2, 58.0


def fee(p):
    return 0.07 * p * (1 - p)


def taker_pick(p, ya, yb):
    na = 1 - yb
    ey, en = p - ya - fee(ya), (1 - p) - na - fee(na)
    if ey >= TAKER_THR and PMIN <= ya <= PMAX:
        return 1, ya, ey
    if en >= TAKER_THR and PMIN <= na <= PMAX:
        return -1, na, en
    return 0, 0.0, 0.0


def maker_pick(p, ya, yb, thr, improve):
    """Side and price of the resting bid (0 = none). YES bid sits at yb, NO bid at 1 - ya."""
    py, pn = yb, 1 - ya
    alone_y = alone_n = False
    if improve and ya - yb >= 0.0199:
        py, pn, alone_y, alone_n = round(yb + 0.01, 4), round(1 - ya + 0.01, 4), True, True
    ey, en = p - py, (1 - p) - pn
    oky, okn = ey >= thr and PMIN <= py <= PMAX, en >= thr and PMIN <= pn <= PMAX
    if oky and (not okn or ey >= en):
        return 1, py, ey, alone_y
    if okn:
        return -1, pn, en, alone_n
    return 0, 0.0, 0.0, False


def filled(tp, T, side, price, rule, alone):
    """Did a 1-contract bid resting from T+DELAY to T+LIFE trade? tp = the market's tape."""
    m = (tp["t"] > T + DELAY) & (tp["t"] <= T + LIFE)
    if side == 1:                                   # YES bid: filled by takers selling YES (buying NO)
        px = tp["yes"][m & ~tp["buy_yes"]]
        return bool((px <= price + 1e-6).any()) if (rule == "touch" or alone) else bool((px < price - 1e-6).any())
    px = 1 - tp["yes"][m & tp["buy_yes"]]           # NO bid: filled by takers buying YES; their NO price
    return bool((px <= price + 1e-6).any()) if (rule == "touch" or alone) else bool((px < price - 1e-6).any())


def run(markets, tape, mode, thr=0.04, improve=False, rule="through"):
    """mode: taker | maker | hybrid | maker_first (rest a bid on taker signals; take next minute if still there)."""
    bets, posted = [], 0
    for tk, rows in markets.items():
        tp, pending_take = tape.get(tk), False
        for (j, ots, p, ya, yb, y) in rows:
            T = ots + 60 * j
            ts, tprice, tedge = taker_pick(p, ya, yb)
            if mode in ("taker", "hybrid") and ts:
                win = y if ts == 1 else 1 - y
                bets.append((ots, tk, "taker", tprice, win, win - tprice - fee(tprice), tedge))
                break
            if mode == "maker_first":
                if not ts:
                    pending_take = False
                    continue
                if pending_take:                                    # second minute in a row with the signal: take
                    win = y if ts == 1 else 1 - y
                    bets.append((ots, tk, "taker", tprice, win, win - tprice - fee(tprice), tedge))
                    break
                bid = round(tprice - 0.01, 4)                       # one cent under the ask, on our side
                posted += 1
                if tp is not None and filled(tp, T, ts, bid, "touch", True):
                    win = y if ts == 1 else 1 - y
                    bets.append((ots, tk, "maker", bid, win, win - bid, tedge))
                    break
                pending_take = True
                continue
            if mode in ("maker", "hybrid") and tp is not None:
                ms, mprice, medge, alone = maker_pick(p, ya, yb, thr, improve)
                if ms:
                    posted += 1
                    if filled(tp, T, ms, mprice, rule, alone):
                        win = y if ms == 1 else 1 - y
                        bets.append((ots, tk, "maker", mprice, win, win - mprice, medge))
                        break
    return bets, posted


def stats(bets, posted, n_days):
    if not bets:
        return {"bets": 0}
    pnl = np.array([b[5] for b in bets])
    by_win = defaultdict(float)
    for b in bets:
        by_win[b[0]] += b[5]                                        # coins in one 15-minute window move together
    w = np.array(list(by_win.values()))
    t = float(w.mean() / w.std(ddof=1) * math.sqrt(len(w))) if len(w) > 2 and w.std() > 0 else 0.0
    mk = np.array([b[2] == "maker" for b in bets])
    out = {"bets": len(bets), "per_day": round(len(bets) / n_days, 1), "cents_per_bet": round(100 * pnl.mean(), 2),
           "usd_per_day": round(float(pnl.sum()) / n_days, 2), "t_windows": round(t, 2),
           "win_rate": round(float(np.mean([b[4] for b in bets])), 3),
           "avg_price": round(float(np.mean([b[3] for b in bets])), 3),
           "model_edge_c": round(100 * float(np.mean([b[6] for b in bets])), 2)}
    if mk.any():
        out.update(maker_bets=int(mk.sum()), maker_cents=round(100 * float(pnl[mk].mean()), 2),
                   fill_rate=round(float(mk.sum()) / max(posted, 1), 3))
    if (~mk).any() and mk.any():
        out.update(taker_bets=int((~mk).sum()), taker_cents=round(100 * float(pnl[~mk].mean()), 2))
    return out


def load(rows_path, tape_path):
    T, tape = pickle.load(open(rows_path, "rb")), pickle.load(open(tape_path, "rb"))
    days = sorted({int(T["day"][i]) for i in range(len(T["day"])) if T["ticker"][i] in tape})
    coins = sorted({str(T["coin"][i]) for i in range(len(T["coin"])) if T["ticker"][i] in tape})
    ok = np.isin(T["day"], days) & np.isin(T["coin"], coins) & (T["j"] >= START) & (T["j"] <= END)
    markets = defaultdict(list)
    for i in np.nonzero(ok)[0]:
        markets[str(T["ticker"][i])].append((int(T["j"][i]), int(T["ots"][i]), float(T["p"][i]), float(T["ya"][i]),
                                             float(T["yb"][i]), float(T["y"][i])))
    for v in markets.values():
        v.sort()
    return dict(markets), tape, days, coins


def main():
    markets, tape, days, coins = load(sys.argv[1], sys.argv[2])
    n = len(days)
    print(f"{len(markets)} markets, {len(tape)} with tape, {n} days, coins {[c[2:-3] for c in coins]}")
    res = {}

    def show(name, bets, posted):
        s = res[name] = stats(bets, posted, n)
        extra = (f"  fill {s['fill_rate']:.0%}  maker {s['maker_bets']} at {s['maker_cents']:+.2f}c"
                 if "maker_bets" in s else "")
        extra += f"  taker {s['taker_bets']} at {s['taker_cents']:+.2f}c" if "taker_bets" in s else ""
        print(f"{name:34s} {s.get('per_day', 0):6.1f}/day {s.get('cents_per_bet', 0):+6.2f}c  "
              f"${s.get('usd_per_day', 0):+6.2f}/day  t {s.get('t_windows', 0):5.2f}  win {s.get('win_rate', 0):.3f} "
              f"at {s.get('avg_price', 0):.3f}  model {s.get('model_edge_c', 0):+.1f}c{extra}")

    show("taker (today's rule)", *run(markets, tape, "taker"))
    show("maker first, then take", *run(markets, tape, "maker_first"))
    for improve in (False, True):
        for rule in ("through", "touch"):
            if improve and rule == "touch":
                continue
            for thr in (0.03, 0.04, 0.05, 0.06, 0.08):
                tag = f"{'improve' if improve else 'join'}/{rule} {thr * 100:.0f}c"
                show("maker " + tag, *run(markets, tape, "maker", thr, improve, rule))
    for improve in (False, True):
        for thr in (0.04, 0.05, 0.06, 0.08):
            tag = f"{'improve' if improve else 'join'}/through {thr * 100:.0f}c"
            show("hybrid " + tag, *run(markets, tape, "hybrid", thr, improve, "through"))
    if len(sys.argv) > 3:
        json.dump({"days": n, "coins": coins, "markets": len(markets), "results": res}, open(sys.argv[3], "w"), indent=1)


if __name__ == "__main__":
    main()
