"""Can the edge model learn what the restored ZEC rule (fv_tau) sees? Walk-forward test of extra features.

fv_tau bets when the vol model's probability is 11c or more away from Kalshi's price; next to the edge model its
extra ZEC bets made +9c each on unseen days, so the model under-reacts to large gaps on ZEC. Candidates, judged
only by the walk-forward scorecard (same folds, same threshold):
  gap      q - mid in probability units (the model has it in log-odds only)
  gapbig   the part of |gap| beyond 8c, signed
  lam      weaker shrinkage of each coin's coefficients toward the pooled fit (LAM_COIN 300 -> 100 / 30)

    python3 research/edge_features/gap_test.py
"""
import math
import sys

import numpy as np

sys.path.insert(0, ".")
from kalshi15m import edge  # noqa: E402

LIVE = ["KXDOGE15M", "KXNEAR15M", "KXSOL15M", "KXXRP15M", "KXZEC15M"]


def card(R, p, days, name):
    b = edge.bets(R, p)
    live = edge._sub(b, np.isin(b["coin"], LIVE))
    s = edge.summary(live, days)
    h = len(days) // 2
    s1, s2 = edge.summary(live, days[:h]), edge.summary(live, days[h:])
    per = {c[2:-3]: edge.summary(edge._sub(b, b["coin"] == c), days) for c in LIVE}
    print(f"{name:26s} {s['per_day']:5.1f}/day {s['cents_per_bet']:+5.2f}c ${s['usd_per_day']:+.2f}/day t {s['t']:5.2f} "
          f"up {s['days_up']}/{s['days']} maxDD ${s['max_drawdown']:.2f} | halves ${s1['usd_per_day']:+.2f} / ${s2['usd_per_day']:+.2f} | "
          + " ".join(f"{c} {v['per_day']:.1f}@{v['cents_per_bet']:+.1f} t{v['t']:.1f}" for c, v in per.items()), flush=True)
    return s


def main():
    R = edge.rows(edge.load_panels(log=lambda *a: None))
    X, off = R["X"], R["off"]
    dl = X[:, edge.FEATURES.index("dl")]
    mid = 1 / (1 + np.exp(-off))
    q = 1 / (1 + np.exp(-(dl + off)))
    gap = np.clip(q - mid, -0.5, 0.5)
    gapbig = np.sign(gap) * np.maximum(np.abs(gap) - 0.08, 0)
    late = (R["j"] >= edge.LATE).astype(float)

    def run(name, extra=(), lam=None):
        R2 = dict(R)
        if extra:
            R2["X"] = np.concatenate([X] + [e[:, None] for e in extra], axis=1)
        old = edge.LAM_COIN
        if lam:
            edge.LAM_COIN = lam
        try:
            p, days = edge.walk_predict(R2, log=lambda *a: None)
        finally:
            edge.LAM_COIN = old
        return card(R2, p, days, name)

    run("base (live model)")
    run("+ gap", (gap,))
    run("+ gapbig", (gapbig,))
    run("+ gap + gapbig", (gap, gapbig))
    run("+ gap + gap_late", (gap, gap * late))
    run("base, LAM_COIN 100", lam=100.0)
    run("base, LAM_COIN 30", lam=30.0)
    run("+ gapbig, LAM_COIN 100", (gapbig,), lam=100.0)


if __name__ == "__main__":
    main()
