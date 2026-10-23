"""Session features for the prop-firm strategies: VWAP, opening range, previous-day levels."""
from __future__ import annotations

import numpy as np
import pandas as pd

from nyopen.data import load_m1, resample
from nyopen.strategy import atr, ema

from .engine import Ctx

_CACHE: dict = {}


def bars_5m() -> pd.DataFrame:
    if "5m" not in _CACHE:
        _CACHE["5m"] = resample(load_m1(), 5)
    return _CACHE["5m"]


def build_days(ema_fast: int = 20, ema_slow: int = 200, atr_len: int = 14, or_minutes: int = 15) -> list[tuple[str, Ctx]]:
    """Return [(date, Ctx)] for every session, with all features precomputed."""
    key = ("days", ema_fast, ema_slow, atr_len, or_minutes)
    if key in _CACHE:
        return _CACHE[key]
    b = bars_5m().copy()
    b["ema_fast"] = ema(b["close"], ema_fast)
    b["ema_slow"] = ema(b["close"], ema_slow)
    b["atr"] = atr(b, atr_len)
    t = b["time"]
    b["date"] = t.dt.date.astype(str)
    b["hhmm"] = (t.dt.hour * 100 + t.dt.minute).astype(int)
    out = []
    prev_high = prev_low = prev_close = np.nan
    for date, g in b.groupby("date", sort=True):
        sess = g[(g.hhmm >= 930) & (g.hhmm < 1600)]
        if len(sess) < 30:
            continue
        g = g.reset_index(drop=True)
        in_sess = ((g.hhmm >= 930) & (g.hhmm < 1600)).to_numpy()
        tp = ((g.high + g.low + g.close) / 3).to_numpy()
        vol = g.volume.to_numpy().copy()
        vol[~in_sess] = 0.0
        cum_v = np.cumsum(vol)
        cum_pv = np.cumsum(tp * vol)
        vwap = np.where(cum_v > 0, cum_pv / np.maximum(cum_v, 1e-9), np.nan)
        orm = g[(g.hhmm >= 930) & (g.hhmm < 930 + or_minutes)]
        ctx = Ctx(o=g.open.to_numpy(float), h=g.high.to_numpy(float), l=g.low.to_numpy(float), c=g.close.to_numpy(float), v=g.volume.to_numpy(float),
                  hhmm=g.hhmm.to_numpy(), atr=g.atr.to_numpy(float), ema_fast=g.ema_fast.to_numpy(float), ema_slow=g.ema_slow.to_numpy(float), vwap=vwap,
                  or_high=float(orm.high.max()) if len(orm) else np.nan, or_low=float(orm.low.min()) if len(orm) else np.nan,
                  prev_high=prev_high, prev_low=prev_low, prev_close=prev_close, day_open=float(sess.open.iloc[0]))
        out.append((date, ctx))
        prev_high, prev_low, prev_close = float(sess.high.max()), float(sess.low.min()), float(sess.close.iloc[-1])
    _CACHE[key] = out
    return out
