"""Step 1 of the resting-bid (maker) study: the walk-forward model's out-of-sample P(YES) for every market x minute
of the last DAYS days, with the quotes it saw, saved as one table.

    python3 research/maker_study/build.py <out.pkl> [days]
"""
import pickle
import sys

import numpy as np

sys.path.insert(0, ".")
from kalshi15m import edge  # noqa: E402

out, days_back = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 14
panels = edge.load_panels(log=lambda *a: None)
R = edge.rows(panels)
p, test_days = edge.walk_predict(R, log=lambda *a: None)
keep = np.isin(R["day"], test_days[-days_back:]) & np.isfinite(p)
tick = np.concatenate([np.asarray(panels[s]["ticker"])[R["m"][R["coin"] == s]] for s in panels])
# rows() concatenates coin by coin in panels order, so the same order rebuilds the ticker column
assert len(tick) == len(R["coin"])
T = {k: R[k][keep] for k in ("coin", "ots", "j", "ya", "yb", "y", "day")}
T["p"], T["ticker"] = p[keep], tick[keep]
pickle.dump(T, open(out, "wb"))
print(len(T["p"]), "rows,", len(np.unique(T["ticker"])), "markets,", len(np.unique(T["day"])), "days")
