"""
Polymarket copy trading engine.

Supports two modes:
  Simulation (dry_run=True)  – logs trades and tracks paper P&L; no wallet needed.
  Live       (dry_run=False) – places real orders via the Polymarket CLOB API.

Multiple target addresses are monitored concurrently in a single polling loop.
Targets are loaded from copy_list.json (written by polymarket_trader_scanner).

Required env vars for live mode only:
  POLYMARKET_PRIVATE_KEY  – Hex private key for your Polygon wallet (with 0x prefix).
                            The wallet must hold USDC on Polygon and have approved
                            Polymarket's CTF Exchange contract.
"""

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
CHAIN_ID = 137

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "polymarket-copy-trader/1.0"})


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    tx_hash: str
    timestamp: int
    condition_id: str
    token_id: str
    outcome: str
    side: str           # "Buy" or "Sell"
    price: float
    shares: float
    usdc_amount: float
    market_title: str
    source_address: str  # which tracked trader made this trade


@dataclass
class SimPosition:
    id: str
    source_address: str
    condition_id: str
    outcome: str
    entry_price: float
    shares: float
    usdc_invested: float
    market_title: str
    opened_at: str
    status: str = "open"   # open | won | lost | sold
    pnl_usdc: float = 0.0
    closed_at: str = ""


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get(url: str, params: dict | None = None) -> Optional[list | dict]:
    try:
        resp = _SESSION.get(url, params=params, timeout=15)
        if resp.status_code in (404, 429):
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def fetch_activity(address: str, limit: int = 50) -> list[dict]:
    data = _get(
        f"{DATA_API}/activity",
        params={"user": address, "limit": limit, "offset": 0,
                "sortBy": "TIMESTAMP", "sortDirection": "DESC"},
    )
    return data if isinstance(data, list) else []


def fetch_market(condition_id: str) -> Optional[dict]:
    return _get(f"{GAMMA_API}/markets/{condition_id}")


def get_token_id(condition_id: str, outcome: str) -> Optional[str]:
    data = _get(f"{CLOB_API}/markets/{condition_id}")
    if not data:
        return None
    for tok in data.get("tokens", []):
        if tok.get("outcome", "").lower() == outcome.lower():
            return tok.get("token_id")
    return None


def is_market_active(condition_id: str) -> bool:
    data = _get(f"{CLOB_API}/markets/{condition_id}")
    return bool(data and data.get("active", False))


# ---------------------------------------------------------------------------
# Username → address resolution
# ---------------------------------------------------------------------------

def resolve_address(username: str) -> str:
    if username.startswith("0x") and len(username) == 42:
        return username.lower()
    for url in [
        f"{GAMMA_API}/profiles?username={username}",
        f"{GAMMA_API}/users?search={username}",
        f"{DATA_API}/users?username={username}",
    ]:
        data = _get(url)
        if data is None:
            continue
        entry = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else None
        if not entry:
            continue
        addr = (
            entry.get("proxyWallet") or entry.get("address")
            or entry.get("walletAddress") or entry.get("proxy_wallet")
        )
        if addr:
            logger.info("Resolved %s → %s", username, addr)
            return addr.lower()
    raise ValueError(
        f"Could not resolve '{username}' to a wallet address. "
        "Pass a 0x... address directly if the username lookup fails."
    )


# ---------------------------------------------------------------------------
# Trade parsing
# ---------------------------------------------------------------------------

def parse_trade(raw: dict, source_address: str) -> Optional[Trade]:
    side = raw.get("type", "")
    if side not in ("Buy", "Sell"):
        return None
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
            source_address=source_address,
        )
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Live order execution (only used when dry_run=False)
# ---------------------------------------------------------------------------

def build_clob_client(private_key: str):
    from py_clob_client.client import ClobClient  # noqa: PLC0415
    client = ClobClient(host=CLOB_API, key=private_key, chain_id=CHAIN_ID, signature_type=0)
    client.set_api_creds(client.create_or_derive_api_key())
    logger.info("CLOB client authenticated (address: %s)", client.get_address())
    return client


def execute_copy_trade(client, trade: Trade, size_usdc: float, slippage: float = 0.02) -> bool:
    from py_clob_client.clob_types import OrderArgs, OrderType, Side  # noqa: PLC0415

    if not is_market_active(trade.condition_id):
        logger.info("Skipping %s – market closed.", trade.market_title)
        return False

    token_id = trade.token_id or get_token_id(trade.condition_id, trade.outcome)
    if not token_id:
        logger.warning("No token ID for %s/%s", trade.condition_id, trade.outcome)
        return False

    if not (0 < trade.price < 1):
        logger.warning("Invalid price %.4f – skipping.", trade.price)
        return False

    shares = round(size_usdc / trade.price, 2)
    side = Side.BUY if trade.side == "Buy" else Side.SELL
    limit_price = (
        min(round(trade.price * (1 + slippage), 4), 0.99)
        if side == Side.BUY
        else max(round(trade.price * (1 - slippage), 4), 0.01)
    )

    logger.info(
        "[LIVE] %s %s @ %.4f | %s | %.2f shares (~$%.2f)",
        trade.side, trade.outcome, limit_price,
        trade.market_title or trade.condition_id, shares, size_usdc,
    )
    try:
        signed = client.create_order(OrderArgs(token_id=token_id, price=limit_price,
                                               size=shares, side=side))
        resp = client.post_order(signed, OrderType.FOK)
        if resp.get("success") or resp.get("orderID"):
            logger.info("Order accepted: %s", resp)
            return True
        logger.warning("Order rejected: %s", resp)
        return False
    except Exception as exc:
        logger.error("Order error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Simulation tracker
# ---------------------------------------------------------------------------

class SimulationTracker:
    """
    Tracks open paper positions and settles them when markets resolve.
    Persists state to a JSON file so restarts don't lose history.
    """

    def __init__(self, path: str = "sim_positions.json", size_usdc: float = 10.0):
        self.path = path
        self.size_usdc = size_usdc
        self.positions: list[SimPosition] = self._load()

    def _load(self) -> list[SimPosition]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path) as f:
                raw = json.load(f)
            return [SimPosition(**p) for p in raw.get("positions", [])]
        except (json.JSONDecodeError, TypeError, KeyError):
            return []

    def _save(self) -> None:
        with open(self.path, "w") as f:
            json.dump({"positions": [asdict(p) for p in self.positions]}, f, indent=2)

    def open_position(self, trade: Trade) -> SimPosition:
        if not (0 < trade.price < 1):
            raise ValueError(f"Invalid price {trade.price}")
        shares = round(self.size_usdc / trade.price, 2)
        pos = SimPosition(
            id=str(uuid.uuid4()),
            source_address=trade.source_address,
            condition_id=trade.condition_id,
            outcome=trade.outcome,
            entry_price=trade.price,
            shares=shares,
            usdc_invested=self.size_usdc,
            market_title=trade.market_title,
            opened_at=datetime.now(timezone.utc).isoformat(),
        )
        self.positions.append(pos)
        self._save()
        logger.info(
            "[SIM] Opened position | %s %s @ %.4f | %d shares | $%.2f invested",
            trade.outcome, trade.market_title or trade.condition_id,
            trade.price, shares, self.size_usdc,
        )
        return pos

    def settle_open_positions(self, resolution_cache: dict) -> int:
        """
        Check all open positions against Polymarket resolution data.
        Returns number of positions settled this call.
        """
        settled = 0
        for pos in self.positions:
            if pos.status != "open":
                continue

            cid = pos.condition_id
            if cid not in resolution_cache:
                market = fetch_market(cid)
                if market and market.get("resolved"):
                    winner = (
                        market.get("winner")
                        or market.get("resolvedOutcome")
                        or market.get("winning_outcome")
                    )
                    resolution_cache[cid] = winner
                else:
                    resolution_cache[cid] = None

            winner = resolution_cache.get(cid)
            if winner is None:
                continue  # not yet resolved

            won = winner.lower() == pos.outcome.lower()
            if won:
                # Payout = shares × $1 per winning share; cost = usdc_invested
                pos.pnl_usdc = round(pos.shares * (1.0 - pos.entry_price), 2)
                pos.status = "won"
            else:
                pos.pnl_usdc = round(-pos.usdc_invested, 2)
                pos.status = "lost"

            pos.closed_at = datetime.now(timezone.utc).isoformat()
            settled += 1
            logger.info(
                "[SIM] Position settled | %s | %s → %s | P&L: $%+.2f",
                pos.market_title or cid, pos.outcome,
                "WON" if won else "LOST", pos.pnl_usdc,
            )

        if settled:
            self._save()
        return settled

    def summary(self) -> dict:
        closed = [p for p in self.positions if p.status != "open"]
        open_ = [p for p in self.positions if p.status == "open"]
        won = [p for p in closed if p.status == "won"]
        lost = [p for p in closed if p.status == "lost"]
        total_pnl = sum(p.pnl_usdc for p in closed)
        invested = sum(p.usdc_invested for p in self.positions)
        return {
            "open_positions": len(open_),
            "closed_positions": len(closed),
            "won": len(won),
            "lost": len(lost),
            "win_rate": len(won) / len(closed) if closed else 0.0,
            "total_pnl_usdc": round(total_pnl, 2),
            "total_invested_usdc": round(invested, 2),
            "roi": round(total_pnl / invested, 4) if invested else 0.0,
        }

    def print_summary(self) -> None:
        s = self.summary()
        logger.info(
            "[SIM SUMMARY] open=%d | closed=%d (won=%d, lost=%d) | "
            "win_rate=%.1f%% | P&L=$%+.2f | ROI=%.1f%%",
            s["open_positions"], s["closed_positions"],
            s["won"], s["lost"],
            s["win_rate"] * 100,
            s["total_pnl_usdc"],
            s["roi"] * 100,
        )


# ---------------------------------------------------------------------------
# State persistence (seen tx hashes)
# ---------------------------------------------------------------------------

def load_seen(path: str) -> set[str]:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def save_seen(path: str, seen: set[str]) -> None:
    with open(path, "w") as f:
        json.dump(list(seen)[-10_000:], f)


# ---------------------------------------------------------------------------
# Multi-target copy trader
# ---------------------------------------------------------------------------

class PolymarketCopyTrader:
    def __init__(
        self,
        targets: list[str],                  # list of wallet addresses to monitor
        trade_size_usdc: float = 10.0,
        max_trade_size_usdc: float = 50.0,
        poll_interval: int = 30,
        state_file: str = "copy_trader_state.json",
        sim_file: str = "sim_positions.json",
        slippage: float = 0.02,
        dry_run: bool = True,
        private_key: str = "",
        summary_interval: int = 300,         # print sim summary every N seconds
    ):
        if not targets:
            raise ValueError("targets list is empty – nothing to monitor.")

        self.targets = [t.lower() for t in targets]
        self.trade_size_usdc = min(trade_size_usdc, max_trade_size_usdc)
        self.poll_interval = poll_interval
        self.slippage = slippage
        self.dry_run = dry_run
        self.summary_interval = summary_interval

        self.seen: set[str] = load_seen(state_file)
        self.state_file = state_file
        self._resolution_cache: dict = {}
        self._last_summary_ts: float = 0.0

        if dry_run:
            self.sim = SimulationTracker(path=sim_file, size_usdc=self.trade_size_usdc)
            self.clob_client = None
            logger.info("SIMULATION mode | tracking %d trader(s) | $%.2f per trade",
                        len(self.targets), self.trade_size_usdc)
        else:
            if not private_key:
                raise ValueError("POLYMARKET_PRIVATE_KEY is required for live mode.")
            self.sim = None
            self.clob_client = build_clob_client(private_key)
            logger.info("LIVE mode | tracking %d trader(s) | $%.2f per trade",
                        len(self.targets), self.trade_size_usdc)

        logger.info("Targets: %s", self.targets)

    def _seed_seen(self) -> None:
        """Mark all existing activity as seen so we don't replay history on startup."""
        if self.seen:
            return
        logger.info("Seeding seen-trade set (existing trades will NOT be copied).")
        for addr in self.targets:
            for raw in fetch_activity(addr, limit=100):
                tx = raw.get("transactionHash") or raw.get("id") or ""
                if tx:
                    self.seen.add(tx)
        save_seen(self.state_file, self.seen)

    def poll_once(self) -> int:
        new_trades: list[Trade] = []
        for addr in self.targets:
            for raw in fetch_activity(addr, limit=50):
                trade = parse_trade(raw, source_address=addr)
                if trade and trade.tx_hash not in self.seen:
                    new_trades.append(trade)

        if not new_trades:
            return 0

        new_trades.sort(key=lambda t: t.timestamp)
        copied = 0

        for trade in new_trades:
            self.seen.add(trade.tx_hash)

            if self.dry_run:
                if trade.side == "Buy" and 0 < trade.price < 1:
                    try:
                        self.sim.open_position(trade)
                        copied += 1
                    except ValueError as exc:
                        logger.debug("Skipping sim position: %s", exc)
                else:
                    logger.info("[SIM] Skipping %s %s (non-buy or invalid price)",
                                trade.side, trade.outcome)
            else:
                if execute_copy_trade(self.clob_client, trade,
                                      self.trade_size_usdc, self.slippage):
                    copied += 1

        save_seen(self.state_file, self.seen)
        return copied

    def _maybe_settle_and_summarise(self) -> None:
        if not self.dry_run:
            return
        settled = self.sim.settle_open_positions(self._resolution_cache)
        now = time.time()
        if now - self._last_summary_ts >= self.summary_interval:
            self.sim.print_summary()
            self._last_summary_ts = now

    def run(self) -> None:
        self._seed_seen()
        logger.info("Polling loop started. Press Ctrl-C to stop.")
        while True:
            try:
                copied = self.poll_once()
                if copied:
                    logger.info("Processed %d new trade(s) this cycle.", copied)
                self._maybe_settle_and_summarise()
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                logger.info("Shutting down.")
                if self.dry_run:
                    self.sim.settle_open_positions(self._resolution_cache)
                    self.sim.print_summary()
                break
            except Exception as exc:
                logger.error("Unexpected error: %s", exc, exc_info=True)
                time.sleep(self.poll_interval)
