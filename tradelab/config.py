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

CRYPTO_UNIVERSE: list[str] = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "AVAX-USD",
    "ADA-USD", "DOT-USD", "LINK-USD", "LTC-USD", "XRP-USD",
]

# High-beta stocks: 3-10% daily swings — ideal for mean reversion
HIGH_VOL_UNIVERSE: list[str] = [
    "TSLA", "NVDA", "AMD", "MSTR", "COIN",
    "SMCI", "PLTR", "RKLB", "IONQ", "HOOD",
    "SOFI", "RIVN", "LCID", "SOUN", "UPST",
    "MARA", "RIOT", "CLSK", "APP", "DKNG",
]

BENCHMARK: str = "SPY"
CRYPTO_BENCHMARK: str = "BTC-USD"

# ---------------------------------------------------------------------------
# Strategy params
# ---------------------------------------------------------------------------
# Defaults set from the 132-config parameter sweep (see sweep.py /
# backtest_output/sweep_results.csv): best risk-adjusted configs over
# the trailing 2 years.
MOMENTUM_LOOKBACK: int = 3       # trailing days for return ranking
MOMENTUM_TOP_N: int = 3          # number of top stocks to hold
MOMENTUM_MIN_HOLD_DAYS: int = 1

RSI_PERIOD: int = 5
RSI_ENTRY: float = 25.0          # buy when RSI < this
RSI_EXIT: float = 60.0           # sell when RSI > this

# ---------------------------------------------------------------------------
# Risk params
# ---------------------------------------------------------------------------
# AGGRESSIVE_MODE deploys the full account across positions instead of the
# conservative 2%/position cap. Set AGGRESSIVE_MODE=false in .env to revert.
AGGRESSIVE_MODE: bool = os.getenv("AGGRESSIVE_MODE", "true").lower() == "true"

MAX_POSITION_PCT: float = 0.34 if AGGRESSIVE_MODE else 0.02
MAX_OPEN_POSITIONS: int = 3
DRAWDOWN_HALT_PCT: float = 0.10  # halt if drawdown >= 10% (kept in both modes)

# Simulated leverage for backtests (1.0 = none). Alpaca paper accounts allow
# up to 2x intraday margin on equities.
BACKTEST_LEVERAGE: float = float(os.getenv("BACKTEST_LEVERAGE", "1.0"))

# ---------------------------------------------------------------------------
# Backtest params
# ---------------------------------------------------------------------------
BACKTEST_YEARS: int = 3          # 3 years captures both bull and bear cycles
SLIPPAGE_PCT: float = 0.001      # 0.1% per side (crypto spreads are wider)
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
# Defaults to a zero-setup SQLite file in the repo. Point DATABASE_URL at
# Postgres in .env for production use (e.g. postgresql://user:pw@host/db).
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///tradelab.db")

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
MARKET_OPEN_HOUR: int = 9
MARKET_OPEN_MINUTE: int = 31     # 1 min after open to get fills
TIMEZONE: str = "America/New_York"
