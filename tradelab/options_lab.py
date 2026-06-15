from __future__ import annotations

"""
Options / LEAPS engine — intelligent catalyst-driven selection.

Decision pipeline for each candidate:
  1. Catalyst signals   — how beaten-down + upcoming earnings catalyst
  2. Fundamental score  — revenue growth, margins, analyst consensus, cash runway
  3. News sentiment     — recent headlines, keyword scoring
  4. AI verdict         — Claude (haiku) synthesises all 3 and rules buy / weak / skip
  5. Final score        — weighted combination; "skip" candidates are eliminated

Live execution: manage TP/SL on open positions, then buy highest-conviction
names up to OPTIONS_BUDGET_PCT of equity.
"""

import logging
import math
import os
from datetime import date, datetime
from typing import Optional

from tradelab.config import (
    OPTIONS_UNDERLYINGS, OPTIONS_BUDGET_PCT, OPTIONS_MAX_POSITIONS,
    OPTIONS_TARGET_OTM_PCT, OPTIONS_MIN_DTE, OPTIONS_CATALYST_WINDOW,
    OPTIONS_PROFIT_TARGET, OPTIONS_STOP_LOSS,
)

logger = logging.getLogger(__name__)

LEAPS_CANDIDATES = ["NVDA", "TSLA", "AMD", "PLTR", "COIN", "MSTR", "AAPL", "AMZN", "GOOGL"]
MIN_DAYS_TO_EXPIRY = 200
TARGET_OTM_PCT = 0.10

# ── screener (analysis only) ────────────────────────────────────────────────

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
    return valid[0][1]


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
            chain = tk.option_chain(exp).calls.copy()
            target_strike = spot * (1 + TARGET_OTM_PCT)
            chain["dist"] = (chain["strike"] - target_strike).abs()
            best = chain.sort_values("dist").iloc[0]
            ask = float(best.get("ask", 0) or 0)
            strike = float(best["strike"])
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - date.today()).days
            premium = ask if ask > 0 else float(best.get("lastPrice", 0) or 0)
            breakeven = strike + premium
            be_move_pct = (breakeven / spot - 1) * 100
            cost_per_contract = premium * 100
            leverage = (spot * 100) / cost_per_contract if cost_per_contract else 0
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
    print("  LEAPS LAB — long-dated call screener")
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
    print(f"  {'-'*78}\n")


# ── intelligence layer ───────────────────────────────────────────────────────

def _catalyst_signals(underlying: str) -> tuple[float, float, int]:
    """
    Returns (beaten_down_score 0-60, catalyst_bonus 0 or 20, days_to_earnings).
    beaten_down: how far off 52-week high (more beaten-down = higher score)
    catalyst:    20 pts if earnings within OPTIONS_CATALYST_WINDOW days
    """
    bd, cat, dte = 0.0, 0.0, -1
    try:
        import yfinance as yf
        import pandas as pd
        tk = yf.Ticker(underlying)
        h = tk.history(period="1y")["Close"].dropna()
        if len(h):
            off_high = (float(h.iloc[-1]) / float(h.max()) - 1) * 100
            bd = max(0.0, min(60.0, -off_high))
        try:
            ed = tk.get_earnings_dates(limit=12)
            if ed is not None and len(ed):
                future = ed[ed.index > pd.Timestamp.now(tz=ed.index.tz)]
                if len(future):
                    nxt = future.index.min()
                    dte = (nxt - pd.Timestamp.now(tz=nxt.tz)).days
                    if 0 <= dte <= OPTIONS_CATALYST_WINDOW:
                        cat = 20.0
        except Exception:
            pass
    except Exception:
        pass
    return bd, cat, dte


def _fundamental_score(underlying: str) -> tuple[float, dict]:
    """
    Score business health from yfinance fundamentals.
    Returns (score, info_dict).

    Range: roughly -60 to +50
    Positive = healthy growing business (beaten-down opportunity)
    Negative = broken / deteriorating (avoid options)

    Key signals:
      Revenue growth — most predictive of recovery vs permanent decline
      Gross margin   — business quality; negative = structurally broken
      Analyst rating — crowd wisdom; strong buy consensus = institutional support
      Debt/equity    — financial risk; can they survive a down cycle?
      Cash runway    — for money-losers, how many quarters until cash out?
    """
    score = 0.0
    info: dict = {}
    try:
        import yfinance as yf
        i = yf.Ticker(underlying).info or {}

        # Revenue growth (most important: growing = temporary setback, declining = broken)
        rev_g = i.get("revenueGrowth")
        if rev_g is not None:
            if rev_g > 0.30:
                score += 25
            elif rev_g > 0.15:
                score += 15
            elif rev_g > 0.05:
                score += 5
            elif rev_g < -0.15:
                score -= 30  # significant revenue decline = structurally broken
            elif rev_g < 0:
                score -= 10
            info["rev_growth"] = f"{rev_g * 100:+.1f}%"

        # Gross margin (business quality indicator)
        gm = i.get("grossMargins")
        if gm is not None:
            if gm > 0.60:
                score += 15
            elif gm > 0.40:
                score += 10
            elif gm > 0.20:
                score += 5
            elif gm < 0:
                score -= 20  # negative gross margin = fundamentally broken pricing
            info["gross_margin"] = f"{gm * 100:.1f}%"

        # Analyst recommendation mean (1=strong buy, 5=strong sell)
        rec = i.get("recommendationMean")
        if rec is not None:
            if rec < 2.0:
                score += 12
            elif rec < 2.5:
                score += 6
            elif rec > 3.5:
                score -= 12
            info["analyst_rating"] = f"{rec:.1f}/5"

        # Debt/equity — high leverage = fragile in a downturn
        de = i.get("debtToEquity")
        if de is not None:
            if de > 300:
                score -= 20
            elif de > 150:
                score -= 10
            elif de > 80:
                score -= 3
            info["debt_equity"] = f"{de:.0f}"

        # Cash runway for money-losers
        fcf = i.get("freeCashflow")
        cash = i.get("totalCash")
        if fcf is not None and fcf < 0 and cash is not None and cash > 0:
            quarterly_burn = abs(fcf) / 4
            if quarterly_burn > 0:
                qrun = cash / quarterly_burn
                if qrun < 2:
                    score -= 35  # near-term bankruptcy risk
                elif qrun < 4:
                    score -= 15
                info["cash_quarters"] = f"{qrun:.1f}Q"

        info["_score"] = round(score, 1)
    except Exception as exc:
        logger.debug("Fundamental score failed for %s: %s", underlying, exc)

    return score, info


def _news_sentiment(underlying: str) -> tuple[float, list[str]]:
    """
    Score recent news headline sentiment using keyword matching.
    Returns (sentiment_score, list_of_headlines).
    Range: roughly -20 to +20.
    """
    POSITIVE = {
        "beat", "beats", "exceeded", "surged", "rally", "upgrade", "outperform",
        "record", "profit", "strong", "raised", "boost", "growth", "breakthrough",
        "wins", "awarded", "partnership", "rebound", "recovery", "bullish",
    }
    NEGATIVE = {
        "miss", "missed", "below", "downgrade", "sell", "cut", "loss", "losses",
        "decline", "warning", "fraud", "SEC", "lawsuit", "investigation",
        "bankruptcy", "layoffs", "layoff", "weak", "disappointing", "recall",
        "default", "delisted", "concern", "probe",
    }
    score = 0.0
    headlines: list[str] = []
    try:
        import yfinance as yf
        news = yf.Ticker(underlying).news or []
        for n in news[:12]:
            title = (
                n.get("title")
                or (n.get("content") or {}).get("title")
                or ""
            )
            if not title:
                continue
            headlines.append(title)
            words = set(title.lower().split())
            pos = len(words & POSITIVE)
            neg = len(words & NEGATIVE)
            score += (pos - neg) * 2.5
    except Exception as exc:
        logger.debug("News sentiment failed for %s: %s", underlying, exc)

    return round(score, 1), headlines


def _ai_verdict(underlying: str, context: dict) -> dict:
    """
    Call Claude (haiku — cheap, fast) to rule whether this is a genuine
    beaten-down opportunity or a broken company to skip.

    context keys: beaten_down, dte_earn, fundamental_score, fund_info,
                  news_score, headlines, be_move, spot

    Returns: {"verdict": "buy"|"skip"|"weak", "reason": str, "confidence": int}
    Falls back to {"verdict": "neutral", ...} if no API key or API error.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"verdict": "neutral", "reason": "no ANTHROPIC_API_KEY — quantitative scoring only"}

    try:
        import anthropic, json

        fi = context.get("fund_info", {})
        hdl = context.get("headlines", [])[:6]
        headlines_text = "\n".join(f"  - {h}" for h in hdl) if hdl else "  (none)"

        prompt = f"""You are a professional options analyst. Decide whether to buy 18-month LEAPS calls on {underlying}.

DATA:
  Price vs 52-week high:  {context.get('beaten_down', 0):.0f}% below high
  Days to next earnings:  {context.get('dte_earn', 'unknown')}
  Revenue growth:         {fi.get('rev_growth', 'N/A')}
  Gross margin:           {fi.get('gross_margin', 'N/A')}
  Analyst rating:         {fi.get('analyst_rating', 'N/A')} (1=strong buy, 5=sell)
  Debt/equity:            {fi.get('debt_equity', 'N/A')}
  Cash runway:            {fi.get('cash_quarters', 'profitable or N/A')}
  Fundamental score:      {context.get('fundamental_score', 0):+.0f}/50
  News sentiment:         {context.get('news_score', 0):+.0f}
  Breakeven move needed:  {context.get('be_move', 0):+.1f}%
Recent headlines:
{headlines_text}

QUESTION: Is this company beaten-down due to *temporary* factors (buying opp for LEAPS)
or is it *fundamentally broken* (avoid)?

Reply ONLY in valid JSON — no markdown, no explanation outside JSON:
{{"verdict": "buy" | "skip" | "weak", "reason": "<15 words max>", "confidence": <0-100>}}

"buy"  = strong opportunity, worth significant allocation
"weak" = possible but uncertain, small allocation only
"skip" = broken fundamentals or excessive risk, do not buy"""

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        if "{" in text:
            text = text[text.index("{"):text.rindex("}") + 1]
        result = json.loads(text)
        result.setdefault("confidence", 50)
        logger.info("AI verdict %s: %s (confidence=%d)", underlying,
                    result["verdict"], result["confidence"])
        return result
    except Exception as exc:
        logger.warning("AI verdict failed for %s: %s", underlying, exc)
        return {"verdict": "neutral", "reason": str(exc)[:80], "confidence": 50}


def _score_candidate(underlying: str, leap: dict, ask: float) -> dict:
    """
    Full intelligence pipeline for one candidate. Returns enriched candidate dict
    with composite score and AI verdict.
    """
    breakeven = leap["strike"] + ask
    be_move = (breakeven / leap["spot"] - 1) * 100

    # Layer 1: catalyst signals (beaten-down + earnings)
    bd, cat, dte_earn = _catalyst_signals(underlying)

    # Layer 2: fundamentals
    fund_score, fund_info = _fundamental_score(underlying)

    # Layer 3: news sentiment
    news_score, headlines = _news_sentiment(underlying)

    # Composite quantitative score (before AI)
    quant_score = bd + cat - be_move + fund_score * 0.5 + news_score * 0.5

    # Layer 4: AI verdict
    verdict = _ai_verdict(underlying, {
        "beaten_down": bd,
        "dte_earn": dte_earn,
        "fundamental_score": fund_score,
        "fund_info": fund_info,
        "news_score": news_score,
        "headlines": headlines,
        "be_move": be_move,
        "spot": leap["spot"],
    })

    # Apply AI multiplier to final score
    v = verdict.get("verdict", "neutral")
    if v == "skip":
        final_score = -9999  # eliminated
    elif v == "weak":
        final_score = quant_score * 0.4
    elif v == "buy":
        conf_bonus = verdict.get("confidence", 50) / 10  # 0-10 pts
        final_score = quant_score + conf_bonus
    else:  # neutral — pure quant
        final_score = quant_score

    return {
        **leap,
        "ask": ask,
        "be_move": be_move,
        "cost": ask * 100,
        "beaten_down": bd,
        "catalyst": cat > 0,
        "dte_earn": dte_earn,
        "fundamental_score": fund_score,
        "fund_info": fund_info,
        "news_score": news_score,
        "headlines": headlines,
        "quant_score": quant_score,
        "verdict": v,
        "verdict_reason": verdict.get("reason", ""),
        "ai_confidence": verdict.get("confidence", 50),
        "score": final_score,
    }


# ── live options execution on Alpaca paper ──────────────────────────────────

def manage_option_positions(broker) -> dict:
    """
    Manage existing option positions:
    - Take-profit at OPTIONS_PROFIT_TARGET
    - Stop-loss at OPTIONS_STOP_LOSS
    - Exit any position where AI now rates the underlying as "skip"
      (fundamentals or news changed since we bought)
    """
    closed_tp, closed_sl, closed_ai = [], [], []
    for p in broker.get_option_positions():
        plpc = p["unrealized_plpc"]
        if plpc >= OPTIONS_PROFIT_TARGET:
            if broker.close_option(p["symbol"]):
                closed_tp.append(p["symbol"])
                logger.info("OPTION TP  %s +%.0f%% -> closed", p["symbol"], plpc * 100)
            continue
        if plpc <= -OPTIONS_STOP_LOSS:
            if broker.close_option(p["symbol"]):
                closed_sl.append(p["symbol"])
                logger.info("OPTION SL  %s %.0f%% -> closed", p["symbol"], plpc * 100)
            continue
        # Re-evaluate: if AI now says "skip" on the underlying, exit the position
        underlying = p["symbol"][:_underlying_len(p["symbol"])]
        if underlying:
            try:
                bd, cat, dte_earn = _catalyst_signals(underlying)
                fund_score, fund_info = _fundamental_score(underlying)
                news_score, headlines = _news_sentiment(underlying)
                verdict = _ai_verdict(underlying, {
                    "beaten_down": bd, "dte_earn": dte_earn,
                    "fundamental_score": fund_score, "fund_info": fund_info,
                    "news_score": news_score, "headlines": headlines,
                    "be_move": 0, "spot": 0,
                })
                if verdict.get("verdict") == "skip":
                    reason = verdict.get("reason", "AI: fundamentals deteriorated")
                    logger.info("OPTION EXIT %s — AI skip: %s (pl=%.1f%%)",
                                p["symbol"], reason, plpc * 100)
                    if broker.close_option(p["symbol"]):
                        closed_ai.append({"symbol": p["symbol"], "reason": reason,
                                          "pl_pct": plpc * 100})
            except Exception as exc:
                logger.debug("Re-eval failed for %s: %s", underlying, exc)
    return {"tp": closed_tp, "sl": closed_sl, "ai_exit": closed_ai}


def run_options_cycle(broker) -> dict:
    """
    Full options cycle:
    1. Manage existing positions (TP/SL).
    2. Score all candidates through the full intelligence pipeline.
    3. Eliminate AI-flagged "skip" names.
    4. Conviction-weighted allocation of remaining budget.
    5. Top-up pass to minimise idle cash.
    """
    acct = broker.get_account()
    equity = acct["equity"]
    cash = acct.get("cash", 0.0)
    budget = equity * OPTIONS_BUDGET_PCT

    mgmt = manage_option_positions(broker)

    existing = broker.get_option_positions()
    held_underlyings = {p["symbol"][:_underlying_len(p["symbol"])] for p in existing}
    options_value = sum(p["market_value"] for p in existing)
    cash_room = max(cash * 0.97, 0.0)
    available = min(budget - options_value, cash_room)
    slots = OPTIONS_MAX_POSITIONS - len(existing)

    bought: list[dict] = []
    skipped: list[dict] = []

    if available < 100:
        logger.info("Options: no cash/budget room (available $%.0f, slots %d)", available, slots)
        return {"bought": bought, "skipped": skipped, **mgmt,
                "options_value": options_value, "budget": budget, "equity": equity}

    # Score every candidate through the full pipeline
    candidates: list[dict] = []
    logger.info("Options: scoring %d candidates through intelligence pipeline...",
                len(OPTIONS_UNDERLYINGS))
    for u in OPTIONS_UNDERLYINGS:
        held = u in held_underlyings
        leap = broker.find_leaps(u, OPTIONS_TARGET_OTM_PCT, OPTIONS_MIN_DTE)
        if not leap:
            continue
        ask = broker.option_quote(leap["symbol"])
        if not ask or ask <= 0:
            continue
        c = _score_candidate(u, leap, ask)
        c["held"] = held
        if c["score"] <= -9000:
            skipped.append({"symbol": u, "reason": c["verdict_reason"],
                            "fundamental_score": c["fundamental_score"],
                            "news_score": c["news_score"]})
            logger.info("SKIP %s — AI verdict: skip (%s)", u, c["verdict_reason"])
        else:
            candidates.append(c)

    candidates.sort(key=lambda c: c["score"], reverse=True)
    new_names = [c for c in candidates if not c["held"]][:max(slots, 0)]

    bought_by_symbol: dict[str, dict] = {}

    def _record_buy(c: dict, qty: int) -> None:
        spent = qty * c["cost"]
        rec = bought_by_symbol.get(c["symbol"])
        if rec:
            rec["qty"] += qty
            rec["cost"] += spent
        else:
            bought_by_symbol[c["symbol"]] = {
                "symbol": c["symbol"], "qty": qty, "cost": spent,
                "be_move": c["be_move"], "beaten_down": c["beaten_down"],
                "catalyst": c["catalyst"], "verdict": c["verdict"],
                "verdict_reason": c["verdict_reason"],
                "ai_confidence": c["ai_confidence"],
                "fundamental_score": c["fundamental_score"],
                "news_score": c["news_score"],
                "fund_info": c["fund_info"],
            }

    # Pass 1: conviction-weighted allocation to new names
    if new_names and slots > 0:
        floor = min(c["score"] for c in new_names)
        weights = [c["score"] - floor + 1.0 for c in new_names]
        wsum = sum(weights) or 1.0
        for c, w in zip(new_names, weights):
            name_budget = available * (w / wsum)
            qty = int(name_budget // c["cost"])
            if qty < 1:
                qty = 1 if c["cost"] <= available else 0
            if qty < 1:
                continue
            if broker.buy_option(c["symbol"], qty):
                available -= qty * c["cost"]
                _record_buy(c, qty)

    # Pass 2: top-up pass — spend leftover cash one contract at a time
    toppable = sorted(
        [c for c in candidates if c["cost"] <= available],
        key=lambda c: (-c["score"], c["cost"]),
    )
    progress = True
    while available >= 50 and toppable and progress:
        progress = False
        for c in toppable:
            if c["cost"] <= available:
                if broker.buy_option(c["symbol"], 1):
                    available -= c["cost"]
                    _record_buy(c, 1)
                    progress = True
        toppable = [c for c in toppable if c["cost"] <= available]

    bought = list(bought_by_symbol.values())
    return {"bought": bought, "skipped": skipped, **mgmt,
            "options_value": options_value, "budget": budget, "equity": equity}


def _underlying_len(occ: str) -> int:
    import re
    m = re.match(r"^([A-Z]{1,6})\d{6}[CP]\d{8}$", occ)
    return len(m.group(1)) if m else 0


def print_options_run(summary: dict) -> None:
    print(f"\n{'='*70}")
    print("  OPTIONS / LEAPS RUN — live on Alpaca paper")
    print(f"{'='*70}")
    print(f"  Equity ${summary['equity']:,.0f}   "
          f"Budget ${summary['budget']:,.0f} ({OPTIONS_BUDGET_PCT*100:.0f}%)   "
          f"In options ${summary['options_value']:,.0f}")
    if summary.get("tp"):
        print(f"  TOOK PROFIT: {', '.join(summary['tp'])}")
    if summary.get("sl"):
        print(f"  STOPPED OUT: {', '.join(summary['sl'])}")
    if summary.get("ai_exit"):
        print(f"  AI EXITED (fundamentals changed):")
        for x in summary["ai_exit"]:
            print(f"    x {x['symbol']:<24} {x['pl_pct']:+.1f}%  reason: {x['reason']}")

    if summary.get("skipped"):
        print(f"\n  SKIPPED (AI ruled out):")
        for s in summary["skipped"]:
            fi = ""
            if s.get("fundamental_score", 0) < -10:
                fi = f"  [fund: {s['fundamental_score']:+.0f}]"
            print(f"    x {s['symbol']:<8} {s['reason']}{fi}")

    if summary["bought"]:
        print(f"\n  BOUGHT — full reasoning:")
        for b in summary["bought"]:
            fi = b.get("fund_info", {})
            verdict_tag = {"buy": "AI:BUY", "weak": "AI:WEAK", "neutral": "QUANT"}.get(
                b.get("verdict", "neutral"), "QUANT"
            )
            print(f"\n    {b['symbol']}")
            print(f"      {verdict_tag} (conf={b.get('ai_confidence',50)}%)  {b.get('verdict_reason','')}")
            print(f"      Qty x{b['qty']}  Cost ${b['cost']:,.0f}  "
                  f"B/E {b['be_move']:+.1f}%  "
                  f"{b.get('beaten_down', 0):.0f}% off 52w high  "
                  f"{'EARNINGS CATALYST' if b.get('catalyst') else 'no catalyst'}")
            if fi:
                parts = []
                if "rev_growth" in fi: parts.append(f"RevG {fi['rev_growth']}")
                if "gross_margin" in fi: parts.append(f"GM {fi['gross_margin']}")
                if "analyst_rating" in fi: parts.append(f"Analyst {fi['analyst_rating']}")
                if "cash_quarters" in fi: parts.append(f"Cash {fi['cash_quarters']}")
                if parts:
                    print(f"      Fundamentals: {' | '.join(parts)}")
    else:
        print("\n  No new positions opened this run.")
    print(f"{'='*70}\n")
