"""Scan every in-season sport and rank picks by market edge.

For each game/prop market we:
  1. Collect the best available price across books ("line shop").
  2. Compute a consensus no-vig fair probability across all books that
     quoted the market (averaging after stripping vig per book).
  3. edge = fair_prob * best_decimal - 1.  Positive = +EV vs the market.

This catches *pricing* edges (a book mis-priced relative to the rest of the
market). It does not model sharp/public splits — that would require a paid
data source.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from .math import american_to_prob, edge as edge_fn, kelly, no_vig_probs
from .odds import OddsAPI, OddsAPIError

log = logging.getLogger(__name__)


@dataclass
class Pick:
    sport: str
    event: str            # "Away @ Home"
    commence_time: str    # ISO8601
    market: str           # h2h / spreads / totals / player_points / ...
    selection: str        # "Lakers", "Over 224.5", "LeBron James Over 27.5 pts"
    best_book: str
    best_price: int       # american
    fair_prob: float      # 0..1
    edge: float           # EV per $1, e.g. 0.042 = +4.2%
    books_count: int
    kelly_frac: float = 0.0
    event_id: str = ""
    correlation_key: str = ""  # same key = same game/prop; used to de-dup parlays
    extra: Dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.selection} ({self.market}) @ {self.best_price:+d} [{self.best_book}]"


def _event_label(ev: Dict) -> str:
    return f"{ev.get('away_team','?')} @ {ev.get('home_team','?')}"


def _selection_label(market_key: str, outcome: Dict, home: str, away: str) -> str:
    name = outcome.get("name") or outcome.get("description") or "?"
    point = outcome.get("point")
    desc = outcome.get("description")
    if market_key == "h2h":
        return name
    if market_key == "spreads":
        sign = "+" if point is not None and point > 0 else ""
        return f"{name} {sign}{point}"
    if market_key == "totals":
        return f"{name} {point}"
    # player props: outcome.name = "Over"/"Under", description = player
    if desc:
        return f"{desc} {name} {point}".strip()
    return f"{name} {point}".strip() if point is not None else name


def _group_key(market_key: str, outcome: Dict, home: str, away: str) -> Tuple:
    """Identify 'the same market outcome' across different books."""
    name = outcome.get("name")
    desc = outcome.get("description")
    point = outcome.get("point")
    return (market_key, desc, name, point)


def _correlation_key(event_id: str, market_key: str, outcome: Dict) -> str:
    """Legs that share this key are correlated (same game / same player prop)."""
    desc = outcome.get("description") or ""
    if desc:
        return f"{event_id}:{desc}"  # same player across o/u = correlated
    return event_id                   # any two legs from same game = correlated


def _picks_from_event(sport_key: str, event: Dict) -> List[Pick]:
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    ev_label = _event_label(event)
    ev_id = event.get("id", "")
    commence = event.get("commence_time", "")

    # Flatten: per (market, outcome_key) -> list of (book, american_price, opposite_price)
    # We need opposite_price to strip vig at that book.
    per_outcome: Dict[Tuple, List[Tuple[str, int, Optional[int]]]] = {}

    for book in event.get("bookmakers", []):
        book_title = book.get("title", book.get("key", "?"))
        for market in book.get("markets", []):
            mkey = market.get("key", "")
            outcomes = market.get("outcomes", [])
            # Build index so we can find the opposite side within the same book+market.
            # For 2-way markets (h2h/spreads/totals/props with Over/Under) we pair sides.
            for i, out in enumerate(outcomes):
                price = out.get("price")
                if price is None:
                    continue
                opposite_price: Optional[int] = None
                # Match opposite by shared point for spreads/totals/props, by different name for h2h.
                if mkey == "h2h":
                    for other in outcomes:
                        if other is out:
                            continue
                        opposite_price = other.get("price")
                        break
                else:
                    target_point = out.get("point")
                    target_desc = out.get("description")
                    for other in outcomes:
                        if other is out:
                            continue
                        if other.get("point") == target_point and other.get("description") == target_desc:
                            opposite_price = other.get("price")
                            break
                key = _group_key(mkey, out, home, away)
                per_outcome.setdefault(key, []).append((book_title, int(price), opposite_price))

    picks: List[Pick] = []
    for key, quotes in per_outcome.items():
        mkey = key[0]
        # Consensus fair probability: average no-vig prob from each book that
        # quoted both sides.
        fair_probs: List[float] = []
        for _, my_price, opp_price in quotes:
            if opp_price is None:
                # single-sided quote -> fall back to raw implied prob
                fair_probs.append(american_to_prob(my_price))
                continue
            a, _ = no_vig_probs([my_price, opp_price])
            fair_probs.append(a)
        if not fair_probs:
            continue
        fair_prob = sum(fair_probs) / len(fair_probs)

        # Best price across books on our side.
        best_book, best_price, _ = max(quotes, key=lambda q: q[1])  # most +American = best
        # For negative-only markets the above still picks the closest-to-zero (best) value.
        ev = edge_fn(fair_prob, best_price)
        if ev <= 0:
            continue

        # Synthesize a representative outcome dict for labeling.
        # We saved the key tuple as (market, desc, name, point).
        outcome_for_label = {
            "description": key[1],
            "name": key[2],
            "point": key[3],
        }
        sel = _selection_label(mkey, outcome_for_label, home, away)
        picks.append(
            Pick(
                sport=sport_key,
                event=ev_label,
                commence_time=commence,
                market=mkey,
                selection=sel,
                best_book=best_book,
                best_price=best_price,
                fair_prob=fair_prob,
                edge=ev,
                books_count=len(quotes),
                kelly_frac=kelly(fair_prob, best_price),
                event_id=ev_id,
                correlation_key=_correlation_key(ev_id, mkey, outcome_for_label),
            )
        )

    return picks


def scan_all(
    api: OddsAPI,
    include_props: bool = True,
    min_books: int = 3,
    min_edge: float = 0.01,
    sports_filter: Optional[Iterable[str]] = None,
) -> List[Pick]:
    """Scan every in-season sport. Returns picks sorted by edge desc."""
    sports = api.sports()
    if sports_filter:
        wanted = set(sports_filter)
        sports = [s for s in sports if s.get("key") in wanted]

    all_picks: List[Pick] = []
    for sp in sports:
        sport_key = sp.get("key")
        if not sport_key or sp.get("has_outrights"):
            continue

        # Game markets
        try:
            games = api.odds(sport_key)
        except OddsAPIError as e:
            log.warning("skip %s odds: %s", sport_key, e)
            continue
        for g in games:
            all_picks.extend(_picks_from_event(sport_key, g))

        # Player props — one request per event, so can burn quota. Gate on include_props.
        if include_props:
            prop_markets = api.prop_markets_for(sport_key)
            if prop_markets:
                for g in games:
                    try:
                        ev = api.event_odds(sport_key, g["id"], prop_markets)
                    except OddsAPIError as e:
                        # 404/422 are common when a book doesn't offer props for an event
                        log.debug("skip props %s/%s: %s", sport_key, g.get("id"), e)
                        continue
                    all_picks.extend(_picks_from_event(sport_key, ev))

    # Filter + sort
    filtered = [p for p in all_picks if p.books_count >= min_books and p.edge >= min_edge]
    filtered.sort(key=lambda p: p.edge, reverse=True)
    return filtered


def only_today(picks: Iterable[Pick]) -> List[Pick]:
    today = datetime.now(timezone.utc).date()
    out: List[Pick] = []
    for p in picks:
        try:
            t = datetime.fromisoformat(p.commence_time.replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.date() == today:
            out.append(p)
    return out
