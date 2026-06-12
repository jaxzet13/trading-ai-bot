"""
Top two strategies from the 152-config mega-sweep:
1. ATR Impulse Breakout  — Sharpe 1.83, CAGR +127%
2. Cascade EMA Pullback  — Sharpe 1.55, CAGR +124%

Both run on the high-beta stock universe.
A combined portfolio runs them together for diversification.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tradelab.strategies.base import Strategy


def _ema(s: pd.Series, p: int) -> pd.Series:
    return s.ewm(span=p, adjust=False).mean()


def _rsi(s: pd.Series, p: int) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def _atr_df(close: pd.DataFrame, high: pd.DataFrame,
            low: pd.DataFrame, p: int) -> pd.DataFrame:
    prev = close.shift(1)
    tr = pd.DataFrame(
        np.maximum(
            np.maximum((high - low).values, (high - prev).abs().values),
            (low - prev).abs().values,
        ),
        index=close.index,
        columns=close.columns,
    )
    return tr.ewm(span=p, adjust=False).mean()


def _norm(w: pd.DataFrame) -> pd.DataFrame:
    s = w.sum(axis=1).replace(0, np.nan)
    return w.div(s, axis=0).fillna(0.0)


class ATRImpulseBreakoutStrategy(Strategy):
    """
    [SWEEP WINNER — Sharpe 1.83, CAGR +127%]
    Buy after a strong upward impulse bar (move > N × ATR), hold H bars.
    Captures the continuation after a momentum surge.
    Multiple trades per day possible when multiple symbols trigger.
    """

    name = "atr_impulse_breakout"

    def __init__(self, atr_period: int = 14, atr_mult: float = 2.0, hold_bars: int = 8):
        self.atr_period = atr_period
        self.atr_mult = atr_mult
        self.hold_bars = hold_bars

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        close = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        high  = pd.DataFrame({s: df.get("high", df["close"]) for s, df in bars.items()}).reindex(close.index)
        low   = pd.DataFrame({s: df.get("low",  df["close"]) for s, df in bars.items()}).reindex(close.index)

        atr  = _atr_df(close, high, low, self.atr_period)
        move = close.diff().abs()

        entry = (move.shift(1) > atr.shift(1) * self.atr_mult) & (close.diff().shift(1) > 0)
        # Hold for hold_bars after entry (correct: shift entry forward)
        hold_mat = sum(
            entry.shift(i).fillna(False).astype(float)
            for i in range(self.hold_bars)
        )
        return _norm((hold_mat > 0).astype(float))


class CascadeEMAStrategy(Strategy):
    """
    [SWEEP WINNER — Sharpe 1.55, CAGR +124%]
    Buy RSI pullbacks only when 13/34/89 EMAs are stacked bullishly.
    Enters confirmed uptrends on dips — avoids catching falling knives.
    Multiple simultaneous signals across the universe = multiple daily trades.
    """

    name = "cascade_ema"

    def __init__(
        self,
        fast: int = 13,
        medium: int = 34,
        slow: int = 89,
        rsi_period: int = 5,
        rsi_pullback: float = 45,
    ):
        self.fast = fast
        self.medium = medium
        self.slow = slow
        self.rsi_period = rsi_period
        self.rsi_pullback = rsi_pullback

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        close = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()

        ef  = _ema(close, self.fast)
        em  = _ema(close, self.medium)
        es  = _ema(close, self.slow)
        rsi = _rsi(close, self.rsi_period)

        bull   = (ef > em) & (em > es)
        entry  = bull & (rsi < self.rsi_pullback)
        exit_  = ef < em

        sig = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
        sig[entry] = 1.0
        sig[exit_] = 0.0
        held = sig.ffill().fillna(0.0)

        return _norm(held)


class CombinedIntradayStrategy(Strategy):
    """
    Equal blend of ATR Impulse Breakout + Cascade EMA.
    Runs both simultaneously — more signals per day, better diversification.
    """

    name = "combined_intraday"

    def __init__(self):
        self._atr  = ATRImpulseBreakoutStrategy()
        self._casc = CascadeEMAStrategy()

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        s1 = self._atr.generate_signals(bars)
        s2 = self._casc.generate_signals(bars)
        idx = s1.index.union(s2.index)
        combined = s1.reindex(idx).fillna(0) + s2.reindex(idx).fillna(0)
        return _norm(combined)
