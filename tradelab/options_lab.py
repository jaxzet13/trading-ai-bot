from __future__ import annotations

"""
LEAPS lab — the options experiment (ANALYSIS ONLY, by design).

This screens for long-dated call options (LEAPS) on the high-conviction names
and shows their leverage and risk profile. It deliberately does NOT place any
options orders automatically.

WHY ANALYSIS-ONLY:
  LEAPS are leverage (3-5x). The same leverage that produced the "155% in a
  month" YouTube result can lose 40-80% in a flat or down month. Auto-firing
  leveraged options against an account with a -4% daily / -8% total drawdown
  limit (your FT+ rules) would blow the challenge on the first bad week.

  So this tool helps you UNDERSTAND and hand-pick LEAPS for a SEPARATE,
  non-challenge paper account — a human-in-the-loop experiment, exactly like
  the video's research phase. You stay in control of execution.

    python -m tradelab.main leaps
"""

import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

# Names to screen for LEAPS (liquid, optionable, high-conviction)
LEAPS_CANDIDATES = ["NVDA", "TSLA", "AMD", "PLTR", "COIN", "MSTR", "AAPL", "AMZN", "GOOGL"]

MIN_DAYS_TO_EXPIRY = 200   # "long-dated": ~7+ months out
TARGET_OTM_PCT = 0.10      # screen calls ~10% out-of-the-money (aggressive upside)


def _pick_expiry(expiries: list[str], min_days: int) -> str | None:
    today = date.today()
    valid = []
    for e in expiries:
        try:
            d = datetime.strptime(e, "%Y-%m-%d").date()
        except ValueError:
            continue
        dte = (d - today).days
        if dte >= min_days:
            valid.append((dte, e))
    if not valid:
        return None
    valid.sort()
    return valid[0][1]   # nearest expiry that still qualifies as long-dated


def screen_leaps() -> list[dict]:
    import yfinance as yf

    rows = []
    for sym in LEAPS_CANDIDATES:
        try:
            tk = yf.Ticker(sym)
            spot = tk.history(period="1d")["Close"]
            if spot.empty:
                continue
            spot = float(spot.iloc[-1])
            expiries = tk.options
            exp = _pick_expiry(list(expiries), MIN_DAYS_TO_EXPIRY)
            if not exp:
                continue
            chain = tk.option_chain(exp).calls
            target_strike = spot * (1 + TARGET_OTM_PCT)
            chain = chain.copy()
            chain["dist"] = (chain["strike"] - target_strike).abs()
            best = chain.sort_values("dist").iloc[0]

            ask = float(best.get("ask", 0) or 0)
            strike = float(best["strike"])
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - date.today()).days
            # Leverage proxy: controlling 100 shares (strike exposure) per contract
            # vs the premium paid. Breakeven = strike + premium.
            premium = ask if ask > 0 else float(best.get("lastPrice", 0) or 0)
            breakeven = strike + premium
            be_move_pct = (breakeven / spot - 1) * 100
            notional_per_contract = spot * 100
            cost_per_contract = premium * 100
            leverage = notional_per_contract / cost_per_contract if cost_per_contract else 0

            rows.append({
                "symbol": sym, "spot": spot, "expiry": exp, "dte": dte,
                "strike": strike, "premium": premium,
                "breakeven": breakeven, "be_move_pct": be_move_pct,
                "leverage": leverage,
                "iv": float(best.get("impliedVolatility", 0) or 0) * 100,
                "cost_per_contract": cost_per_contract,
            })
        except Exception as exc:
            logger.info("LEAPS screen skipped %s: %s", sym, exc)
    return rows


def print_leaps(rows: list[dict]) -> None:
    print(f"\n{'='*80}")
    print("  🧪 LEAPS LAB — long-dated call screener  (ANALYSIS ONLY, no auto-trading)")
    print(f"{'='*80}")
    if not rows:
        print("  No LEAPS data available (market closed or data rate-limited). Try again.")
        print(f"{'='*80}\n")
        return
    print(f"  {'SYM':<7}{'SPOT':>9}{'EXPIRY':>12}{'DTE':>5}{'STRIKE':>9}"
          f"{'PREM':>8}{'B/E%':>7}{'LEV':>6}{'IV%':>7}{'COST':>9}")
    print(f"  {'-'*78}")
    for r in sorted(rows, key=lambda x: x["leverage"], reverse=True):
        print(f"  {r['symbol']:<7}{r['spot']:>9.2f}{r['expiry']:>12}{r['dte']:>5}"
              f"{r['strike']:>9.0f}{r['premium']:>8.2f}{r['be_move_pct']:>+7.1f}"
              f"{r['leverage']:>6.1f}{r['iv']:>7.0f}{r['cost_per_contract']:>9.0f}")
    print(f"  {'-'*78}")
    print("\n  HOW TO READ THIS:")
    print("    LEV   = leverage vs buying shares (e.g. 5.0 = 5x the upside AND downside)")
    print("    B/E%  = how far the stock must rise just to break even at expiry")
    print("    IV%   = implied volatility; high IV = expensive options = worse entry")
    print("    COST  = $ to buy ONE contract (controls 100 shares)")
    print("\n  ⚠️  These are LEVERAGED bets. A LEAP can go to ZERO if the stock stalls.")
    print("     Trade these ONLY on a separate paper account, never the FT+ challenge,")
    print("     and size each one as a small % you can afford to lose entirely.")
    print(f"{'='*80}\n")
