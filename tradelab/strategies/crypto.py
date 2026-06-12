from __future__ import annotations

import numpy as np
import pandas as pd

from tradelab.strategies.base import Strategy


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


class CryptoMeanReversionStrategy(Strategy):
    """
    Mean reversion on crypto:
    - Buy when RSI(period) < entry_threshold
    - Exit when RSI > exit_threshold
    - Optional trend filter: only enter when price > MA(trend_period)
      (catches dip-buys in up-trends; skips oversold in death spirals)
    - Equal-weight across all active positions
    """

    name = "crypto_mean_reversion"

    def __init__(
        self,
        rsi_period: int = 3,
        entry_threshold: float = 25,
        exit_threshold: float = 55,
        trend_period: int = 50,
        use_trend_filter: bool = True,
    ):
        self.rsi_period = rsi_period
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.trend_period = trend_period
        self.use_trend_filter = use_trend_filter

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        rsi_df = closes.apply(lambda col: _rsi(col, self.rsi_period))
        ma_df = closes.rolling(self.trend_period, min_periods=1).mean() if self.use_trend_filter else None

        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        in_position: dict[str, bool] = {sym: False for sym in closes.columns}

        for i in range(1, len(closes)):
            date = closes.index[i]
            prev_date = closes.index[i - 1]

            for sym in closes.columns:
                rsi_prev = rsi_df.loc[prev_date, sym]
                rsi_cur = rsi_df.loc[date, sym]
                price = closes.loc[date, sym]

                if pd.isna(rsi_prev) or pd.isna(rsi_cur) or pd.isna(price):
                    in_position[sym] = False
                    continue

                in_trend = True
                if self.use_trend_filter and ma_df is not None:
                    ma_val = ma_df.loc[date, sym]
                    in_trend = not pd.isna(ma_val) and price > ma_val * 0.85  # allow slight below MA

                if in_position[sym]:
                    if rsi_cur > self.exit_threshold:
                        in_position[sym] = False
                        targets.loc[date, sym] = 0.0
                    else:
                        targets.loc[date, sym] = 1.0
                else:
                    if rsi_prev < self.entry_threshold and in_trend:
                        in_position[sym] = True
                        targets.loc[date, sym] = 1.0

        row_sums = targets.sum(axis=1).replace(0, np.nan)
        return targets.div(row_sums, axis=0).fillna(0.0)


class CryptoMomentumStrategy(Strategy):
    """
    Momentum on crypto:
    - Rank by N-day return
    - Hold top-K coins
    - Trend filter: only hold coins trading above their MA
    """

    name = "crypto_momentum"

    def __init__(
        self,
        lookback: int = 7,
        top_n: int = 3,
        trend_period: int = 30,
    ):
        self.lookback = lookback
        self.top_n = top_n
        self.trend_period = trend_period

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = pd.DataFrame({s: df["close"] for s, df in bars.items()}).sort_index()
        returns = closes.pct_change(self.lookback)
        ma = closes.rolling(self.trend_period, min_periods=1).mean()

        weight = 1.0 / self.top_n
        targets = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)

        for i in range(self.lookback, len(closes)):
            date = closes.index[i]
            row = returns.iloc[i].dropna()
            price_row = closes.iloc[i]
            ma_row = ma.iloc[i]

            # Only consider coins above their trend MA
            above_ma = {s: price_row[s] > ma_row[s] * 0.9 for s in row.index if s in ma_row.index}
            row_filtered = row[[s for s in row.index if above_ma.get(s, True)]]

            if row_filtered.empty:
                continue
            top = row_filtered.nlargest(min(self.top_n, len(row_filtered))).index.tolist()
            targets.loc[date, top] = weight

        return targets
