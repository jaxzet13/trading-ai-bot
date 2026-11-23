"""Kalshi public market data for tennis (no keys needed to read)."""
from __future__ import annotations

import math
import time

import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
# head-to-head match winner series: each event = one match with exactly two markets (one per player), exactly one
# of which settles YES
MATCH_SERIES = ["KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXITFMATCH", "KXITFWMATCH"]
TAKER_RATE = 0.07


def fee(price: float, contracts: float = 1, rate: float = TAKER_RATE) -> float:
    """Kalshi taker fee for one order: ceil to the cent of rate x C x P x (1-P) (tennis series: 'quadratic')."""
    return math.ceil(rate * contracts * price * (1 - price) * 100 - 1e-9) / 100


def get(path, params=None, tries=4, session=requests):
    for i in range(tries):
        try:
            r = session.get(f"{BASE}{path}", params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(1.5 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def open_markets(series, session=requests):
    """Every open market of a series (paged)."""
    out, cursor = [], None
    while True:
        p = {"series_ticker": series, "status": "open", "limit": 1000}
        if cursor:
            p["cursor"] = cursor
        d = get("/markets", p, session=session)
        out += d.get("markets", [])
        cursor = d.get("cursor")
        if not cursor:
            return out


def top_of_book(m):
    """The prices and sizes a taker could hit now: yes/no ask and bid in dollars, sizes in contracts."""
    return {"ticker": m["ticker"], "event": m["event_ticker"], "player": m.get("yes_sub_title"),
            "yes_ask": _f(m.get("yes_ask_dollars")), "yes_ask_size": _f(m.get("yes_ask_size_fp")),
            "yes_bid": _f(m.get("yes_bid_dollars")), "yes_bid_size": _f(m.get("yes_bid_size_fp")),
            "no_ask": _f(m.get("no_ask_dollars")), "no_bid": _f(m.get("no_bid_dollars")),
            "volume": _f(m.get("volume_fp")), "close": m.get("close_time"), "status": m.get("status")}
