"""Parameter search with honest scoring.

Every candidate is run once over the full history; the trade list is then split at OOS_START so
the in-sample (IS) and out-of-sample (OOS) metrics come from the same simulation. Selection only
ever looks at IS. OOS is reported, never optimised on, and the dashboard shows both side by side.
"""
from __future__ import annotations

import itertools
import math
from typing import Iterable

import pandas as pd

from .backtest import backtest, get_bars, log_experiment
from .metrics import compute_metrics
from .strategy import Params

OOS_START = "2024-01-01"   # everything from here on is held out from optimisation
KEEP = ("trades", "total_return_pct", "win_rate_pct", "profit_factor", "max_drawdown_pct", "avg_r", "sharpe", "cagr_pct")


def split_metrics(result: dict, start_equity: float) -> tuple[dict, dict]:
    """IS / OOS metrics from one full run. Equity in each slice is re-based to the slice's starting equity."""
    t: pd.DataFrame = result["trades"]
    if t.empty:
        return {"trades": 0}, {"trades": 0}
    is_t = t[t.date < OOS_START]
    oos_t = t[t.date >= OOS_START]
    is_m = compute_metrics(is_t, start_equity) if len(is_t) else {"trades": 0}
    oos_start_eq = float(is_t.equity_after.iloc[-1]) if len(is_t) else start_equity
    oos_m = compute_metrics(oos_t, oos_start_eq) if len(oos_t) else {"trades": 0}
    return is_m, oos_m


def year_consistency(trades: pd.DataFrame) -> float:
    """Share of calendar years with positive total R. 1.0 = every year made money."""
    if trades.empty:
        return 0.0
    yr = pd.to_datetime(trades.date).dt.year
    s = trades.groupby(yr).r_multiple.sum()
    return float((s > 0).mean())


def score(m: dict, consistency: float = 1.0, min_trades: int = 150) -> float:
    """Single number to rank candidates. Rewards expectancy and smoothness, punishes drawdown and
    small samples, and requires the edge to show up in most years rather than one lucky stretch."""
    if m.get("trades", 0) < min_trades:
        return -math.inf
    pf = min(m["profit_factor"], 3.0)
    return (m["sharpe"] * 0.5 + (pf - 1) * 2 + m["avg_r"] * 5 - m["max_drawdown_pct"] / 50) * (0.5 + 0.5 * consistency)


def evaluate(p: Params, bars: pd.DataFrame | None = None) -> dict:
    bars = get_bars(p.bar_minutes) if bars is None else bars
    full = backtest(p, bars)
    is_m, oos_m = split_metrics(full, p.start_equity)
    t = full["trades"]
    is_t = t[t.date < OOS_START] if not t.empty else t
    cons = year_consistency(is_t)
    full["is"], full["oos"] = is_m, oos_m
    full["is_score"], full["oos_score"] = score(is_m, cons), score(oos_m, 1.0, 60)
    full["consistency"] = cons
    return full


def grid(base: Params, space: dict[str, Iterable]) -> list[Params]:
    keys = list(space)
    out = []
    for combo in itertools.product(*[list(space[k]) for k in keys]):
        d = base.to_dict()
        d.update(dict(zip(keys, combo)))
        out.append(Params.from_dict(d))
    return out


def sweep(base: Params, space: dict[str, Iterable], name: str = "sweep", log: bool = True) -> pd.DataFrame:
    rows = []
    bars = get_bars(base.bar_minutes)
    for p in grid(base, space):
        res = evaluate(p, bars)
        row = {k: p.to_dict()[k] for k in space}
        row.update({f"is_{k}": res["is"].get(k) for k in KEEP})
        row.update({f"oos_{k}": res["oos"].get(k) for k in KEEP})
        row["is_score"], row["oos_score"], row["consistency"] = res["is_score"], res["oos_score"], res["consistency"]
        row["full_return_pct"] = res["metrics"].get("total_return_pct")
        rows.append(row)
        if log:
            log_experiment(f"{name}:" + ",".join(f"{k}={row[k]}" for k in space), res,
                           extra={"is": res["is"], "oos": res["oos"], "is_score": res["is_score"], "oos_score": res["oos_score"], "consistency": res["consistency"], "sweep": name})
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items() if k in space or k in ("is_profit_factor", "oos_profit_factor", "is_score", "oos_score")}, flush=True)
    return pd.DataFrame(rows)


def walk_forward(p: Params, folds: list[tuple[str, str]]) -> list[dict]:
    """Evaluate fixed params on consecutive periods to see whether the edge is stable."""
    bars = get_bars(p.bar_minutes)
    out = []
    for start, end in folds:
        m = backtest(p, bars, start=start, end=end)["metrics"]
        out.append({"start": start, "end": end, **{k: m.get(k) for k in KEEP}})
    return out
