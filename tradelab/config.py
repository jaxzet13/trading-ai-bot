from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
UNIVERSE: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "BRK-B", "UNH", "JPM",
    "V", "MA", "XOM", "PG", "HD",
    "CVX", "ABBV", "MRK", "COST", "AVGO",
]

BENCHMARK: str = "SPY"

# ---------------------------------------------------------------------------
# Strategy params
# ---------------------------------------------------------------------------
MOMENTUM_LOOKBACK: int = 5       # trailing days for return ranking
MOMENTUM_TOP_N: int = 3          # number of top stocks to hold
MOMENTUM_MIN_HOLD_DAYS: int = 1

RSI_PERIOD: int = 14
RSI_ENTRY: float = 30.0          # buy when RSI < this
RSI_EXIT: float = 50.0           # sell when RSI > this

# ---------------------------------------------------------------------------
# Risk params
# ---------------------------------------------------------------------------
MAX_POSITION_PCT: float = 0.02   # 2% of equity per position
MAX_OPEN_POSITIONS: int = 3
DRAWDOWN_HALT_PCT: float = 0.10  # halt if drawdown >= 10%

# ---------------------------------------------------------------------------
# Backtest params
# ---------------------------------------------------------------------------
BACKTEST_YEARS: int = 2
SLIPPAGE_PCT: float = 0.0005     # 0.05% per side
COMMISSION: float = 0.0          # Alpaca is $0 commission
SHARPE_PASS_THRESHOLD: float = 1.0

# ---------------------------------------------------------------------------
# Alpaca paper trading
# ---------------------------------------------------------------------------
ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY: str = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER_BASE_URL: str = os.getenv(
    "ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets"
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "postgresql://tradelab:tradelab@localhost:5432/tradelab"
)

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
MARKET_OPEN_HOUR: int = 9
MARKET_OPEN_MINUTE: int = 31     # 1 min after open to get fills
TIMEZONE: str = "America/New_York"
