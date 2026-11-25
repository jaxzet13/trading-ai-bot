"""Edge model (kalshi15m/edge.py): the math, the bet rule, the sizing, and that the LIVE path (golden_live engine
fed minute by minute, with a BTC reference engine) computes exactly the features and predictions the batch
(training / walk-forward) path computes. No network, no credentials.

    nice python3 -m pytest -q tests/test_edge.py
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kalshi15m import backtest as B  # noqa: E402
from kalshi15m import edge as E  # noqa: E402
from kalshi15m import golden_live as GL  # noqa: E402
from kalshi15m import lab3, real  # noqa: E402
from kalshi15m.data import DATA_DIR  # noqa: E402


def test_fit_recovers_known_coefficients():
    rng = np.random.default_rng(1)
    n, k = 60000, 4
    X = rng.normal(size=(n, k))
    off = rng.normal(scale=0.8, size=n)
    true = np.array([0.30, -0.20, 0.0, 0.10])
    y = (rng.random(n) < 1 / (1 + np.exp(-(off + X @ true)))).astype(float)
    b = E.fit(X, y, off, lam=1.0)
    assert np.abs(b - true).max() < 0.04
    # a strong prior with a huge penalty returns the prior; per-coin fits shrink toward the pooled one
    assert np.abs(E.fit(X[:500], y[:500], off[:500], lam=1e9, prior=true) - true).max() < 1e-4
    coin = np.where(np.arange(n) % 2 == 0, "A", "B")
    bp, bc = E.fit_all(X, y, off, coin)
    assert set(bc) == {"A", "B"} and np.abs(bc["A"] - bp).max() < 0.1


def test_pick_buys_only_past_the_threshold_after_fees():
    p = np.array([0.50, 0.50, 0.50, 0.90, 0.50])
    ya = np.array([0.44, 0.45, 0.60, 0.97, 0.60])
    yb = np.array([0.43, 0.44, 0.58, 0.96, 0.59])
    side, price, q, e = E.pick(p, ya, yb, thr=0.04)
    # 0.50 - 0.44 - fee(0.44) = 0.0428 -> YES; at 0.45 the edge is 0.0327 -> nothing
    assert side[0] == 1 and abs(price[0] - 0.44) < 1e-12 and abs(e[0] - (0.06 - E.fee(0.44))) < 1e-12
    assert side[1] == 0
    # YES too dear at 0.60, NO costs 1 - 0.58 = 0.42: 0.50 - 0.42 - fee = 0.0629 -> NO
    assert side[2] == -1 and abs(price[2] - 0.42) < 1e-12 and abs(q[2] - 0.50) < 1e-12
    assert side[3] == 0                    # YES ask 0.97 is outside PMAX; NO at 0.04 is outside PMIN
    assert side[4] == -1 and abs(price[4] - 0.41) < 1e-12


def test_bets_take_the_first_qualifying_minute_once_per_market():
    R = {"coin": np.array(["A"] * 4 + ["B"] * 2), "m": np.array([0, 0, 0, 1, 0, 0]), "j": np.array([3, 5, 6, 5, 4, 9]),
         "ots": np.array([900, 900, 900, 1800, 900, 900]), "ya": np.full(6, 0.40), "yb": np.full(6, 0.39),
         "y": np.array([1., 1., 1., 0., 0., 0.]), "day": np.zeros(6, int)}
    p = np.array([0.60, 0.60, 0.60, 0.41, 0.60, 0.60])
    b = E.bets(R, p)
    # A/0: minute 3 is before START, so minute 5; A/1: no edge; B/0: minute 4
    assert sorted(zip(b["coin"], b["j"])) == [("A", 5), ("B", 4)]
    assert abs(b["pnl"][b["coin"] == "A"][0] - (1 - 0.40 - E.fee(0.40))) < 1e-12
    assert abs(b["pnl"][b["coin"] == "B"][0] - (0 - 0.40 - E.fee(0.40))) < 1e-12


def test_stake_is_a_fraction_of_kelly_and_grows_with_balance_and_edge():
    cost = 0.40 + E.fee(0.40)
    want = 0.3 * 100 * 0.6 * (0.50 - cost) / (1 - cost)
    assert abs(E.stake_usd(100, 0.50, 0.40, 0.3, 0.6) - want) < 1e-12
    assert E.stake_usd(200, 0.50, 0.40) == 2 * E.stake_usd(100, 0.50, 0.40)
    assert E.stake_usd(100, 0.55, 0.40) > E.stake_usd(100, 0.50, 0.40)
    assert E.stake_usd(100, 0.40, 0.40) == 0.0 and E.stake_usd(None, 0.5, 0.4) == 0.0


def _panel_row():
    P = real.new_panel()
    for k in ("r1", "r3", "r5", "r10", "ref_z", "ref_r1", "ref_r3", "ref_v60"):
        P[k] = np.full((1, 14), np.nan)
    j = 5                                                   # minute 6
    P["spot"][0, j], P["strike"][0, j], P["vol1m"][0, j], P["vol240"][0, j] = 100.0, 100.0, 0.001, 0.001
    P["yes_ask"][0, j], P["yes_bid"][0, j], P["prev_ret"][0, j] = 0.50, 0.48, 0.0
    for k in ("r1", "r3", "r5", "r10", "ref_z", "ref_r1", "ref_r3"):
        P[k][0, j] = 0.0
    P["ref_v60"][0, j] = 0.001
    return P


def test_live_signal_uses_the_coin_coefficients_and_respects_the_live_list():
    P = _panel_row()
    P["r5"][0, 5] = 0.004                                    # +1.79 sd over 5 minutes
    b = [0.0] * len(E.FEATURES)
    b[E.FEATURES.index("r5z")] = 0.25
    model = {"features": E.FEATURES, "thr": 0.04, "start": 4, "end": 13, "coins": {"KXNEAR15M": b},
             "live_coins": ["KXNEAR15M"]}
    s = E.live_signal("KXNEAR15M", P, 6, model)
    r5z = 0.004 / (0.001 * math.sqrt(5))
    p = 1 / (1 + math.exp(-(math.log(0.49 / 0.51) + 0.25 * r5z)))
    assert s and s["side"] == "yes" and abs(s["p_yes"] - p) < 1e-12 and abs(s["edge"] - (p - 0.50 - E.fee(0.50))) < 1e-12
    assert E.live_signal("KXNEAR15M", P, 3, model) is None                 # before START
    assert E.live_signal("KXNEAR15M", P, 7, model) is None                 # no quotes at that minute
    assert E.live_signal("KXNEAR15M", P, 6, {**model, "live_coins": []}) is None
    P["ref_z"][0, 5] = np.nan                                              # a missing feature -> no bet
    assert E.live_signal("KXNEAR15M", P, 6, model) is None


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fake_engine(coin, state, first_T, ref_engine=None):
    sp_df = pd.read_csv(DATA_DIR / f"{coin}_spot.csv").drop_duplicates("ts").sort_values("ts")
    bars = sp_df[["ts", "low", "high", "open", "close", "volume"]].to_numpy()
    bts = sp_df.ts.to_numpy(np.int64)
    batch_spot = lab3.spot(coin, "main")

    def fetch_candles(**kw):
        upto = state["T"] - (120 if state["late"] else 60)
        lo, hi = np.searchsorted(bts, upto - 300 * 60, "right"), np.searchsorted(bts, upto, "right")
        return [list(r) for r in bars[lo:hi][::-1]]

    def fetch_ticker():
        return float(batch_spot.at(batch_spot.c, np.array([state["T"] - 60]))[0])

    eng = GL.GoldenEngine(coin, history=sp_df[sp_df.ts <= first_T - 120], fetch_candles=fetch_candles,
                          fetch_ticker=fetch_ticker, clock=lambda: state["T"] + 0.5, data_dir=None,
                          ref_engine=ref_engine)
    return eng.prepare()


def test_live_engine_features_and_predictions_match_the_batch_panel():
    """Replay 30 stored NEAR markets minute by minute through the live engine (with a live BTC reference engine)
    and compare every edge feature and the model's P(YES) with the batch panel the model is trained on."""
    coin, n = "KXNEAR15M", 30
    lab3._SPOT.clear()
    full = B.Panel(B.build_panel(coin))
    ots = np.asarray(full.open_ts, np.int64)
    start = int(ots.max()) - 5 * 86400
    sub = full.subset((ots >= start) & (ots < start + n * 900))
    lab3.add_features(sub, coin, "main")
    Xb, offb, okb = E.features(sub.P)
    rng = np.random.default_rng(7)
    beta = rng.normal(scale=0.1, size=len(E.FEATURES))
    model = {"features": E.FEATURES, "thr": 0.01, "start": 4, "end": 13, "coins": {coin: list(beta)},
             "live_coins": [coin]}
    pb = E.prob(offb, Xb, beta)
    cd = pd.read_csv(DATA_DIR / f"{coin}_candles.csv", usecols=["ticker", "ts", "yes_bid", "yes_ask"])
    quotes = cd[cd.ticker.isin(set(sub.ticker))].drop_duplicates(["ticker", "ts"]).set_index(["ticker", "ts"]).to_dict("index")
    mk = pd.read_csv(DATA_DIR / f"{coin}_markets.csv").set_index("ticker")
    order = np.argsort(np.asarray(sub.open_ts, np.int64), kind="stable")
    first_T = int(sub.open_ts[order[0]]) + 60
    state = {"T": first_T, "late": False}
    ref = _fake_engine("KXBTC15M", state, first_T)
    eng = _fake_engine(coin, state, first_T, ref_engine=ref)
    checked = bets = 0
    for m in order:
        tk, o = sub.ticker[m], int(sub.open_ts[m])
        P = real.new_panel()
        for minute in range(1, 15):
            state["T"], state["late"] = o + 60 * minute, bool(rng.random() < 0.5)
            q = quotes.get((tk, o + 60 * minute), {})
            yb, ya = q.get("yes_bid", np.nan), q.get("yes_ask", np.nan)
            real.observe(P, {"open_time": _iso(o), "floor_strike": float(mk.loc[tk, "strike"]),
                             "yes_bid_dollars": f"{yb:.4f}" if np.isfinite(yb) else "0",
                             "yes_ask_dollars": f"{ya:.4f}" if np.isfinite(ya) else "1"}, minute, np.nan, np.nan, np.nan, {})
            eng.update(P, o, minute)
            j = minute - 1
            Xl, offl, okl = E.features(P)
            assert bool(okl[0, j]) == bool(okb[m, j]), (tk, minute)
            if okb[m, j]:
                assert np.abs(Xl[0, j] - Xb[m, j]).max() < 1e-7, (tk, minute, E.FEATURES[int(np.abs(Xl[0, j] - Xb[m, j]).argmax())])
                assert abs(offl[0, j] - offb[m, j]) < 1e-9
                checked += 1
            s = E.live_signal(coin, P, minute, model)
            side, price, qq, e = E.pick(pb[m, j:j + 1], np.asarray(sub.P["yes_ask"], float)[m, j:j + 1],
                                        np.asarray(sub.P["yes_bid"], float)[m, j:j + 1], 0.01)
            want = okb[m, j] and 4 <= minute <= 13 and side[0] != 0
            assert (s is not None) == bool(want), (tk, minute)
            if s:
                assert s["side"] == ("yes" if side[0] == 1 else "no") and abs(s["price"] - price[0]) < 1e-9
                assert abs(s["p_yes"] - pb[m, j]) < 1e-7
                bets += 1
    lab3._SPOT.clear()
    assert checked > 250 and bets > 20, (checked, bets)


def test_edge_rule_is_registered_for_every_coin_and_ranked_last():
    for s in GL.ALL9:
        rid = f"edge:{s}"
        assert GL.RULES[rid]["kind"] == "edge" and GL.rules_for(s)[-1] == rid
    assert real.golden_frozen()["edge:KXZEC15M"] == {"id": "edge:KXZEC15M", "family": "edge", "scope": "KXZEC15M",
                                                      "t": 0.0, "params": {}}


def test_edge_orders_may_pay_a_little_more_but_keep_their_edge():
    # q 0.57 at a 0.50 ask: +2c allowed (0.57 - 0.05 = 0.52)
    assert real.walk_limit(0.50, 0.57, 2, 0.05, 0.95) == 0.52
    # q 0.565: only +1c keeps 5c to the model value
    assert real.walk_limit(0.50, 0.565, 2, 0.05, 0.95) == 0.51
    # edge too thin for any walk, or the walk would pass max_price: stay at the quote
    assert real.walk_limit(0.50, 0.55, 2, 0.05, 0.95) == 0.50
    assert real.walk_limit(0.94, 0.99, 2, 0.01, 0.95) == 0.94        # 0.96 is past max_price: no walk at all
    assert real.walk_limit(0.93, 0.99, 2, 0.01, 0.95) == 0.95
    # the old rules' walk (5c, keep 8c) is unchanged
    assert real.walk_limit(0.33, 0.50, 5, 0.08, 0.95) == 0.38
