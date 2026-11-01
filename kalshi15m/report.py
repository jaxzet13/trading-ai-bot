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
                      "train_pnl": best_m["pnl"], "train_t": best_m["t_stat"], "train_trades": best_m["trades"],
                      "test_pnl": tm["pnl"], "test_trades": tm["trades"], "test_roi": tm["roi"], "_trades": tr})
        oos.append(tr)
        if k == n_folds - 1 and len(combos) > 1:
            last_sweep = [{"params": p, "train_pnl": m["pnl"], "train_trades": m["trades"],
                           "test_pnl": metrics(run(test, fn, stake=stake, execution=execution, **p))["pnl"]}
                          for p, m in scored]
    oos = pd.concat([t for t in oos if not t.empty], ignore_index=True) if any(not t.empty for t in oos) \
        else pd.DataFrame(columns=["ts", "pnl", "win", "cost", "price", "fee", "series", "minute"])
    return folds, oos, last_sweep, merge_diag(diags)


def evaluate(series_list, n_folds=6, stake=10.0, min_trades=60, keep=None):
    """keep: optional dict filled with {(strategy, execution): folds incl. their trades}."""
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
            if keep is not None:
                keep[(name, ex)] = folds
            folds = [{k: v for k, v in f.items() if k != "_trades"} for f in folds]
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


def coin_picks(keep: dict, coin: str, min_train_t: float = 2.0):
    """Walk-forward strategy selection for one coin. At each fold, among every strategy x order
    type (already tuned on earlier data only), take the one with the best earlier-data t-stat.
    If none reaches `min_train_t`, sit the fold out. Then trade it on the fold."""
    n = len(next(iter(keep.values())))
    picks, trades = [], []
    for k in range(n):
        cands = [(name, ex, folds[k]) for (name, ex), folds in keep.items()
                 if name != "baseline_yes" and folds[k]["train_trades"] >= 60]
        name, ex, f = max(cands, key=lambda c: c[2]["train_t"]) if cands else (None, None, None)
        base = next(iter(keep.values()))[k]
        if f is None or f["train_t"] < min_train_t:
            picks.append({"start": base["start"], "end": base["end"], "strategy": None, "execution": None,
                          "params": {}, "train_t": f["train_t"] if f else None, "test_pnl": 0.0, "test_trades": 0})
            continue
        picks.append({"start": f["start"], "end": f["end"], "strategy": name, "execution": ex, "params": f["params"],
                      "train_t": f["train_t"], "train_pnl": f["train_pnl"],
                      "test_pnl": f["test_pnl"], "test_trades": f["test_trades"]})
        if not f["_trades"].empty:
            trades.append(f["_trades"].assign(strategy=name, execution=ex))
    tr = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame(columns=["ts", "pnl", "win", "cost", "price", "fee"])
    return picks, tr


def portfolio(series_list, n_folds=6, stake=10.0, min_train_t=2.0):
    """Each coin gets its own strategy, chosen walk-forward. Returns (solo scopes, portfolio summary)."""
    scopes, coins, all_tr = {}, {}, []
    for s in series_list:
        label = s.replace("KX", "").replace("15M", "") + " only"
        print(f"== {s} on its own ==")
        keep = {}
        scopes[label] = evaluate([s], n_folds=n_folds, stake=stake, keep=keep)
        picks, tr = coin_picks(keep, s, min_train_t)
        m = metrics(tr)
        # what each coin would run today: best earlier-data t-stat on ALL data up to now = last fold's pick
        coins[s] = {"picks": picks, "oos": m, "curve": _curve(tr),
                    "folds_traded": sum(p["strategy"] is not None for p in picks),
                    "fold_win": round(float(np.mean([p["test_pnl"] > 0 for p in picks if p["strategy"]] or [0])), 2),
                    "current": picks[-1] if picks else None,
                    "recent": (tr.sort_values("ts").tail(20)[["ticker", "ts", "strategy", "execution", "side", "minute",
                                                              "price", "contracts", "pnl"]].to_dict("records")
                               if not tr.empty else [])}
        print(f"  -> {s}: OOS ${m['pnl']} on {m['trades']} trades, t={m['t_stat']}; picks: "
              + ", ".join(f"{p['strategy']}/{p['execution']}" for p in picks))
        if not tr.empty:
            all_tr.append(tr)
    tot = pd.concat(all_tr, ignore_index=True) if all_tr else pd.DataFrame(columns=["ts", "pnl", "win", "cost", "price", "fee"])
    return scopes, {"min_train_t": min_train_t, "coins": coins, "total": metrics(tot), "curve": _curve(tot)}


def build(series_list=tuple(SERIES), stake=10.0, n_folds=6, out=None, solo=(), per_coin=True):
    """Write the dashboard. `solo` adds single-coin views (e.g. SOL only) next to the pooled one."""
    out_dir = Path(out) if out else OUT
    series_list = [s for s in series_list if (DATA_DIR / f"{s}_markets.csv").exists()]
    scopes = {"All coins" if len(series_list) > 1 else series_list[0].replace("KX", "").replace("15M", "") + " only":
              evaluate(series_list, n_folds=n_folds, stake=stake)}
    port = None
    if per_coin and len(series_list) > 1:
        solo_scopes, port = portfolio(series_list, n_folds=n_folds, stake=stake)
        scopes.update(solo_scopes)
    else:
        for s in solo:
            if (DATA_DIR / f"{s}_markets.csv").exists():
                print(f"== {s} on its own ==")
                scopes[s.replace("KX", "").replace("15M", "") + " only"] = evaluate([s], n_folds=n_folds, stake=stake)
    results = {"scopes": scopes, "portfolio": port} if len(scopes) > 1 else next(iter(scopes.values()))
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
