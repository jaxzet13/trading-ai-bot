"""Walk-forward test of a cross-coin "consensus" feature: at the same minute of the same 15-minute window, the
average of the OTHER coins' own 5-minute move (r5z) and of their distance from the strike (zown). Same folds and
threshold as the live scorecard.

    python3 research/edge_features/consensus_test.py
"""
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "research/edge_features")
from kalshi15m import edge  # noqa: E402
from gap_test import card  # noqa: E402


def others_mean(R, col):
    v = R["X"][:, edge.FEATURES.index(col)]
    key = R["ots"] * 100 + R["j"]
    s, n = defaultdict(float), defaultdict(int)
    for k, x in zip(key, v):
        s[k] += x
        n[k] += 1
    return np.array([(s[k] - x) / (n[k] - 1) if n[k] > 1 else 0.0 for k, x in zip(key, v)])


def main():
    R = edge.rows(edge.load_panels(log=lambda *a: None))
    c5, cz = others_mean(R, "r5z"), others_mean(R, "zown")

    def run(name, extra=()):
        R2 = dict(R)
        if extra:
            R2["X"] = np.concatenate([R["X"]] + [e[:, None] for e in extra], axis=1)
        p, days = edge.walk_predict(R2, log=lambda *a: None)
        card(R2, p, days, name)

    run("base (live model)")
    run("+ others' 5-min move", (c5,))
    run("+ others' distance", (cz,))
    run("+ both", (c5, cz))


if __name__ == "__main__":
    main()
