"""Walk-forward evaluation -> dashboard/results.json + dashboard/index.html.

Method (designed to resist overfitting):
  * All coins are pooled and ONE parameter set is tuned across them, so a rule
    has to work on BTC, ETH and SOL at once.
  * History is cut into consecutive time folds. For every fold after the first,
    parameters are tuned on everything before it and then traded, untouched, on
    that fold. Gluing those test folds together gives an out-of-sample record
    that covers most of the history, not just the last 30%.
  * Every strategy is run with taker execution (cross the spread) and maker
    execution (rest a limit order at the bid).
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import Panel, build_panel, merge_diag, metrics, run
from .data import DATA_DIR, SERIES
from .strategies import STRATEGIES

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "dashboard"
EXECUTIONS = ("taker", "maker")


def _grid(grid: dict):
    keys = list(grid)
    for vals in itertools.product(*(grid[k] for k in keys)):
        yield dict(zip(keys, vals))


def _curve(trades: pd.DataFrame, max_pts=700):
    if trades.empty:
        return []
    t = trades.sort_values("ts")
    eq, ts = t.pnl.cumsum().round(2).to_numpy(), t.ts.to_numpy()
    idx = np.unique(np.r_[np.linspace(0, len(eq) - 1, min(max_pts, len(eq))).astype(int), len(eq) - 1])
    return [[int(ts[i]), float(eq[i])] for i in idx]


def _score(m: dict, min_trades: int) -> float:
    """Tuning objective: total P&L, but only for parameter sets that trade enough."""
    return m["pnl"] if m["trades"] >= min_trades else -1e12


def calibration(long: pd.DataFrame, minutes=(1, 5, 10, 13)):
    out = {}
    for m in minutes:
        p = long[(long.minute == m) & long.yes_ask.notna()].copy()
        p["mid"] = (p.yes_bid + p.yes_ask) / 2
        p["b"] = (p.mid * 10).clip(0, 9.999).astype(int)
        g = p.groupby("b").agg(implied=("mid", "mean"), actual=("result", "mean"), n=("result", "size"))
        out[str(m)] = [{"implied": round(r.implied, 3), "actual": round(r.actual, 3), "n": int(r.n)}
                       for r in g.itertuples() if r.n >= 10]
    return out


def model_calibration(panel: Panel):
    p, y = panel.P["p_model"][:, 2:13], np.repeat(panel.result[:, None], 11, axis=1)
    mid = (panel.P["yes_bid"][:, 2:13] + panel.P["yes_ask"][:, 2:13]) / 2
    ok = np.isfinite(p)
    df = pd.DataFrame({"p": p[ok], "y": y[ok], "mid": mid[ok]})
    df["b"] = (df.p * 10).clip(0, 9.999).astype(int)
    g = df.groupby("b").agg(model=("p", "mean"), actual=("y", "mean"), n=("y", "size"))
    return [{"model": round(r.model, 3), "actual": round(r.actual, 3), "n": int(r.n)}
            for r in g.itertuples() if r.n >= 20]


def walk_forward(panel: Panel, fn, grid: dict, execution: str, n_folds: int, stake: float, min_trades: int):
    t0, t1 = panel.open_ts.min(), panel.open_ts.max() + 1
    edges = np.linspace(t0, t1, n_folds + 1).astype(int)
    combos = list(_grid(grid))
    folds, oos, diags = [], [], []
    last_sweep = None
    for k in range(1, n_folds):
        train = panel.subset(panel.open_ts < edges[k])
        test = panel.subset((panel.open_ts >= edges[k]) & (panel.open_ts < edges[k + 1]))
        scored = []
        for params in combos:
            m = metrics(run(train, fn, stake=stake, execution=execution, **params))
            scored.append((params, m))
        best, best_m = max(scored, key=lambda s: _score(s[1], min_trades))
        tr = run(test, fn, stake=stake, execution=execution, **best)
        tm = metrics(tr)
        diags.append(tr.attrs.get("diag", {}))
        folds.append({"start": int(edges[k]), "end": int(edges[k + 1]), "params": best,
                      "train_pnl": best_m["pnl"], "test_pnl": tm["pnl"], "test_trades": tm["trades"],
                      "test_roi": tm["roi"]})
        oos.append(tr)
        if k == n_folds - 1 and len(combos) > 1:
            last_sweep = [{"params": p, "train_pnl": m["pnl"], "train_trades": m["trades"],
                           "test_pnl": metrics(run(test, fn, stake=stake, execution=execution, **p))["pnl"]}
                          for p, m in scored]
    oos = pd.concat([t for t in oos if not t.empty], ignore_index=True) if any(not t.empty for t in oos) \
        else pd.DataFrame(columns=["ts", "pnl", "win", "cost", "price", "fee", "series", "minute"])
    return folds, oos, last_sweep, merge_diag(diags)


def evaluate(series_list, n_folds=6, stake=10.0, min_trades=60):
    panels, longs = {}, {}
    for s in series_list:
        print(f"[{s}] building panel ...")
        longs[s] = build_panel(s)
        panels[s] = Panel(longs[s])
    pooled = Panel.concat(list(panels.values()))
    res = {"generated": int(datetime.now(timezone.utc).timestamp()), "stake": stake, "n_folds": n_folds,
           "start": int(pooled.open_ts.min()), "end": int(pooled.open_ts.max() + 900),
           "coins": {s: {"markets": len(p), "start": int(p.open_ts.min()), "end": int(p.open_ts.max() + 900),
                         "up_rate": round(float(p.result.mean()), 4),
                         "maker_data": bool(np.isfinite(p.P["ask_low"]).mean() > 0.5),
                         "calibration": calibration(longs[s]), "model_calibration": model_calibration(p)}
                     for s, p in panels.items()},
           "strategies": {}}
    for name, (fn, desc, grid) in STRATEGIES.items():
        res["strategies"][name] = {"description": desc, "runs": {}}
        for ex in EXECUTIONS:
            folds, oos, sweep, diag = walk_forward(pooled, fn, grid, ex, n_folds, stake, min_trades)
            m = metrics(oos)
            per_coin = {s: metrics(oos[oos.series == s]) for s in series_list} if not oos.empty else {}
            by_min = (oos.groupby("minute").agg(trades=("pnl", "size"), pnl=("pnl", "sum"), win=("win", "mean"))
                      .reset_index().round(3).to_dict("records")) if not oos.empty else []
            recent = (oos.sort_values("ts").tail(40)[["ticker", "series", "ts", "side", "minute", "price",
                                                     "contracts", "fee", "win", "pnl"]].to_dict("records")
                      if not oos.empty else [])
            res["strategies"][name]["runs"][ex] = {
                "oos": m, "per_coin": per_coin, "folds": folds, "curve": _curve(oos),
                "fold_win": round(float(np.mean([f["test_pnl"] > 0 for f in folds])), 2),
                "sweep": sweep, "by_minute": by_min, "recent": recent,
                "final_params": folds[-1]["params"] if folds else {},
                "diag": diag,
            }
            if ex == "maker" and diag.get("orders"):
                print(f"      maker: {diag['fills']}/{diag['orders']} filled, win {diag.get('fill_win_rate')} vs "
                      f"{diag.get('signal_win_rate')} for all signals, saved {diag.get('avg_saved_c')}c/fill")
            print(f"  {name:14s} {ex}: OOS ${m['pnl']:>9} on {m['trades']:>5} trades, t={m['t_stat']:>6}, "
                  f"folds+ {res['strategies'][name]['runs'][ex]['fold_win']}")
    return res


def build(series_list=tuple(SERIES), stake=10.0, n_folds=6, out=None):
    out_dir = Path(out) if out else OUT
    series_list = [s for s in series_list if (DATA_DIR / f"{s}_markets.csv").exists()]
    results = evaluate(series_list, n_folds=n_folds, stake=stake)
    out_dir.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(results, default=_np)
    (out_dir / "results.json").write_text(blob)
    html = (ROOT / "dashboard_template.html").read_text()
    (out_dir / "index.html").write_text(html.replace("/*__RESULTS__*/null", blob))
    print(f"wrote {out_dir / 'index.html'}")
    return results


def _np(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(type(o))
