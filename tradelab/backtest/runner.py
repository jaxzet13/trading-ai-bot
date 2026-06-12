from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from tradelab.config import (
    BACKTEST_YEARS,
    BENCHMARK,
    COMMISSION,
    SHARPE_PASS_THRESHOLD,
    SLIPPAGE_PCT,
)
from tradelab.data.fetcher import fetch_bars, fetch_benchmark, fetch_universe
from tradelab.strategies.base import Strategy

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252


@dataclass
class BacktestResult:
    strategy_name: str
    total_return: float
    cagr: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    num_trades: int
    equity_curve: pd.Series
    passes: bool = field(init=False)

    def __post_init__(self) -> None:
        self.passes = self.sharpe > SHARPE_PASS_THRESHOLD

    def print_report(self) -> None:
        verdict = "[PASS]" if self.passes else "[FAIL]"
        print(f"\n{'='*60}")
        print(f"  Backtest Report — {self.strategy_name}  {verdict}")
        print(f"{'='*60}")
        print(f"  Total Return   : {self.total_return*100:+.2f}%")
        print(f"  CAGR           : {self.cagr*100:+.2f}%")
        print(f"  Sharpe Ratio   : {self.sharpe:.3f}  (threshold {SHARPE_PASS_THRESHOLD})")
        print(f"  Max Drawdown   : {self.max_drawdown*100:.2f}%")
        print(f"  Win Rate       : {self.win_rate*100:.1f}%")
        print(f"  Profit Factor  : {self.profit_factor:.2f}")
        print(f"  Trades         : {self.num_trades}")
        print(f"  Verdict        : {verdict}")
        print(f"{'='*60}\n")


def _calc_drawdown_series(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return (equity - peak) / peak


def _sharpe(returns: pd.Series, periods: int = TRADING_DAYS_PER_YEAR) -> float:
    if returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * math.sqrt(periods))


def _profit_factor(returns: pd.Series) -> float:
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def _cagr(equity: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    if len(equity) < 2 or equity.iloc[0] == 0:
        return 0.0
    years = len(equity) / periods_per_year
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def _simulate_portfolio(
    close: pd.DataFrame,
    targets: pd.DataFrame,
    slippage: float = SLIPPAGE_PCT,
    commission: float = COMMISSION,
    initial_capital: float = 100_000.0,
) -> tuple[pd.Series, list[dict]]:
    """
    Simple vectorised simulation that doesn't depend on vectorbt.
    Handles fractional shares, slippage, and commission.
    Returns (equity_series, trade_records).
    """
    dates = close.index
    equity = pd.Series(index=dates, dtype=float)
    cash = initial_capital
    positions: dict[str, float] = {}   # symbol -> shares held
    entry_prices: dict[str, float] = {}
    entry_dates: dict[str, pd.Timestamp] = {}
    trades: list[dict] = []

    for i, date in enumerate(dates):
        # Mark to market
        port_value = cash
        for sym, shares in positions.items():
            if sym in close.columns and not pd.isna(close.loc[date, sym]):
                port_value += shares * close.loc[date, sym]

        equity[date] = port_value

        if i == len(dates) - 1:
            break

        # Get today's target weights
        if date not in targets.index:
            continue
        target_row = targets.loc[date]

        # Desired notional per symbol
        desired: dict[str, float] = {}
        for sym in close.columns:
            w = float(target_row.get(sym, 0.0))
            if not pd.isna(w) and w > 0:
                desired[sym] = w * port_value

        # Determine exits
        for sym in list(positions.keys()):
            if sym not in desired or desired.get(sym, 0) == 0:
                px = float(close.loc[date, sym]) if sym in close.columns else None
                if px and not math.isnan(px):
                    cost = abs(positions[sym]) * px * slippage + commission
                    pnl = (px - entry_prices[sym]) * positions[sym] - cost
                    trades.append({
                        "symbol": sym,
                        "entry_date": entry_dates[sym],
                        "entry_price": entry_prices[sym],
                        "exit_date": date,
                        "exit_price": px,
                        "shares": positions[sym],
                        "pnl": pnl,
                        "fees": cost,
                    })
                    cash += positions[sym] * px - cost
                del positions[sym]
                del entry_prices[sym]
                del entry_dates[sym]

        # Determine entries / rebalances
        for sym, notional in desired.items():
            price = float(close.loc[date, sym]) if sym in close.columns else None
            if price is None or math.isnan(price) or price <= 0:
                continue
            fill_price = price * (1 + slippage)
            target_shares = notional / fill_price
            current_shares = positions.get(sym, 0.0)

            delta = target_shares - current_shares
            cost = abs(delta) * fill_price * slippage + commission if delta != 0 else 0
            trade_cost = delta * fill_price + cost

            if cash >= trade_cost or delta < 0:
                cash -= trade_cost
                if sym not in positions:
                    positions[sym] = target_shares
                    entry_prices[sym] = fill_price
                    entry_dates[sym] = date
                else:
                    positions[sym] = target_shares

    return equity, trades


def run_backtest(
    strategy: Strategy,
    years: int = BACKTEST_YEARS,
    output_dir: Optional[Path] = None,
) -> BacktestResult:
    from tradelab.data.fetcher import fetch_universe
    bars = fetch_universe(years=years)
    targets = strategy.generate_signals(bars)

    close = pd.DataFrame({sym: df["close"] for sym, df in bars.items()}).sort_index()
    targets = targets.reindex(close.index).fillna(0.0)

    equity, trade_records = _simulate_portfolio(close, targets)
    equity = equity.dropna()

    daily_returns = equity.pct_change().dropna()
    total_return = float((equity.iloc[-1] / equity.iloc[0]) - 1) if len(equity) > 0 else 0.0
    cagr = _cagr(equity)
    sharpe = _sharpe(daily_returns)
    dd_series = _calc_drawdown_series(equity)
    max_drawdown = float(dd_series.min())

    trade_pnls = pd.Series([t["pnl"] for t in trade_records])
    win_rate = float((trade_pnls > 0).mean()) if len(trade_pnls) > 0 else 0.0
    profit_factor = _profit_factor(trade_pnls)

    result = BacktestResult(
        strategy_name=strategy.name,
        total_return=total_return,
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        profit_factor=profit_factor,
        num_trades=len(trade_records),
        equity_curve=equity,
    )

    if output_dir is not None:
        _save_equity_chart(equity, strategy.name, output_dir)

    return result


def run_benchmark(years: int = BACKTEST_YEARS) -> BacktestResult:
    spy = fetch_benchmark(years=years)
    if spy.empty:
        raise RuntimeError("No SPY data returned")

    equity = spy["close"] / spy["close"].iloc[0] * 100_000
    daily_returns = equity.pct_change().dropna()

    return BacktestResult(
        strategy_name="SPY Buy & Hold",
        total_return=float((equity.iloc[-1] / equity.iloc[0]) - 1),
        cagr=_cagr(equity),
        sharpe=_sharpe(daily_returns),
        max_drawdown=float(_calc_drawdown_series(equity).min()),
        win_rate=float((daily_returns > 0).mean()),
        profit_factor=_profit_factor(daily_returns),
        num_trades=1,
        equity_curve=equity,
    )


def _save_equity_chart(equity: pd.Series, name: str, output_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        output_dir.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(12, 5))
        equity.plot(ax=ax, title=f"Equity Curve — {name}")
        ax.set_ylabel("Portfolio Value ($)")
        ax.set_xlabel("Date")
        ax.grid(True, alpha=0.3)
        path = output_dir / f"equity_{name}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        logger.info("Equity curve saved to %s", path)
    except Exception as exc:
        logger.warning("Could not save equity chart: %s", exc)


def compare_with_benchmark(results: list[BacktestResult]) -> None:
    benchmark = run_benchmark()
    print(f"\n{'='*70}")
    print(f"  Strategy vs Benchmark Comparison")
    print(f"{'='*70}")
    header = f"  {'Strategy':<26} {'Total Ret':>10} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8}  Verdict"
    print(header)
    print(f"  {'-'*64}")

    all_results = results + [benchmark]
    for r in all_results:
        verdict = "PASS" if r.passes else "FAIL"
        print(
            f"  {r.strategy_name:<26} "
            f"{r.total_return*100:>+9.1f}% "
            f"{r.cagr*100:>+7.1f}% "
            f"{r.sharpe:>8.3f} "
            f"{r.max_drawdown*100:>7.1f}%  {verdict}"
        )
    print(f"{'='*70}\n")
