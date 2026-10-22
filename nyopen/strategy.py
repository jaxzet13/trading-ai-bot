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
    max_leverage: float = 20.0      # cap on notional / equity so a 1-point stop cannot imply absurd size (0 = off)
    min_risk_points: float = 5.0    # skip signal candles narrower than this (flat holiday sessions produce 0.1-point "candles")
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
    out["hhmm"] = (t.dt.hour * 100 + t.dt.minute).astype("int32")  # 09:35 -> 935
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


def trail_level(mode: str, direction: int, p: Params, ema_v: float, swing_v: float, close_v: float, atr_v: float) -> float | None:
    """Candidate trailing stop derived from the just-closed bar. None = no trail."""
    if mode == "ema":
        return ema_v
    if mode == "swing":
        return swing_v
    if mode == "atr":
        return close_v - direction * p.atr_mult * atr_v
    return None


def _hhmm(s: str) -> int:
    hh, mm = s.split(":")
    return int(hh) * 100 + int(mm)


def _fmt(v: int) -> str:
    return f"{v // 100:02d}:{v % 100:02d}"


def run_day(day: pd.DataFrame, p: Params, equity: float) -> Trade | None:
    """Simulate one trading day. `day` holds that day's bars (with indicators), sorted by time."""
    hhmm = day["hhmm"].to_numpy()
    hits = np.flatnonzero(hhmm == _hhmm(p.signal_time))
    if len(hits) == 0:
        return None
    i0 = int(hits[0])
    o, h, l, c = (day[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    ema_a, atr_a = day["ema"].to_numpy(dtype=float), day["atr"].to_numpy(dtype=float)
    if np.isnan(ema_a[i0]):
        return None

    if c[i0] > ema_a[i0] and p.allow_long:
        direction = 1
    elif c[i0] < ema_a[i0] and p.allow_short:
        direction = -1
    else:
        return None
    swing_a = day["swing_low" if direction > 0 else "swing_high"].to_numpy(dtype=float)

    entry = float(c[i0])
    stop0 = float(l[i0] if direction > 0 else h[i0])
    stop = stop0
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    if p.max_risk_points and risk > p.max_risk_points:
        return None
    if p.min_risk_points and risk < p.min_risk_points:
        return None
    if p.min_body_r and abs(entry - ema_a[i0]) / risk < p.min_body_r:
        return None

    size = equity * (p.risk_pct / 100.0) / risk      # units of index per point
    if p.max_leverage:
        size = min(size, equity * p.max_leverage / entry)
    exit_price, exit_reason, exit_time, bars_held = None, "", "", 0
    best, worst = 0.0, 0.0  # in R
    n = len(day)
    exit_hhmm = _hhmm(p.exit_time)

    for j in range(i0 + 1, n):
        bars_held += 1
        # 1) time exit at the open of the exit bar
        if hhmm[j] >= exit_hhmm:
            exit_price, exit_reason, exit_time = float(o[j]), "time", _fmt(hhmm[j])
            break
        # 2) stop hit inside the bar (gap through the stop fills at the open)
        if direction > 0 and l[j] <= stop:
            exit_price = min(stop, float(o[j]))
            exit_reason, exit_time = "stop" if stop < entry else "trail", _fmt(hhmm[j])
            break
        if direction < 0 and h[j] >= stop:
            exit_price = max(stop, float(o[j]))
            exit_reason, exit_time = "stop" if stop > entry else "trail", _fmt(hhmm[j])
            break
        # excursion bookkeeping
        fav = (h[j] - entry) if direction > 0 else (entry - l[j])
        adv = (entry - l[j]) if direction > 0 else (h[j] - entry)
        best, worst = max(best, fav / risk), max(worst, adv / risk)
        # 3) update the trail at bar close (only ever tightens)
        open_r = (c[j] - entry) * direction / risk
        if p.breakeven_at_r and open_r >= p.breakeven_at_r:
            stop = max(stop, entry) if direction > 0 else min(stop, entry)
        if open_r >= p.trail_after_r:
            lvl = trail_level(p.trail_mode, direction, p, ema_a[j], swing_a[j], c[j], atr_a[j])
            if lvl is not None and not np.isnan(lvl):
                stop = max(stop, lvl) if direction > 0 else min(stop, lvl)
    if exit_price is None:  # data ended mid-trade
        exit_price, exit_reason, exit_time = float(c[-1]), "eod", _fmt(hhmm[-1])

    pnl_points = (exit_price - entry) * direction - p.cost_points
    pnl = pnl_points * size
    return Trade(
        date=str(day["date"].iloc[i0]), direction="long" if direction > 0 else "short",
        entry_time=str(day["time"].iloc[i0]), exit_time=exit_time, entry=entry,
        stop=stop0, exit=exit_price, risk_points=risk,
        r_multiple=pnl_points / risk, pnl=pnl, equity_after=equity + pnl, bars_held=bars_held,
        exit_reason=exit_reason, mfe_r=best, mae_r=worst, ema_at_entry=float(ema_a[i0]), signal_close=float(c[i0]),
    )
