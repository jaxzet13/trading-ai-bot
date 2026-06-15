from __future__ import annotations

"""
Daily AI analyst briefing — the "non-deterministic" layer.

Every morning it reads price action + news on your actual holdings, scores
each one, and flags anything that changed: positions near a partial-TP
trigger, near a stop, big movers, fresh news catalysts. Runs deterministically
on free data; if ANTHROPIC_API_KEY is set it adds a short Claude narrative.

    python -m tradelab.main brief
"""

import logging
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tradelab.config import (
    PARTIAL_TP_PCT, SYMBOL_LOSS_LIMIT_PCT, TRAILING_STOP_PCT,
)

logger = logging.getLogger(__name__)


def _rsi(s: pd.Series, p: int = 14) -> float:
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
    rsi = 100 - 100 / (1 + g / l.replace(0, np.nan))
    val = rsi.dropna()
    return float(val.iloc[-1]) if len(val) else float("nan")


def _fetch_news(symbol: str, limit: int = 3) -> list[str]:
    """Recent headlines via yfinance. Degrades to [] on rate-limit/errors."""
    try:
        import yfinance as yf
        items = yf.Ticker(symbol).news or []
    except Exception:
        return []
    out = []
    for it in items[:limit]:
        # yfinance changed shape across versions: title may be top-level or under 'content'
        title = it.get("title") or (it.get("content") or {}).get("title")
        if title:
            out.append(title)
    return out


def _price_action(df: pd.DataFrame) -> dict:
    if df is None or df.empty or "close" not in df:
        return {}
    c = df["close"].dropna()
    if c.empty:
        return {}
    last = float(c.iloc[-1])
    def chg(n):
        if len(c) > n:
            return (last / float(c.iloc[-1 - n]) - 1) * 100
        return float("nan")
    high20 = float(c.tail(20).max())
    return {
        "last": last,
        "d1": chg(1),
        "d5": chg(5),
        "d20": chg(20),
        "rsi": _rsi(c),
        "from_high20": (last / high20 - 1) * 100 if high20 else float("nan"),
    }


def build_briefing(broker, bars: dict) -> dict:
    """Assemble structured data for every open position."""
    positions = broker.get_positions()
    rows = []
    for p in positions:
        sym = p["symbol"]
        ep, cp = p["avg_entry_price"], p["current_price"]
        gain = (cp - ep) / ep * 100 if ep > 0 else 0.0
        pa = _price_action(bars[sym]) if sym in bars else {}
        flags = []
        if gain >= PARTIAL_TP_PCT * 100:
            flags.append(f"🎯 above +{PARTIAL_TP_PCT*100:.1f}% TP trigger")
        if gain <= -SYMBOL_LOSS_LIMIT_PCT * 100:
            flags.append(f"🛑 at/below -{SYMBOL_LOSS_LIMIT_PCT*100:.0f}% symbol stop")
        if pa and not np.isnan(pa.get("d1", np.nan)) and abs(pa["d1"]) >= 5:
            flags.append(f"⚡ big 1-day move {pa['d1']:+.1f}%")
        if pa and not np.isnan(pa.get("rsi", np.nan)):
            if pa["rsi"] >= 75:
                flags.append(f"📈 overbought RSI {pa['rsi']:.0f}")
            elif pa["rsi"] <= 25:
                flags.append(f"📉 oversold RSI {pa['rsi']:.0f}")
        rows.append({
            "symbol": sym, "qty": p["qty"], "entry": ep, "price": cp,
            "pnl_pct": gain, "pnl_usd": p["unrealized_pl"],
            "mkt_value": p["market_value"], "pa": pa,
            "flags": flags, "news": _fetch_news(sym),
        })
    rows.sort(key=lambda r: r["mkt_value"], reverse=True)
    acct = broker.get_account()
    return {"account": acct, "positions": rows,
            "ts": datetime.now(timezone.utc)}


def _claude_narrative(brief: dict) -> str | None:
    """Optional: a short narrative from Claude if an API key is configured."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.info("anthropic SDK not installed — skipping AI narrative. `pip install anthropic`")
        return None

    lines = []
    for r in brief["positions"]:
        pa = r["pa"]
        lines.append(
            f"{r['symbol']}: P&L {r['pnl_pct']:+.1f}%, "
            f"1d {pa.get('d1', float('nan')):+.1f}%, 5d {pa.get('d5', float('nan')):+.1f}%, "
            f"RSI {pa.get('rsi', float('nan')):.0f}, flags={r['flags'] or 'none'}, "
            f"news={r['news'][:2] or 'none'}"
        )
    prompt = (
        "You are a risk-focused portfolio analyst. Given today's holdings data, "
        "write a concise morning brief (<200 words): overall posture, the 2-3 "
        "positions that most need attention and why, and any risks. Be direct, "
        "no hype, no financial-advice disclaimers.\n\n" + "\n".join(lines)
    )
    try:
        client = Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as exc:
        logger.warning("Claude narrative failed: %s", exc)
        return None


def print_briefing(brief: dict) -> None:
    acct = brief["account"]
    ts = brief["ts"].strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*64}")
    print(f"  📋 DAILY ANALYST BRIEFING — {ts}")
    print(f"{'='*64}")
    print(f"  Equity ${acct['equity']:,.2f}   Cash ${acct['cash']:,.2f}   "
          f"Positions {len(brief['positions'])}")
    print(f"{'-'*64}")

    # Most-flagged first
    flagged = [r for r in brief["positions"] if r["flags"]]
    if flagged:
        print("\n  ⚠️  NEEDS ATTENTION")
        for r in flagged:
            print(f"    {r['symbol']:<8} {r['pnl_pct']:+6.1f}%   " + " | ".join(r["flags"]))

    print("\n  HOLDINGS")
    print(f"    {'SYM':<8}{'P&L%':>7}{'1d':>7}{'5d':>7}{'RSI':>6}  NEWS")
    for r in brief["positions"]:
        pa = r["pa"]
        d1 = pa.get("d1", float("nan"))
        d5 = pa.get("d5", float("nan"))
        rsi = pa.get("rsi", float("nan"))
        news = r["news"][0][:42] + "…" if r["news"] else "—"
        print(f"    {r['symbol']:<8}{r['pnl_pct']:>+6.1f}%{d1:>+6.1f}%{d5:>+6.1f}%"
              f"{rsi:>6.0f}  {news}")

    narrative = _claude_narrative(brief)
    if narrative:
        print(f"\n{'-'*64}")
        print("  🤖 CLAUDE'S READ")
        print(f"{'-'*64}")
        for line in narrative.splitlines():
            print(f"  {line}")
    else:
        print(f"\n  (Set ANTHROPIC_API_KEY in .env for an AI narrative summary.)")
    print(f"{'='*64}\n")
