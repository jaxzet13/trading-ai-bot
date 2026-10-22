"""Parameter sweeps and walk-forward validation.

The goal is to let an agent (or a human) keep improving the strategy *honestly*:
every candidate is scored in-sample AND out-of-sample, and every run is logged.
"""
from __future__ import annotations

import itertools
import math
from typing import Iterable

import pandas as pd

from .backtest import backtest, get_bars, log_experiment
from .strategy import Params

OOS_START = "2024-01-01"   # everything from here on is held out from optimisation


def score(m: dict) -> float:
    """Single number to rank candidates: reward return and smoothness, punish drawdown and tiny samples."""
    if m.get("trades", 0) < 100:
        return -math.inf
    pf = min(m["profit_factor"], 3.0)
    return m["sharpe"] * 0.5 + (pf - 1) * 2 + m["avg_r"] * 5 - m["max_drawdown_pct"] / 50


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
        is_res = backtest(p, bars, end=OOS_START)
        oos_res = backtest(p, bars, start=OOS_START)
        full = backtest(p, bars)
        row = {k: p.to_dict()[k] for k in space}
        row.update({f"is_{k}": v for k, v in is_res["metrics"].items() if k in ("trades", "total_return_pct", "win_rate_pct", "profit_factor", "max_drawdown_pct", "avg_r", "sharpe")})
        row.update({f"oos_{k}": v for k, v in oos_res["metrics"].items() if k in ("trades", "total_return_pct", "win_rate_pct", "profit_factor", "max_drawdown_pct", "avg_r", "sharpe")})
        row["is_score"], row["oos_score"] = score(is_res["metrics"]), score(oos_res["metrics"])
        row["full_return_pct"] = full["metrics"].get("total_return_pct")
        rows.append(row)
        if log:
            log_experiment(f"{name}:" + ",".join(f"{k}={row[k]}" for k in space), full,
                           extra={"is": is_res["metrics"], "oos": oos_res["metrics"], "sweep": name})
        print(f"{row}", flush=True)
    return pd.DataFrame(rows)


def walk_forward(p: Params, folds: list[tuple[str, str]]) -> list[dict]:
    """Evaluate fixed params on consecutive periods to see whether the edge is stable."""
    bars = get_bars(p.bar_minutes)
    out = []
    for start, end in folds:
        m = backtest(p, bars, start=start, end=end)["metrics"]
        out.append({"start": start, "end": end, **{k: m.get(k) for k in ("trades", "total_return_pct", "win_rate_pct", "profit_factor", "max_drawdown_pct", "avg_r", "sharpe")}})
    return out
