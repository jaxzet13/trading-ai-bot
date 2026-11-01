"""Parameter sweep + walk-forward (train/test) evaluation -> results.json -> dashboard."""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import Panel, build_panel, metrics, run
from .data import DATA_DIR
from .strategies import STRATEGIES

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "dashboard"


def _grid(grid: dict):
    keys = list(grid)
    for vals in itertools.product(*(grid[k] for k in keys)):
        yield dict(zip(keys, vals))


def _curve(trades: pd.DataFrame, max_pts=600):
    if trades.empty:
        return []
    t = trades.sort_values("ts")
    eq = t.pnl.cumsum().round(2).tolist()
    ts = t.ts.tolist()
    step = max(1, len(eq) // max_pts)
    idx = list(range(0, len(eq), step))
    if idx[-1] != len(eq) - 1:
        idx.append(len(eq) - 1)
    return [[ts[i], eq[i]] for i in idx]


def calibration(panel: pd.DataFrame, minutes=(1, 5, 10, 13)):
    out = {}
    for m in minutes:
        p = panel[(panel.minute == m) & panel.yes_ask.notna()].copy()
        p["mid"] = (p.yes_bid + p.yes_ask) / 2
        p["b"] = (p.mid * 10).clip(0, 9.999).astype(int)
        g = p.groupby("b").agg(implied=("mid", "mean"), actual=("result", "mean"), n=("result", "size"))
        out[str(m)] = [{"implied": round(r.implied, 3), "actual": round(r.actual, 3), "n": int(r.n)}
                       for r in g.itertuples() if r.n >= 10]
    return out


def model_calibration(panel: pd.DataFrame):
    p = panel[panel.p_model.notna() & panel.minute.between(3, 13)].copy()
    p["b"] = (p.p_model * 10).clip(0, 9.999).astype(int)
    p["mid"] = (p.yes_bid + p.yes_ask) / 2
    g = p.groupby("b").agg(model=("p_model", "mean"), market=("mid", "mean"),
                           actual=("result", "mean"), n=("result", "size"))
    return [{"model": round(r.model, 3), "market": round(r.market, 3) if np.isfinite(r.market) else None,
             "actual": round(r.actual, 3), "n": int(r.n)} for r in g.itertuples() if r.n >= 20]


def evaluate(series: str, train_frac=0.7, stake=10.0, min_trades=30):
    print(f"[{series}] building panel ...")
    long = build_panel(series)
    panel = Panel(long)
    long = long.merge(pd.DataFrame({"ticker": panel.ticker}), on="ticker")
    pm = pd.DataFrame(panel.P["p_model"], columns=range(1, 15))
    pm["ticker"] = panel.ticker
    long = long.merge(pm.melt(id_vars="ticker", var_name="minute", value_name="p_model")
                      .astype({"minute": int}), on=["ticker", "minute"])
    opens = np.sort(panel.open_ts)
    split_ts = int(opens[int(len(opens) * train_frac)])
    train, test = panel.subset(panel.open_ts < split_ts), panel.subset(panel.open_ts >= split_ts)
    res = {"series": series, "split_ts": split_ts, "markets": int(len(opens)),
           "train_markets": len(train), "test_markets": len(test),
           "start": int(opens[0]), "end": int(opens[-1] + 900),
           "up_rate": round(float(panel.result.mean()), 4),
           "calibration": calibration(long), "model_calibration": model_calibration(long),
           "strategies": {}}
    for name, (fn, desc, grid) in STRATEGIES.items():
        sweep = []
        for params in _grid(grid):
            tr = run(train, fn, stake=stake, **params)
            mtr = metrics(tr)
            sweep.append((params, mtr))
        ok = [s for s in sweep if s[1]["trades"] >= min_trades] or sweep
        best_params, best_tr = max(ok, key=lambda s: s[1]["pnl"])
        te = run(test, fn, stake=stake, **best_params)
        full = run(panel, fn, stake=stake, **best_params)
        # test-set result for every param set (shows how much the in-sample pick overfits)
        sweep_out = []
        for params, mtr in sweep:
            mte = metrics(run(test, fn, stake=stake, **params))
            sweep_out.append({"params": params, "train_pnl": mtr["pnl"], "test_pnl": mte["pnl"],
                              "train_trades": mtr["trades"], "test_trades": mte["trades"],
                              "train_roi": mtr["roi"], "test_roi": mte["roi"]})
        by_min = (full.groupby("minute").agg(trades=("pnl", "size"), pnl=("pnl", "sum"),
                                              win=("win", "mean")).reset_index().round(3)
                  .to_dict("records") if not full.empty else [])
        recent = full.sort_values("ts").tail(40)[["ticker", "ts", "side", "minute", "price", "contracts",
                                                  "fee", "win", "pnl"]].to_dict("records") if not full.empty else []
        res["strategies"][name] = {
            "description": desc, "best_params": best_params,
            "train": best_tr, "test": metrics(te), "full": metrics(full),
            "curve": _curve(full), "sweep": sweep_out, "by_minute": by_min, "recent": recent,
        }
        print(f"  {name:14s} best={best_params} train pnl ${best_tr['pnl']:>8} | "
              f"test pnl ${metrics(te)['pnl']:>8} ({metrics(te)['trades']} trades)")
    return res


def build(series_list=("KXBTC15M", "KXETH15M", "KXSOL15M"), stake=10.0):
    results = {"generated": int(datetime.now(timezone.utc).timestamp()), "stake": stake,
               "fee_note": "Kalshi taker fee ceil(0.07*C*P*(1-P)); fills at the quoted ask",
               "series": {}}
    for s in series_list:
        if not (DATA_DIR / f"{s}_markets.csv").exists():
            print(f"skip {s}: no data (run `python -m kalshi15m download`)")
            continue
        results["series"][s] = evaluate(s, stake=stake)
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, default=_np))
    html = (ROOT / "dashboard_template.html").read_text()
    (OUT / "index.html").write_text(html.replace("/*__RESULTS__*/null", json.dumps(results, default=_np)))
    print(f"wrote {OUT / 'index.html'}")
    return results


def _np(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))
