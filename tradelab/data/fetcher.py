from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

from tradelab.config import UNIVERSE, BENCHMARK, BACKTEST_YEARS

logger = logging.getLogger(__name__)


def fetch_bars(
    symbols: list[str],
    start: Optional[date] = None,
    end: Optional[date] = None,
    years: int = BACKTEST_YEARS,
) -> dict[str, pd.DataFrame]:
    """
    Download daily OHLCV bars for each symbol via yfinance.
    Returns a dict of {symbol: DataFrame with columns [open,high,low,close,volume]}.
    """
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=years * 365 + 30)

    start_str = start.isoformat()
    end_str = end.isoformat()

    logger.info("Fetching bars for %d symbols from %s to %s", len(symbols), start_str, end_str)

    all_syms = list(set(symbols))
    raw = yf.download(
        tickers=all_syms,
        start=start_str,
        end=end_str,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    result: dict[str, pd.DataFrame] = {}

    if isinstance(raw.columns, pd.MultiIndex):
        for sym in all_syms:
            try:
                df = raw.xs(sym, axis=1, level=1).copy()
                df.columns = [c.lower() for c in df.columns]
                df = df.dropna(subset=["close"])
                df.index = pd.to_datetime(df.index)
                result[sym] = df
            except KeyError:
                logger.warning("No data returned for %s", sym)
    else:
        # Single symbol
        sym = all_syms[0]
        df = raw.copy()
        df.columns = [c.lower() for c in df.columns]
        df = df.dropna(subset=["close"])
        df.index = pd.to_datetime(df.index)
        result[sym] = df

    logger.info("Fetched data for %d/%d symbols", len(result), len(all_syms))
    return result


def fetch_universe(years: int = BACKTEST_YEARS) -> dict[str, pd.DataFrame]:
    return fetch_bars(UNIVERSE, years=years)


def fetch_benchmark(years: int = BACKTEST_YEARS) -> pd.DataFrame:
    data = fetch_bars([BENCHMARK], years=years)
    return data.get(BENCHMARK, pd.DataFrame())


def build_close_matrix(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Align all symbols' close prices into a single DataFrame."""
    closes = {sym: df["close"] for sym, df in bars.items()}
    return pd.DataFrame(closes).sort_index()
