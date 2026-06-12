"""
15 intraday strategies — classic technical + original designs.
All work on any OHLCV DataFrame dict keyed by symbol.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from tradelab.strategies.base import Strategy


# ── helpers ────────────────────────────────────────────────────────────────

def _rsi(s: pd.Series, p: int) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))

def _atr(df: pd.DataFrame, p: int = 14) -> pd.Series:
    hi, lo, cl = df["high"], df["low"], df["close"]
    prev = cl.shift(1)
    tr = pd.concat([hi-lo, (hi-prev).abs(), (lo-prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()

def _ema(s: pd.Series, p: int) -> pd.Series:
    return s.ewm(span=p, adjust=False).mean()

def _bb(s: pd.Series, p: int = 20, k: float = 2.0):
    mid = s.rolling(p).mean()
    std = s.rolling(p).std()
    return mid - k*std, mid, mid + k*std

def _macd(s: pd.Series, fast=12, slow=26, sig=9):
    line = _ema(s, fast) - _ema(s, slow)
    signal = _ema(line, sig)
    return line, signal

def _normalize(targets: pd.DataFrame) -> pd.DataFrame:
    row_sums = targets.sum(axis=1).replace(0, np.nan)
    return targets.div(row_sums, axis=0).fillna(0.0)


# ── 1. Bollinger Band Mean Reversion ───────────────────────────────────────
class BollingerReversionStrategy(Strategy):
    """Buy at lower band, exit at midline."""
    name = "bb_reversion"
    def __init__(self, period=20, k=2.0): self.period, self.k = period, k
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            lo, mid, _ = _bb(closes[s], self.period, self.k)
            for i in range(self.period, len(closes)):
                d = closes.index[i]
                p = closes[s].iloc[i]
                if held[s]:
                    targets.loc[d, s] = 1.0
                    if p >= mid.iloc[i]: held[s] = False; targets.loc[d, s] = 0.0
                else:
                    if p <= lo.iloc[i]: held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 2. Bollinger + RSI Combo ────────────────────────────────────────────────
class BollingerRSIStrategy(Strategy):
    """Buy when price < lower BB AND RSI < threshold. Exit at midline."""
    name = "bb_rsi_combo"
    def __init__(self, bb_period=20, k=2.0, rsi_period=7, rsi_entry=35):
        self.bb_period, self.k = bb_period, k
        self.rsi_period, self.rsi_entry = rsi_period, rsi_entry
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            lo, mid, _ = _bb(closes[s], self.bb_period, self.k)
            rsi = _rsi(closes[s], self.rsi_period)
            for i in range(max(self.bb_period, self.rsi_period), len(closes)):
                d = closes.index[i]
                p = closes[s].iloc[i]
                if held[s]:
                    targets.loc[d, s] = 1.0
                    if p >= mid.iloc[i]: held[s] = False; targets.loc[d, s] = 0.0
                else:
                    if p <= lo.iloc[i] and rsi.iloc[i] < self.rsi_entry:
                        held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 3. VWAP Reversion ──────────────────────────────────────────────────────
class VWAPReversionStrategy(Strategy):
    """Buy when price is X% below its rolling VWAP proxy (volume-wtd avg)."""
    name = "vwap_reversion"
    def __init__(self, period=24, pct_below=0.015, pct_exit=0.005):
        self.period, self.pct_below, self.pct_exit = period, pct_below, pct_exit
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            vol = bars[s].get("volume", pd.Series(1.0, index=bars[s].index))
            tp = (bars[s]["high"] + bars[s]["low"] + bars[s]["close"]) / 3
            vwap = (tp * vol).rolling(self.period).sum() / vol.rolling(self.period).sum()
            vwap = vwap.reindex(closes.index)
            for i in range(self.period, len(closes)):
                d = closes.index[i]
                p = closes[s].iloc[i]
                v = vwap.iloc[i]
                if pd.isna(v): continue
                if held[s]:
                    targets.loc[d, s] = 1.0
                    if p >= v * (1 + self.pct_exit): held[s] = False; targets.loc[d, s] = 0.0
                else:
                    if p <= v * (1 - self.pct_below): held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 4. Donchian Breakout ───────────────────────────────────────────────────
class DonchianBreakoutStrategy(Strategy):
    """Buy new N-bar high, exit at N/2-bar low."""
    name = "donchian_breakout"
    def __init__(self, period=24):
        self.period = period
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            high_n = closes[s].rolling(self.period).max().shift(1)
            low_half = closes[s].rolling(self.period // 2).min().shift(1)
            for i in range(self.period, len(closes)):
                d = closes.index[i]
                p = closes[s].iloc[i]
                if held[s]:
                    targets.loc[d, s] = 1.0
                    if p <= low_half.iloc[i]: held[s] = False; targets.loc[d, s] = 0.0
                else:
                    if p > high_n.iloc[i]: held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 5. MACD Cross ──────────────────────────────────────────────────────────
class MACDCrossStrategy(Strategy):
    """Buy on MACD line crossing above signal, sell on cross below."""
    name = "macd_cross"
    def __init__(self, fast=8, slow=21, sig=5):
        self.fast, self.slow, self.sig = fast, slow, sig
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        for s in closes.columns:
            line, signal = _macd(closes[s], self.fast, self.slow, self.sig)
            hist = line - signal
            held = False
            for i in range(self.slow + self.sig, len(closes)):
                d = closes.index[i]
                if hist.iloc[i] > 0 and hist.iloc[i-1] <= 0:
                    held = True
                elif hist.iloc[i] < 0 and hist.iloc[i-1] >= 0:
                    held = False
                targets.loc[d, s] = 1.0 if held else 0.0
        return _normalize(targets)


# ── 6. Keltner Channel Reversion ───────────────────────────────────────────
class KeltnerReversionStrategy(Strategy):
    """Reversion to EMA using ATR bands instead of std-dev bands."""
    name = "keltner_reversion"
    def __init__(self, ema_period=20, atr_period=10, mult=2.0):
        self.ema_period, self.atr_period, self.mult = ema_period, atr_period, mult
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            ema = _ema(closes[s], self.ema_period)
            atr = _atr(bars[s].reindex(closes.index), self.atr_period)
            lo = ema - self.mult * atr
            for i in range(max(self.ema_period, self.atr_period), len(closes)):
                d = closes.index[i]
                p = closes[s].iloc[i]
                if held[s]:
                    targets.loc[d, s] = 1.0
                    if p >= ema.iloc[i]: held[s] = False; targets.loc[d, s] = 0.0
                else:
                    if p <= lo.iloc[i]: held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 7. Stochastic RSI ──────────────────────────────────────────────────────
class StochRSIStrategy(Strategy):
    """Stochastic applied to RSI values. Buy when StochRSI < 10, exit > 80."""
    name = "stoch_rsi"
    def __init__(self, rsi_period=14, stoch_period=14, entry=10, exit_=80):
        self.rsi_period, self.stoch_period = rsi_period, stoch_period
        self.entry, self.exit_ = entry, exit_
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            rsi = _rsi(closes[s], self.rsi_period)
            lo = rsi.rolling(self.stoch_period).min()
            hi = rsi.rolling(self.stoch_period).max()
            stochrsi = (rsi - lo) / (hi - lo + 1e-9) * 100
            for i in range(self.rsi_period + self.stoch_period, len(closes)):
                d = closes.index[i]
                if held[s]:
                    targets.loc[d, s] = 1.0
                    if stochrsi.iloc[i] > self.exit_: held[s] = False; targets.loc[d, s] = 0.0
                else:
                    if stochrsi.iloc[i] < self.entry: held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 8. Gap Fade ────────────────────────────────────────────────────────────
class GapFadeStrategy(Strategy):
    """
    [Original] When price spikes up > gap_pct in one bar (panic buying),
    fade it (short proxy: go flat next bar) OR buy when spike is down (panic sell fade).
    We implement the buy-side: buy after a large down spike.
    """
    name = "gap_fade"
    def __init__(self, gap_pct=0.025, hold_bars=4):
        self.gap_pct, self.hold_bars = gap_pct, hold_bars
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        for s in closes.columns:
            ret = closes[s].pct_change()
            hold_count = 0
            for i in range(2, len(closes)):
                d = closes.index[i]
                if hold_count > 0:
                    targets.loc[d, s] = 1.0
                    hold_count -= 1
                elif ret.iloc[i-1] <= -self.gap_pct:
                    targets.loc[d, s] = 1.0
                    hold_count = self.hold_bars - 1
        return _normalize(targets)


# ── 9. Volatility-Gated Mean Reversion (Original) ─────────────────────────
class VolGatedMRStrategy(Strategy):
    """
    [Original] RSI mean reversion ONLY when hourly ATR is above its rolling
    average — i.e. only trade when moves are large enough to pay fees.
    High vol sessions = bigger bounces = fee is smaller % of the move.
    """
    name = "vol_gated_mr"
    def __init__(self, rsi_period=5, entry=25, exit_=60,
                 atr_period=14, vol_mult=1.2):
        self.rsi_period, self.entry, self.exit_ = rsi_period, entry, exit_
        self.atr_period, self.vol_mult = atr_period, vol_mult
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            rsi = _rsi(closes[s], self.rsi_period)
            atr = _atr(bars[s].reindex(closes.index), self.atr_period)
            avg_atr = atr.rolling(5 * 24).mean()
            for i in range(max(self.rsi_period, self.atr_period, 120), len(closes)):
                d = closes.index[i]
                high_vol = atr.iloc[i] > avg_atr.iloc[i] * self.vol_mult
                if held[s]:
                    targets.loc[d, s] = 1.0
                    if rsi.iloc[i] > self.exit_: held[s] = False; targets.loc[d, s] = 0.0
                else:
                    if high_vol and rsi.iloc[i-1] < self.entry:
                        held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 10. Cascade EMA Alignment (Original) ──────────────────────────────────
class CascadeEMAStrategy(Strategy):
    """
    [Original] Buy when fast EMA > medium EMA > slow EMA (full bull cascade)
    AND RSI pulls back. Rides confirmed trends, enters on pullbacks.
    Exit when fast drops below medium.
    """
    name = "cascade_ema"
    def __init__(self, fast=8, medium=21, slow=55, rsi_period=5, rsi_pull=45):
        self.fast, self.medium, self.slow = fast, medium, slow
        self.rsi_period, self.rsi_pull = rsi_period, rsi_pull
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            ef = _ema(closes[s], self.fast)
            em = _ema(closes[s], self.medium)
            es = _ema(closes[s], self.slow)
            rsi = _rsi(closes[s], self.rsi_period)
            for i in range(self.slow + 5, len(closes)):
                d = closes.index[i]
                cascade = ef.iloc[i] > em.iloc[i] > es.iloc[i]
                if held[s]:
                    targets.loc[d, s] = 1.0
                    if ef.iloc[i] < em.iloc[i]: held[s] = False; targets.loc[d, s] = 0.0
                else:
                    if cascade and rsi.iloc[i] < self.rsi_pull:
                        held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 11. Regime Switcher (Original) ────────────────────────────────────────
class RegimeSwitcherStrategy(Strategy):
    """
    [Original] Uses ADX to detect trending vs ranging. In trending (ADX>25):
    momentum. In ranging (ADX<20): mean reversion. Switches between them.
    """
    name = "regime_switcher"
    def __init__(self, adx_period=14, adx_trend=25, adx_range=20,
                 mr_rsi=5, mr_entry=30, mr_exit=60,
                 mom_lookback=12):
        self.adx_period = adx_period
        self.adx_trend, self.adx_range = adx_trend, adx_range
        self.mr_rsi, self.mr_entry, self.mr_exit = mr_rsi, mr_entry, mr_exit
        self.mom_lookback = mom_lookback

    def _adx(self, df: pd.DataFrame, p: int) -> pd.Series:
        hi, lo, cl = df["high"], df["low"], df["close"]
        up = hi.diff().clip(lower=0)
        dn = (-lo.diff()).clip(lower=0)
        up = up.where(up > dn, 0)
        dn = dn.where(dn > up, 0)
        tr = _atr(df, 1)
        atr_p = tr.ewm(span=p, adjust=False).mean()
        dip = (up.ewm(span=p, adjust=False).mean() / atr_p * 100)
        dim = (dn.ewm(span=p, adjust=False).mean() / atr_p * 100)
        dx = ((dip - dim).abs() / (dip + dim + 1e-9) * 100)
        return dx.ewm(span=p, adjust=False).mean()

    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            rsi = _rsi(closes[s], self.mr_rsi)
            adx = self._adx(bars[s].reindex(closes.index), self.adx_period)
            mom_ret = closes[s].pct_change(self.mom_lookback)
            for i in range(max(self.adx_period*2, self.mr_rsi, self.mom_lookback) + 5, len(closes)):
                d = closes.index[i]
                adx_val = adx.iloc[i]
                if pd.isna(adx_val): continue
                if held[s]:
                    targets.loc[d, s] = 1.0
                    # exit: MR exit if ranging, momentum reversal if trending
                    if adx_val < self.adx_range and rsi.iloc[i] > self.mr_exit:
                        held[s] = False; targets.loc[d, s] = 0.0
                    elif adx_val > self.adx_trend and mom_ret.iloc[i] < 0:
                        held[s] = False; targets.loc[d, s] = 0.0
                else:
                    if adx_val < self.adx_range and rsi.iloc[i-1] < self.mr_entry:
                        held[s] = True; targets.loc[d, s] = 1.0
                    elif adx_val > self.adx_trend and mom_ret.iloc[i] > 0 and mom_ret.iloc[i-1] <= 0:
                        held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 12. Triple Confluence (Original) ──────────────────────────────────────
class TripleConfluenceStrategy(Strategy):
    """
    [Original] Require 3 independent signals to align before entering:
    RSI oversold + price below lower BB + price below VWAP proxy.
    High conviction entries only — fewer trades but better quality.
    """
    name = "triple_confluence"
    def __init__(self, rsi_period=7, rsi_entry=30, bb_period=20, k=2.0,
                 vwap_period=24, rsi_exit=60):
        self.rsi_period, self.rsi_entry = rsi_period, rsi_entry
        self.bb_period, self.k = bb_period, k
        self.vwap_period, self.rsi_exit = vwap_period, rsi_exit
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        held = {s: False for s in closes.columns}
        for s in closes.columns:
            rsi = _rsi(closes[s], self.rsi_period)
            lo_bb, mid_bb, _ = _bb(closes[s], self.bb_period, self.k)
            vol = bars[s].get("volume", pd.Series(1.0, index=bars[s].index))
            tp = (bars[s]["high"] + bars[s]["low"] + bars[s]["close"]) / 3
            vwap = (tp * vol).rolling(self.vwap_period).sum() / vol.rolling(self.vwap_period).sum()
            vwap = vwap.reindex(closes.index)
            lookback = max(self.rsi_period, self.bb_period, self.vwap_period)
            for i in range(lookback, len(closes)):
                d = closes.index[i]
                p = closes[s].iloc[i]
                v = vwap.iloc[i]
                if pd.isna(v) or pd.isna(lo_bb.iloc[i]): continue
                if held[s]:
                    targets.loc[d, s] = 1.0
                    if rsi.iloc[i] > self.rsi_exit: held[s] = False; targets.loc[d, s] = 0.0
                else:
                    below_bb = p < lo_bb.iloc[i]
                    below_vwap = p < v * 0.99
                    rsi_os = rsi.iloc[i-1] < self.rsi_entry
                    if below_bb and below_vwap and rsi_os:
                        held[s] = True; targets.loc[d, s] = 1.0
        return _normalize(targets)


# ── 13. ATR Momentum Breakout (Original) ──────────────────────────────────
class ATRBreakoutStrategy(Strategy):
    """
    [Original] Buy when price moves > N * ATR in one bar (strong impulse move).
    Hold for a fixed number of bars then exit. Captures impulsive momentum runs.
    """
    name = "atr_breakout"
    def __init__(self, atr_period=14, atr_mult=1.5, hold_bars=6):
        self.atr_period, self.atr_mult, self.hold_bars = atr_period, atr_mult, hold_bars
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        for s in closes.columns:
            atr = _atr(bars[s].reindex(closes.index), self.atr_period)
            price_move = closes[s].diff().abs()
            ret_1bar = closes[s].pct_change()
            hold_count = 0
            for i in range(self.atr_period + 1, len(closes)):
                d = closes.index[i]
                if hold_count > 0:
                    targets.loc[d, s] = 1.0
                    hold_count -= 1
                elif (price_move.iloc[i-1] > atr.iloc[i-1] * self.atr_mult
                      and ret_1bar.iloc[i-1] > 0):
                    targets.loc[d, s] = 1.0
                    hold_count = self.hold_bars - 1
        return _normalize(targets)


# ── 14. Pairs Spread Mean Reversion (BTC/ETH) ─────────────────────────────
class PairsSpreadStrategy(Strategy):
    """
    [Original] Trade the BTC-ETH price ratio. Buy the laggard when spread
    deviates 2+ std from its rolling mean (stat-arb style).
    Returns a signal where laggard gets weight 1, leader gets 0.
    """
    name = "pairs_spread"
    def __init__(self, period=48, z_entry=2.0, z_exit=0.5,
                 asset_a="BTC-USD", asset_b="ETH-USD"):
        self.period = period
        self.z_entry, self.z_exit = z_entry, z_exit
        self.asset_a, self.asset_b = asset_a, asset_b

    def generate_signals(self, bars):
        if self.asset_a not in bars or self.asset_b not in bars:
            cols = list(bars.keys())[:2] if len(bars) >= 2 else list(bars.keys())
            if len(cols) < 2:
                return pd.DataFrame(0.0, index=next(iter(bars.values())).index, columns=list(bars.keys()))
            self.asset_a, self.asset_b = cols[0], cols[1]

        ca = bars[self.asset_a]["close"]
        cb = bars[self.asset_b]["close"]
        idx = ca.index.intersection(cb.index)
        ca, cb = ca.loc[idx], cb.loc[idx]

        log_spread = np.log(ca / cb)
        mean = log_spread.rolling(self.period).mean()
        std = log_spread.rolling(self.period).std()
        z = (log_spread - mean) / (std + 1e-9)

        all_cols = list(bars.keys())
        targets = pd.DataFrame(0.0, index=idx, columns=all_cols)

        held_a, held_b = False, False
        for i in range(self.period, len(idx)):
            d = idx[i]
            zv = z.iloc[i]
            if pd.isna(zv): continue
            # z > z_entry: A is expensive vs B → buy B
            if not held_b and zv > self.z_entry:
                held_b = True; held_a = False
            elif not held_a and zv < -self.z_entry:
                held_a = True; held_b = False
            if held_b and abs(zv) < self.z_exit:
                held_b = False
            if held_a and abs(zv) < self.z_exit:
                held_a = False
            if held_a and self.asset_a in targets.columns:
                targets.loc[d, self.asset_a] = 1.0
            if held_b and self.asset_b in targets.columns:
                targets.loc[d, self.asset_b] = 1.0

        return _normalize(targets)


# ── 15. Supertrend (Classic) ───────────────────────────────────────────────
class SupertrendStrategy(Strategy):
    """Supertrend indicator — uses ATR to define dynamic support/resistance."""
    name = "supertrend"
    def __init__(self, atr_period=10, mult=3.0):
        self.atr_period, self.mult = atr_period, mult
    def generate_signals(self, bars):
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        for s in closes.columns:
            df_s = bars[s].reindex(closes.index)
            hl2 = (df_s["high"] + df_s["low"]) / 2
            atr = _atr(df_s, self.atr_period)
            upper_basic = hl2 + self.mult * atr
            lower_basic = hl2 - self.mult * atr
            upper = upper_basic.copy(); lower = lower_basic.copy()
            trend = pd.Series(1, index=closes.index)
            cl = closes[s]
            for i in range(1, len(closes)):
                upper.iloc[i] = upper_basic.iloc[i] if (upper_basic.iloc[i] < upper.iloc[i-1] or cl.iloc[i-1] > upper.iloc[i-1]) else upper.iloc[i-1]
                lower.iloc[i] = lower_basic.iloc[i] if (lower_basic.iloc[i] > lower.iloc[i-1] or cl.iloc[i-1] < lower.iloc[i-1]) else lower.iloc[i-1]
                if trend.iloc[i-1] == -1 and cl.iloc[i] > upper.iloc[i-1]:
                    trend.iloc[i] = 1
                elif trend.iloc[i-1] == 1 and cl.iloc[i] < lower.iloc[i-1]:
                    trend.iloc[i] = -1
                else:
                    trend.iloc[i] = trend.iloc[i-1]
            targets[s] = (trend == 1).astype(float)
        return _normalize(targets)
