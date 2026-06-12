"""
Aggressive parameter sweep: hunt for the highest weekly-return configuration
across momentum and mean-reversion params, with leverage variants.
Reports honest stats including how often the 10% drawdown halt would fire.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from tradelab.data.fetcher import fetch_universe
from tradelab.backtest.runner import _simulate_portfolio, _sharpe, _calc_drawdown_series
from tradelab.strategies.momentum import MomentumStrategy
from tradelab.strategies.mean_reversion import MeanReversionStrategy

print("Fetching 2 years of data (once)...")
bars = fetch_universe(years=2)
close = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()

results = []


def evaluate(name: str, targets: pd.DataFrame, leverage: float = 1.0):
    t = (targets.reindex(close.index).fillna(0.0) * leverage)
    equity, trades = _simulate_portfolio(close, t)
    equity = equity.dropna()
    if len(equity) < 50:
        return
    daily = equity.pct_change().dropna()
    weekly = equity.resample("W").last().pct_change().dropna()
    dd = _calc_drawdown_series(equity)
    halts = int((dd <= -0.10).any())
    results.append({
        "config": name,
        "lev": leverage,
        "total_ret_%": (equity.iloc[-1] / equity.iloc[0] - 1) * 100,
        "avg_wk_%": weekly.mean() * 100,
        "best_wk_%": weekly.max() * 100,
        "worst_wk_%": weekly.min() * 100,
        "wk>=10%": int((weekly >= 0.10).sum()),
        "n_weeks": len(weekly),
        "sharpe": _sharpe(daily),
        "maxDD_%": dd.min() * 100,
        "would_halt": halts,
        "trades": len(trades),
    })


# --- Momentum sweep ---
for lookback in [3, 5, 10, 20]:
    for top_n in [1, 2, 3]:
        strat = MomentumStrategy(lookback=lookback, top_n=top_n)
        targets = strat.generate_signals(bars)
        for lev in [1.0, 2.0]:
            evaluate(f"mom lb={lookback} top={top_n}", targets, lev)
        print(f"  done: momentum lb={lookback} top={top_n}")

# --- Mean reversion sweep ---
for period in [2, 5, 14]:
    for entry in [15, 20, 25, 30]:
        for exit_ in [50, 60, 70]:
            strat = MeanReversionStrategy(
                rsi_period=period, entry_threshold=entry, exit_threshold=exit_
            )
            targets = strat.generate_signals(bars)
            for lev in [1.0, 2.0]:
                evaluate(f"mr rsi{period} in<{entry} out>{exit_}", targets, lev)
    print(f"  done: mean_reversion period={period}")

df = pd.DataFrame(results)
df = df.sort_values("avg_wk_%", ascending=False)

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 100)
print("\n=== TOP 15 BY AVERAGE WEEKLY RETURN ===")
print(df.head(15).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

print("\n=== TOP 10 BY SHARPE ===")
print(df.sort_values("sharpe", ascending=False).head(10).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

best = df.iloc[0]
print(f"\nBest avg weekly return found: {best['avg_wk_%']:.2f}%/week ({best['config']} lev={best['lev']})")
print(f"Weeks at >=10%: {best['wk>=10%']}/{best['n_weeks']}")
df.to_csv("backtest_output/sweep_results.csv", index=False)
print("Full results: backtest_output/sweep_results.csv")
