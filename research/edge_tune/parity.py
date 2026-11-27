"""Live vs backtest on the same markets: does the live edge model bet what the walk-forward backtest bets, and do
the shared bets earn the same? (python3 research/edge_tune/parity.py [since_ts])

Nov 27 2026, account holder: "Notice how at the start it skyrocketed ... and now it's been plateaued, try to figure
that out". First run: since the Nov 24 switch, 174 backtest bets vs 177 live, 147 shared (same side on all 147,
same minute on 117, live paid +0.4c more); the backtest itself made -$0.16 on its 174 bets at 1 contract, so the
flat stretch is the market, not the bot.
"""
import collections
import json
import sys

import numpy as np

sys.path.insert(0, ".")
from kalshi15m import edge as E                                     # noqa: E402

ev = [json.loads(l) for l in open(E.REAL_LOG)]
live = {(e["series"], e["close_ts"] - 900): e for e in ev
        if e.get("event") == "order_intent" and str(e.get("rule", "")).startswith("edge")}
settle = {e["ticker"]: e for e in ev if e.get("event") == "settle"}
since = int(sys.argv[1]) if len(sys.argv) > 1 else min(k[1] for k in live)
R = E.rows(E.load_panels(log=lambda *a: None))
p, _ = E.walk_predict(R)
coins = json.load(open(E.MODEL))["live_coins"]
b = E.bets(R, p, E.THR)
m = np.isin(b["coin"], coins) & (b["ots"] >= since)
bt = {(b["coin"][i], int(b["ots"][i])): (int(b["j"][i]), int(b["side"][i]), float(b["price"][i]), float(b["pnl"][i]))
      for i in np.nonzero(m)[0]}
last = int(R["ots"].max())
lv = {k: v for k, v in live.items() if since <= k[1] <= last}
both = set(bt) & set(lv)


def lpl(k):
    s = settle.get(lv[k]["ticker"])
    return s["pnl"] / s["n"] if s and s.get("n") else None


shared = [x for x in (lpl(k) for k in both) if x is not None]
print(f"backtest bets {len(bt)}  live bets {len(lv)}  shared {len(both)}  backtest-only {len(set(bt) - set(lv))}  "
      f"live-only {len(set(lv) - set(bt))}")
print(f"backtest P&L at 1 contract: {sum(v[3] for v in bt.values()):+.2f}  (shared {sum(bt[k][3] for k in both):+.2f})")
print(f"live P&L per contract on shared bets: {sum(shared):+.2f} over {len(shared)}")
print(f"same side {sum(1 for k in both if (1 if lv[k]['side'] == 'yes' else -1) == bt[k][1])}/{len(both)}, "
      f"same minute {sum(1 for k in both if lv[k]['minute'] == bt[k][0])}/{len(both)}")
