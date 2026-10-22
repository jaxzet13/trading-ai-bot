"""Run the strategy over the full history, log the experiment, and return results."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .data import load_m1, resample
from .metrics import compute_metrics, monthly_returns, yearly_breakdown
from .strategy import Params, add_indicators, run_day

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS = ROOT / "experiments" / "experiments.jsonl"

_BARS_CACHE: dict[int, pd.DataFrame] = {}


def get_bars(minutes: int) -> pd.DataFrame:
    if minutes not in _BARS_CACHE:
        _BARS_CACHE[minutes] = resample(load_m1(), minutes)
    return _BARS_CACHE[minutes]


def backtest(p: Params, bars: pd.DataFrame | None = None, start: str | None = None, end: str | None = None) -> dict:
    bars = get_bars(p.bar_minutes) if bars is None else bars
    df = add_indicators(bars, p)
    if start:
        df = df[df["time"] >= pd.Timestamp(start, tz="America/New_York")]
    if end:
        df = df[df["time"] < pd.Timestamp(end, tz="America/New_York")]
    equity = p.start_equity
    trades = []
    for _, day in df.groupby("date", sort=True):
        t = run_day(day, p, equity)
        if t is not None:
            trades.append(asdict(t))
            equity = t.equity_after
    tdf = pd.DataFrame(trades)
    result = {"params": p.to_dict(), "metrics": compute_metrics(tdf, p.start_equity), "trades": tdf}
    if not tdf.empty:
        result["yearly"] = yearly_breakdown(tdf, p.start_equity)
        result["monthly"] = monthly_returns(tdf, p.start_equity)
    return result


def log_experiment(name: str, result: dict, note: str = "", extra: dict | None = None) -> dict:
    """Append one line to experiments/experiments.jsonl so every run is remembered."""
    EXPERIMENTS.parent.mkdir(exist_ok=True)
    m = {k: v for k, v in result["metrics"].items()}
    rec = {
        "id": f"exp_{int(time.time())}",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name": name,
        "note": note,
        "params": result["params"],
        "metrics": m,
        **(extra or {}),
    }
    with EXPERIMENTS.open("a") as f:
        f.write(json.dumps(rec, default=float) + "\n")
    return rec


def load_experiments() -> list[dict]:
    if not EXPERIMENTS.exists():
        return []
    return [json.loads(l) for l in EXPERIMENTS.read_text().splitlines() if l.strip()]
