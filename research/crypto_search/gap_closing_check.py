"""Is the 'gap closing' input (change in dl over the last minute) a real improvement? Paired, day by day.

Same walk-forward and betting rule as the live model; compares daily P&L of the model with and without the input on
the same test days, by halves, by coin, and at 3/4/5c bars.
"""
import json
import math
import sys

import numpy as np

sys.path.insert(0, ".")
from kalshi15m import edge as E                                   # noqa: E402

R = E.rows(E.load_panels(log=lambda *a: None))
live = json.load(open(E.MODEL))["live_coins"]
dl = R["X"][:, E.FEATURES.index("dl")]
key = {(c, o, j): i for i, (c, o, j) in enumerate(zip(R["coin"], R["ots"], R["j"]))}
ddl = np.zeros(len(dl))
for i, (c, o, j) in enumerate(zip(R["coin"], R["ots"], R["j"])):
    r = key.get((c, o, j - 1))
    ddl[i] = dl[i] - dl[r] if r is not None else 0.0
ddl = np.clip(ddl, -2, 2)
p0, days = E.walk_predict(R)
days = np.asarray(days)[14:]
X0 = R["X"]
R["X"] = np.column_stack([X0, ddl])
p1, _ = E.walk_predict(R)
R["X"] = X0


def daily(p, thr, coins=live):
    b = E.bets(R, p, thr)
    b = E._sub(b, np.isin(b["coin"], coins))
    return np.array([b["pnl"][b["day"] == d].sum() for d in days])


for thr in (0.03, 0.04, 0.05):
    a, b = daily(p0, thr), daily(p1, thr)
    d = b - a
    h = len(d) // 2
    t = d.mean() / d.std(ddof=1) * math.sqrt(len(d))
    print(f"bar {thr}: model ${a.mean():.3f}/day, + gap closing ${b.mean():.3f}/day, difference ${d.mean():+.3f}/day "
          f"paired t {t:+.2f}, days better {(d > 0).sum()}/{(d != 0).sum()}, halves {d[:h].mean():+.3f}/{d[h:].mean():+.3f}")
for c in live:
    a, b = daily(p0, 0.04, [c]), daily(p1, 0.04, [c])
    print(f"  {c}: {a.sum():+.2f} -> {b.sum():+.2f}")
