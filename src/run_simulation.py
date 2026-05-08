"""
Polymarket simulation runner.

Steps:
  1. Scan the Polymarket leaderboard for traders with >= 70% win rate
     and >= 5 trades/day.  Results are saved to copy_list.json.
  2. Start the copy trader in simulation mode, monitoring all discovered
     traders simultaneously.  Paper P&L is tracked in sim_positions.json.

All configuration is via environment variables (or a .env file).

Env vars
--------
  # Scanner
  MIN_WIN_RATE          Minimum win rate to qualify (default: 0.70)
  MIN_DAILY_TRADES      Minimum avg trades/day to qualify (default: 5.0)
  MIN_RESOLVED_TRADES   Minimum resolved positions for statistical validity (default: 10)
  MAX_CANDIDATES        How many leaderboard entries to evaluate (default: 200)
  COPY_LIST_PATH        Where to save/load qualified trader list (default: copy_list.json)

  # Simulation
  TRADE_SIZE_USDC       Simulated USDC per copied trade (default: 10.0)
  MAX_TRADE_SIZE_USDC   Hard cap per trade (default: 50.0)
  POLL_INTERVAL_SECONDS How often to check for new trades (default: 30)
  STATE_FILE            Seen-tx-hash persistence file (default: copy_trader_state.json)
  SIM_FILE              Simulated positions file (default: sim_positions.json)
  SUMMARY_INTERVAL      Seconds between P&L summary logs (default: 300)

  # Extra targets always included (comma-separated usernames or 0x addresses)
  EXTRA_TARGETS         e.g. "kch123,0xABC..."
"""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("Invalid value for %s; using default %.2f", name, default)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def run_scanner() -> list[str]:
    from polymarket_trader_scanner import TraderScanner  # noqa: PLC0415

    scanner = TraderScanner(
        min_win_rate=_env_float("MIN_WIN_RATE", 0.70),
        min_daily_trades=_env_float("MIN_DAILY_TRADES", 5.0),
        min_resolved_trades=_env_int("MIN_RESOLVED_TRADES", 10),
        max_candidates=_env_int("MAX_CANDIDATES", 200),
        copy_list_path=os.getenv("COPY_LIST_PATH", "copy_list.json"),
    )

    qualifying = scanner.scan()

    if not qualifying:
        logger.warning(
            "Scanner found no qualifying traders. "
            "Try lowering MIN_WIN_RATE or MIN_DAILY_TRADES."
        )
    else:
        scanner.save(qualifying)
        logger.info(
            "Top traders found:\n%s",
            "\n".join(
                f"  {t.username} ({t.address}) | win={t.win_rate:.1%} | "
                f"daily={t.avg_daily_trades:.1f} | pnl=${t.total_pnl_usdc:+.2f}"
                for t in qualifying
            ),
        )

    return [t.address for t in qualifying]


def load_existing_copy_list() -> list[str]:
    """Load addresses from a previously saved copy_list.json if it exists."""
    from polymarket_trader_scanner import TraderScanner  # noqa: PLC0415
    scanner = TraderScanner(copy_list_path=os.getenv("COPY_LIST_PATH", "copy_list.json"))
    traders = scanner.load()
    return [t["address"] for t in traders if t.get("address")]


def resolve_extra_targets(raw: str) -> list[str]:
    from polymarket_copy_trader import resolve_address  # noqa: PLC0415
    addresses = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            addresses.append(resolve_address(token))
        except ValueError as exc:
            logger.warning("Could not resolve extra target %r: %s", token, exc)
    return addresses


def main() -> None:
    skip_scan = os.getenv("SKIP_SCAN", "false").lower() in ("true", "1", "yes")

    if skip_scan:
        logger.info("SKIP_SCAN=true – loading copy list from disk.")
        target_addresses = load_existing_copy_list()
    else:
        target_addresses = run_scanner()

    # Always include any manually specified extra targets
    extra_raw = os.getenv("EXTRA_TARGETS", "kch123")
    if extra_raw:
        extras = resolve_extra_targets(extra_raw)
        for addr in extras:
            if addr not in target_addresses:
                target_addresses.append(addr)
                logger.info("Added extra target: %s", addr)

    if not target_addresses:
        logger.error("No targets to monitor. Exiting.")
        sys.exit(1)

    logger.info("Starting simulation with %d target(s).", len(target_addresses))

    from polymarket_copy_trader import PolymarketCopyTrader  # noqa: PLC0415

    trader = PolymarketCopyTrader(
        targets=target_addresses,
        trade_size_usdc=_env_float("TRADE_SIZE_USDC", 10.0),
        max_trade_size_usdc=_env_float("MAX_TRADE_SIZE_USDC", 50.0),
        poll_interval=_env_int("POLL_INTERVAL_SECONDS", 30),
        state_file=os.getenv("STATE_FILE", "copy_trader_state.json"),
        sim_file=os.getenv("SIM_FILE", "sim_positions.json"),
        summary_interval=_env_int("SUMMARY_INTERVAL", 300),
        dry_run=True,
        private_key="",       # not needed in simulation mode
    )
    trader.run()


if __name__ == "__main__":
    main()
