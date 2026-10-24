"""Day-trading setups, parametrised on session times so they work on any instrument.
Each factory returns on_bar(ctx, i) -> Order | None for propbot.engine.simulate_day."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from propbot.engine import Ctx, Order


@dataclass
class DP:
    target_r: float = 2.0
    start: int = 945          # first bar allowed to signal
    end: int = 1130           # last bar allowed to signal
    time_exit: int = 1555
    trend: str = "slow_ema"   # slow_ema | vwap | none
    be_at_r: float = 0.0
    trail_atr: float = 0.0
    stop_mode: str = "mid"    # orb / asia: mid of the range or the far side
    max_range_atr: float = 3.0


def _trend(ctx: Ctx, i: int, mode: str) -> int:
    if mode == "slow_ema":
        return 1 if ctx.c[i] > ctx.ema_slow[i] else -1
    if mode == "vwap":
        return 1 if ctx.c[i] > ctx.vwap[i] else -1
    return 0


def range_breakout(dp: DP, which: str = "or"):
    """Close outside a range (session opening range, or the Asian range), stop at its midpoint or far side, fixed R target."""
    def on_bar(ctx: Ctx, i: int) -> Order | None:
        if ctx.hhmm[i] < dp.start or ctx.hhmm[i] > dp.end:
            return None
        hi, lo = (ctx.or_high, ctx.or_low) if which == "or" else (ctx.extra.get("asia_high", np.nan), ctx.extra.get("asia_low", np.nan))
        if np.isnan(hi) or np.isnan(lo) or hi <= lo or (hi - lo) > dp.max_range_atr * ctx.atr[i] * 4:
            return None
        c = ctx.c[i]
        tdir = _trend(ctx, i, dp.trend)
        mid = (hi + lo) / 2
        if c > hi and tdir >= 0:
            d, stop = 1, (mid if dp.stop_mode == "mid" else lo)
        elif c < lo and tdir <= 0:
            d, stop = -1, (mid if dp.stop_mode == "mid" else hi)
        else:
            return None
        risk = abs(c - stop)
        if risk <= 0 or risk > dp.max_range_atr * ctx.atr[i]:
            return None
        return Order(d, "market", c, stop, c + d * dp.target_r * risk if dp.target_r else None, 1, dp.time_exit, dp.trail_atr, dp.be_at_r, which + "_break")
    return on_bar


def vwap_pullback(dp: DP):
    """With the trend, a bar dips to session VWAP and closes back beyond it in the trend direction."""
    def on_bar(ctx: Ctx, i: int) -> Order | None:
        if ctx.hhmm[i] < dp.start or ctx.hhmm[i] > dp.end or np.isnan(ctx.vwap[i]):
            return None
        d = _trend(ctx, i, "slow_ema")
        c, o, hi, lo, v, a = ctx.c[i], ctx.o[i], ctx.h[i], ctx.l[i], ctx.vwap[i], ctx.atr[i]
        if d > 0 and lo <= v < c and c > o:
            stop = lo - 0.25 * a
        elif d < 0 and hi >= v > c and c < o:
            stop = hi + 0.25 * a
        else:
            return None
        risk = abs(c - stop)
        if risk <= 0 or risk > 2.5 * a:
            return None
        return Order(d, "market", c, stop, c + d * dp.target_r * risk if dp.target_r else None, 1, dp.time_exit, dp.trail_atr, dp.be_at_r, "vwap_pb")
    return on_bar


SETUPS = {"or_break": lambda dp: range_breakout(dp, "or"), "asia_break": lambda dp: range_breakout(dp, "asia"), "vwap_pullback": vwap_pullback}
