"""Build +EV parlays from scanned singles.

Assumes legs are independent once we require distinct `correlation_key`s
(same game / same player props are excluded from a parlay). Real-world
correlation is obviously not zero — treat these as a starting point, not
gospel.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import List

from .math import american_to_decimal, decimal_to_american
from .scanner import Pick


@dataclass
class Parlay:
    legs: List[Pick]
    combined_decimal: float
    combined_american: int
    fair_prob: float
    edge: float

    @property
    def label(self) -> str:
        return " + ".join(f"{p.selection}" for p in self.legs)


def build_parlays(
    picks: List[Pick],
    sizes: tuple = (2, 3),
    pool_size: int = 12,
    top_n: int = 5,
    min_edge: float = 0.05,
) -> List[Parlay]:
    """Pick top-`pool_size` singles, try every 2- and 3-leg combo whose legs
    are not correlated, rank by combined edge."""
    pool = picks[:pool_size]
    out: List[Parlay] = []

    for size in sizes:
        for combo in combinations(pool, size):
            keys = {p.correlation_key for p in combo}
            if len(keys) < size:
                continue  # correlated legs — skip
            dec = 1.0
            prob = 1.0
            for leg in combo:
                dec *= american_to_decimal(leg.best_price)
                prob *= leg.fair_prob
            ev = prob * dec - 1.0
            if ev < min_edge:
                continue
            out.append(
                Parlay(
                    legs=list(combo),
                    combined_decimal=dec,
                    combined_american=decimal_to_american(dec),
                    fair_prob=prob,
                    edge=ev,
                )
            )

    out.sort(key=lambda p: p.edge, reverse=True)
    return out[:top_n]
