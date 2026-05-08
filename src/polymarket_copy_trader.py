"""
Polymarket copy trading engine.

Monitors a target user's trades on Polymarket and replicates them on your account.

Required env vars:
  POLYMARKET_PRIVATE_KEY  - Hex private key for your Polygon wallet (with 0x prefix)
  TARGET_USERNAME         - Polymarket username to copy (default: kch123)
  TRADE_SIZE_USDC         - Fixed USDC amount per copied trade (default: 10.0)
  MAX_TRADE_SIZE_USDC     - Hard cap per trade (default: 50.0)
  POLL_INTERVAL_SECONDS   - How often to check for new trades (default: 30)
  STATE_FILE              - Path to persist seen trade IDs (default: copy_trader_state.json)
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "polymarket-copy-trader/1.0"})


@dataclass
class Trade:
    tx_hash: str
    timestamp: int
    condition_id: str
    token_id: str
    outcome: str
    side: str  # "Buy" or "Sell"
    price: float
    shares: float
    usdc_amount: float
    market_title: str


# ---------------------------------------------------------------------------
# User resolution
# ---------------------------------------------------------------------------

def resolve_address(username: str) -> str:
    """
    Resolve a Polymarket username to a wallet address.
    Tries the Gamma profile search API first, then falls back to treating
    the input as a raw address.
    """
    if username.startswith("0x") and len(username) == 42:
        return username.lower()

    for url in [
        f"{GAMMA_API}/profiles?username={username}",
        f"{GAMMA_API}/users?search={username}",
        f"{DATA_API}/users?username={username}",
    ]:
        try:
            resp = _SESSION.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Handle list or dict responses
                if isinstance(data, list) and data:
                    entry = data[0]
                elif isinstance(data, dict):
                    entry = data
                else:
                    continue

                address = (
                    entry.get("proxyWallet")
                    or entry.get("address")
                    or entry.get("walletAddress")
                    or entry.get("proxy_wallet")
                )
                if address:
                    logger.info("Resolved %s → %s", username, address)
                    return address.lower()
        except requests.RequestException as exc:
            logger.debug("Address lookup failed at %s: %s", url, exc)

    raise ValueError(
        f"Could not resolve '{username}' to a Polymarket wallet address. "
        "Set TARGET_USERNAME to a 0x... address if the username lookup fails."
    )


# ---------------------------------------------------------------------------
# Activity fetching
# ---------------------------------------------------------------------------

def fetch_activity(address: str, limit: int = 50) -> list[dict]:
    url = f"{DATA_API}/activity"
    params = {
        "user": address,
        "limit": limit,
        "offset": 0,
        "sortBy": "TIMESTAMP",
        "sortDirection": "DESC",
    }
    resp = _SESSION.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json() or []


def parse_trade(raw: dict) -> Optional[Trade]:
    """Parse a raw activity dict into a Trade. Returns None for non-trade events."""
    side = raw.get("type", "")
    if side not in ("Buy", "Sell"):
        return None  # skip redeems, etc.

    tx_hash = raw.get("transactionHash") or raw.get("id") or ""
    if not tx_hash:
        return None

    try:
        return Trade(
            tx_hash=tx_hash,
            timestamp=int(raw.get("timestamp", 0)),
            condition_id=raw.get("conditionId", ""),
            token_id=raw.get("asset") or raw.get("tokenId", ""),
            outcome=raw.get("outcome", ""),
            side=side,
            price=float(raw.get("price", 0)),
            shares=float(raw.get("size") or raw.get("shares", 0)),
            usdc_amount=float(raw.get("amount", 0)),
            market_title=raw.get("title") or raw.get("name", ""),
        )
    except (TypeError, ValueError) as exc:
        logger.debug("Could not parse trade %s: %s", raw, exc)
        return None


# ---------------------------------------------------------------------------
# Market / token helpers
# ---------------------------------------------------------------------------

def get_token_id(condition_id: str, outcome: str) -> Optional[str]:
    """Fetch the CLOB token ID for a given market outcome."""
    try:
        resp = _SESSION.get(f"{CLOB_API}/markets/{condition_id}", timeout=10)
        resp.raise_for_status()
        tokens = resp.json().get("tokens", [])
        for tok in tokens:
            if tok.get("outcome", "").lower() == outcome.lower():
                return tok.get("token_id")
    except requests.RequestException as exc:
        logger.warning("Could not fetch token ID for %s/%s: %s", condition_id, outcome, exc)
    return None


def is_market_active(condition_id: str) -> bool:
    """Return True if the market is still open for trading."""
    try:
        resp = _SESSION.get(f"{CLOB_API}/markets/{condition_id}", timeout=10)
        resp.raise_for_status()
        return bool(resp.json().get("active", False))
    except requests.RequestException:
        return False


# ---------------------------------------------------------------------------
# Order execution
# ---------------------------------------------------------------------------

def build_clob_client(private_key: str):
    """Initialise and return an authenticated py-clob-client ClobClient."""
    from py_clob_client.client import ClobClient  # noqa: PLC0415

    client = ClobClient(
        host=CLOB_API,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=0,  # EOA (standard wallet)
    )
    # Derive API credentials from the private key
    creds = client.create_or_derive_api_key()
    client.set_api_creds(creds)
    logger.info("CLOB client authenticated (address: %s)", client.get_address())
    return client


def execute_copy_trade(client, trade: Trade, size_usdc: float, slippage: float = 0.02) -> bool:
    """
    Place a market order copying the given trade.

    Uses Fill-Or-Kill so we either get filled at an acceptable price or skip.
    Returns True if the order was accepted.
    """
    from py_clob_client.clob_types import OrderArgs, OrderType, Side  # noqa: PLC0415

    if not is_market_active(trade.condition_id):
        logger.info("Skipping %s – market is closed.", trade.market_title)
        return False

    # Prefer the token_id from the activity feed; fall back to CLOB lookup
    token_id = trade.token_id or get_token_id(trade.condition_id, trade.outcome)
    if not token_id:
        logger.warning("Cannot find token ID for %s %s", trade.condition_id, trade.outcome)
        return False

    side = Side.BUY if trade.side == "Buy" else Side.SELL

    # Compute share count from fixed USDC size at the observed price
    if trade.price <= 0 or trade.price >= 1:
        logger.warning("Skipping trade with invalid price %.4f", trade.price)
        return False

    shares = round(size_usdc / trade.price, 2)

    # Apply slippage tolerance to the limit price
    if side == Side.BUY:
        limit_price = min(round(trade.price * (1 + slippage), 4), 0.99)
    else:
        limit_price = max(round(trade.price * (1 - slippage), 4), 0.01)

    logger.info(
        "Placing %s order | market: %s | outcome: %s | price: %.4f | shares: %.2f | ~$%.2f USDC",
        trade.side,
        trade.market_title or trade.condition_id,
        trade.outcome,
        limit_price,
        shares,
        size_usdc,
    )

    try:
        order_args = OrderArgs(
            token_id=token_id,
            price=limit_price,
            size=shares,
            side=side,
        )
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.FOK)

        if response.get("success") or response.get("orderID"):
            logger.info("Order placed successfully: %s", response)
            return True
        else:
            logger.warning("Order rejected: %s", response)
            return False

    except Exception as exc:
        logger.error("Order execution failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def load_state(path: str) -> set[str]:
    """Load previously seen transaction hashes from disk."""
    if os.path.exists(path):
        try:
            with open(path) as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def save_state(path: str, seen: set[str]) -> None:
    # Keep only the most recent 10 000 hashes to bound file size
    with open(path, "w") as f:
        json.dump(list(seen)[-10_000:], f)


# ---------------------------------------------------------------------------
# Main copy-trader
# ---------------------------------------------------------------------------

class PolymarketCopyTrader:
    def __init__(
        self,
        private_key: str,
        target_username: str,
        trade_size_usdc: float,
        max_trade_size_usdc: float,
        poll_interval: int,
        state_file: str,
        slippage: float = 0.02,
        dry_run: bool = False,
    ):
        self.trade_size_usdc = trade_size_usdc
        self.max_trade_size_usdc = max_trade_size_usdc
        self.poll_interval = poll_interval
        self.state_file = state_file
        self.slippage = slippage
        self.dry_run = dry_run

        self.target_address = resolve_address(target_username)
        self.seen_hashes: set[str] = load_state(state_file)

        if not dry_run:
            self.clob_client = build_clob_client(private_key)
        else:
            self.clob_client = None
            logger.info("DRY RUN mode – no real orders will be placed.")

        logger.info(
            "Copy trader ready | target: %s | size: $%.2f USDC | poll: %ds",
            self.target_address,
            self.trade_size_usdc,
            self.poll_interval,
        )

    def _seed_seen(self) -> None:
        """On first run, mark current activity as seen so we don't replay history."""
        if self.seen_hashes:
            return  # already seeded from state file
        logger.info("Seeding seen-trade set from current activity (no trades will be copied on startup).")
        try:
            for raw in fetch_activity(self.target_address):
                tx = raw.get("transactionHash") or raw.get("id") or ""
                if tx:
                    self.seen_hashes.add(tx)
            save_state(self.state_file, self.seen_hashes)
        except requests.RequestException as exc:
            logger.warning("Could not seed seen set: %s", exc)

    def poll_once(self) -> int:
        """Fetch latest activity and copy any new trades. Returns number of trades copied."""
        try:
            raw_trades = fetch_activity(self.target_address)
        except requests.RequestException as exc:
            logger.warning("Activity fetch failed: %s", exc)
            return 0

        new_trades = []
        for raw in raw_trades:
            trade = parse_trade(raw)
            if trade is None:
                continue
            if trade.tx_hash in self.seen_hashes:
                continue
            new_trades.append(trade)

        if not new_trades:
            return 0

        logger.info("Found %d new trade(s) to copy.", len(new_trades))

        # Process oldest first
        new_trades.sort(key=lambda t: t.timestamp)

        copied = 0
        for trade in new_trades:
            self.seen_hashes.add(trade.tx_hash)

            capped_size = min(self.trade_size_usdc, self.max_trade_size_usdc)

            if self.dry_run:
                logger.info(
                    "[DRY RUN] Would copy: %s %s @ %.4f (~$%.2f USDC)",
                    trade.side, trade.outcome, trade.price, capped_size,
                )
                copied += 1
            else:
                success = execute_copy_trade(
                    self.clob_client, trade, capped_size, self.slippage
                )
                if success:
                    copied += 1

        save_state(self.state_file, self.seen_hashes)
        return copied

    def run(self) -> None:
        self._seed_seen()
        logger.info("Starting copy-trade loop. Press Ctrl-C to stop.")
        while True:
            try:
                copied = self.poll_once()
                if copied:
                    logger.info("Copied %d trade(s) this cycle.", copied)
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                logger.info("Shutting down.")
                break
            except Exception as exc:
                logger.error("Unexpected error: %s", exc, exc_info=True)
                time.sleep(self.poll_interval)
