from __future__ import annotations

"""
Black-Scholes LEAPS backtest.

Simulates buying 10% OTM calls with ~200 DTE every month over historical data
and holding for a fixed period, using realized volatility as an IV proxy.
Answers: "would this strategy have worked on this name historically?"
"""

import logging
import math
from datetime import timedelta

logger = logging.getLogger(__name__)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF — Abramowitz & Stegun approximation (error < 7.5e-8)."""
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1.0 if x >= 0 else -1.0
    xabs = abs(x)
    t = 1.0 / (1.0 + p * xabs)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-xabs * xabs / 2)
    return 0.5 * (1.0 + sign * y)


def _bs_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes European call price. T in years."""
    if T <= 0:
        return max(0.0, S - K)
    if sigma <= 0:
        return max(0.0, S - K * math.exp(-r * T))
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def run_options_backtest(
    underlying: str,
    years: int = 2,
    otm_pct: float = 0.10,
    entry_dte: int = 200,
    hold_days: int = 60,
    risk_free: float = 0.045,
) -> dict:
    """
    Simulate buying 10% OTM calls with `entry_dte` days to expiry,
    holding for `hold_days`, monthly, over `years` of history.

    Uses 30-day realized volatility as IV proxy (conservative — actual IV
    is usually higher, making real options slightly more expensive than modelled).

    Returns a result dict with win_rate, avg_return, sharpe, etc.
    """
    try:
        import yfinance as yf
        import numpy as np

        hist = yf.Ticker(underlying).history(period=f"{years + 1}y")["Close"].dropna()
        if len(hist) < 252:
            return {"symbol": underlying, "error": "insufficient data (<252 bars)"}

        daily_returns = hist.pct_change().dropna()
        rv30 = daily_returns.rolling(30).std() * math.sqrt(252)  # annualised

        T_entry = entry_dte / 365.0
        results: list[float] = []
        dates = hist.index[30 : -hold_days - 5]

        # Sample approximately monthly (every ~21 trading days)
        for entry_date in dates[::21]:
            try:
                S = float(hist.loc[entry_date])
                iv = float(rv30.loc[entry_date])
                if iv <= 0 or math.isnan(iv):
                    continue

                K = S * (1 + otm_pct)
                entry_price = _bs_call(S, K, T_entry, risk_free, iv)
                if entry_price < 0.01:
                    continue

                # Find exit date
                future = hist.index[hist.index >= entry_date + timedelta(days=hold_days)]
                if len(future) == 0:
                    continue
                exit_date = future[0]
                S_exit = float(hist.loc[exit_date])
                iv_exit = float(rv30.loc[exit_date]) if exit_date in rv30.index else iv
                T_exit = max(T_entry - hold_days / 365.0, 0.001)

                exit_price = _bs_call(S_exit, K, T_exit, risk_free, iv_exit)
                ret = (exit_price - entry_price) / entry_price
                results.append(ret)
            except Exception:
                continue

        if not results:
            return {"symbol": underlying, "error": "no valid sample periods"}

        arr = np.array(results)
        return {
            "symbol": underlying,
            "sample_n": len(arr),
            "win_rate": float((arr > 0).mean()),
            "avg_return": float(arr.mean()),
            "median_return": float(np.median(arr)),
            "best_trade": float(arr.max()),
            "worst_trade": float(arr.min()),
            "sharpe": float(arr.mean() / arr.std()) if arr.std() > 0 else 0.0,
            "avg_return_pct": float(arr.mean() * 100),
        }
    except Exception as exc:
        return {"symbol": underlying, "error": str(exc)}


def run_all_options_backtest(
    underlyings: list[str] | None = None,
    years: int = 2,
    hold_days: int = 60,
) -> list[dict]:
    """Backtest all option underlyings and return sorted results."""
    from tradelab.config import OPTIONS_UNDERLYINGS
    targets = underlyings or OPTIONS_UNDERLYINGS
    results = []
    for sym in targets:
        logger.info("Options backtest: %s ...", sym)
        r = run_options_backtest(sym, years=years, hold_days=hold_days)
        results.append(r)
    results.sort(key=lambda r: r.get("sharpe", -99), reverse=True)
    return results


def print_options_backtest(results: list[dict], hold_days: int = 60) -> None:
    print(f"\n{'='*78}")
    print(f"  OPTIONS BACKTEST — 10% OTM LEAPS, {hold_days}-day hold, B-S pricing")
    print(f"{'='*78}")
    print(f"  {'SYM':<7}{'N':>4}{'WIN%':>7}{'AVG%':>8}{'MED%':>8}"
          f"{'BEST%':>8}{'WORST%':>8}{'SHARPE':>8}  VERDICT")
    print(f"  {'-'*76}")
    for r in results:
        if "error" in r:
            print(f"  {r['symbol']:<7}  ERROR: {r['error']}")
            continue
        win = r["win_rate"] * 100
        avg = r["avg_return_pct"]
        med = r["median_return"] * 100
        best = r["best_trade"] * 100
        worst = r["worst_trade"] * 100
        sh = r["sharpe"]
        verdict = (
            "STRONG" if sh > 0.5 and avg > 10
            else "OK" if sh > 0.2 and avg > 0
            else "WEAK" if avg > 0
            else "AVOID"
        )
        print(f"  {r['symbol']:<7}{r['sample_n']:>4}{win:>7.0f}{avg:>+8.1f}{med:>+8.1f}"
              f"{best:>+8.0f}{worst:>+8.0f}{sh:>8.2f}  {verdict}")
    print(f"  {'-'*76}")
    print("\n  NOTE: B-S prices use realized vol as IV proxy. Real options cost")
    print("  slightly more (vol risk premium) so actual returns may be lower.")
    print(f"{'='*78}\n")
