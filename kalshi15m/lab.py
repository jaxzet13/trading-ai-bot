"""Strategy search across every Kalshi 15-minute crypto series, with a locked holdout.

    python -m kalshi15m lab

1. Each coin's most recent HOLDOUT_FRAC of markets is locked away. Nothing below looks at it
   until step 4.
2. Search: on the remaining data, walk-forward every strategy x order type, per coin and pooled
   across all coins (params re-tuned on earlier folds only).
3. Shortlist: combinations whose search-period out-of-sample record is positive, t >= T_SHORTLIST,
   with enough trades and most folds profitable.
4. Final exam: tune each shortlisted combination on the whole search period, freeze it, and run it
   once on the holdout. The two strategies currently paper-traded are run on the same holdout with
   their frozen settings as the bar to beat.
"""
from __future__ import annotations

import itertools
import json
import math
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import Panel, build_panel, metrics, run
from .data import DATA_DIR, SERIES
from .report import walk_forward
from .strategies import STRATEGIES

OUT = DATA_DIR.parent / "lab"
HOLDOUT_DAYS = 15        # same calendar cutoff for every coin
_CUT = None
N_FOLDS = 5
MIN_TRADES = 30
T_SHORTLIST = 1.5
STAKE = 10.0
EXECUTIONS = ("taker", "maker")

BENCHMARKS = [  # the two strategies in kalshi15m/live.json
    ("KXETH15M", "reversal_z", "maker", {"minute": 2, "min_z": 1.5, "max_price": 0.55}),
    ("KXSOL15M", "fair_value", "maker", {"start": 2, "end": 13, "edge": 0.12, "vol_mult": 1.0}),
]

_PANELS: dict = {}


def _add_btc(panels: dict):
    """Give every coin's panel BTC's move since the open (in sd), aligned by market open time."""
    if "KXBTC15M" not in panels:
        return
    b = panels["KXBTC15M"]
    with np.errstate(invalid="ignore", divide="ignore"):
        bz = np.log(b.P["spot"] / b.P["strike"]) / (b.P["vol1m"] * np.sqrt(np.arange(1, 15))[None, :])
    idx = {t: i for i, t in enumerate(b.open_ts)}
    for s, p in panels.items():
        rows = np.array([idx.get(t, -1) for t in p.open_ts])
        z = np.full(p.P["spot"].shape, np.nan)
        ok = rows >= 0
        z[ok] = bz[rows[ok]]
        p.P["btc_z"] = z


SESSIONS = {"asia": (0, 8), "europe": (8, 14), "us": (14, 21), "late": (21, 24)}  # UTC hours of the open
SESSION_BASE = ["fair_value", "fair_value_bid", "closing_value", "spot_lag", "reversal_z", "momentum_z",
                "late_favorite", "cross_lead", "quote_move", "opening_value"]


def _session_wrap(fn, lo, hi):
    def wrapped(P, **kw):
        side, minute = fn(P, **kw)
        h = P["hour"][:, 0]
        return np.where((h >= lo) & (h < hi), side, 0), minute
    return wrapped


def _register_sessions():
    for base in SESSION_BASE:
        fn, desc, grid = STRATEGIES[base]
        for name, (lo, hi) in SESSIONS.items():
            STRATEGIES[f"{base}@{name}"] = (_session_wrap(fn, lo, hi), f"{desc} Only markets opening {lo:02d}-{hi:02d} UTC.", grid)


def load_panels(series=None):
    series = [s for s in (series or SERIES) if (DATA_DIR / f"{s}_markets.csv").exists()]
    panels = {}
    for s in series:
        p = Panel(build_panel(s))
        if len(p) >= 500:
            panels[s] = p
            print(f"  {s}: {len(p)} markets")
    _add_btc(panels)
    for p in panels.values():
        p.P["hour"] = np.repeat(((p.open_ts % 86400) // 3600)[:, None], 14, axis=1).astype(float)
    return panels


def split(p: Panel):
    cut = _CUT if _CUT is not None else int(p.open_ts.max() - HOLDOUT_DAYS * 86400)
    return p.subset(p.open_ts < cut), p.subset(p.open_ts >= cut), cut


def _scope_panel(scope):
    if scope == "ALL":
        return Panel.concat([split(p)[0] for p in _PANELS.values()])
    return split(_PANELS[scope])[0]


def _task(args):
    scope, name, ex = args
    fn, _, grid = STRATEGIES[name]
    search = _scope_panel(scope)
    folds, oos, _, diag = walk_forward(search, fn, grid, ex, N_FOLDS, STAKE, MIN_TRADES)
    m = metrics(oos)
    return {"scope": scope, "strategy": name, "execution": ex, "oos": m,
            "fold_win": round(float(np.mean([f["test_pnl"] > 0 for f in folds])), 2),
            "fill_rate": diag.get("fill_rate")}


def _tune(panel, fn, grid, ex):
    best, best_m = None, None
    for vals in itertools.product(*grid.values()):
        params = dict(zip(grid.keys(), vals))
        m = metrics(run(panel, fn, stake=STAKE, execution=ex, **params))
        if m["trades"] >= MIN_TRADES and (best_m is None or m["pnl"] > best_m["pnl"]):
            best, best_m = params, m
    return best, best_m


def _holdout_panel(scope):
    if scope == "ALL":
        return Panel.concat([split(p)[1] for p in _PANELS.values()])
    return split(_PANELS[scope])[1]


def _final(args):
    scope, name, ex = args
    fn, _, grid = STRATEGIES[name]
    params, tm = _tune(_scope_panel(scope), fn, grid, ex)
    if params is None:
        return None
    hold = _holdout_panel(scope)
    tr = run(hold, fn, stake=STAKE, execution=ex, **params)
    hm = metrics(tr)
    flat = (tr.pnl / tr.contracts * 10) if len(tr) else pd.Series(dtype=float)
    ft = float(flat.mean() / (flat.std() / math.sqrt(len(flat)))) if len(flat) > 2 and flat.std() > 0 else 0.0
    curve = tr.sort_values("ts").pnl.cumsum().round(2).tolist() if len(tr) else []
    ts = tr.sort_values("ts").ts.tolist() if len(tr) else []
    step = max(1, len(curve) // 300)
    return {"scope": scope, "strategy": name, "execution": ex, "params": params, "search_tuned": tm,
            "holdout": hm, "holdout_flat_t": round(ft, 2),
            "curve": [[int(ts[i]), curve[i]] for i in range(0, len(curve), step)]}


def main(series=None, workers=4):
    global _PANELS
    t0 = time.time()
    print("loading panels ...")
    global _CUT
    _register_sessions()
    _PANELS = load_panels(series)
    _CUT = int(min(p.open_ts.max() for p in _PANELS.values()) - HOLDOUT_DAYS * 86400)
    scopes = list(_PANELS) + (["ALL"] if len(_PANELS) > 1 else [])
    info = {s: {"markets": len(p), "start": int(p.open_ts.min()), "end": int(p.open_ts.max() + 900),
                "holdout_start": split(p)[2], "holdout_markets": len(split(p)[1])} for s, p in _PANELS.items()}
    tasks = [(sc, n, ex) for sc in scopes for n in STRATEGIES for ex in EXECUTIONS]
    print(f"search: {len(tasks)} walk-forwards over {len(scopes)} scopes ...")
    with Pool(workers) as pool:
        search = []
        for i, r in enumerate(pool.imap_unordered(_task, tasks, chunksize=2)):
            search.append(r)
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(tasks)}  ({time.time() - t0:.0f}s)", flush=True)
    short = [r for r in search if r["strategy"] != "baseline_yes" and r["oos"]["pnl"] > 0
             and r["oos"]["t_stat"] >= T_SHORTLIST and r["oos"]["trades"] >= 50 and r["fold_win"] >= 0.5]
    short.sort(key=lambda r: -r["oos"]["t_stat"])
    print(f"shortlist: {len(short)} of {len(search)}")
    for r in short:
        print(f"  {r['scope']:10s} {r['strategy']:18s} {r['execution']}: search OOS ${r['oos']['pnl']} "
              f"t={r['oos']['t_stat']} trades={r['oos']['trades']} folds+={r['fold_win']}")
    with Pool(workers) as pool:
        finals = [f for f in pool.map(_final, [(r["scope"], r["strategy"], r["execution"]) for r in short]) if f]
    # benchmarks: frozen params straight onto the holdout
    bench = []
    for s, name, ex, params in BENCHMARKS:
        if s not in _PANELS:
            continue
        tr = run(split(_PANELS[s])[1], STRATEGIES[name][0], stake=STAKE, execution=ex, **params)
        bench.append({"scope": s, "strategy": name, "execution": ex, "params": params, "holdout": metrics(tr)})
    k = max(1, len(finals))
    # one-sided Bonferroni bar for k simultaneous holdout tests at 5%
    from statistics import NormalDist
    t_bar = round(NormalDist().inv_cdf(1 - 0.05 / k), 2)
    for f in finals:
        h = f["holdout"]
        f["passed"] = bool(h["pnl"] > 0 and h["t_stat"] >= 2)
        f["passed_strict"] = bool(h["pnl"] > 0 and h["t_stat"] >= t_bar)
    finals.sort(key=lambda f: -f["holdout"]["t_stat"])
    res = {"generated": int(time.time()), "holdout_days": HOLDOUT_DAYS, "holdout_start": _CUT, "n_folds": N_FOLDS, "stake": STAKE,
           "t_shortlist": T_SHORTLIST, "t_bar_strict": t_bar, "coins": info,
           "n_strategies": len(STRATEGIES), "n_combos": sum(len(list(itertools.product(*g.values())))
                                                            for _, _, g in STRATEGIES.values()),
           "search": search, "finals": finals, "benchmarks": bench, "runtime_s": int(time.time() - t0)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(f"\nHOLDOUT (final exam), strict bar t >= {t_bar} for {k} tests:")
    for f in finals:
        h = f["holdout"]
        print(f"  {'PASS' if f['passed_strict'] else ('pass' if f['passed'] else 'fail')}  {f['scope']:10s} "
              f"{f['strategy']:18s} {f['execution']}: ${h['pnl']} on {h['trades']} trades, t={h['t_stat']}  {f['params']}")
    for b in bench:
        h = b["holdout"]
        print(f"  BENCH {b['scope']:10s} {b['strategy']:18s} {b['execution']}: ${h['pnl']} on {h['trades']} trades, t={h['t_stat']}")
    print(f"done in {time.time() - t0:.0f}s -> {OUT / 'results.json'}")
    return res
