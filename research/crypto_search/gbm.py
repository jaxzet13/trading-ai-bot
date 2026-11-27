"""Can a gradient-boosted model beat the live edge model? Same data, same walk-forward, same betting rule.

The live model is a regularised logistic regression on 21 features with Kalshi's mid price as the offset. A
LightGBM model can learn interactions the linear model cannot. Both are trained only on the 35 days before each test
day (refit every 3 days), start from the market's own price (init_score = logit(mid)), and bet the same way (net edge
after fee >= 4c, first minute 4-13, live coins, ask fill). Variants also add the coin and minute as inputs, and a blend
(average of the two models' log-odds).

    python3 research/crypto_search/gbm.py
"""
import json
import math
import sys
import time

import numpy as np
import lightgbm as lgb

sys.path.insert(0, ".")
from kalshi15m import edge as E                                  # noqa: E402

T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def walk_gbm(R, extra, params, rounds):
    days = np.unique(R["day"])
    p = np.full(len(R["y"]), np.nan)
    coin_id = np.searchsorted(np.array(sorted(set(R["coin"]))), R["coin"])
    X = R["X"]
    if extra:
        X = np.column_stack([X, coin_id, R["j"]])
    model = None
    for i, d in enumerate(days):
        if i < E.WARM_DAYS:
            continue
        if model is None or (i - E.WARM_DAYS) % E.REFIT_DAYS == 0:
            tr = (R["day"] < d) & (R["day"] >= d - E.ROLL_DAYS) & np.all(np.isfinite(R["X"]), 1)
            ds = lgb.Dataset(X[tr], label=R["y"][tr], init_score=R["off"][tr],
                             categorical_feature=[X.shape[1] - 2] if extra else "auto", free_raw_data=True)
            model = lgb.train(params, ds, num_boost_round=rounds)
        te = R["day"] == d
        p[te] = 1 / (1 + np.exp(-(R["off"][te] + model.predict(X[te], raw_score=True))))
    return p


def score(R, p, days, live, thr=0.04):
    b = E.bets(R, p, thr)
    b = E._sub(b, np.isin(b["coin"], live))
    return E.summary(b, days[14:]), b


def main():
    log("loading")
    R = E.rows(E.load_panels(log=lambda *a: None))
    live = json.load(open(E.MODEL))["live_coins"]
    p0, days = E.walk_predict(R)
    days = np.asarray(days)
    s0, _ = score(R, p0, days, live)
    log("live model (ridge)", s0)
    res = {"ridge": s0}
    base = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=400, feature_fraction=0.8,
                bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, verbose=-1, num_threads=2)
    for name, extra, params, rounds in (("gbm small", False, base, 150),
                                        ("gbm small + coin/minute", True, base, 150),
                                        ("gbm deeper", False, {**base, "num_leaves": 31, "min_data_in_leaf": 200}, 250),
                                        ("gbm shallow slow", False, {**base, "num_leaves": 7, "learning_rate": 0.02}, 300)):
        p = walk_gbm(R, extra, params, rounds)
        s, _ = score(R, p, days, live)
        res[name] = s
        log(name, s)
        pb = 1 / (1 + np.exp(-(0.5 * logit(p) + 0.5 * logit(p0))))
        sb, _ = score(R, pb, days, live)
        res[name + " + ridge blend"] = sb
        log(name + " + ridge blend", sb)
        for thr in (0.03, 0.05):
            st, _ = score(R, pb, days, live, thr)
            res[f"{name} + ridge blend thr {thr}"] = st
            log(f"  blend thr {thr}", st)
    json.dump(res, open("research/crypto_search/gbm_results.json", "w"), indent=1, default=float)
    log("done")


if __name__ == "__main__":
    main()
