"""Sportsbook promo conversion: turn sign-up bonus bets into cash by hedging the other side.

Three promo shapes cover almost every US offer:
  bonus     - a bonus bet: stake is NOT returned if it wins.   Hedge H = B*(o1-1)/o2, profit = B*(o1-1)*(o2-1)/o2
  qualifier - a small cash bet you must place to unlock the bonus (you lose ~the vig on it when hedged)
  bet_back  - cash bet Q refunded as bonus bets worth c*Q if it loses.  Hedge H = Q*(o1-c)/o2, profit = Q*(o1-1) - H
o1 / o2 are decimal odds on the promo side and the hedge side. c is the expected conversion of a bonus bet (~0.70).

Offers below were collected from sportsbook promo roundups in October 2026. Availability and terms vary by state
and change weekly: check the book's own terms page. 21+, one account per person, your own identity only.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


def american_to_decimal(a: float) -> float:
    return 1 + (a / 100 if a > 0 else 100 / -a)


def convert_bonus(bonus: float, promo_american: float, hedge_american: float) -> dict:
    o1, o2 = american_to_decimal(promo_american), american_to_decimal(hedge_american)
    hedge = bonus * (o1 - 1) / o2
    profit = hedge * (o2 - 1)
    return {"hedge_stake": hedge, "profit": profit, "conversion_pct": profit / bonus * 100, "capital_needed": hedge}


def convert_bet_back(stake: float, promo_american: float, hedge_american: float, c: float = 0.70) -> dict:
    o1, o2 = american_to_decimal(promo_american), american_to_decimal(hedge_american)
    hedge = stake * (o1 - c) / o2
    profit = stake * (o1 - 1) - hedge
    return {"hedge_stake": hedge, "profit": profit, "conversion_pct": profit / stake * 100, "capital_needed": stake + hedge}


def qualifier_cost(stake: float, a1: float = -110, a2: float = -110) -> float:
    """Expected loss of a hedged qualifying cash bet (the vig)."""
    o1, o2 = american_to_decimal(a1), american_to_decimal(a2)
    hedge = stake * o1 / o2
    return stake - (stake * o1 - hedge)  # loss if promo side wins == loss if hedge side wins


@dataclass
class Offer:
    book: str
    headline: str
    shape: str            # bonus | bet_back | matched_daily
    cash_in: float        # cash you must stake to unlock
    bonus_value: float    # face value of bonus bets / FanCash
    token_size: float     # largest single bonus token (sets the hedge capital needed)
    days: int             # days to complete
    notes: str


OFFERS = [
    Offer("DraftKings", "Bet $5, get $200 in bonus bets", "bonus", 5, 200, 25, 2, "Usually issued as 8 x $25 tokens. Also a 20% deposit match up to $1,000 in most states (skip it, the playthrough eats it)."),
    Offer("FanDuel", "Bet $5 a day for 7 days, get $50 bonus bets each day ($350)", "bonus", 35, 350, 50, 8, "Bonus arrives within 72 hours of each qualifying bet settling."),
    Offer("bet365", "Bet $10, get $200 in bonus bets, win or lose", "bonus", 10, 200, 50, 2, "Minimum odds -500 on the qualifier. Bonus-bet stake excluded from returns. Token split varies."),
    Offer("Fanatics", "Bet up to $100 a day for 10 days, get matching FanCash ($1,000)", "matched_daily", 1000, 1000, 100, 10, "Highest value offer this month. FanCash is paid win or lose. Needs ~$200 rolling: the day's $100 qualifier plus its hedge."),
    Offer("Caesars", "Up to $250 in Bet Resets (5 x $50)", "bet_back", 250, 250, 50, 5, "Each losing bet up to $50 refunded as a bonus bet. Worth roughly 28% of the stake when hedged."),
    Offer("BetMGM", "First bet back up to $1,500 in bonus bets", "bet_back", 1500, 1500, 1500, 2, "Scales with your capital. With $100 it is worth ~$28; with $1,500 ~$415. Do it last, once the other promos have built the bankroll."),
]


def offer_value(o: Offer, c: float = 0.70, bankroll: float = 100.0) -> dict:
    """Expected cash from an offer with sensible defaults: bonus tokens at +400 hedged at -500, qualifiers at -110."""
    if o.shape == "bonus":
        conv = convert_bonus(o.token_size, 400, -500)
        value = o.bonus_value * conv["conversion_pct"] / 100 - qualifier_cost(o.cash_in)
        capital = o.cash_in + conv["capital_needed"]
    elif o.shape == "matched_daily":
        conv = convert_bonus(o.token_size, 400, -500)
        value = o.bonus_value * conv["conversion_pct"] / 100 - qualifier_cost(o.cash_in)
        capital = o.token_size * 2 + conv["capital_needed"]
    else:  # bet_back: limited by bankroll
        stake = min(o.cash_in, max(bankroll, o.token_size if o.token_size < o.cash_in else bankroll))
        bb = convert_bet_back(stake if o.token_size >= o.cash_in else o.token_size, -110, -110, c)
        n_tokens = 1 if o.token_size >= o.cash_in else o.cash_in / o.token_size
        value = bb["profit"] * n_tokens
        capital = bb["capital_needed"]
    return {**asdict(o), "expected_cash": value, "capital_needed": capital}


def promo_plan(bankroll: float = 100.0) -> list[dict]:
    rows = [offer_value(o, bankroll=bankroll) for o in OFFERS]
    # order: cheapest capital first, so the bankroll snowballs
    rows.sort(key=lambda r: r["capital_needed"])
    return rows


if __name__ == "__main__":
    import pandas as pd
    print(convert_bonus(25, 400, -500))
    print(convert_bet_back(100, -110, -110))
    df = pd.DataFrame(promo_plan(100))
    print(df[["book", "headline", "cash_in", "bonus_value", "capital_needed", "expected_cash", "days"]].round(0).to_string())
    print("total expected", round(df.expected_cash.sum()))
