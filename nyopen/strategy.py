"""NY Open first-candle 12-EMA strategy (NAS100, 5-minute).

Rule (from the video):
  * Take the first 5-minute candle after the 09:30 New York open.
  * Close above the 12 EMA  -> go LONG at that candle's close.
  * Close below the 12 EMA  -> go SHORT at that candle's close.
  * Initial stop at the signal candle's low (long) / high (short). 1R = entry - stop.
  * Trail the stop as momentum develops and stay in for as long as it lasts.
  * One trade per day, flat before the cash close.

Everything is parametrised through `Params` so an optimiser (or an AI agent) can iterate.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Literal

import numpy as np
import pandas as pd

TrailMode = Literal["ema", "swing", "atr", "none"]


@dataclass
class Params:
    ema_len: int = 12               # EMA length on 5-minute closes
    bar_minutes: int = 5            # timeframe of the signal candle
    signal_time: str = "09:30"      # open time of the signal candle (NY time)
    exit_time: str = "15:55"        # flatten if still open at this bar's open
    trail_mode: TrailMode = "ema"   # how the stop trails: ema | swing | atr | none
    swing_len: int = 3              # bars for the swing-low/high trail
    atr_len: int = 14               # ATR length for the atr trail
    atr_mult: float = 2.0           # ATR multiple for the atr trail
    trail_after_r: float = 0.0      # only start trailing once the trade is this many R in profit
    breakeven_at_r: float = 0.0     # move stop to entry once this many R in profit (0 = off)
    min_body_r: float = 0.0         # skip if |close - ema| / R is below this (filter weak signals)
    max_risk_points: float = 0.0    # skip if signal candle range exceeds this many points (0 = off)
    allow_long: bool = True
    allow_short: bool = True
    risk_pct: float = 1.0           # % of equity risked per trade (position sizing)
    cost_points: float = 1.0        # round-trip spread + slippage in index points
    start_equity: float = 10_000.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Params":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def atr(df: pd.DataFrame, length: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def add_indicators(bars: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Add ema / atr / swing columns to a bar frame (bars labelled by open time, NY tz)."""
    out = bars.copy()
    out["ema"] = ema(out["close"], p.ema_len)
    out["atr"] = atr(out, p.atr_len)
    out["swing_low"] = out["low"].rolling(p.swing_len).min()
    out["swing_high"] = out["high"].rolling(p.swing_len).max()
    t = out["time"]
    out["date"] = t.dt.date
    out["hhmm"] = t.dt.strftime("%H:%M")
    return out


@dataclass
class Trade:
    date: str
    direction: str
    entry_time: str
    exit_time: str
    entry: float
    stop: float
    exit: float
    risk_points: float
    r_multiple: float
    pnl: float
    equity_after: float
    bars_held: int
    exit_reason: str
    mfe_r: float
    mae_r: float
    ema_at_entry: float
    signal_close: float


def trail_level(row: pd.Series, direction: int, p: Params) -> float | None:
    """Candidate trailing stop derived from the just-closed bar. None = no trail."""
    if p.trail_mode == "ema":
        return float(row["ema"])
    if p.trail_mode == "swing":
        return float(row["swing_low"] if direction > 0 else row["swing_high"])
    if p.trail_mode == "atr":
        return float(row["close"] - direction * p.atr_mult * row["atr"])
    return None


def run_day(day: pd.DataFrame, p: Params, equity: float) -> Trade | None:
    """Simulate one trading day. `day` holds that day's bars (with indicators), sorted by time."""
    day = day.reset_index(drop=True)
    sig_idx = day.index[day["hhmm"] == p.signal_time]
    if len(sig_idx) == 0:
        return None
    i0 = int(sig_idx[0])
    sig = day.loc[i0]
    if np.isnan(sig["ema"]):
        return None

    if sig["close"] > sig["ema"] and p.allow_long:
        direction = 1
    elif sig["close"] < sig["ema"] and p.allow_short:
        direction = -1
    else:
        return None

    entry = float(sig["close"])
    stop = float(sig["low"] if direction > 0 else sig["high"])
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    if p.max_risk_points and risk > p.max_risk_points:
        return None
    if p.min_body_r and abs(entry - sig["ema"]) / risk < p.min_body_r:
        return None

    size = equity * (p.risk_pct / 100.0) / risk      # units of index per point
    exit_price, exit_reason, exit_time, bars_held = None, "", "", 0
    best, worst = 0.0, 0.0  # in R
    exit_hhmm = p.exit_time

    for j in range(i0 + 1, len(day)):
        bar = day.loc[j]
        bars_held += 1
        # 1) time exit at the open of the exit bar
        if bar["hhmm"] >= exit_hhmm:
            exit_price, exit_reason, exit_time = float(bar["open"]), "time", bar["hhmm"]
            break
        # 2) stop hit inside the bar (gap through the stop fills at the open)
        if direction > 0 and bar["low"] <= stop:
            exit_price = min(stop, float(bar["open"]))
            exit_reason, exit_time = "stop" if stop < entry else "trail", bar["hhmm"]
            break
        if direction < 0 and bar["high"] >= stop:
            exit_price = max(stop, float(bar["open"]))
            exit_reason, exit_time = "stop" if stop > entry else "trail", bar["hhmm"]
            break
        # excursion bookkeeping
        fav = (bar["high"] - entry) if direction > 0 else (entry - bar["low"])
        adv = (entry - bar["low"]) if direction > 0 else (bar["high"] - entry)
        best, worst = max(best, fav / risk), max(worst, adv / risk)
        # 3) update the trail at bar close (only ever tightens)
        open_r = (bar["close"] - entry) * direction / risk
        if p.breakeven_at_r and open_r >= p.breakeven_at_r:
            stop = max(stop, entry) if direction > 0 else min(stop, entry)
        if open_r >= p.trail_after_r:
            lvl = trail_level(bar, direction, p)
            if lvl is not None and not np.isnan(lvl):
                stop = max(stop, lvl) if direction > 0 else min(stop, lvl)
    if exit_price is None:  # data ended mid-trade
        last = day.iloc[-1]
        exit_price, exit_reason, exit_time = float(last["close"]), "eod", last["hhmm"]

    pnl_points = (exit_price - entry) * direction - p.cost_points
    pnl = pnl_points * size
    return Trade(
        date=str(sig["date"]), direction="long" if direction > 0 else "short",
        entry_time=str(sig["time"]), exit_time=exit_time, entry=entry,
        stop=float(sig["low"] if direction > 0 else sig["high"]), exit=exit_price, risk_points=risk,
        r_multiple=pnl_points / risk, pnl=pnl, equity_after=equity + pnl, bars_held=bars_held,
        exit_reason=exit_reason, mfe_r=best, mae_r=worst, ema_at_entry=float(sig["ema"]), signal_close=float(sig["close"]),
    )
