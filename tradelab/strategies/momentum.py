from __future__ import annotations

import pandas as pd

from tradelab.config import MOMENTUM_LOOKBACK, MOMENTUM_TOP_N
from tradelab.strategies.base import Strategy


class MomentumStrategy(Strategy):
    """
    Rank by trailing N-day return daily. Hold top-K equal-weight.
    Exit anything that drops out of the top K.
    """

    name = "momentum"

    def __init__(
        self,
        lookback: int = MOMENTUM_LOOKBACK,
        top_n: int = MOMENTUM_TOP_N,
    ):
        self.lookback = lookback
        self.top_n = top_n

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = pd.DataFrame({sym: df["close"] for sym, df in bars.items()}).sort_index()
        returns = closes.pct_change(self.lookback)

        weight = 1.0 / self.top_n
        targets = pd.DataFrame(0.0, index=returns.index, columns=returns.columns)

        for i in range(self.lookback, len(returns)):
            row = returns.iloc[i].dropna()
            if row.empty:
                continue
            top = row.nlargest(self.top_n).index.tolist()
            targets.loc[targets.index[i], top] = weight

        return targets
