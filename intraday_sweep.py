"""
Intraday (hourly) crypto sweep — day-trading timeframe.
Uses Alpaca's real crypto taker fee (0.25%/side) as cost model.
Reports per-DAY return stats, including how many days hit >= 3%.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

from tradelab.backtest.runner import _simulate_portfolio, _calc_drawdown_series
from tradelab.strategies.crypto import CryptoMeanReversionStrategy, CryptoMomentumStrategy

COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "LINK-USD", "DOGE-USD"]
ALPACA_CRYPTO_FEE = 0.0025  # 0.25% taker per side

print("Fetching hourly bars (max ~730 days from yfinance)...")
raw = yf.download(COINS, period="729d", interval="1h", auto_adjust=True, progress=False)
closes = raw["Close"].dropna(how="all")
print(f"  {len(closes)} hourly bars, {closes.index[0]} → {closes.index[-1]}")

bars = {}
for c in COINS:
    if c in closes.columns:
        s = closes[c].dropna()
        bars[c] = pd.DataFrame({"close": s})

close_df = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
results = []


def evaluate(name: str, targets: pd.DataFrame, kelly: float = 1.0):
    t = targets.reindex(close_df.index).fillna(0.0)
    equity, trades = _simulate_portfolio(
        close_df, t, slippage=ALPACA_CRYPTO_FEE, kelly_fraction=kelly
    )
    equity = equity.dropna()
    if len(equity) < 500 or len(trades) < 10:
        return
    daily_eq = equity.resample("D").last().dropna()
    daily_ret = daily_eq.pct_change().dropna()
    n_days = len(daily_ret)
    years = n_days / 365
    total = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 else 0
    dd = _calc_drawdown_series(equity)
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(365) if daily_ret.std() > 0 else 0
    results.append({
        "config": name,
        "kelly": kelly,
        "avg_day_%": daily_ret.mean() * 100,
        "days>=3%": int((daily_ret >= 0.03).sum()),
        "days<=-3%": int((daily_ret <= -0.03).sum()),
        "n_days": n_days,
        "best_day_%": daily_ret.max() * 100,
        "worst_day_%": daily_ret.min() * 100,
        "cagr_%": cagr * 100,
        "total_%": total * 100,
        "sharpe": sharpe,
        "maxDD_%": dd.min() * 100,
        "trades": len(trades),
    })


print("\nSweeping intraday mean reversion...")
for rsi_p in [3, 5, 14]:
    for entry in [20, 25, 30]:
        for exit_ in [55, 65, 75]:
            strat = CryptoMeanReversionStrategy(
                rsi_period=rsi_p, entry_threshold=entry,
                exit_threshold=exit_, use_trend_filter=False,
            )
            tgts = strat.generate_signals(bars)
            evaluate(f"MR-1h rsi{rsi_p} in<{entry} out>{exit_}", tgts)
    print(f"  rsi_period={rsi_p} done")

print("Sweeping intraday momentum...")
for lb in [6, 12, 24, 48]:   # hours
    for top_n in [1, 2]:
        strat = CryptoMomentumStrategy(lookback=lb, top_n=top_n, trend_period=24)
        tgts = strat.generate_signals(bars)
        evaluate(f"MOM-1h lb={lb}h top={top_n}", tgts)
    print(f"  lookback={lb}h done")

df = pd.DataFrame(results).sort_values("avg_day_%", ascending=False)
pd.set_option("display.width", 230)

cols = ["config", "avg_day_%", "days>=3%", "days<=-3%", "n_days",
        "best_day_%", "worst_day_%", "cagr_%", "sharpe", "maxDD_%", "trades"]
print("\n=== TOP 12 BY AVERAGE DAILY RETURN (after 0.25%/side Alpaca fees) ===")
print(df[cols].head(12).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

best = df.iloc[0]
print(f"\nBest config: {best['config']}")
print(f"  Average day:   {best['avg_day_%']:+.3f}%")
print(f"  Days >= +3%:   {best['days>=3%']} of {best['n_days']} ({best['days>=3%']/best['n_days']*100:.1f}%)")
print(f"  Days <= -3%:   {best['days<=-3%']} of {best['n_days']}")

Path("backtest_output").mkdir(exist_ok=True)
df.to_csv("backtest_output/intraday_crypto_sweep.csv", index=False)
print("\nSaved: backtest_output/intraday_crypto_sweep.csv")
