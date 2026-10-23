"""Build dashboard/data.js: everything the dashboard needs, as one JS global (works from file:// too)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import backtest, get_bars, load_experiments
from .optimize import OOS_START, split_metrics, walk_forward
from .strategy import Params, VIDEO_RULE, add_indicators

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


def monte_carlo(trades: pd.DataFrame, start_equity: float, risk_pct: float, n: int = 2000, seed: int = 7) -> dict:
    """Bootstrap the trade sequence: draw len(trades) R-multiples with replacement, compound at risk_pct, and
    look at the spread of outcomes. Answers 'how different could the equity path have been with the same edge?'
    (A plain shuffle would leave the final return unchanged, since compounding is order-independent.)"""
    rng = np.random.default_rng(seed)
    r = trades.r_multiple.to_numpy()
    f = risk_pct / 100.0
    finals, maxdds = np.empty(n), np.empty(n)
    for i in range(n):
        path = np.cumprod(1 + f * rng.choice(r, size=len(r), replace=True))
        peak = np.maximum.accumulate(np.concatenate([[1.0], path]))
        maxdds[i] = (1 - np.concatenate([[1.0], path]) / peak).max() * 100
        finals[i] = (path[-1] - 1) * 100
    q = lambda a, p: float(np.percentile(a, p))
    return {"runs": n, "return_pct": {"p5": q(finals, 5), "p25": q(finals, 25), "p50": q(finals, 50), "p75": q(finals, 75), "p95": q(finals, 95)},
            "max_dd_pct": {"p5": q(maxdds, 5), "p25": q(maxdds, 25), "p50": q(maxdds, 50), "p75": q(maxdds, 75), "p95": q(maxdds, 95)},
            "dd_hist": [{"bin": float(b), "count": int(c)} for c, b in zip(*np.histogram(maxdds, bins=np.arange(0, min(100, maxdds.max() + 5), 2.5)))],
            "prob_dd_over_30": float((maxdds > 30).mean() * 100), "prob_loss": float((finals < 0).mean() * 100)}


def load_improve_runs() -> list[dict]:
    out = []
    for p in sorted((ROOT / "experiments").glob("improve_*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            pass
    return out


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

    # baseline: the plain video rule, for the overlay
    base_p = Params.from_dict({**p.to_dict(), **VIDEO_RULE})
    base = backtest(base_p, bars)
    bt = base["trades"]
    base_eq = pd.concat([pd.Series([p.start_equity]), bt.equity_after], ignore_index=True)
    base_series = pd.Series(base_eq.values[1:], index=bt.date.values)
    # align baseline equity to this run's trade dates (forward fill)
    aligned = base_series.reindex(sorted(set(base_series.index) | set(tr.date))).ffill().reindex(tr.date).fillna(p.start_equity)
    is_m, oos_m = split_metrics(res, p.start_equity)
    b_is, b_oos = split_metrics(base, p.start_equity)
    mc = monte_carlo(tr, p.start_equity, p.risk_pct)
    mfe_mae = [[round(float(t.mfe_r), 2), round(float(t.mae_r), 2), round(float(t.r_multiple), 2), t.direction] for t in tr.itertuples()]
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": run_id,
        "instrument": "NAS100 (Dukascopy USATECHIDXUSD CFD)",
        "data_range": {"start": str(bars.time.min()), "end": str(bars.time.max()), "bars": int(len(bars)), "days": int(bars.time.dt.date.nunique())},
        "oos_start": OOS_START,
        "params": p.to_dict(),
        "metrics": m,
        "equity": {"dates": dates, "equity": [round(float(x), 2) for x in eq], "drawdown_pct": [round(float(x), 2) for x in dd], "cum_r": [0.0] + [round(float(x), 2) for x in cum_r],
                   "baseline": [round(float(p.start_equity), 2)] + [round(float(x), 2) for x in aligned]},
        "baseline": {"params": base_p.to_dict(), "metrics": base["metrics"], "is": b_is, "oos": b_oos},
        "is": is_m, "oos": oos_m,
        "monte_carlo": mc, "mfe_mae": mfe_mae,
        "improve_runs": load_improve_runs(),
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
