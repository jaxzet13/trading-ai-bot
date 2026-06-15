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

from tradelab.config import (
    OPTIONS_UNDERLYINGS, OPTIONS_BUDGET_PCT, OPTIONS_MAX_POSITIONS,
    OPTIONS_TARGET_OTM_PCT, OPTIONS_MIN_DTE,
    OPTIONS_PROFIT_TARGET, OPTIONS_STOP_LOSS,
)

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


# ── live options execution on Alpaca paper ──────────────────────────────────

def manage_option_positions(broker) -> dict:
    """Take-profit / stop-loss on existing option positions."""
    closed_tp, closed_sl = [], []
    for p in broker.get_option_positions():
        plpc = p["unrealized_plpc"]   # fraction, e.g. +1.0 = +100%
        if plpc >= OPTIONS_PROFIT_TARGET:
            if broker.close_option(p["symbol"]):
                closed_tp.append(p["symbol"])
                logger.info("OPTION TP  %s +%.0f%% → closed", p["symbol"], plpc * 100)
        elif plpc <= -OPTIONS_STOP_LOSS:
            if broker.close_option(p["symbol"]):
                closed_sl.append(p["symbol"])
                logger.info("OPTION SL  %s %.0f%% → closed", p["symbol"], plpc * 100)
    return {"tp": closed_tp, "sl": closed_sl}


def run_options_cycle(broker) -> dict:
    """
    Buy LEAPS calls up to OPTIONS_BUDGET_PCT of equity, capped at
    OPTIONS_MAX_POSITIONS. Take-profit/stop-loss handled first.
    Returns a summary dict.
    """
    acct = broker.get_account()
    equity = acct["equity"]
    budget = equity * OPTIONS_BUDGET_PCT

    mgmt = manage_option_positions(broker)

    existing = broker.get_option_positions()
    held_underlyings = {p["symbol"][:_underlying_len(p["symbol"])] for p in existing}
    options_value = sum(p["market_value"] for p in existing)
    available = budget - options_value
    slots = OPTIONS_MAX_POSITIONS - len(existing)

    bought = []
    if available < 100 or slots <= 0:
        logger.info("Options: no room (available $%.0f, slots %d)", available, slots)
        return {"bought": bought, **mgmt, "options_value": options_value,
                "budget": budget, "equity": equity}

    # Screen candidates we don't already hold, rank by lowest breakeven move
    candidates = []
    for u in OPTIONS_UNDERLYINGS:
        if u in held_underlyings:
            continue
        leap = broker.find_leaps(u, OPTIONS_TARGET_OTM_PCT, OPTIONS_MIN_DTE)
        if not leap:
            continue
        ask = broker.option_quote(leap["symbol"])
        if not ask or ask <= 0:
            continue
        breakeven = leap["strike"] + ask
        be_move = (breakeven / leap["spot"] - 1) * 100
        candidates.append({**leap, "ask": ask, "be_move": be_move,
                           "cost": ask * 100})
    candidates.sort(key=lambda c: c["be_move"])
    candidates = candidates[:slots]
    if not candidates:
        return {"bought": bought, **mgmt, "options_value": options_value,
                "budget": budget, "equity": equity}

    per_name = available / len(candidates)
    for c in candidates:
        qty = int(per_name // c["cost"])
        if qty < 1:
            logger.info("Options: skip %s — 1 contract ($%.0f) exceeds per-name budget ($%.0f)",
                        c["symbol"], c["cost"], per_name)
            continue
        order_id = broker.buy_option(c["symbol"], qty)
        if order_id:
            bought.append({"symbol": c["symbol"], "qty": qty,
                           "cost": qty * c["cost"], "be_move": c["be_move"]})
    return {"bought": bought, **mgmt, "options_value": options_value,
            "budget": budget, "equity": equity}


def _underlying_len(occ: str) -> int:
    """Length of the underlying portion of an OCC symbol (before the 6-digit date)."""
    import re
    m = re.match(r"^([A-Z]{1,6})\d{6}[CP]\d{8}$", occ)
    return len(m.group(1)) if m else 0


def print_options_run(summary: dict) -> None:
    print(f"\n{'='*64}")
    print("  🧪 OPTIONS / LEAPS RUN — live on Alpaca paper")
    print(f"{'='*64}")
    print(f"  Equity ${summary['equity']:,.0f}   "
          f"Options budget ${summary['budget']:,.0f} ({OPTIONS_BUDGET_PCT*100:.0f}%)   "
          f"Currently in options ${summary['options_value']:,.0f}")
    if summary.get("tp"):
        print(f"  🎯 Took profit: {', '.join(summary['tp'])}")
    if summary.get("sl"):
        print(f"  🛑 Stopped out: {', '.join(summary['sl'])}")
    if summary["bought"]:
        print("\n  🟢 BOUGHT:")
        for b in summary["bought"]:
            print(f"    {b['symbol']:<22} x{b['qty']:<3} ${b['cost']:>8,.0f}  "
                  f"(needs {b['be_move']:+.1f}% to break even)")
    else:
        print("\n  No new option positions opened this run.")
    print(f"{'='*64}\n")
