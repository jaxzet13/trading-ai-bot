from __future__ import annotations

import math
import pandas as pd


class KellySizer:
    """
    Fractional Kelly position sizing.

    Each bar, position size = kelly_fraction * current_equity.
    As equity compounds, every position automatically grows —
    this is what produces exponential account growth.

    Kelly fraction = (p * b - q) / b
      p = win probability, q = 1-p, b = avg_win / avg_loss
    We use half-Kelly (0.5x) by default to reduce volatility.
    """

    def __init__(self, kelly_multiplier: float = 0.5, max_fraction: float = 0.95):
        self.kelly_multiplier = kelly_multiplier
        self.max_fraction = max_fraction  # never bet more than this fraction of equity

    def fraction(self, win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> float:
        """Return the fraction of equity to deploy per position."""
        if avg_loss_pct <= 0 or win_rate <= 0:
            return 0.0
        b = avg_win_pct / avg_loss_pct          # payout ratio
        q = 1.0 - win_rate
        raw_kelly = (win_rate * b - q) / b
        adjusted = raw_kelly * self.kelly_multiplier
        return float(min(max(adjusted, 0.0), self.max_fraction))

    def from_trades(self, pnl_series: pd.Series) -> float:
        """Estimate Kelly fraction from a historical P&L series (% returns)."""
        wins = pnl_series[pnl_series > 0]
        losses = pnl_series[pnl_series < 0].abs()
        if len(wins) == 0 or len(losses) == 0:
            return 0.1
        win_rate = len(wins) / len(pnl_series)
        avg_win = wins.mean()
        avg_loss = losses.mean()
        return self.fraction(win_rate, avg_win, avg_loss)
