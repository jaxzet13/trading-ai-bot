from __future__ import annotations

import numpy as np
import pandas as pd

from tradelab.config import RSI_PERIOD, RSI_ENTRY, RSI_EXIT
from tradelab.strategies.base import Strategy


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


class MeanReversionStrategy(Strategy):
    """
    Buy when RSI(period) < entry_threshold.
    Exit when RSI > exit_threshold OR price gains take_profit_pct.
    Equal-weight across active positions.
    """

    name = "mean_reversion"

    def __init__(
        self,
        rsi_period: int = RSI_PERIOD,
        entry_threshold: float = RSI_ENTRY,
        exit_threshold: float = RSI_EXIT,
        take_profit_pct: float = 1.0,    # 1.0 = disabled; set e.g. 0.05 for 5% TP
    ):
        self.rsi_period = rsi_period
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.take_profit_pct = take_profit_pct

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = pd.DataFrame({sym: df["close"] for sym, df in bars.items()}).sort_index()
        rsi_df = closes.apply(lambda col: _rsi(col, self.rsi_period))

        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        in_position: dict[str, bool] = {sym: False for sym in closes.columns}
        entry_price: dict[str, float] = {}

        for i in range(1, len(closes)):
            date = closes.index[i]
            prev_date = closes.index[i - 1]

            for sym in closes.columns:
                rsi_prev = rsi_df.loc[prev_date, sym]
                rsi_cur = rsi_df.loc[date, sym]
                price = closes.loc[date, sym]

                if pd.isna(rsi_prev) or pd.isna(rsi_cur) or pd.isna(price):
                    targets.loc[date, sym] = 0.0
                    in_position[sym] = False
                    continue

                if in_position[sym]:
                    ep = entry_price.get(sym, price)
                    at_tp = (price - ep) / ep >= self.take_profit_pct
                    if rsi_cur > self.exit_threshold or at_tp:
                        in_position[sym] = False
                        targets.loc[date, sym] = 0.0
                    else:
                        targets.loc[date, sym] = 1.0
                else:
                    if rsi_prev < self.entry_threshold:
                        in_position[sym] = True
                        entry_price[sym] = price
                        targets.loc[date, sym] = 1.0

        row_sums = targets.sum(axis=1).replace(0, np.nan)
        targets = targets.div(row_sums, axis=0).fillna(0.0)

        return targets
