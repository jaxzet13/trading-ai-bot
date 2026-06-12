# TradeLab — Paper Trading System

A Python paper-trading system using Alpaca's paper API with momentum and mean-reversion strategies.

## Easiest setup (Windows, no terminal)

1. Download the project as a ZIP: https://github.com/jaxzet13/trading-ai-bot/archive/refs/heads/claude/tradelab-paper-trading-g5kyl8.zip
2. Right-click the ZIP → **Extract All**
3. Open the extracted folder and double-click **`Start-Dashboard.bat`**

It sets up everything automatically and opens the dashboard in your browser. (Requires Python from https://python.org — tick "Add Python to PATH" when installing.)

## Setup (9 steps)

The database defaults to a zero-setup SQLite file (`tradelab.db`) — no Postgres needed to get started.

1. **Clone** this repo and `cd trading-ai-bot`
2. **Create a virtualenv**: `python3.11 -m venv .venv && source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
3. **Install deps**: `pip install -r requirements.txt`
4. **Copy env file**: `cp .env.example .env`
5. **Get Alpaca paper keys**: sign up at https://app.alpaca.markets, switch to Paper, copy API Key + Secret into `.env`
6. **Run backtests** (no keys needed): `python -m tradelab.main backtest all` — equity PNGs land in `backtest_output/`
7. **Start live paper trading**: `python -m tradelab.main run`
8. **View dashboard** (in a second terminal): `python -m tradelab.main dashboard`
9. **Monthly report**: `python -m tradelab.main report`

To use PostgreSQL instead of SQLite, set `DATABASE_URL=postgresql://user:pw@host:5432/tradelab` in `.env`.

## CLI Commands

| Command | Description |
|---|---|
| `python -m tradelab.main backtest [momentum\|mean_reversion\|all]` | Run backtest |
| `python -m tradelab.main run` | Start daily scheduler |
| `python -m tradelab.main dashboard` | Live terminal dashboard |
| `python -m tradelab.main resume` | Clear a risk halt |
| `python -m tradelab.main report` | Monthly trade summary |

## Risk Rules

- Aggressive mode (default): full equity deployed across 3 position slots. Set `AGGRESSIVE_MODE=false` in `.env` for conservative 2%-per-position sizing.
- Max **3 open positions** at once
- **Auto-halt** if drawdown from peak >= 10% — clears with `python -m tradelab.main resume`

## Safety

The system asserts `"paper"` is in `ALPACA_PAPER_BASE_URL` at startup and crashes if not — you cannot accidentally connect to live trading.

## Strategies

Defaults tuned via a 132-config parameter sweep (`sweep.py`):

- **Momentum**: Rank 20 large-caps by 3-day return daily, hold top 3 equal-weight
- **Mean Reversion**: Buy when RSI(5) < 25, exit when RSI > 60 — backtests at Sharpe 1.29, +27% CAGR over the trailing 2 years
