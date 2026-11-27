"""New inputs for the live edge model, judged by the same walk-forward (Nov 27 2026).

Already tested and rejected earlier (research/edge_features): the vol-model gap, cross-coin consensus. New here:
  dmid1, dmid3  the market's own move: logit(mid) now minus 1 / 3 minutes ago (same market)
  ddl1          is the gap between the spot model and the market closing or widening (dl now - dl a minute ago)
  spread        ask - bid
Each added to the 21 live features; same fit (pooled ridge + per-coin), same 35-day window, 4c bar, live coins.

    python3 research/crypto_search/features2.py
"""
import json
import sys

import numpy as np

sys.path.insert(0, ".")
from kalshi15m import edge as E                                   # noqa: E402


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def main():
    R = E.rows(E.load_panels(log=lambda *a: None))
    live = json.load(open(E.MODEL))["live_coins"]
    mid = (R["ya"] + R["yb"]) / 2
    lm = logit(mid)
    dl = R["X"][:, E.FEATURES.index("dl")]
    key = {(c, o, j): i for i, (c, o, j) in enumerate(zip(R["coin"], R["ots"], R["j"]))}

    def lag(arr, k):
        out = np.zeros(len(arr))
        for i, (c, o, j) in enumerate(zip(R["coin"], R["ots"], R["j"])):
            r = key.get((c, o, j - k))
            out[i] = arr[i] - arr[r] if r is not None else 0.0
        return np.clip(out, -2, 2)

    new = {"dmid1": lag(lm, 1), "dmid3": lag(lm, 3), "ddl1": lag(dl, 1), "spread": np.clip(R["ya"] - R["yb"], 0, 0.2) * 10}
    p0, days = E.walk_predict(R)
    days = np.asarray(days)

    def score(p):
        b = E.bets(R, p, 0.04)
        b = E._sub(b, np.isin(b["coin"], live))
        return E.summary(b, days[14:])

    res = {"live model": score(p0)}
    print("live model", res["live model"], flush=True)
    X0 = R["X"]
    for name, cols in (("+ market move 1m", ["dmid1"]), ("+ market move 3m", ["dmid3"]), ("+ gap closing", ["ddl1"]),
                       ("+ spread", ["spread"]), ("+ all four", ["dmid1", "dmid3", "ddl1", "spread"])):
        R["X"] = np.column_stack([X0] + [new[c] for c in cols])
        p, _ = E.walk_predict(R)
        res[name] = score(p)
        print(name, res[name], flush=True)
    R["X"] = X0
    json.dump(res, open("research/crypto_search/features2_results.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
