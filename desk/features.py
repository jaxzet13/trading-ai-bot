"""Session-aware day contexts for any instrument: session VWAP, opening range, Asian range, previous session levels."""
from __future__ import annotations

import numpy as np
import pandas as pd

from nyopen.data import load_m1, resample
from nyopen.strategy import atr, ema
from propbot.engine import Ctx

from .instruments import INSTRUMENTS

_CACHE: dict = {}


def bars(name: str, minutes: int = 5) -> pd.DataFrame:
    key = ("bars", name, minutes)
    if key not in _CACHE:
        _CACHE[key] = resample(load_m1(INSTRUMENTS[name].symbol), minutes)
    return _CACHE[key]


def build_days(name: str, session: tuple[int, int], or_minutes: int = 15, ema_fast: int = 20, ema_slow: int = 200, atr_len: int = 14) -> list[tuple[str, Ctx]]:
    key = ("days", name, session, or_minutes, ema_fast, ema_slow, atr_len)
    if key in _CACHE:
        return _CACHE[key]
    s0, s1 = session
    b = bars(name).copy()
    b["ema_fast"] = ema(b["close"], ema_fast)
    b["ema_slow"] = ema(b["close"], ema_slow)
    b["atr"] = atr(b, atr_len)
    t = b["time"]
    b["date"] = t.dt.date.astype(str)
    b["hhmm"] = (t.dt.hour * 100 + t.dt.minute).astype(int)
    # Asian range: 19:00 (previous NY day) to 02:59, keyed to the NY date it leads into
    asia_key = (t + pd.Timedelta(hours=5)).dt.date.astype(str)
    in_asia = (b.hhmm >= 1900) | (b.hhmm < 300)
    asia = b[in_asia].groupby(asia_key[in_asia]).agg(ah=("high", "max"), al=("low", "min"))
    out = []
    prev_high = prev_low = prev_close = np.nan
    or_end = (s0 // 100 * 60 + s0 % 100 + or_minutes)
    or_end = or_end // 60 * 100 + or_end % 60
    for date, g in b.groupby("date", sort=True):
        g = g.reset_index(drop=True)
        in_sess = ((g.hhmm >= s0) & (g.hhmm < s1)).to_numpy()
        if in_sess.sum() < 20:
            continue
        sess = g[in_sess]
        tp = ((g.high + g.low + g.close) / 3).to_numpy()
        vol = g.volume.to_numpy().copy()
        vol[~in_sess] = 0.0
        vol[in_sess] = np.maximum(vol[in_sess], 1e-9)
        cv, cpv = np.cumsum(vol), np.cumsum(tp * vol)
        vwap = np.where(cv > 0, cpv / np.maximum(cv, 1e-12), np.nan)
        orm = g[(g.hhmm >= s0) & (g.hhmm < or_end)]
        ctx = Ctx(o=g.open.to_numpy(float), h=g.high.to_numpy(float), l=g.low.to_numpy(float), c=g.close.to_numpy(float), v=g.volume.to_numpy(float),
                  hhmm=g.hhmm.to_numpy(), atr=g.atr.to_numpy(float), ema_fast=g.ema_fast.to_numpy(float), ema_slow=g.ema_slow.to_numpy(float), vwap=vwap,
                  or_high=float(orm.high.max()) if len(orm) else np.nan, or_low=float(orm.low.min()) if len(orm) else np.nan,
                  prev_high=prev_high, prev_low=prev_low, prev_close=prev_close, day_open=float(sess.open.iloc[0]))
        if date in asia.index:
            ctx.extra["asia_high"], ctx.extra["asia_low"] = float(asia.loc[date, "ah"]), float(asia.loc[date, "al"])
        out.append((date, ctx))
        prev_high, prev_low, prev_close = float(sess.high.max()), float(sess.low.min()), float(sess.close.iloc[-1])
    _CACHE[key] = out
    return out
