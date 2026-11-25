"""What does a late order really get? Replay of every walk-forward taker signal against the trade tape.

The scorecard assumes each bet fills at the ask seen at the minute boundary T. The real order lands later (T + delay)
and the price has often moved. From the tape, the ask at T + delay is estimated from the next trade: a purchase of
our side prints at the ask; a sale prints at the bid (ask = that + the spread seen at T); no trade within WINDOW
seconds = unchanged.

Rules compared (all: one contract, P&L = win - price paid - fee, unfilled = 0):
  walk c     limit = min(ask at T + c, model probability - 5c): today's rule is c = 2c
  guard g    walk 2c, but skip when the ask has FALLEN by more than g since T (the market knows something new)
  relative   re-price the model at the new mid (same log-odds adjustment as at T); buy at the new ask whenever
             the edge after the fee is still >= 5c

    python3 research/fill_study/sim.py <sig_tape.pkl> [out.json]
"""
import json
import math
import pickle
import sys
from collections import defaultdict

import numpy as np

WINDOW, KEEP = 3.0, 0.05


def fee(p):
    return 0.07 * p * (1 - p)


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def ask_at(s, delay):
    """Estimated ask of our side when an order sent for signal s lands `delay` seconds after the minute."""
    spread = max(s["ya"] - s["yb"], 0.01)
    t, yes, buy_yes = s["t"], s["yes"], s["buy_yes"]
    if len(t) == 0:
        return s["price"], False
    o = np.argsort(t, kind="stable")
    t, yes, buy_yes = t[o], yes[o], buy_yes[o]
    i = np.searchsorted(t, s["T"] + delay, side="right")
    if i >= len(t) or t[i] > s["T"] + delay + WINDOW:
        return s["price"], False
    px = float(yes[i]) if s["side"] == 1 else 1 - float(yes[i])
    bought_ours = bool(buy_yes[i]) == (s["side"] == 1)
    return (px if bought_ours else px + spread), True


def decide(s, ask, rule, arg):
    """Price paid (None = no bet) under one rule, given the ask our order meets."""
    if not (0.02 <= ask <= 0.98):
        return None
    if rule in ("walk", "guard"):
        c = arg if rule == "walk" else 0.02
        lim = math.floor(min(s["price"] + c, s["q"] - KEEP) * 100 + 1e-9) / 100
        lim = max(lim, s["price"])                     # the order is never priced below the ask it saw
        if rule == "guard" and ask < s["price"] - arg - 1e-9:
            return None
        return ask if ask <= lim + 1e-9 else None
    if rule == "relative":
        spread = max(s["ya"] - s["yb"], 0.01)
        mid_T = s["price"] - spread / 2
        q_new = 1 / (1 + math.exp(-(logit(s["q"]) + logit(ask - spread / 2) - logit(mid_T))))
        return ask if q_new - ask - fee(ask) >= arg else None
    raise ValueError(rule)


def run(sigs, delay, rule, arg):
    out = []
    for tk, s in sigs.items():
        ask, _ = ask_at(s, delay)
        px = decide(s, ask, rule, arg)
        win = s["y"] if s["side"] == 1 else 1 - s["y"]
        out.append((s["T"] // 900, None if px is None else win - px - fee(px), px, s["price"]))
    return out


def stats(res, n_days):
    pnl = np.array([r[1] if r[1] is not None else 0.0 for r in res])
    filled = np.array([r[1] is not None for r in res])
    by = defaultdict(float)
    for r in res:
        by[r[0]] += r[1] or 0.0
    w = np.array(list(by.values()))
    t = float(w.mean() / w.std(ddof=1) * math.sqrt(len(w))) if len(w) > 2 and w.std() > 0 else 0.0
    slip = np.mean([r[2] - r[3] for r in res if r[1] is not None]) if filled.any() else 0.0
    return {"signals": len(res), "fill_rate": round(float(filled.mean()), 3), "usd_per_day": round(float(pnl.sum()) / n_days, 3),
            "cents_per_signal": round(100 * float(pnl.mean()), 2),
            "cents_per_fill": round(100 * float(pnl[filled].mean()), 2) if filled.any() else 0.0,
            "paid_vs_ask_c": round(100 * float(slip), 2), "t_windows": round(t, 2)}


def main():
    sigs = pickle.load(open(sys.argv[1], "rb"))
    days = sorted({s["day"] for s in sigs.values()})
    n = len(days)
    with_tape = sum(1 for s in sigs.values() if len(s["t"]))
    print(f"{len(sigs)} signals over {n} days ({with_tape} with trades in the 14 s around the minute)")
    base = [((s["y"] if s["side"] == 1 else 1 - s["y"]) - s["price"] - fee(s["price"])) for s in sigs.values()]
    print(f"scorecard assumption (every signal fills at the ask at T): {100 * np.mean(base):+.2f}c a signal, "
          f"${np.sum(base) / n:+.2f}/day")
    res = {}
    for delay in (0.3, 0.6, 1.0, 1.35):
        print(f"--- order lands {delay} s after the minute")
        for rule, args in (("walk", (0.0, 0.01, 0.02, 0.03, 0.05, 0.10)), ("guard", (0.01, 0.02, 0.03)),
                           ("relative", (0.05, 0.04))):
            for a in args:
                s = stats(run(sigs, delay, rule, a), n)
                res[f"{delay}/{rule}/{a}"] = s
                print(f"  {rule:8s} {100 * a:4.0f}c: fills {s['fill_rate']:.0%}  ${s['usd_per_day']:+.2f}/day  "
                      f"{s['cents_per_signal']:+.2f}c a signal  {s['cents_per_fill']:+.2f}c a fill  "
                      f"paid {s['paid_vs_ask_c']:+.2f}c vs ask at T  t {s['t_windows']:.2f}")
    if len(sys.argv) > 2:
        json.dump({"days": n, "signals": len(sigs), "results": res}, open(sys.argv[2], "w"), indent=1)


if __name__ == "__main__":
    main()
