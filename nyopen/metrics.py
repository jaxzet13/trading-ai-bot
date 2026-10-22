"""Performance statistics for a list of trades."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(trades: pd.DataFrame, start_equity: float) -> dict:
    if trades.empty:
        return {"trades": 0}
    eq = pd.concat([pd.Series([start_equity]), trades["equity_after"]], ignore_index=True)
    peak = eq.cummax()
    dd = (eq / peak - 1.0)
    r = trades["r_multiple"]
    wins, losses = trades[trades.pnl > 0], trades[trades.pnl <= 0]
    gross_win, gross_loss = wins.pnl.sum(), -losses.pnl.sum()
    days = (pd.to_datetime(trades.date).max() - pd.to_datetime(trades.date).min()).days or 1
    years = days / 365.25
    final = float(eq.iloc[-1])
    daily = trades.groupby("date")["pnl"].sum() / start_equity
    sharpe = float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0
    neg = daily[daily < 0]
    sortino = float(daily.mean() / neg.std() * np.sqrt(252)) if len(neg) > 1 and neg.std() > 0 else 0.0
    # streaks
    sign = (trades.pnl > 0).astype(int).to_numpy()
    def longest(v):
        best = cur = 0
        for s in sign:
            cur = cur + 1 if s == v else 0
            best = max(best, cur)
        return int(best)
    return {
        "trades": int(len(trades)),
        "start_equity": start_equity,
        "final_equity": final,
        "total_return_pct": (final / start_equity - 1) * 100,
        "cagr_pct": ((final / start_equity) ** (1 / years) - 1) * 100 if years > 0 and final > 0 else 0.0,
        "win_rate_pct": len(wins) / len(trades) * 100,
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "max_drawdown_pct": float(-dd.min() * 100),
        "avg_r": float(r.mean()),
        "avg_win_r": float(wins.r_multiple.mean()) if len(wins) else 0.0,
        "avg_loss_r": float(losses.r_multiple.mean()) if len(losses) else 0.0,
        "expectancy_pct": float(trades.pnl.sum() / len(trades) / start_equity * 100),
        "sharpe": sharpe,
        "sortino": sortino,
        "best_r": float(r.max()),
        "worst_r": float(r.min()),
        "longest_win_streak": longest(1),
        "longest_loss_streak": longest(0),
        "long_trades": int((trades.direction == "long").sum()),
        "short_trades": int((trades.direction == "short").sum()),
        "long_win_rate_pct": float((trades[trades.direction == "long"].pnl > 0).mean() * 100) if (trades.direction == "long").any() else 0.0,
        "short_win_rate_pct": float((trades[trades.direction == "short"].pnl > 0).mean() * 100) if (trades.direction == "short").any() else 0.0,
        "avg_bars_held": float(trades.bars_held.mean()),
        "years": years,
    }


def yearly_breakdown(trades: pd.DataFrame, start_equity: float) -> list[dict]:
    out = []
    t = trades.copy()
    t["year"] = pd.to_datetime(t.date).dt.year
    prev_eq = start_equity
    for y, g in t.groupby("year"):
        end_eq = float(g.equity_after.iloc[-1])
        out.append({
            "year": int(y), "trades": int(len(g)), "return_pct": (end_eq / prev_eq - 1) * 100,
            "win_rate_pct": float((g.pnl > 0).mean() * 100), "avg_r": float(g.r_multiple.mean()),
            "profit_factor": float(g[g.pnl > 0].pnl.sum() / -g[g.pnl <= 0].pnl.sum()) if (g.pnl <= 0).any() else float("inf"),
            "sum_r": float(g.r_multiple.sum()),
        })
        prev_eq = end_eq
    return out


def monthly_returns(trades: pd.DataFrame, start_equity: float) -> list[dict]:
    t = trades.copy()
    t["ym"] = pd.to_datetime(t.date).dt.to_period("M")
    prev = start_equity
    rows = []
    for ym, g in t.groupby("ym"):
        end = float(g.equity_after.iloc[-1])
        rows.append({"year": ym.year, "month": ym.month, "return_pct": (end / prev - 1) * 100, "trades": int(len(g)), "sum_r": float(g.r_multiple.sum())})
        prev = end
    return rows
