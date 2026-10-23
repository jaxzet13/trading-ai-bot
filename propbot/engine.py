"""A small intraday event engine for NAS100 5-minute bars.

A strategy is a function `on_bar(ctx, i) -> Order | None` called on every bar of the session while flat.
Orders are filled by the engine with a conservative fill model (stop-through gaps fill at the open,
stop and target in the same bar resolve as a stop). One position at a time, N trades a day max,
and a daily loss cap in R so a bad morning cannot become a bad day.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd


@dataclass
class Order:
    direction: int               # +1 long, -1 short
    kind: str                    # market | stop | limit
    price: float                 # trigger / limit price (ignored for market)
    stop: float                  # protective stop price
    target: float | None = None  # take-profit price (None = no target)
    valid_bars: int = 1          # bars the pending order stays alive
    time_exit: int = 1555        # hhmm of the flatten bar
    trail_atr: float = 0.0       # if > 0, trail the stop this many ATR behind the best price
    be_at_r: float = 0.0         # move stop to entry at this many R
    tag: str = ""


@dataclass
class Ctx:
    """Per-day arrays the strategy reads. Indices are positions within the day."""
    o: np.ndarray; h: np.ndarray; l: np.ndarray; c: np.ndarray; v: np.ndarray
    hhmm: np.ndarray; atr: np.ndarray; ema_fast: np.ndarray; ema_slow: np.ndarray; vwap: np.ndarray
    or_high: float = np.nan; or_low: float = np.nan   # opening range (first N minutes)
    prev_high: float = np.nan; prev_low: float = np.nan; prev_close: float = np.nan
    day_open: float = np.nan
    extra: dict = field(default_factory=dict)


@dataclass
class EngineParams:
    max_trades_per_day: int = 2
    daily_loss_cap_r: float = 1.0      # stop trading for the day after losing this many R (0 = off)
    daily_profit_stop_r: float = 0.0   # stop trading for the day after making this many R (0 = off)
    cost_points: float = 1.0
    risk_pct: float = 0.5
    max_leverage: float = 20.0
    start_equity: float = 10_000.0
    min_risk_points: float = 5.0
    session_start: int = 930
    session_end: int = 1600


def simulate_day(ctx: Ctx, strategy: Callable[[Ctx, int], Order | None], ep: EngineParams, equity: float, date: str) -> list[dict]:
    n = len(ctx.c)
    trades: list[dict] = []
    day_r = 0.0
    pending: Order | None = None
    pending_age = 0
    i = 0
    while i < n:
        if ctx.hhmm[i] < ep.session_start or ctx.hhmm[i] >= ep.session_end:
            i += 1
            continue
        if len(trades) >= ep.max_trades_per_day or (ep.daily_loss_cap_r and day_r <= -ep.daily_loss_cap_r) or (ep.daily_profit_stop_r and day_r >= ep.daily_profit_stop_r):
            break
        if pending is None:
            pending = strategy(ctx, i)
            pending_age = 0
            if pending is None:
                i += 1
                continue
            if pending.kind == "market":
                # fill at the next bar's open
                if i + 1 >= n:
                    break
                i += 1
                fill, j_entry = float(ctx.o[i]), i
            else:
                i += 1
                continue
        else:
            pending_age += 1
            d, od = pending.direction, pending
            if od.kind == "stop":
                hit = (d > 0 and ctx.h[i] >= od.price) or (d < 0 and ctx.l[i] <= od.price)
                fill = (max(od.price, float(ctx.o[i])) if d > 0 else min(od.price, float(ctx.o[i]))) if hit else None
            else:  # limit
                hit = (d > 0 and ctx.l[i] <= od.price) or (d < 0 and ctx.h[i] >= od.price)
                fill = (min(od.price, float(ctx.o[i])) if d > 0 else max(od.price, float(ctx.o[i]))) if hit else None
            if fill is None:
                if pending_age >= od.valid_bars or ctx.hhmm[i] >= od.time_exit:
                    pending = None
                i += 1
                continue
            j_entry = i
        # ---- we have a fill ----
        od = pending
        pending = None
        d = od.direction
        entry = fill
        stop = od.stop
        risk = abs(entry - stop)
        if risk < ep.min_risk_points or risk <= 0:
            i = j_entry + 1
            continue
        size = equity * ep.risk_pct / 100.0 / risk
        if ep.max_leverage:
            size = min(size, equity * ep.max_leverage / entry)
        best = entry
        exit_price, reason, j_exit = None, "", None
        for j in range(j_entry, n):
            if j > j_entry and ctx.hhmm[j] >= od.time_exit:
                exit_price, reason, j_exit = float(ctx.o[j]), "time", j
                break
            lo, hi = ctx.l[j], ctx.h[j]
            if j == j_entry:
                # on the entry bar only the part of the bar after the fill matters; be conservative: use the bar's extremes
                pass
            if d > 0 and lo <= stop:
                exit_price = (min(stop, float(ctx.o[j])) if j > j_entry else stop)
                reason, j_exit = ("stop" if stop < entry else "trail"), j
                break
            if d < 0 and hi >= stop:
                exit_price = (max(stop, float(ctx.o[j])) if j > j_entry else stop)
                reason, j_exit = ("stop" if stop > entry else "trail"), j
                break
            if od.target is not None and ((d > 0 and hi >= od.target) or (d < 0 and lo <= od.target)):
                exit_price, reason, j_exit = od.target, "target", j
                break
            best = max(best, hi) if d > 0 else min(best, lo)
            open_r = (ctx.c[j] - entry) * d / risk
            if od.be_at_r and open_r >= od.be_at_r:
                stop = max(stop, entry) if d > 0 else min(stop, entry)
            if od.trail_atr:
                lvl = best - d * od.trail_atr * ctx.atr[j]
                stop = max(stop, lvl) if d > 0 else min(stop, lvl)
        if exit_price is None:
            exit_price, reason, j_exit = float(ctx.c[-1]), "eod", n - 1
        pts = (exit_price - entry) * d - ep.cost_points
        r = pts / risk
        pnl = pts * size
        equity += pnl
        day_r += r
        trades.append({"date": date, "direction": "long" if d > 0 else "short", "entry_time": f"{ctx.hhmm[j_entry] // 100:02d}:{ctx.hhmm[j_entry] % 100:02d}",
                       "exit_time": f"{ctx.hhmm[j_exit] // 100:02d}:{ctx.hhmm[j_exit] % 100:02d}", "entry": entry, "stop": od.stop, "exit": exit_price,
                       "risk_points": risk, "r_multiple": r, "pnl": pnl, "equity_after": equity, "bars_held": j_exit - j_entry, "exit_reason": reason,
                       "tag": od.tag, "mfe_r": abs(best - entry) / risk, "mae_r": 0.0})
        i = j_exit + 1
    return trades
