from __future__ import annotations

"""
Crypto 1-2 hour day trading signals.

Research synthesis (deep-research, June 2026):
──────────────────────────────────────────────
1. MACD Cross + RSI Filter       — 73-77% combined win rate in backtests
   • MACD alone: 54-60% win rate; RSI alone: 40-60% (can be negative with std settings)
   • Combined improves substantially; confirmed by Gate.io 2026, QuantifiedStrategies
   • Use RSI(7) not RSI(14) on 1h crypto — faster, less lag on volatile assets
   • Overbought/oversold thresholds: 75/25 for crypto (not 70/30)

2. BB Squeeze Breakout            — 58% of runs profitable; ETH best (profit factor 1.59)
   • Use BB(20, 2.5 std) — wider bands reduce false signals in crypto
   • Bandwidth < 8% = squeeze; expansion + close above upper = breakout signal
   • REQUIRES volume 2.5x+ to be valid; without volume = false breakout

3. Volume Surge Momentum          — volume precedes price (academic consensus)
   • Threshold: 2x-2.5x 20-period average for entry, 1.5x for breakout confirmation
   • Volume spike + bullish bar + MACD positive = early momentum signal

REFUTED / NOT IMPLEMENTED:
   • BTC→ETH lead-lag (1h): "intraday traders can barely exploit this" — ScienceDirect
   • RSI(14, 70/30) alone: showed NEGATIVE returns in one rigorous study
   • Order flow imbalance: only predictive at seconds scale, not 1h

BEST TRADING WINDOW:
   • 12:00–22:00 UTC — US/Europe overlap peak liquidity (12-18 UTC) + extended
   • Worst: Sat/Sun low volume, avoid late Friday closes

All signals LONG ONLY — Alpaca paper does not support crypto short selling.
"""

import logging
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)

# ── Evidence-based parameters ────────────────────────────────────────────────
RSI_PERIOD = 7           # faster than 14; outperforms on 1h crypto (MC² Finance)
RSI_ENTRY_MIN = 32       # not already oversold/falling knife
RSI_ENTRY_MAX = 68       # not yet overbought
RSI_OB = 75              # overbought threshold (wider for crypto)
RSI_OS = 25              # oversold threshold

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

BB_PERIOD = 20
BB_STD = 2.5             # wider for crypto; reduces false breakouts
BB_SQUEEZE_BW = 0.08     # bandwidth < 8% = squeeze state
VOLUME_SURGE = 2.5       # 2.5x avg = surge (volume spike signal)
VOLUME_CONFIRM = 1.5     # 1.5x avg minimum for any breakout confirmation
EMA_PERIOD = 20          # price > EMA20 = uptrend context

# Trading window (UTC) — US-Europe overlap has highest volume and tightest spreads
WINDOW_START_UTC = 12
WINDOW_END_UTC = 22


# ── Indicator helpers ────────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return line, sig, hist


def _bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.5):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    bw = (upper - lower) / sma  # bandwidth as fraction of price
    return upper, sma, lower, bw


# ── Trading window guard ─────────────────────────────────────────────────────

def in_trading_window() -> bool:
    hour = datetime.now(timezone.utc).hour
    return WINDOW_START_UTC <= hour < WINDOW_END_UTC


# ── Signal generation ────────────────────────────────────────────────────────

def generate_signals(symbol: str, bars: pd.DataFrame) -> list[dict]:
    """
    Run all three strategies on 1h OHLCV bars.

    bars: yfinance DataFrame with columns Open, High, Low, Close, Volume
    Returns list of signal dicts, each with:
        symbol, strategy, conviction (0-2+), reason, stop_pct
    """
    if bars is None or len(bars) < 35:
        return []

    # Normalise column names (yfinance returns Title Case)
    cols = {c.lower(): c for c in bars.columns}
    close = bars[cols.get("close", "Close")]
    volume = bars[cols.get("volume", "Volume")]

    if close.dropna().__len__() < 30:
        return []

    # ── Compute indicators ───────────────────────────────────────
    rsi_s = _rsi(close, RSI_PERIOD)
    macd_line, macd_sig, macd_hist = _macd(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    bb_upper, bb_mid, bb_lower, bb_bw = _bollinger(close, BB_PERIOD, BB_STD)
    ema20 = close.ewm(span=EMA_PERIOD, adjust=False).mean()
    vol_avg = volume.rolling(20).mean()

    # Current (last closed bar) and previous bar values
    def _f(s, idx=-1):
        v = s.iloc[idx]
        return float(v) if not (v != v) else 0.0  # NaN → 0

    c0 = _f(close)
    c1 = _f(close, -2)
    rsi = _f(rsi_s)
    macd0 = _f(macd_line)
    macd1 = _f(macd_line, -2)
    msig0 = _f(macd_sig)
    msig1 = _f(macd_sig, -2)
    hist0 = _f(macd_hist)
    hist1 = _f(macd_hist, -2)
    bw0 = _f(bb_bw)
    bw1 = _f(bb_bw, -2)
    ub0 = _f(bb_upper)
    ema0 = _f(ema20)
    vol0 = _f(volume)
    vavg = _f(vol_avg)
    vol_ratio = vol0 / vavg if vavg > 0 else 0.0
    bar_chg = (c0 - c1) / c1 * 100 if c1 > 0 else 0.0

    signals: list[dict] = []

    # ── Strategy 1: MACD Cross + RSI Filter (primary) ───────────
    # MACD line crosses above signal line + RSI in healthy range + uptrend + volume
    macd_crossed_up = macd1 < msig1 and macd0 > msig0
    rsi_ok = RSI_ENTRY_MIN < rsi < RSI_ENTRY_MAX
    uptrend = c0 > ema0
    vol_ok = vol_ratio >= VOLUME_CONFIRM

    if macd_crossed_up and rsi_ok and uptrend and vol_ok:
        hist_range = float(macd_hist.abs().rolling(20).max().iloc[-1]) or 1e-9
        conv = min(2.0, 1.0 + abs(hist0) / hist_range)
        signals.append({
            "symbol": symbol,
            "strategy": "macd_cross",
            "conviction": round(conv, 2),
            "reason": (
                f"MACD bullish cross (hist={hist0:+.4f}), "
                f"RSI={rsi:.0f}, vol={vol_ratio:.1f}x, above EMA20"
            ),
            "stop_pct": 0.020,
            "target_pct": 0.035,
        })

    # ── Strategy 2: BB Squeeze Breakout (high conviction) ───────
    # Bandwidth was compressed → now expanding + price breaks upper band + volume surge
    was_squeezed = bw1 < BB_SQUEEZE_BW
    expanding = bw0 > bw1
    broke_upper = c0 > ub0
    big_vol = vol_ratio >= VOLUME_SURGE
    not_extreme_rsi = rsi < RSI_OB

    if was_squeezed and expanding and broke_upper and big_vol and not_extreme_rsi:
        vol_mult = min(vol_ratio / VOLUME_SURGE, 2.0)
        conv = 1.5 + 0.5 * vol_mult
        signals.append({
            "symbol": symbol,
            "strategy": "bb_squeeze",
            "conviction": round(conv, 2),
            "reason": (
                f"BB squeeze breakout, bw {bw1:.3f}→{bw0:.3f}, "
                f"vol={vol_ratio:.1f}x, RSI={rsi:.0f}"
            ),
            "stop_pct": 0.025,   # wider stop; squeeze moves can retrace then continue
            "target_pct": 0.050, # bigger target; squeeze breakouts often run
        })

    # ── Strategy 3: Volume Surge Momentum (early signal) ────────
    # Massive volume + strong bullish bar + MACD histogram rising
    big_bar = bar_chg > 0.4    # at least 0.4% up on this bar
    surge = vol_ratio >= VOLUME_SURGE
    hist_rising = hist0 > 0 and hist0 > hist1
    rsi_momentum = 38 < rsi < 72

    if big_bar and surge and hist_rising and rsi_momentum:
        conv = min(2.0, 1.0 + (vol_ratio - VOLUME_SURGE) * 0.2 + bar_chg * 0.08)
        signals.append({
            "symbol": symbol,
            "strategy": "vol_surge",
            "conviction": round(conv, 2),
            "reason": (
                f"Vol surge {vol_ratio:.1f}x, bar +{bar_chg:.1f}%, "
                f"MACD hist rising ({hist1:+.4f}→{hist0:+.4f}), RSI={rsi:.0f}"
            ),
            "stop_pct": 0.018,
            "target_pct": 0.030,
        })

    return signals


def fetch_hourly_bars(symbol: str, days: int = 30) -> pd.DataFrame | None:
    """Fetch 1h OHLCV bars via yfinance. Returns None on failure."""
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period=f"{days}d", interval="1h")
        if df.empty or len(df) < 35:
            return None
        return df
    except Exception as exc:
        logger.warning("Hourly bars failed for %s: %s", symbol, exc)
        return None


def scan_crypto(symbols: list[str]) -> list[dict]:
    """
    Fetch 1h bars for all symbols and run all strategies.
    Returns all signals sorted by conviction descending.
    """
    all_signals: list[dict] = []
    for sym in symbols:
        bars = fetch_hourly_bars(sym)
        if bars is None:
            logger.info("No 1h data for %s", sym)
            continue
        sigs = generate_signals(sym, bars)
        all_signals.extend(sigs)
        for s in sigs:
            logger.info(
                "SIGNAL %s %s conviction=%.2f  %s",
                sym, s["strategy"], s["conviction"], s["reason"],
            )
    all_signals.sort(key=lambda s: s["conviction"], reverse=True)
    return all_signals
