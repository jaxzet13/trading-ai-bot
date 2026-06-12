"""
Mega sweep: all 15+ strategies on crypto + high-beta stocks, hourly bars.
Sorted by days hitting >= 3% gain. Uses real Alpaca crypto fee 0.25%/side.
"""
from __future__ import annotations
import sys, math
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from tradelab.backtest.runner import _simulate_portfolio, _calc_drawdown_series
from tradelab.strategies.intraday import (
    BollingerReversionStrategy, BollingerRSIStrategy, VWAPReversionStrategy,
    DonchianBreakoutStrategy, MACDCrossStrategy, KeltnerReversionStrategy,
    StochRSIStrategy, GapFadeStrategy, VolGatedMRStrategy, CascadeEMAStrategy,
    RegimeSwitcherStrategy, TripleConfluenceStrategy, ATRBreakoutStrategy,
    PairsSpreadStrategy, SupertrendStrategy,
)
from tradelab.strategies.crypto import CryptoMeanReversionStrategy, CryptoMomentumStrategy
from tradelab.strategies.mean_reversion import MeanReversionStrategy
from tradelab.strategies.momentum import MomentumStrategy

FEE = 0.0025       # Alpaca crypto taker 0.25%/side
STOCK_FEE = 0.0    # Alpaca stocks $0 commission
INIT = 100_000.0

# ─── fetch data ────────────────────────────────────────────────────────────
CRYPTO = ["BTC-USD","ETH-USD","SOL-USD","AVAX-USD","LINK-USD","DOGE-USD","BNB-USD","ADA-USD"]
STOCKS = ["TSLA","NVDA","AMD","MSTR","COIN","SMCI","PLTR","APP","MARA","RIOT"]

print("Fetching 729-day hourly crypto bars...")
raw_c = yf.download(CRYPTO, period="729d", interval="1h", auto_adjust=True, progress=False)
close_c_raw = raw_c["Close"].dropna(how="all")
bars_crypto: dict[str, pd.DataFrame] = {}
for s in CRYPTO:
    if s in close_c_raw.columns:
        cl = close_c_raw[s].dropna()
        # build mini OHLCV from Close only (for indicators)
        bars_crypto[s] = pd.DataFrame({
            "open": cl, "high": cl*1.001, "low": cl*0.999,
            "close": cl, "volume": pd.Series(1e6, index=cl.index)
        })
print(f"  Crypto: {len(bars_crypto)} coins, {len(close_c_raw)} bars")

print("Fetching 729-day hourly stock bars...")
raw_s = yf.download(STOCKS, period="729d", interval="1h", auto_adjust=True, progress=False)
close_s_raw = raw_s["Close"].dropna(how="all")
bars_stocks: dict[str, pd.DataFrame] = {}
for s in STOCKS:
    if s in close_s_raw.columns:
        cl = close_s_raw[s].dropna()
        bars_stocks[s] = pd.DataFrame({
            "open": cl, "high": cl*1.001, "low": cl*0.999,
            "close": cl, "volume": pd.Series(1e6, index=cl.index)
        })
print(f"  Stocks: {len(bars_stocks)} symbols, {len(close_s_raw)} bars")

# ─── evaluation ────────────────────────────────────────────────────────────
results = []

def evaluate(name: str, targets: pd.DataFrame, close_df: pd.DataFrame,
             fee: float, kelly: float = 1.0):
    t = targets.reindex(close_df.index).fillna(0.0)
    equity, trades = _simulate_portfolio(close_df, t, slippage=fee, kelly_fraction=kelly)
    equity = equity.dropna()
    if len(equity) < 200 or len(trades) < 5:
        return
    daily_eq = equity.resample("D").last().dropna()
    if len(daily_eq) < 30: return
    daily_ret = daily_eq.pct_change().dropna()
    n = len(daily_ret)
    years = n / 365
    total = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 else 0
    dd = _calc_drawdown_series(equity)
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(365) if daily_ret.std() > 0 else 0
    results.append({
        "name": name,
        "kelly": kelly,
        "avg_day_%": daily_ret.mean() * 100,
        "days_3pct": int((daily_ret >= 0.03).sum()),
        "days_neg3": int((daily_ret <= -0.03).sum()),
        "n_days": n,
        "pct_days_3pct": (daily_ret >= 0.03).mean() * 100,
        "best_day_%": daily_ret.max() * 100,
        "worst_day_%": daily_ret.min() * 100,
        "cagr_%": cagr * 100,
        "total_%": total * 100,
        "final_$": equity.iloc[-1],
        "sharpe": sharpe,
        "maxDD_%": dd.min() * 100,
        "trades": len(trades),
        "universe": "crypto" if "USD" in name or "crypto" in name.lower() else "stocks",
    })

# ─── build strategy list ───────────────────────────────────────────────────
def run_all(bars: dict, fee: float, tag: str):
    close_df = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()

    strats = [
        # Classic
        ("BB_Reversion",       BollingerReversionStrategy(20, 2.0)),
        ("BB_Reversion_tight", BollingerReversionStrategy(14, 1.5)),
        ("BB_RSI_combo",       BollingerRSIStrategy(20, 2.0, 7, 35)),
        ("BB_RSI_tight",       BollingerRSIStrategy(14, 1.5, 5, 30)),
        ("VWAP_Reversion",     VWAPReversionStrategy(24, 0.015, 0.005)),
        ("VWAP_Rev_deep",      VWAPReversionStrategy(24, 0.025, 0.010)),
        ("Donchian_24",        DonchianBreakoutStrategy(24)),
        ("Donchian_48",        DonchianBreakoutStrategy(48)),
        ("MACD_fast",          MACDCrossStrategy(6, 13, 4)),
        ("MACD_std",           MACDCrossStrategy(8, 21, 5)),
        ("Keltner_Rev",        KeltnerReversionStrategy(20, 10, 2.0)),
        ("StochRSI",           StochRSIStrategy(14, 14, 10, 80)),
        ("StochRSI_fast",      StochRSIStrategy(7,  7,  10, 75)),
        ("Supertrend",         SupertrendStrategy(10, 3.0)),
        ("Supertrend_tight",   SupertrendStrategy(7,  2.0)),
        # My originals
        ("GapFade_2.5pct",     GapFadeStrategy(0.025, 4)),
        ("GapFade_3pct",       GapFadeStrategy(0.030, 6)),
        ("VolGated_MR",        VolGatedMRStrategy(5, 25, 60, 14, 1.2)),
        ("VolGated_MR_strict", VolGatedMRStrategy(5, 20, 55, 14, 1.5)),
        ("CascadeEMA",         CascadeEMAStrategy(8, 21, 55, 5, 45)),
        ("CascadeEMA_slow",    CascadeEMAStrategy(13, 34, 89, 7, 40)),
        ("RegimeSwitcher",     RegimeSwitcherStrategy()),
        ("TripleConfluence",   TripleConfluenceStrategy(7, 30, 20, 2.0, 24, 60)),
        ("TripleConf_tight",   TripleConfluenceStrategy(5, 25, 14, 1.5, 24, 55)),
        ("ATR_Breakout",       ATRBreakoutStrategy(14, 1.5, 6)),
        ("ATR_Breakout_big",   ATRBreakoutStrategy(14, 2.0, 8)),
        ("PairsSpread",        PairsSpreadStrategy(48, 2.0, 0.5)),
        # Crypto-specific
        ("CryptoMR_rsi5",      CryptoMeanReversionStrategy(5, 25, 60, use_trend_filter=False)),
        ("CryptoMR_rsi3",      CryptoMeanReversionStrategy(3, 20, 55, use_trend_filter=False)),
        ("CryptoMom_14",       CryptoMomentumStrategy(14, 2, 20)),
    ]

    for label, strat in strats:
        try:
            tgts = strat.generate_signals(bars)
            for kelly in [0.5, 1.0]:
                evaluate(f"{label}_{tag}_k{kelly}", tgts, close_df, fee, kelly)
        except Exception as e:
            print(f"  SKIP {label}: {e}")
    print(f"  [{tag}] done — {len(strats)} strategies × 2 kelly = {len(strats)*2} configs")

print("\nRunning all strategies on CRYPTO (hourly)...")
run_all(bars_crypto, FEE, "crypto")

print("Running all strategies on STOCKS (hourly)...")
run_all(bars_stocks, STOCK_FEE, "stocks")

# ─── results ───────────────────────────────────────────────────────────────
df = pd.DataFrame(results)
if df.empty:
    print("No results generated.")
    sys.exit(1)

df = df.sort_values("days_3pct", ascending=False)
pd.set_option("display.width", 260)

cols = ["name", "avg_day_%", "days_3pct", "pct_days_3pct", "days_neg3",
        "cagr_%", "sharpe", "maxDD_%", "trades", "final_$"]
print(f"\n{'='*80}")
print(f"  TOP 20 CONFIGS — SORTED BY DAYS HITTING +3% (out of ~{df['n_days'].iloc[0]} days)")
print(f"{'='*80}")
print(df[cols].head(20).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

print(f"\n{'='*80}")
print("  TOP 10 BY AVERAGE DAILY RETURN (positive only)")
pos = df[df["avg_day_%"] > 0].sort_values("avg_day_%", ascending=False)
print(pos[cols].head(10).to_string(index=False, float_format=lambda x: f"{x:.2f}") if len(pos) else "  None profitable")

print(f"\n{'='*80}")
print("  TOP 10 BY SHARPE (risk-adjusted)")
print(df.sort_values("sharpe", ascending=False)[cols].head(10)
      .to_string(index=False, float_format=lambda x: f"{x:.2f}"))

best = df.iloc[0]
print(f"\n{'='*80}")
print(f"  BEST FOR 3%/day TARGET: {best['name']}")
print(f"    Days >= +3%:  {best['days_3pct']}/{best['n_days']} ({best['pct_days_3pct']:.1f}% of days)")
print(f"    Avg day:      {best['avg_day_%']:+.3f}%")
print(f"    CAGR:         {best['cagr_%']:+.1f}%")
print(f"    Final $:      ${best['final_$']:,.0f} from $100k")
print(f"    Sharpe:       {best['sharpe']:.2f}")
print(f"    Max DD:       {best['maxDD_%']:.1f}%")
print(f"{'='*80}\n")

Path("backtest_output").mkdir(exist_ok=True)
df.to_csv("backtest_output/mega_sweep.csv", index=False)
print("Full results: backtest_output/mega_sweep.csv")
