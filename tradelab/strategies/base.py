from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """
    Base interface for all TradeLab strategies.
    """

    name: str = "base"

    @abstractmethod
    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Given OHLCV bars keyed by symbol, return a DataFrame indexed by date
        with columns per symbol containing target weights (float, sum may be < 1).
        Positive weight = long. 0 = flat.
        """
        ...

    def __repr__(self) -> str:
        return f"<Strategy: {self.name}>"
