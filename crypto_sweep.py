"""
Crypto parameter sweep with Kelly compounding.
Fetches data once, tests all strategy/parameter combos, ranks by CAGR.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import pandas as pd
import numpy as np
from pathlib import Path

from tradelab.config import CRYPTO_UNIVERSE
from tradelab.data.fetcher import fetch_bars
from tradelab.backtest.runner import (
    _simulate_portfolio, _sharpe, _cagr, _calc_drawdown_series, _profit_factor
)
from tradelab.strategies.crypto import CryptoMeanReversionStrategy, CryptoMomentumStrategy

TRADING_DAYS = 365  # crypto trades every day including weekends

print("Fetching 3 years of crypto data (once)...")
bars = fetch_bars(CRYPTO_UNIVERSE, years=3)
close = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
print(f"  {len(close)} days, {len(close.columns)} coins\n")

results = []


def evaluate(name: str, targets: pd.DataFrame, kelly: float):
    t = targets.reindex(close.index).fillna(0.0)
    equity, trades = _simulate_portfolio(close, t, slippage=0.001, kelly_fraction=kelly)
    equity = equity.dropna()
    if len(equity) < 90 or len(trades) < 5:
        return
    daily = equity.pct_change().dropna()
    trade_pnls = pd.Series([tr["pnl"] / (tr["shares"] * tr["entry_price"]) * 100
                            for tr in trades if tr["entry_price"] > 0])
    dd = _calc_drawdown_series(equity)
    results.append({
        "config": name,
        "kelly": kelly,
        "total_ret_%": (equity.iloc[-1] / equity.iloc[0] - 1) * 100,
        "cagr_%": _cagr(equity, TRADING_DAYS) * 100,
        "sharpe": _sharpe(daily, TRADING_DAYS),
        "maxDD_%": dd.min() * 100,
        "win_rate_%": (trade_pnls > 0).mean() * 100 if len(trade_pnls) else 0,
        "profit_factor": _profit_factor(trade_pnls / 100) if len(trade_pnls) else 0,
        "trades": len(trades),
        "final_$": equity.iloc[-1],
    })


# ---- Mean Reversion sweep ----
for rsi_p in [2, 3, 5]:
    for entry in [20, 25, 30, 35]:
        for exit_ in [50, 60, 70]:
            for trend in [True, False]:
                strat = CryptoMeanReversionStrategy(
                    rsi_period=rsi_p,
                    entry_threshold=entry,
                    exit_threshold=exit_,
                    use_trend_filter=trend,
                )
                tgts = strat.generate_signals(bars)
                for kelly in [0.25, 0.5, 1.0]:
                    evaluate(f"MR rsi{rsi_p} in<{entry} out>{exit_} trend={trend}", tgts, kelly)
    print(f"  done MR rsi_period={rsi_p}")

# ---- Momentum sweep ----
for lb in [3, 7, 14]:
    for top_n in [1, 2, 3]:
        for trend_p in [20, 50]:
            strat = CryptoMomentumStrategy(lookback=lb, top_n=top_n, trend_period=trend_p)
            tgts = strat.generate_signals(bars)
            for kelly in [0.25, 0.5, 1.0]:
                evaluate(f"MOM lb={lb} top={top_n} ma={trend_p}", tgts, kelly)
    print(f"  done MOM lookback={lb}")

df = pd.DataFrame(results).sort_values("cagr_%", ascending=False)

pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 20)
print("\n=== TOP 15 CRYPTO CONFIGS BY CAGR (Kelly compounding on) ===")
cols = ["config", "kelly", "cagr_%", "total_ret_%", "sharpe", "maxDD_%",
        "win_rate_%", "profit_factor", "trades", "final_$"]
print(df[cols].head(15).to_string(index=False, float_format=lambda x: f"{x:.1f}"))

best = df.iloc[0]
print(f"\nBest: {best['config']}  kelly={best['kelly']}")
print(f"  CAGR:         {best['cagr_%']:.1f}%/yr")
print(f"  Total return: {best['total_ret_%']:.1f}%  (${best['final_$']:,.0f} from $100k)")
print(f"  Sharpe:       {best['sharpe']:.2f}")
print(f"  Max drawdown: {best['maxDD_%']:.1f}%")
print(f"  Win rate:     {best['win_rate_%']:.1f}%")

Path("backtest_output").mkdir(exist_ok=True)
df.to_csv("backtest_output/crypto_sweep.csv", index=False)
print("\nFull results: backtest_output/crypto_sweep.csv")
