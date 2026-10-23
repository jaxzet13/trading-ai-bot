"""Candidate strategies for the prop-firm bot. Each is `on_bar(ctx, i) -> Order | None`, called while flat.

Design goals, in order: (1) small, defined risk with a target so single trades cannot run away,
(2) win rate above 50% so losing streaks stay short, (3) a reason a trader recognises.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .engine import Ctx, Order


@dataclass
class SP:
    """Strategy params shared by the candidates (each uses the ones it needs)."""
    target_r: float = 1.5
    stop_atr: float = 1.0        # stop distance in ATR for pullback entries
    start: int = 945             # first bar that may signal
    end: int = 1430              # last bar that may signal
    time_exit: int = 1555
    trail_atr: float = 0.0
    be_at_r: float = 0.0
    ext_atr: float = 1.0         # fade: how far beyond the opening range price must stretch
    trend: str = "slow_ema"      # slow_ema | vwap | both | none
    long_only: bool = False


def _trend_dir(ctx: Ctx, i: int, sp: SP) -> int:
    c = ctx.c[i]
    up_e, up_v = c > ctx.ema_slow[i], c > ctx.vwap[i]
    if sp.trend == "slow_ema":
        return 1 if up_e else -1
    if sp.trend == "vwap":
        return 1 if up_v else -1
    if sp.trend == "both":
        return 1 if (up_e and up_v) else (-1 if (not up_e and not up_v) else 0)
    return 0


def orb(sp: SP):
    """Opening-range breakout: first 5-minute close outside the 15-minute opening range, in the trend
    direction. Stop at the range midpoint, fixed R target, done by the time exit."""
    def on_bar(ctx: Ctx, i: int) -> Order | None:
        if ctx.hhmm[i] < sp.start or ctx.hhmm[i] > sp.end or np.isnan(ctx.or_high):
            return None
        mid = (ctx.or_high + ctx.or_low) / 2
        c = ctx.c[i]
        tdir = _trend_dir(ctx, i, sp)
        if c > ctx.or_high and (tdir >= 0 or sp.trend == "none"):
            d, stop = 1, mid
        elif c < ctx.or_low and (tdir <= 0 or sp.trend == "none") and not sp.long_only:
            d, stop = -1, mid
        else:
            return None
        risk = abs(c - stop)
        if risk <= 0 or risk > 3 * ctx.atr[i]:
            return None
        return Order(d, "market", c, stop, c + d * sp.target_r * risk, 1, sp.time_exit, sp.trail_atr, sp.be_at_r, "orb")
    return on_bar


def vwap_pullback(sp: SP):
    """Trend continuation: in an up trend (price above the slow EMA), wait for a bar that dips to VWAP and
    closes back above it with a bullish close. Enter next open, stop under that bar, fixed R target."""
    def on_bar(ctx: Ctx, i: int) -> Order | None:
        if ctx.hhmm[i] < sp.start or ctx.hhmm[i] > sp.end or np.isnan(ctx.vwap[i]):
            return None
        d = _trend_dir(ctx, i, sp)
        if d == 0 or (d < 0 and sp.long_only):
            return None
        c, o, hi, lo, v = ctx.c[i], ctx.o[i], ctx.h[i], ctx.l[i], ctx.vwap[i]
        a = ctx.atr[i]
        if d > 0 and lo <= v and c > v and c > o:
            stop = min(lo, v) - sp.stop_atr * a * 0.25
        elif d < 0 and hi >= v and c < v and c < o:
            stop = max(hi, v) + sp.stop_atr * a * 0.25
        else:
            return None
        risk = abs(c - stop)
        if risk <= 0 or risk > 2.5 * a:
            return None
        return Order(d, "market", c, stop, c + d * sp.target_r * risk, 1, sp.time_exit, sp.trail_atr, sp.be_at_r, "vwap_pb")
    return on_bar


def ema_pullback(sp: SP):
    """Same idea with the fast EMA instead of VWAP: bar touches the 20 EMA and closes with the trend."""
    def on_bar(ctx: Ctx, i: int) -> Order | None:
        if ctx.hhmm[i] < sp.start or ctx.hhmm[i] > sp.end:
            return None
        d = _trend_dir(ctx, i, sp)
        if d == 0 or (d < 0 and sp.long_only):
            return None
        c, o, hi, lo, e, a = ctx.c[i], ctx.o[i], ctx.h[i], ctx.l[i], ctx.ema_fast[i], ctx.atr[i]
        if d > 0 and lo <= e and c > e and c > o:
            stop = lo - sp.stop_atr * a * 0.25
        elif d < 0 and hi >= e and c < e and c < o:
            stop = hi + sp.stop_atr * a * 0.25
        else:
            return None
        risk = abs(c - stop)
        if risk <= 0 or risk > 2.5 * a:
            return None
        return Order(d, "market", c, stop, c + d * sp.target_r * risk, 1, sp.time_exit, sp.trail_atr, sp.be_at_r, "ema_pb")
    return on_bar


def or_fade(sp: SP):
    """Mean reversion: price stretches `ext_atr` ATR beyond the opening range and then closes back inside
    it. Fade toward VWAP with the stop beyond the extreme."""
    def on_bar(ctx: Ctx, i: int) -> Order | None:
        if ctx.hhmm[i] < sp.start or ctx.hhmm[i] > sp.end or np.isnan(ctx.or_high) or i < 2:
            return None
        a = ctx.atr[i]
        c, hi, lo = ctx.c[i], ctx.h[i], ctx.l[i]
        recent_hi, recent_lo = ctx.h[max(0, i - 3):i + 1].max(), ctx.l[max(0, i - 3):i + 1].min()
        if recent_hi >= ctx.or_high + sp.ext_atr * a and c < ctx.or_high and not sp.long_only:
            d, stop = -1, recent_hi + 0.25 * a
        elif recent_lo <= ctx.or_low - sp.ext_atr * a and c > ctx.or_low:
            d, stop = 1, recent_lo - 0.25 * a
        else:
            return None
        risk = abs(c - stop)
        if risk <= 0:
            return None
        target = c + d * sp.target_r * risk
        return Order(d, "market", c, stop, target, 1, sp.time_exit, 0.0, sp.be_at_r, "or_fade")
    return on_bar


def prev_day_break(sp: SP):
    """Break of the previous session's high/low after 10:00 in the trend direction, stop 1 ATR, fixed target."""
    def on_bar(ctx: Ctx, i: int) -> Order | None:
        if ctx.hhmm[i] < sp.start or ctx.hhmm[i] > sp.end or np.isnan(ctx.prev_high) or i < 1:
            return None
        c, pc, a = ctx.c[i], ctx.c[i - 1], ctx.atr[i]
        d = _trend_dir(ctx, i, sp)
        if c > ctx.prev_high >= pc and d >= 0:
            dd, stop = 1, c - sp.stop_atr * a
        elif c < ctx.prev_low <= pc and d <= 0 and not sp.long_only:
            dd, stop = -1, c + sp.stop_atr * a
        else:
            return None
        return Order(dd, "market", c, stop, c + dd * sp.target_r * abs(c - stop), 1, sp.time_exit, sp.trail_atr, sp.be_at_r, "pdhl")
    return on_bar


CANDIDATES = {"orb": orb, "vwap_pullback": vwap_pullback, "ema_pullback": ema_pullback, "or_fade": or_fade, "prev_day_break": prev_day_break}
