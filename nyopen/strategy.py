"""NY Open first-candle 12-EMA strategy (NAS100, 5-minute).

Rule (from the video):
  * Take the first 5-minute candle after the 09:30 New York open.
  * Close above the 12 EMA  -> go LONG at that candle's close.
  * Close below the 12 EMA  -> go SHORT at that candle's close.
  * Initial stop at the signal candle's low (long) / high (short). 1R = entry - stop.
  * Trail the stop as momentum develops and stay in for as long as it lasts.
  * One trade per day, flat before the cash close.

Everything is parametrised through `Params` so an optimiser (or an AI agent) can iterate.
Each lever below is off by default unless the comment says otherwise, so the plain video rule is
`Params(trail_mode="ema", min_risk_points=0)` and the current defaults are whatever survived out of sample.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

import numpy as np
import pandas as pd

TrailMode = Literal["ema", "swing", "atr", "chandelier", "none"]
EntryMode = Literal["close", "breakout"]
TrendFilter = Literal["none", "slow_ema", "prev_day"]


@dataclass
class Params:
    # --- signal -----------------------------------------------------------------------------------
    ema_len: int = 8                # EMA length on 5-minute closes (video: 12; 8 survived the v3 search)
    bar_minutes: int = 5            # timeframe of the signal candle
    signal_time: str = "09:30"      # open time of the signal candle (NY time)
    entry_mode: EntryMode = "close" # close: enter at the signal close. breakout: stop order at the signal high/low
    breakout_wait_bars: int = 3     # breakout mode: cancel if not triggered within this many bars
    # --- exits ------------------------------------------------------------------------------------
    exit_time: str = "15:55"        # flatten if still open at this bar's open
    trail_mode: TrailMode = "chandelier"  # ema | swing | atr | chandelier | none (video: ema)
    swing_len: int = 3              # bars for the swing-low/high trail
    atr_len: int = 14               # ATR length (bars) used by the atr/chandelier trails and the filters
    atr_mult: float = 3.0           # ATR multiple for the atr / chandelier trails
    trail_after_r: float = 0.0      # only start trailing once the trade is this many R in profit
    breakeven_at_r: float = 0.0     # move stop to entry once this many R in profit (0 = off)
    tp_r: float = 0.0               # fixed take-profit in R for the whole position (0 = off)
    partial_tp_r: float = 0.0       # scale out `partial_frac` of the position at this many R (0 = off)
    partial_frac: float = 0.5
    # --- filters ----------------------------------------------------------------------------------
    min_body_r: float = 0.1         # skip if |close - ema| / R is below this (weak signal; video: 0)
    min_risk_points: float = 5.0    # skip signal candles narrower than this (flat holiday sessions produce 0.1-point "candles")
    max_risk_points: float = 0.0    # skip if signal candle range exceeds this many points (0 = off)
    min_risk_atr: float = 0.0       # skip if risk < this many ATRs (0 = off)
    max_risk_atr: float = 0.0       # skip if risk > this many ATRs (0 = off)
    max_gap_atr: float = 0.0        # skip if |open - previous session close| > this many ATRs (0 = off)
    trend_filter: TrendFilter = "slow_ema"  # slow_ema: trade only with price vs slow EMA; prev_day: only with yesterday's direction (video: none)
    slow_ema_len: int = 200         # for trend_filter = slow_ema
    skip_weekdays: str = ""         # e.g. "Mon,Fri"
    allow_long: bool = True
    allow_short: bool = True
    # --- sizing & costs ---------------------------------------------------------------------------
    risk_pct: float = 1.0           # % of equity risked per trade (position sizing)
    max_leverage: float = 20.0      # cap on notional / equity so a 1-point stop cannot imply absurd size (0 = off)
    cost_points: float = 1.0        # round-trip spread + slippage in index points
    start_equity: float = 10_000.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Params":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


VIDEO_RULE = dict(trail_mode="ema", ema_len=12, exit_time="15:55", min_risk_points=0.0, min_body_r=0.0, entry_mode="close",
                  tp_r=0.0, partial_tp_r=0.0, breakeven_at_r=0.0, trail_after_r=0.0, trend_filter="none",
                  max_gap_atr=0.0, min_risk_atr=0.0, max_risk_atr=0.0, skip_weekdays="")

WEEKDAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def atr(df: pd.DataFrame, length: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def add_indicators(bars: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Add ema / atr / swing / trend columns to a bar frame (bars labelled by open time, NY tz)."""
    out = bars.copy()
    out["ema"] = ema(out["close"], p.ema_len)
    out["slow_ema"] = ema(out["close"], p.slow_ema_len)
    out["atr"] = atr(out, p.atr_len)
    out["swing_low"] = out["low"].rolling(p.swing_len).min()
    out["swing_high"] = out["high"].rolling(p.swing_len).max()
    t = out["time"]
    out["date"] = t.dt.date
    out["hhmm"] = (t.dt.hour * 100 + t.dt.minute).astype("int32")  # 09:35 -> 935
    out["weekday"] = t.dt.weekday.astype("int8")
    # previous cash-session close (16:00 bar close of the prior day) and its direction
    sess = out[(out["hhmm"] >= 930) & (out["hhmm"] < 1600)]
    daily = sess.groupby("date").agg(o=("open", "first"), c=("close", "last"))
    daily["prev_close"] = daily["c"].shift(1)
    daily["prev_dir"] = np.sign(daily["c"] - daily["o"]).shift(1)
    out = out.merge(daily[["prev_close", "prev_dir"]], left_on="date", right_index=True, how="left")
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
    if np.isnan(ema_a[i0]) or np.isnan(atr_a[i0]):
        return None

    if c[i0] > ema_a[i0] and p.allow_long:
        direction = 1
    elif c[i0] < ema_a[i0] and p.allow_short:
        direction = -1
    else:
        return None

    # ---- filters evaluated on the signal candle ----
    if p.skip_weekdays and int(day["weekday"].iloc[i0]) in {WEEKDAYS[w.strip()] for w in p.skip_weekdays.split(",") if w.strip() in WEEKDAYS}:
        return None
    if p.trend_filter == "slow_ema":
        slow = float(day["slow_ema"].iloc[i0])
        if np.isnan(slow) or (c[i0] - slow) * direction <= 0:
            return None
    elif p.trend_filter == "prev_day":
        pd_dir = day["prev_dir"].iloc[i0]
        if pd.isna(pd_dir) or pd_dir != direction:
            return None
    if p.max_gap_atr:
        pc = day["prev_close"].iloc[i0]
        if pd.isna(pc) or abs(o[i0] - pc) > p.max_gap_atr * atr_a[i0]:
            return None

    sig_high, sig_low = float(h[i0]), float(l[i0])
    risk = sig_high - sig_low if p.entry_mode == "breakout" else abs(float(c[i0]) - (sig_low if direction > 0 else sig_high))
    if risk <= 0:
        return None
    if p.max_risk_points and risk > p.max_risk_points:
        return None
    if p.min_risk_points and risk < p.min_risk_points:
        return None
    if p.min_risk_atr and risk < p.min_risk_atr * atr_a[i0]:
        return None
    if p.max_risk_atr and risk > p.max_risk_atr * atr_a[i0]:
        return None
    if p.min_body_r and abs(c[i0] - ema_a[i0]) / risk < p.min_body_r:
        return None

    swing_a = day["swing_low" if direction > 0 else "swing_high"].to_numpy(dtype=float)
    n = len(day)
    exit_hhmm = _hhmm(p.exit_time)

    # ---- entry ----
    j_entry = i0
    if p.entry_mode == "close":
        entry = float(c[i0])
        entry_time = _fmt(hhmm[i0])
    else:
        trigger = sig_high if direction > 0 else sig_low
        entry = None
        for j in range(i0 + 1, min(n, i0 + 1 + p.breakout_wait_bars)):
            if hhmm[j] >= exit_hhmm:
                return None
            if (direction > 0 and h[j] >= trigger) or (direction < 0 and l[j] <= trigger):
                entry = max(trigger, float(o[j])) if direction > 0 else min(trigger, float(o[j]))
                j_entry = j
                break
        if entry is None:
            return None
        entry_time = _fmt(hhmm[j_entry])
    stop0 = sig_low if direction > 0 else sig_high
    stop = stop0
    risk = abs(entry - stop)
    if risk <= 0:
        return None

    size = equity * (p.risk_pct / 100.0) / risk      # units of index per point
    if p.max_leverage:
        size = min(size, equity * p.max_leverage / entry)
    tp = entry + direction * p.tp_r * risk if p.tp_r else None
    ptp = entry + direction * p.partial_tp_r * risk if p.partial_tp_r else None
    open_frac = 1.0
    realised_points = 0.0          # points * fraction already banked by the partial
    exit_price, exit_reason, exit_time, bars_held = None, "", "", 0
    best, worst = 0.0, 0.0  # in R

    # in breakout mode the entry bar itself can hit the stop after triggering; check from the entry bar on
    start = j_entry if p.entry_mode == "breakout" else i0 + 1
    for j in range(start, n):
        if j > j_entry:
            bars_held += 1
        # 1) time exit at the open of the exit bar
        if hhmm[j] >= exit_hhmm:
            exit_price, exit_reason, exit_time = float(o[j]), "time", _fmt(hhmm[j])
            break
        # 2) stop hit inside the bar (gap through the stop fills at the open)
        if direction > 0 and l[j] <= stop:
            exit_price = min(stop, float(o[j])) if j > j_entry else stop
            exit_reason, exit_time = "stop" if stop < entry else "trail", _fmt(hhmm[j])
            break
        if direction < 0 and h[j] >= stop:
            exit_price = max(stop, float(o[j])) if j > j_entry else stop
            exit_reason, exit_time = "stop" if stop > entry else "trail", _fmt(hhmm[j])
            break
        # 3) targets (checked after the stop: conservative when both are inside one bar)
        if ptp is not None and ((direction > 0 and h[j] >= ptp) or (direction < 0 and l[j] <= ptp)):
            realised_points += (ptp - entry) * direction * p.partial_frac
            open_frac -= p.partial_frac
            ptp = None
            if p.breakeven_at_r == 0:  # a partial always protects the rest at breakeven
                stop = max(stop, entry) if direction > 0 else min(stop, entry)
        if tp is not None and ((direction > 0 and h[j] >= tp) or (direction < 0 and l[j] <= tp)):
            exit_price, exit_reason, exit_time = tp, "target", _fmt(hhmm[j])
            break
        # excursion bookkeeping
        fav = (h[j] - entry) if direction > 0 else (entry - l[j])
        adv = (entry - l[j]) if direction > 0 else (h[j] - entry)
        best, worst = max(best, fav / risk), max(worst, adv / risk)
        # 4) update the trail at bar close (only ever tightens)
        open_r = (c[j] - entry) * direction / risk
        if p.breakeven_at_r and open_r >= p.breakeven_at_r:
            stop = max(stop, entry) if direction > 0 else min(stop, entry)
        if open_r >= p.trail_after_r:
            lvl = None
            if p.trail_mode == "ema":
                lvl = ema_a[j]
            elif p.trail_mode == "swing":
                lvl = swing_a[j]
            elif p.trail_mode == "atr":
                lvl = c[j] - direction * p.atr_mult * atr_a[j]
            elif p.trail_mode == "chandelier":
                ext = h[j_entry:j + 1].max() if direction > 0 else l[j_entry:j + 1].min()
                lvl = ext - direction * p.atr_mult * atr_a[j]
            if lvl is not None and not np.isnan(lvl):
                stop = max(stop, lvl) if direction > 0 else min(stop, lvl)
    if exit_price is None:  # data ended mid-trade
        exit_price, exit_reason, exit_time = float(c[-1]), "eod", _fmt(hhmm[-1])

    pnl_points = realised_points + (exit_price - entry) * direction * open_frac - p.cost_points
    pnl = pnl_points * size
    return Trade(
        date=str(day["date"].iloc[i0]), direction="long" if direction > 0 else "short",
        entry_time=str(day["time"].iloc[j_entry]), exit_time=exit_time, entry=entry,
        stop=stop0, exit=exit_price, risk_points=risk,
        r_multiple=pnl_points / risk, pnl=pnl, equity_after=equity + pnl, bars_held=bars_held,
        exit_reason=exit_reason, mfe_r=best, mae_r=worst, ema_at_entry=float(ema_a[i0]), signal_close=float(c[i0]),
    )
