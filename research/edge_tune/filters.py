"""Second tuning pass for the live edge model (Nov 27 2026): filters chosen walk-forward.

On top of the current out-of-sample predictions (4c bar), try skipping bets by
  hour of day (UTC, 4-hour blocks), spread width (ask - bid), side (YES only / NO only), coin.
Each test day uses the combination of allowed hours / spread cap / side with the best record on EARLIER days only
(>= 14 days of history). Compared with taking every bet on the same days.

    python3 research/edge_tune/filters.py
"""
import itertools
import json
import sys

import numpy as np

sys.path.insert(0, ".")
from kalshi15m import edge as E                     # noqa: E402

live = json.load(open(E.MODEL))["live_coins"]
R = E.rows(E.load_panels(log=lambda *a: None))
p, days = E.walk_predict(R)
b = E.bets(R, p, E.THR)
b = E._sub(b, np.isin(b["coin"], live))
spread = np.zeros(len(b["pnl"]))
# spread at the bet: look up ya-yb from R for the same coin/ots/minute
key = {(c, o, j): i for i, (c, o, j) in enumerate(zip(R["coin"], R["ots"], R["j"]))}
for k in range(len(b["pnl"])):
    i = key[(b["coin"][k], b["ots"][k], b["j"][k])]
    spread[k] = R["ya"][i] - R["yb"][i]
hour = ((b["ots"] % 86400) // 3600).astype(int)
block = hour // 4

rules = []
for drop_block in [None] + list(range(6)):
    for cap in (None, 0.015, 0.025, 0.035):
        for side in (None, 1, -1):
            rules.append((drop_block, cap, side))


def mask(r):
    db, cap, side = r
    m = np.ones(len(b["pnl"]), bool)
    if db is not None:
        m &= block != db
    if cap is not None:
        m &= spread <= cap + 1e-9
    if side is not None:
        m &= b["side"] == side
    return m


M = np.array([[b["pnl"][mask(r) & (b["day"] == d)].sum() for d in days] for r in rules])
base = M[0]
cum = np.cumsum(M, 1)
wf, picks = [], {}
for i in range(14, len(days)):
    k = int(np.argmax(cum[:, i - 1]))
    wf.append(M[k, i])
    picks[str(rules[k])] = picks.get(str(rules[k]), 0) + 1
wf = np.array(wf)
bb = base[14:]
print(f"take every bet: ${bb.mean():+.3f}/day t {E._t(bb):.2f}  halves {bb[:len(bb)//2].mean():+.3f}/{bb[len(bb)//2:].mean():+.3f}")
print(f"filters chosen walk-forward: ${wf.mean():+.3f}/day t {E._t(wf):.2f}  halves {wf[:len(wf)//2].mean():+.3f}/{wf[len(wf)//2:].mean():+.3f}")
print("picks:", sorted(picks.items(), key=lambda x: -x[1])[:5])
print("per 4h block (UTC) cents/bet:", {f"{4*k:02d}-{4*k+4:02d}": round(100 * float(b['pnl'][block == k].mean()), 2) for k in range(6)})
print("by spread:", {f"<= {c}": round(100 * float(b['pnl'][spread <= c + 1e-9].mean()), 2) for c in (0.01, 0.02, 0.03, 0.05)},
      "wider:", round(100 * float(b['pnl'][spread > 0.03].mean()), 2))
print("by side: YES", round(100 * float(b['pnl'][b['side'] == 1].mean()), 2), "NO", round(100 * float(b['pnl'][b['side'] == -1].mean()), 2))
