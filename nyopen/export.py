"""Build dashboard/data.js: everything the dashboard needs, as one JS global (works from file:// too)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import get_bars, load_experiments
from .optimize import OOS_START, walk_forward
from .strategy import Params, add_indicators

ROOT = Path(__file__).resolve().parent.parent
DASH = ROOT / "dashboard"


def _clean(o):
    if isinstance(o, float):
        return None if (np.isnan(o) or np.isinf(o)) else round(o, 4)
    if isinstance(o, (np.floating,)):
        return _clean(float(o))
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def trade_chart(trades: pd.DataFrame, p: Params, which: int = -1, before: int = 24, after: int = 60) -> dict:
    """5-minute candles around one trade, for the 'latest trade' chart."""
    t = trades.iloc[which]
    bars = add_indicators(get_bars(p.bar_minutes), p)
    entry_ts = pd.Timestamp(t.entry_time)
    i = int(bars.index[bars.time == entry_ts][0])
    win = bars.iloc[max(0, i - before): i + after + 1]
    return {
        "trade": _clean(t.to_dict()),
        "candles": [[r.time.strftime("%Y-%m-%d %H:%M"), r.open, r.close, r.low, r.high] for r in win.itertuples()],
        "ema": [round(float(x), 2) for x in win.ema],
        "entry_index": int(i - win.index[0]),
    }


def export_dashboard(res: dict, run_id: str) -> Path:
    p = Params.from_dict(res["params"])
    tr: pd.DataFrame = res["trades"]
    m = res["metrics"]
    eq = pd.concat([pd.Series([p.start_equity]), tr.equity_after], ignore_index=True)
    dd = (eq / eq.cummax() - 1) * 100
    dates = [str(pd.to_datetime(tr.date.iloc[0]).date() - pd.Timedelta(days=1))] + tr.date.tolist()
    cum_r = tr.r_multiple.cumsum()

    tr2 = tr.copy()
    tr2["weekday"] = pd.to_datetime(tr2.date).dt.day_name()
    tr2["year"] = pd.to_datetime(tr2.date).dt.year
    by_weekday = [{"weekday": k, "trades": int(len(g)), "avg_r": float(g.r_multiple.mean()), "win_rate_pct": float((g.pnl > 0).mean() * 100), "sum_r": float(g.r_multiple.sum())}
                  for k, g in tr2.groupby("weekday")]
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    by_weekday.sort(key=lambda r: order.index(r["weekday"]) if r["weekday"] in order else 9)
    by_exit = [{"reason": k, "trades": int(len(g)), "avg_r": float(g.r_multiple.mean()), "sum_r": float(g.r_multiple.sum())} for k, g in tr2.groupby("exit_reason")]
    by_dir = [{"direction": k, "trades": int(len(g)), "avg_r": float(g.r_multiple.mean()), "win_rate_pct": float((g.pnl > 0).mean() * 100), "sum_r": float(g.r_multiple.sum()),
               "profit_factor": float(g[g.pnl > 0].pnl.sum() / -g[g.pnl <= 0].pnl.sum()) if (g.pnl <= 0).any() else None} for k, g in tr2.groupby("direction")]
    hist_edges = np.arange(-1.5, 8.01, 0.25)
    counts, _ = np.histogram(tr.r_multiple.clip(-1.5, 8), bins=hist_edges)
    r_hist = [{"bin": float(hist_edges[i]), "count": int(c)} for i, c in enumerate(counts)]
    exit_hours = tr2.exit_time.str.slice(0, 2).value_counts().sort_index()
    by_exit_hour = [{"hour": k, "trades": int(v), "avg_r": float(tr2[tr2.exit_time.str.startswith(k)].r_multiple.mean())} for k, v in exit_hours.items()]

    # rolling 100-trade stats
    roll = tr.r_multiple.rolling(100)
    rolling = [{"date": d, "avg_r": a, "win_rate_pct": w} for d, a, w in zip(tr.date, roll.mean().round(3), ((tr.pnl > 0).astype(float).rolling(100).mean() * 100).round(1)) if not np.isnan(a)]

    years = sorted(tr2.year.unique())
    folds = [(f"{y}-01-01", f"{y + 1}-01-01") for y in years]
    wf = walk_forward(p, folds)

    exps = load_experiments()
    bars = get_bars(p.bar_minutes)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": run_id,
        "instrument": "NAS100 (Dukascopy USATECHIDXUSD CFD)",
        "data_range": {"start": str(bars.time.min()), "end": str(bars.time.max()), "bars": int(len(bars)), "days": int(bars.time.dt.date.nunique())},
        "oos_start": OOS_START,
        "params": p.to_dict(),
        "metrics": m,
        "equity": {"dates": dates, "equity": [round(float(x), 2) for x in eq], "drawdown_pct": [round(float(x), 2) for x in dd], "cum_r": [0.0] + [round(float(x), 2) for x in cum_r]},
        "yearly": res.get("yearly", []),
        "monthly": res.get("monthly", []),
        "by_weekday": by_weekday, "by_exit": by_exit, "by_direction": by_dir, "by_exit_hour": by_exit_hour,
        "r_hist": r_hist, "rolling": rolling, "walk_forward": wf,
        "trades": [_clean(r) for r in tr.drop(columns=["equity_after"]).assign(equity_after=tr.equity_after.round(2)).to_dict("records")],
        "latest_trade": trade_chart(tr, p, -1),
        "best_trade": trade_chart(tr, p, int(tr.r_multiple.idxmax())),
        "experiments": exps[-400:],
    }
    DASH.mkdir(exist_ok=True)
    out = DASH / "data.js"
    out.write_text("window.DASHBOARD_DATA = " + json.dumps(_clean(data), default=str) + ";\n")
    (DASH / "data.json").write_text(json.dumps(_clean(data), default=str))
    print(f"dashboard data written to {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out
