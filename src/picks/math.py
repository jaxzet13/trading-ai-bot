"""Betting math: odds conversion, no-vig fair prices, edge, Kelly."""
from __future__ import annotations

from typing import Iterable, List


def american_to_decimal(american: float) -> float:
    if american >= 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def decimal_to_american(decimal: float) -> int:
    if decimal >= 2.0:
        return int(round((decimal - 1.0) * 100))
    return int(round(-100.0 / (decimal - 1.0)))


def american_to_prob(american: float) -> float:
    return 1.0 / american_to_decimal(american)


def no_vig_probs(american_prices: Iterable[float]) -> List[float]:
    """Strip the book's vig by normalizing implied probabilities to sum to 1."""
    implied = [american_to_prob(p) for p in american_prices]
    total = sum(implied)
    if total <= 0:
        return implied
    return [p / total for p in implied]


def edge(fair_prob: float, offered_american: float) -> float:
    """Expected value per $1 staked. Positive = +EV."""
    return fair_prob * american_to_decimal(offered_american) - 1.0


def kelly(fair_prob: float, offered_american: float, fraction: float = 0.25) -> float:
    """Fractional Kelly stake as a fraction of bankroll. Clamped at 0."""
    dec = american_to_decimal(offered_american)
    b = dec - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - fair_prob
    full = (b * fair_prob - q) / b
    return max(0.0, full * fraction)
