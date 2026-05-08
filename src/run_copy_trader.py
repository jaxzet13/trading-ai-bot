"""
Entry point for the Polymarket copy trading bot.

Configuration is via environment variables (or a .env file):

  POLYMARKET_PRIVATE_KEY   Required. Your Polygon wallet private key (0x...).
                           The wallet must hold USDC on Polygon and have approved
                           Polymarket's CTF Exchange contract as a spender.

  TARGET_USERNAME          Polymarket username or 0x address to copy.
                           Default: kch123

  TRADE_SIZE_USDC          Fixed USDC amount to spend per copied trade.
                           Default: 10.0

  MAX_TRADE_SIZE_USDC      Hard cap per trade (safety guardrail).
                           Default: 50.0

  POLL_INTERVAL_SECONDS    Seconds between activity checks.
                           Default: 30

  SLIPPAGE                 Maximum acceptable price slippage (0.02 = 2%).
                           Default: 0.02

  STATE_FILE               JSON file used to persist seen trade IDs.
                           Default: copy_trader_state.json

  DRY_RUN                  Set to "true" to log trades without placing orders.
                           Default: false

Prerequisites
-------------
1. Install dependencies:   pip install -r requirements.txt
2. Fund your wallet with USDC on Polygon (network ID 137).
3. Visit https://polymarket.com and approve USDC spending for your wallet.
4. Export your private key from your wallet and set POLYMARKET_PRIVATE_KEY.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        print(f"ERROR: Environment variable {name!r} is not set.", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    private_key = _require_env("POLYMARKET_PRIVATE_KEY")

    target_username = os.getenv("TARGET_USERNAME", "kch123")
    trade_size_usdc = float(os.getenv("TRADE_SIZE_USDC", "10.0"))
    max_trade_size_usdc = float(os.getenv("MAX_TRADE_SIZE_USDC", "50.0"))
    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    slippage = float(os.getenv("SLIPPAGE", "0.02"))
    state_file = os.getenv("STATE_FILE", "copy_trader_state.json")
    dry_run = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")

    from polymarket_copy_trader import PolymarketCopyTrader

    trader = PolymarketCopyTrader(
        private_key=private_key,
        target_username=target_username,
        trade_size_usdc=trade_size_usdc,
        max_trade_size_usdc=max_trade_size_usdc,
        poll_interval=poll_interval,
        state_file=state_file,
        slippage=slippage,
        dry_run=dry_run,
    )
    trader.run()


if __name__ == "__main__":
    main()
