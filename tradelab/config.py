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

# Crypto traded live via Alpaca paper (24/7, higher volatility than stocks).
# Smaller position cap applied to account for 5-15% daily swings.
CRYPTO_TRADING_UNIVERSE: list[str] = [
    "BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD",
]
CRYPTO_MAX_POSITION_PCT: float = float(os.getenv("CRYPTO_MAX_POSITION_PCT", "0.08"))  # 8% per crypto name

BENCHMARK: str = "SPY"
CRYPTO_BENCHMARK: str = "BTC-USD"

# ---------------------------------------------------------------------------
# Strategy params
# ---------------------------------------------------------------------------
# Defaults set from 152-config mega-sweep (see fast_sweep.py /
# backtest_output/mega_sweep.csv). ATR Impulse Breakout on the
# high-volatility universe won: Sharpe 1.51, CAGR +48%, $100k→$333k in 3yr.
MOMENTUM_LOOKBACK: int = 3
MOMENTUM_TOP_N: int = 3
MOMENTUM_MIN_HOLD_DAYS: int = 1

RSI_PERIOD: int = 5
RSI_ENTRY: float = 25.0
RSI_EXIT: float = 60.0

# ---------------------------------------------------------------------------
# Risk params
# ---------------------------------------------------------------------------
# AGGRESSIVE_MODE deploys the full account across positions instead of the
# conservative 2%/position cap. Set AGGRESSIVE_MODE=false in .env to revert.
AGGRESSIVE_MODE: bool = os.getenv("AGGRESSIVE_MODE", "true").lower() == "true"

MAX_POSITION_PCT: float = 0.20 if AGGRESSIVE_MODE else 0.02  # 20% max per position
MAX_OPEN_POSITIONS: int = 15   # 12 stock slots + 3 crypto slots

# Fraction of equity to actually deploy into positions each cycle. 0.95 keeps a
# small cash buffer for fees/slippage while putting the rest to work. The old
# behaviour left ~half the account idle, which capped returns.
TARGET_DEPLOYMENT: float = float(os.getenv("TARGET_DEPLOYMENT", "0.95"))

# ---------------------------------------------------------------------------
# Prop-firm / funded-account challenge rules
# ---------------------------------------------------------------------------
# These match common prop firm challenges (FTMO-style). Adjust in .env to
# match your specific firm's rules.
DRAWDOWN_HALT_PCT: float = float(os.getenv("MAX_TOTAL_LOSS_PCT", "0.075"))   # 7.5% → buffer before 8% limit
DAILY_LOSS_LIMIT_PCT: float = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.04"))  # 4% max daily loss
SYMBOL_LOSS_LIMIT_PCT: float = float(os.getenv("SYMBOL_LOSS_LIMIT_PCT", "0.03"))  # 3% of account per symbol
PROFIT_TARGET_PCT: float = float(os.getenv("PROFIT_TARGET_PCT", "0.07"))     # 7% to pass challenge

# ---------------------------------------------------------------------------
# Partial take-profit + trailing stop
# ---------------------------------------------------------------------------
# When a position is up PARTIAL_TP_PCT, sell PARTIAL_TP_FRACTION of it to bank
# the gain, then let the rest ride protected by a trailing stop. The freed cash
# is redeployed into fresh signals on the next cycle. Backtest showed selling
# the WHOLE position at +1.5% cuts profit ~85% (kills the big winners), so we
# only take half and let the remainder run.
PARTIAL_TP_PCT: float = float(os.getenv("PARTIAL_TP_PCT", "0.015"))       # +1.5% triggers it
PARTIAL_TP_FRACTION: float = float(os.getenv("PARTIAL_TP_FRACTION", "0.5"))  # sell half
TRAILING_STOP_PCT: float = float(os.getenv("TRAILING_STOP_PCT", "0.03"))  # close remainder if it falls 3% from peak

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
