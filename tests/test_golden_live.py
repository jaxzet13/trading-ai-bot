"""Equivalence of the LIVE golden-rule path (kalshi15m/golden_live.py) with lab3's batch backtest.

    nice -n 19 python3 tests/test_golden_live.py              # all tests, replay of 288 holdout markets per coin
    nice -n 19 python3 tests/test_golden_live.py --markets 40 # quicker replay
    nice -n 19 python3 tests/test_golden_live.py --norms      # also recompute the sized norms (~20 s)

The replay feeds historical markets (data/kalshi15m CSVs, lab3 holdout window) through the live code minute
by minute, the way the runners call it: the engine starts from spot bars up to two minutes before the first
decision, then each minute gets "Coinbase candles" (the CSV bars published so far; in about half of the
minutes the bar that just closed is held back, as Coinbase usually publishes it a few seconds late, so the
synthetic-bar path is exercised) and the quotes of that minute (the Kalshi candle closes, via real.observe).
For every golden rule, the side / minute / price it picks live must equal lab3.signal on the batch panel;
sized rules must get the same Kelly fraction and scalp rules the same exit minute and price.
No network, no credentials.
"""
from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kalshi15m import backtest as B  # noqa: E402
from kalshi15m import golden_live as GL  # noqa: E402
from kalshi15m import lab3, real  # noqa: E402
from kalshi15m.data import DATA_DIR  # noqa: E402

RESULTS = ROOT / "data" / "lab" / "lab3_results.json"
OPTS = {"markets": 288, "norms": False}
CHECK_FEATURES = ("spot", "vol1m", "vol240", "prev_ret", "ret_from_open", "vol_ewma30", "vol_v15", "vol_ewma120",
                  "r1", "r5", "emp21_1.0", "emp7_0.8", "tod_ratio")


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------- fast tests
def test_rule_table_matches_lab3_results():
    res = json.loads(RESULTS.read_text())
    gold = sorted([c for c in res["candidates"] if c["status"] == "golden"], key=lambda c: -c["holdout"]["t"])
    assert len(gold) == 16 == len(GL.GOLDEN)
    for c, r in zip(gold, GL.GOLDEN):
        assert r["id"] == f"{c['family']}:{c['scope']}", (r["id"], c["id"])
        assert r["params"] == c["params"] and r["family"] == c["family"] and r["scope"] == c["scope"]
        assert r["t"] == c["holdout"]["t"] and r["kind"] == lab3.FAMILIES[r["family"]]["kind"]
        assert not lab3.FAMILIES[r["family"]]["needs_ref"]
    assert [r["t"] for r in GL.GOLDEN] == sorted([r["t"] for r in GL.GOLDEN], reverse=True)
    assert GL.rules_for("KXBTC15M") == [r["id"] for r in GL.GOLDEN if r["scope"] == "ALL"]
    assert len(GL.rules_for("KXDOGE15M")) == 13 and len(GL.rules_for("KXHYPE15M")) == 13
    assert abs(GL.RULES["sized:ALL"]["norm"] - 0.26276) < 1e-5 and abs(GL.RULES["sized:KXHYPE15M"]["norm"] - 0.22610) < 1e-5


def test_sized_stake_formula():
    n = GL.RULES["sized:ALL"]["norm"]
    st, k = GL.sized_stake("sized:ALL", 0.70, 0.40, 4.0)
    assert abs(k - 0.5) < 1e-12 and abs(st - 4.0 * min(0.5 / n, 5)) < 1e-12
    st, k = GL.sized_stake("sized:ALL", 0.99, 0.05, 4.0)          # kelly <= 1, so the 5x cap never binds
    assert abs(k - 0.94 / 0.95) < 1e-12 and abs(st - 4.0 * k / n) < 1e-12 and st < 4.0 * 5
    st, k = GL.sized_stake("sized:KXHYPE15M", 0.10, 0.40, 4.0)     # negative edge -> floor 1e-4
    assert k == 1e-4


def test_exit_check_rule():
    P = real.new_panel()
    P["spot"][0, :] = 4.0
    P["strike"][0, :] = 4.0
    P["vol1m"][0, :] = 0.002
    P["yes_bid"][0, 4], P["yes_ask"][0, 4] = 0.52, 0.54           # model = 0.5 at the money
    assert GL.exit_check("scalp:ALL", P, 5, "yes", 3) == (0.52, 0.5)
    assert GL.exit_check("scalp:ALL", P, 5, "yes", 5) is None      # never in the entry minute
    assert GL.exit_check("scalp:ALL", P, 5, "no", 3) is None       # NO bid 0.46 < 0.5
    P["yes_ask"][0, 4] = 0.48
    P["yes_bid"][0, 4] = 0.46
    assert GL.exit_check("scalp:ALL", P, 5, "no", 2) == (0.52, 0.5)
    assert GL.exit_check("sized:ALL", P, 5, "no", 2) is None        # only scalp rules exit


def test_emp_cache_equals_lab3_emp_probs():
    """The per-day cached bootstrap equals lab3._emp_probs bit for bit on the same Spot."""
    coin = "KXNEAR15M"
    sp_df = pd.read_csv(DATA_DIR / f"{coin}_spot.csv")
    T_end = int(sp_df.ts.max()) - 3600
    hist = sp_df[sp_df.ts <= T_end]
    eng = GL.GoldenEngine(coin, history=hist, fetch_candles=lambda **k: [], fetch_ticker=lambda: np.nan,
                          clock=lambda: T_end + 60, data_dir=None)
    eng.prepare()
    rng = np.random.default_rng(1)
    day = (T_end // 86400)
    ots = day * 86400 + 900 * rng.integers(0, (T_end - day * 86400) // 900 - 1, 20)
    panel = type("Pn", (), {})()
    panel.open_ts = ots
    panel.P = {k: np.full((len(ots), 14), np.nan) for k in ("spot", "strike", "vol1m")}
    for i, o in enumerate(ots):
        for j in range(14):
            bar = o + 60 * j
            panel.P["spot"][i, j] = eng.sp.at(eng.sp.c, np.array([bar]))[0]
            panel.P["vol1m"][i, j] = eng.sp.at(eng.sp.v60, np.array([bar]))[0]
        panel.P["strike"][i, :] = panel.P["spot"][i, 0] * (1 + rng.normal(0, 0.001))
    want = lab3._emp_probs(eng.sp, type("X", (), {"P": panel.P, "open_ts": ots, "__len__": lambda s: len(ots)})())
    for i, o in enumerate(ots):
        for j in range(14):
            if o + 60 * (j + 1) - 60 > T_end:
                continue
            f = eng._features(int(o), j + 1, float(panel.P["strike"][i, 0]))
            for (lb, vm), arr in want.items():
                a, b = arr[i, j], f[f"emp{lb}_{vm}"]
                assert (np.isnan(a) and np.isnan(b)) or a == b, (o, j, lb, vm, a, b)


def test_sized_norms_recomputed():
    if not OPTS["norms"]:
        print("  (skipped: pass --norms to recompute the sized norms from the search window)")
        return
    got = GL.compute_sized_norms()
    for k, v in got.items():
        assert abs(v - GL.SIZED_NORMS[k]) < 1e-12, (k, v, GL.SIZED_NORMS[k])
    print("  sized norms:", got)


# ----------------------------------------------------------------------------- the replay
def _batch(coin, mask_fn):
    """lab3's own batch path: build_panel + add_features + lab3.signal / execute."""
    full = B.Panel(B.build_panel(coin))
    sub = full.subset(mask_fn(np.asarray(full.open_ts, np.int64)))
    lab3.add_features(sub, coin, "main")
    ctx = lab3.Ctx(coin, sub)
    out = {}
    for rid in GL.rules_for(coin):
        r = GL.RULES[rid]
        ctx.cache = {}
        side, minute, p = lab3.signal(ctx, r["family"], r["params"])
        tr = lab3.execute(ctx, r["family"], r["params"], side, minute, p, norm=r.get("norm"))
        d = {}
        for k, m in enumerate(tr["m"]):
            j = int(tr["j"][k])
            yes = bool(tr["yes"][k])
            q = float(p[m, j] if yes else 1 - p[m, j])
            e = {"side": "yes" if yes else "no", "minute": j + 1, "price": float(tr["price"][k]),
                 "kelly": max((q - tr["price"][k]) / (1 - tr["price"][k]), 1e-4)}
            if r["kind"] == "scalp":
                ej = int(tr["exit_j"][k])
                e["exit"] = None if ej < 0 else ej + 1
                if ej >= 0:
                    e["sell"] = float(sub.P["yes_bid"][m, ej] if yes else 1 - sub.P["yes_ask"][m, ej])
            d[sub.ticker[m]] = e
        # markets where the signal exists but no taker fill (never happens: masks require a valid ask)
        out[rid] = d
    return sub, out


def _replay(coin, sub, seed):
    """The live path, minute by minute."""
    rng = np.random.default_rng(seed)
    sp_df = pd.read_csv(DATA_DIR / f"{coin}_spot.csv").drop_duplicates("ts").sort_values("ts")
    bars = sp_df[["ts", "low", "high", "open", "close", "volume"]].to_numpy()
    bts = sp_df.ts.to_numpy(np.int64)
    batch_spot = lab3.spot(coin, "main")                     # only for the "ticker" (= close of the bar)
    cd = pd.read_csv(DATA_DIR / f"{coin}_candles.csv", usecols=["ticker", "ts", "yes_bid", "yes_ask"])
    cd = cd[cd.ticker.isin(set(sub.ticker))].drop_duplicates(["ticker", "ts"]).set_index(["ticker", "ts"])
    quotes = cd.to_dict("index")
    mk = pd.read_csv(DATA_DIR / f"{coin}_markets.csv").set_index("ticker")
    order = np.argsort(np.asarray(sub.open_ts, np.int64), kind="stable")
    first_T = int(sub.open_ts[order[0]]) + 60
    state = {"T": first_T, "fed": first_T - 120, "late": False}
    clock = lambda: state["T"] + 0.5

    def fetch_candles(**kw):
        upto = state["T"] - (120 if state["late"] else 60)
        lo, hi = np.searchsorted(bts, state["fed"], "right"), np.searchsorted(bts, upto, "right")
        state["fed"] = max(state["fed"], upto)
        return [list(r) for r in bars[max(lo - 3, 0):hi][::-1]]            # newest first, like Coinbase

    def fetch_ticker():
        return float(batch_spot.at(batch_spot.c, np.array([state["T"] - 60]))[0])

    hist = sp_df[sp_df.ts <= first_T - 120]
    eng = GL.GoldenEngine(coin, history=hist, fetch_candles=fetch_candles, fetch_ticker=fetch_ticker,
                          clock=clock, data_dir=None)
    eng.prepare()
    live = {rid: {} for rid in eng.rule_ids}
    feats = {}
    t_upd, t_sig, n_min = 0.0, 0.0, 0
    for m in order:
        tk, o = sub.ticker[m], int(sub.open_ts[m])
        strike = float(mk.loc[tk, "strike"])
        P = real.new_panel()
        held = {}
        for minute in range(1, 15):
            T = o + 60 * minute
            state["T"], state["late"] = T, bool(rng.random() < 0.5)
            q = quotes.get((tk, T), {})
            yb, ya = q.get("yes_bid", np.nan), q.get("yes_ask", np.nan)
            mkt = {"open_time": iso(o), "floor_strike": strike,
                   "yes_bid_dollars": f"{yb:.4f}" if np.isfinite(yb) else "0",
                   "yes_ask_dollars": f"{ya:.4f}" if np.isfinite(ya) else "1"}
            real.observe(P, mkt, minute, np.nan, np.nan, np.nan, {})           # quotes + strike as the runner does
            t0 = time.perf_counter()
            eng.update(P, o, minute)
            t1 = time.perf_counter()
            todo = [rid for rid in eng.rule_ids if tk not in live[rid]]
            for s in eng.signals(P, minute, todo):
                e = {"side": s.side, "minute": s.minute, "price": s.price, "kelly": max((s.q - s.price) / (1 - s.price), 1e-4)}
                if s.kind == "scalp":
                    e["exit"] = None
                    held[s.rule] = e
                live[s.rule][tk] = e
            for rid, e in list(held.items()):
                hit = eng.exit_check(rid, P, minute, e["side"], e["minute"])
                if hit:
                    e["exit"], e["sell"] = minute, hit[0]
                    held.pop(rid)
            t_sig += time.perf_counter() - t1
            t_upd += t1 - t0
            n_min += 1
        feats[tk] = {k: P[k][0].copy() for k in CHECK_FEATURES}
    return live, feats, {"update_ms": 1000 * t_upd / n_min, "signals_ms": 1000 * t_sig / n_min, "minutes": n_min}


def _same(a, b):
    if a is None or b is None:
        return a is b
    if a["side"] != b["side"] or a["minute"] != b["minute"] or abs(a["price"] - b["price"]) > 1e-9:
        return False
    if abs(a["kelly"] - b["kelly"]) > 1e-9 * max(1, abs(a["kelly"])):
        return False
    if "exit" in a and (a["exit"] != b.get("exit") or (a["exit"] and abs(a["sell"] - b["sell"]) > 1e-9)):
        return False
    return True


REPLAY, DEDUP = {}, {}


def replay_all():
    if REPLAY:
        return REPLAY
    res = json.loads(RESULTS.read_text())
    cut = int(res["method"]["holdout_start"])
    n = OPTS["markets"]
    for ci, coin in enumerate(GL.ALL9):
        start = cut + 86400 * (ci % 9) + 7 * 3600             # a different 3-day stretch of the holdout per coin

        def mask(ots, start=start):
            ok = ots >= start
            first = np.sort(ots[ok])[:n]
            return ok & (ots <= first[-1])
        t0 = time.time()
        sub, batch = _batch(coin, mask)
        tb = time.time() - t0
        live, feats, tm = _replay(coin, sub, seed=ci)
        # feature agreement (every market x minute)
        fd = {}
        for k in CHECK_FEATURES:
            a = np.stack([feats[tk][k] for tk in sub.ticker])
            b = sub.P[k]
            both = np.isfinite(a) & np.isfinite(b)
            nan_mismatch = int((np.isfinite(a) != np.isfinite(b)).sum())
            rel = np.abs(a[both] - b[both]) / np.maximum(np.abs(b[both]), 1e-12)
            fd[k] = {"max_rel": float(rel.max()) if len(rel) else 0.0, "nan_mismatch": nan_mismatch}
        REPLAY[coin] = {"sub": sub, "batch": batch, "live": live, "features": fd, "time": tm, "batch_s": tb,
                        "markets": len(sub)}
        print(f"  {coin}: {len(sub)} markets replayed, live update {tm['update_ms']:.1f} ms + rules "
              f"{tm['signals_ms']:.1f} ms per minute (batch {tb:.0f}s)", flush=True)
    return REPLAY


def test_replay_features_match_batch():
    R = replay_all()
    worst = {}
    for coin, r in R.items():
        for k, v in r["features"].items():
            w = worst.setdefault(k, {"max_rel": 0.0, "nan_mismatch": 0})
            w["max_rel"] = max(w["max_rel"], v["max_rel"])
            w["nan_mismatch"] += v["nan_mismatch"]
    print("  feature agreement live vs batch (max relative difference, NaN mismatches):")
    for k, w in worst.items():
        print(f"    {k:<14} {w['max_rel']:.1e}  {w['nan_mismatch']}")
    for k, w in worst.items():
        assert w["nan_mismatch"] == 0, (k, w)
        assert w["max_rel"] < 1e-9, (k, w)


def test_replay_rules_match_lab3_signal():
    R = replay_all()
    rows = []
    bad = []
    for rid in [r["id"] for r in GL.GOLDEN]:
        n = match = trades_b = trades_l = 0
        for coin, r in R.items():
            if rid not in r["batch"]:
                continue
            for tk in r["sub"].ticker:
                a, b = r["batch"][rid].get(tk), r["live"][rid].get(tk)
                n += 1
                trades_b += a is not None
                trades_l += b is not None
                if _same(a, b):
                    match += 1
                else:
                    bad.append((rid, tk, a, b))
        rows.append((rid, n, trades_b, trades_l, match))
    print(f"  {'rule':<22}{'markets':>8}{'lab3 bets':>10}{'live bets':>10}{'match':>9}")
    for rid, n, tb, tl, m in rows:
        print(f"  {rid:<22}{n:>8}{tb:>10}{tl:>10}{100 * m / n:>8.2f}%")
    for x in bad[:20]:
        print("  MISMATCH", x)
    assert not bad, f"{len(bad)} mismatches"


def test_replay_priority_dedup():
    """Best-first on each minute: count markets where the rule that takes the market (earliest minute, best
    rule on ties) is not the best rule that would have fired in that market at some minute."""
    R = replay_all()
    tot = taken_not_best = multi = 0
    by_rule = {}
    for coin, r in R.items():
        for tk in r["sub"].ticker:
            fired = [(e["minute"], GL.PRIORITY[rid], rid) for rid, d in r["live"].items() if (e := d.get(tk))]
            if not fired:
                continue
            tot += 1
            multi += len(fired) > 1
            taken = min(fired)
            best = min(fired, key=lambda x: x[1])
            by_rule[taken[2]] = by_rule.get(taken[2], 0) + 1
            if taken[2] != best[2]:
                taken_not_best += 1
    DEDUP.update({"markets_with_bet": tot, "several_rules": multi, "taken_not_best": taken_not_best,
                        "taken_by_rule": by_rule})
    print(f"  markets with a bet: {tot}; several rules fired in {multi}; the rule that took the market was not "
          f"the best rule that fired in it (a lower-ranked rule fired at an earlier minute) in {taken_not_best} "
          f"({100 * taken_not_best / max(tot, 1):.1f}%)")
    print("  bets by rule:", dict(sorted(by_rule.items(), key=lambda kv: GL.PRIORITY[kv[0]])))


def test_replay_speed():
    R = replay_all()
    worst = max(r["time"]["update_ms"] + r["time"]["signals_ms"] for r in R.values())
    print(f"  slowest coin: {worst:.1f} ms per minute (features + all rules), replay incl. per-market setup")
    assert worst < 250


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--markets" in args:
        OPTS["markets"] = int(args[args.index("--markets") + 1])
    OPTS["norms"] = "--norms" in args
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                t0 = time.time()
                fn()
                print(f"PASS {name} ({time.time() - t0:.0f}s)", flush=True)
            except Exception:
                import traceback
                fails += 1
                print(f"FAIL {name}", flush=True)
                traceback.print_exc()
    print(f"{'ALL PASSED' if not fails else f'{fails} FAILED'}")
    sys.exit(1 if fails else 0)
