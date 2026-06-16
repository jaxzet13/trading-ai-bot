from __future__ import annotations

"""
5-minute intraday signal engine — long AND short.

Patterns (evidence-based for intraday 5m day trading):

1. EMA 9/21 Cross — trend direction signal
   Golden cross (9 > 21): BUY / close shorts
   Death cross  (9 < 21): SHORT / close longs
   Filtered by RSI direction and volume confirmation.

2. VWAP Cross + Momentum — dynamic S/R level
   Price crosses above VWAP + EMA uptrend → BUY
   Price crosses below VWAP + EMA downtrend → SHORT
   VWAP acts as the strongest magnet in intraday price action.

3. 3-Bar Momentum Continuation — pattern + volume surge
   3 consecutive bullish bars (close>open) + volume ↑ + EMA aligned → BUY
   3 consecutive bearish bars + volume ↑ + EMA aligned → SHORT
   High-probability when the move is confirmed by expanding volume.

4. Engulfing Candle — reversal signal at extremes
   Bullish engulfing (big green bar engulfs prior red bar) + RSI <40 → BUY
   Bearish engulfing (big red bar engulfs prior green bar) + RSI >60 → SHORT

Crypto: LONG signals only (Alpaca paper cannot short crypto).
Stocks: LONG + SHORT signals.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Parameters ───────────────────────────────────────────────────────────────
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 7
VWAP_PERIOD = 40        # rolling 40-bar VWAP ≈ last 3.3 hours on 5m
VOLUME_CONFIRM = 1.4    # 1.4× avg volume minimum for any signal
VOLUME_SURGE = 2.2      # 2.2× avg for momentum / engulfing signals
RSI_LONG_MAX = 65       # don't buy overbought
RSI_SHORT_MIN = 35      # don't short oversold


# ── Indicator helpers ────────────────────────────────────────────────────────

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 7) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    ag = gain.ewm(alpha=1 / period, adjust=False).mean()
    al = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = ag / al.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)


def _vwap(bars: pd.DataFrame, period: int = 40) -> pd.Series:
    """Rolling VWAP over last `period` bars."""
    cols = {c.lower(): c for c in bars.columns}
    h = bars[cols.get("high", "High")]
    l = bars[cols.get("low", "Low")]
    c = bars[cols.get("close", "Close")]
    v = bars[cols.get("volume", "Volume")]
    tp = (h + l + c) / 3
    return (tp * v).rolling(period).sum() / v.rolling(period).sum()


def fetch_5m_bars(symbol: str, days: int = 3) -> Optional[pd.DataFrame]:
    """
    Fetch 5-minute OHLCV bars via yfinance.
    days=3 gives ~3 days of 5m bars (plenty for all indicators).
    """
    try:
        import yfinance as yf
        period = f"{days}d"
        df = yf.Ticker(symbol).history(period=period, interval="5m")
        if df.empty or len(df) < 25:
            return None
        return df
    except Exception as exc:
        logger.warning("5m bars failed for %s: %s", symbol, exc)
        return None


# ── Signal generation ────────────────────────────────────────────────────────

def generate_5m_signals(
    symbol: str,
    bars: pd.DataFrame,
    is_crypto: bool = False,
) -> list[dict]:
    """
    Run all 4 patterns on 5m bars.
    is_crypto=True → only returns BUY signals.
    Returns list of signal dicts: {symbol, side, strategy, conviction, reason, stop_pct, target_pct}
    """
    if bars is None or len(bars) < 25:
        return []

    cols = {c.lower(): c for c in bars.columns}
    close = bars[cols.get("close", "Close")]
    open_ = bars[cols.get("open", "Open")]
    high = bars[cols.get("high", "High")]
    low = bars[cols.get("low", "Low")]
    volume = bars[cols.get("volume", "Volume")]

    ema_fast = _ema(close, EMA_FAST)
    ema_slow = _ema(close, EMA_SLOW)
    rsi_s = _rsi(close, RSI_PERIOD)
    vwap_s = _vwap(bars, VWAP_PERIOD)
    vol_avg = volume.rolling(20).mean()

    def _f(s, i=-1):
        v = s.iloc[i]
        return float(v) if v == v else 0.0

    c0, c1 = _f(close), _f(close, -2)
    o0, o1 = _f(open_), _f(open_, -2)
    h0 = _f(high)
    l0 = _f(low)
    ef0, ef1 = _f(ema_fast), _f(ema_fast, -2)
    es0, es1 = _f(ema_slow), _f(ema_slow, -2)
    rsi = _f(rsi_s)
    rsi1 = _f(rsi_s, -2)
    vw0 = _f(vwap_s)
    vw1 = _f(vwap_s, -2)
    vol0 = _f(volume)
    vavg = _f(vol_avg)
    vol_ratio = vol0 / vavg if vavg > 1 else 0.0

    # Bar direction helpers
    def _bull(i): return _f(close, i) > _f(open_, i)
    def _bear(i): return _f(close, i) < _f(open_, i)

    signals: list[dict] = []

    # ── 1. EMA 9/21 Cross ────────────────────────────────────────
    ema_bullish_cross = ef1 < es1 and ef0 >= es0   # just crossed up
    ema_bearish_cross = ef1 > es1 and ef0 <= es0   # just crossed down
    vol_ok = vol_ratio >= VOLUME_CONFIRM

    if ema_bullish_cross and rsi < RSI_LONG_MAX and vol_ok:
        gap = abs(ef0 - es0) / es0 * 100   # how decisively it crossed
        conv = min(2.0, 1.0 + gap * 10 + (vol_ratio - VOLUME_CONFIRM) * 0.3)
        signals.append({
            "symbol": symbol, "side": "buy", "strategy": "ema_cross",
            "conviction": round(conv, 2),
            "reason": f"EMA 9/21 golden cross, RSI={rsi:.0f}, vol={vol_ratio:.1f}x",
            "stop_pct": 0.008, "target_pct": 0.015,
        })

    if not is_crypto and ema_bearish_cross and rsi > RSI_SHORT_MIN and vol_ok:
        gap = abs(ef0 - es0) / es0 * 100
        conv = min(2.0, 1.0 + gap * 10 + (vol_ratio - VOLUME_CONFIRM) * 0.3)
        signals.append({
            "symbol": symbol, "side": "sell", "strategy": "ema_cross",
            "conviction": round(conv, 2),
            "reason": f"EMA 9/21 death cross, RSI={rsi:.0f}, vol={vol_ratio:.1f}x",
            "stop_pct": 0.008, "target_pct": 0.015,
        })

    # ── 2. VWAP Cross + Momentum ─────────────────────────────────
    vwap_cross_up = c1 < vw1 and c0 >= vw0
    vwap_cross_dn = c1 > vw1 and c0 <= vw0
    ema_uptrend = ef0 > es0
    ema_dntrend = ef0 < es0
    rsi_rising = rsi > rsi1
    rsi_falling = rsi < rsi1

    if vwap_cross_up and ema_uptrend and rsi_rising and rsi < RSI_LONG_MAX and vol_ok:
        conv = min(2.0, 1.2 + (vol_ratio - VOLUME_CONFIRM) * 0.4)
        signals.append({
            "symbol": symbol, "side": "buy", "strategy": "vwap_cross",
            "conviction": round(conv, 2),
            "reason": f"Price crossed above VWAP, EMA uptrend, RSI={rsi:.0f} rising, vol={vol_ratio:.1f}x",
            "stop_pct": 0.007, "target_pct": 0.014,
        })

    if not is_crypto and vwap_cross_dn and ema_dntrend and rsi_falling and rsi > RSI_SHORT_MIN and vol_ok:
        conv = min(2.0, 1.2 + (vol_ratio - VOLUME_CONFIRM) * 0.4)
        signals.append({
            "symbol": symbol, "side": "sell", "strategy": "vwap_cross",
            "conviction": round(conv, 2),
            "reason": f"Price crossed below VWAP, EMA downtrend, RSI={rsi:.0f} falling, vol={vol_ratio:.1f}x",
            "stop_pct": 0.007, "target_pct": 0.014,
        })

    # ── 3. 3-Bar Momentum Continuation ───────────────────────────
    three_bull = _bull(-1) and _bull(-2) and _bull(-3)
    three_bear = _bear(-1) and _bear(-2) and _bear(-3)
    big_vol = vol_ratio >= VOLUME_SURGE

    if three_bull and ema_uptrend and big_vol and rsi < RSI_LONG_MAX:
        conv = min(2.2, 1.3 + (vol_ratio - VOLUME_SURGE) * 0.2)
        signals.append({
            "symbol": symbol, "side": "buy", "strategy": "momentum_3bar",
            "conviction": round(conv, 2),
            "reason": f"3 bullish bars, EMA uptrend, vol={vol_ratio:.1f}x surge, RSI={rsi:.0f}",
            "stop_pct": 0.010, "target_pct": 0.018,
        })

    if not is_crypto and three_bear and ema_dntrend and big_vol and rsi > RSI_SHORT_MIN:
        conv = min(2.2, 1.3 + (vol_ratio - VOLUME_SURGE) * 0.2)
        signals.append({
            "symbol": symbol, "side": "sell", "strategy": "momentum_3bar",
            "conviction": round(conv, 2),
            "reason": f"3 bearish bars, EMA downtrend, vol={vol_ratio:.1f}x surge, RSI={rsi:.0f}",
            "stop_pct": 0.010, "target_pct": 0.018,
        })

    # ── 4. Engulfing Candle Reversal ─────────────────────────────
    # Bullish: current big green bar fully engulfs prior red bar + oversold
    body0 = abs(c0 - o0)
    body1 = abs(c1 - o1)
    bull_engulf = (
        c0 > o0 and c1 < o1  # current bullish, prior bearish
        and c0 > o1 and o0 < c1  # current engulfs prior
        and body0 > body1 * 1.2   # meaningfully bigger
    )
    bear_engulf = (
        c0 < o0 and c1 > o1
        and c0 < o1 and o0 > c1
        and body0 > body1 * 1.2
    )

    if bull_engulf and rsi < 42 and big_vol:
        conv = min(2.0, 1.4 + (42 - rsi) * 0.03)
        signals.append({
            "symbol": symbol, "side": "buy", "strategy": "engulfing",
            "conviction": round(conv, 2),
            "reason": f"Bullish engulfing at RSI={rsi:.0f} (oversold), vol={vol_ratio:.1f}x",
            "stop_pct": 0.009, "target_pct": 0.016,
        })

    if not is_crypto and bear_engulf and rsi > 58 and big_vol:
        conv = min(2.0, 1.4 + (rsi - 58) * 0.03)
        signals.append({
            "symbol": symbol, "side": "sell", "strategy": "engulfing",
            "conviction": round(conv, 2),
            "reason": f"Bearish engulfing at RSI={rsi:.0f} (overbought), vol={vol_ratio:.1f}x",
            "stop_pct": 0.009, "target_pct": 0.016,
        })

    return signals


def is_market_open() -> bool:
    """True during NYSE regular hours (Mon-Fri 9:30-16:00 ET)."""
    try:
        import pytz
        et = pytz.timezone("America/New_York")
        now = datetime.now(et)
        if now.weekday() >= 5:
            return False
        t = now.time()
        from datetime import time
        return time(9, 30) <= t < time(16, 0)
    except Exception:
        # Fallback: check UTC (ET = UTC-4 or UTC-5)
        utc = datetime.now(timezone.utc)
        if utc.weekday() >= 5:
            return False
        h = utc.hour
        return 13 <= h < 20  # approximate
