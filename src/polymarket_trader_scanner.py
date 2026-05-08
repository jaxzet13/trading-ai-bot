"""
Polymarket trader scanner.

Scans the Polymarket leaderboard, computes win rates, and writes a
copy_list.json containing traders who meet the activity and win-rate thresholds.

Thresholds (all configurable via constructor args or env vars):
  MIN_WIN_RATE       >= 0.70 (70 %)
  MIN_DAILY_TRADES   >= 5 trades/day average
  MIN_RESOLVED       >= 10 resolved positions (statistical floor)
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "polymarket-copy-trader/1.0"})

DEFAULT_COPY_LIST_PATH = "copy_list.json"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TraderStats:
    address: str
    username: str
    win_rate: float            # fraction, e.g. 0.73
    avg_daily_trades: float
    total_pnl_usdc: float
    resolved_trades: int       # resolved positions used to compute win_rate
    total_trades: int          # all trades in the analysis window
    scanned_at: str            # ISO-8601


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get(url: str, params: dict | None = None, retries: int = 3) -> Optional[dict | list]:
    for attempt in range(retries):
        try:
            resp = _SESSION.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.debug("Rate limited at %s, waiting %ds", url, wait)
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt == retries - 1:
                logger.debug("Request failed %s: %s", url, exc)
                return None
            time.sleep(2 ** attempt)
    return None


def fetch_leaderboard(limit: int = 300, interval: str = "weekly") -> list[dict]:
    """
    Fetch top traders from the Polymarket leaderboard.
    Falls back to the daily interval if weekly returns nothing.
    """
    for iv in (interval, "daily", "monthly"):
        data = _get(
            f"{DATA_API}/leaderboard",
            params={"interval": iv, "limit": limit, "offset": 0},
        )
        if isinstance(data, list) and data:
            logger.info("Fetched %d leaderboard entries (interval=%s)", len(data), iv)
            return data
    return []


def fetch_activity(address: str, limit: int = 500) -> list[dict]:
    data = _get(
        f"{DATA_API}/activity",
        params={
            "user": address,
            "limit": limit,
            "offset": 0,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
        },
    )
    return data if isinstance(data, list) else []


def fetch_market(condition_id: str) -> Optional[dict]:
    return _get(f"{GAMMA_API}/markets/{condition_id}")


def get_winner(condition_id: str, cache: dict) -> Optional[str]:
    """Return the winning outcome string for a resolved market, or None."""
    if condition_id in cache:
        return cache[condition_id]
    market = fetch_market(condition_id)
    if not market or not market.get("resolved", False):
        cache[condition_id] = None
        return None
    winner = (
        market.get("winner")
        or market.get("resolvedOutcome")
        or market.get("winning_outcome")
    )
    cache[condition_id] = winner
    return winner


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------

def _extract_address(entry: dict) -> Optional[str]:
    raw = (
        entry.get("proxyWallet")
        or entry.get("proxy_wallet_address")
        or entry.get("address")
        or entry.get("walletAddress")
    )
    return raw.lower() if raw else None


def _extract_username(entry: dict, address: str) -> str:
    return (
        entry.get("name")
        or entry.get("pseudonym")
        or entry.get("username")
        or address[:10]
    )


def compute_stats_from_leaderboard(entry: dict) -> Optional[TraderStats]:
    """
    Fast path: use win/loss counts already on the leaderboard entry.
    Returns None if the data isn't present or doesn't meet thresholds.
    """
    address = _extract_address(entry)
    if not address:
        return None

    won = entry.get("positionsWon") or entry.get("positions_won") or 0
    lost = entry.get("positionsLost") or entry.get("positions_lost") or 0
    resolved = won + lost
    if resolved == 0:
        return None

    win_rate = won / resolved
    volume = float(entry.get("volume", 0) or 0)
    pnl = float(entry.get("profit") or entry.get("pnl", 0) or 0)

    # Estimate avg daily trades from volume proxy (rough but avoids extra API calls)
    avg_daily = float(entry.get("avgDailyTrades") or entry.get("avg_daily_trades") or 0)

    return TraderStats(
        address=address,
        username=_extract_username(entry, address),
        win_rate=win_rate,
        avg_daily_trades=avg_daily,
        total_pnl_usdc=pnl,
        resolved_trades=resolved,
        total_trades=won + lost,
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )


def compute_stats_from_activity(
    address: str,
    username: str,
    pnl_hint: float,
    resolution_cache: dict,
) -> Optional[TraderStats]:
    """
    Slow path: fetch the trader's full activity and derive stats ourselves.
    Only called when the leaderboard entry lacks win/loss breakdown.
    """
    activity = fetch_activity(address, limit=500)
    if not activity:
        return None

    buys = [r for r in activity if r.get("type") == "Buy"]
    all_trades = [r for r in activity if r.get("type") in ("Buy", "Sell")]

    if len(buys) < 5:
        return None

    # --- avg daily trades ---
    timestamps = [r["timestamp"] for r in all_trades if r.get("timestamp")]
    if len(timestamps) >= 2:
        span_days = (max(timestamps) - min(timestamps)) / 86400.0
        avg_daily = len(all_trades) / max(span_days, 1.0)
    else:
        avg_daily = len(all_trades)

    # --- win rate from resolved buy positions ---
    # Deduplicate condition IDs to minimise API calls
    seen_cids: dict[str, list[str]] = {}  # cid → list of outcomes trader bet on
    for raw in buys:
        cid = raw.get("conditionId", "")
        outcome = raw.get("outcome", "")
        if cid and outcome:
            seen_cids.setdefault(cid, []).append(outcome)

    wins = losses = 0
    for cid, outcomes in list(seen_cids.items())[:60]:  # cap at 60 markets
        winner = get_winner(cid, resolution_cache)
        time.sleep(0.08)  # stay well within rate limits
        if winner is None:
            continue
        for outcome in outcomes:
            if outcome.lower() == winner.lower():
                wins += 1
            else:
                losses += 1

    resolved = wins + losses
    if resolved == 0:
        return None

    # --- rough P&L ---
    pnl = pnl_hint
    if pnl == 0.0:
        for raw in activity:
            amount = float(raw.get("amount", 0) or 0)
            if raw.get("type") == "Redeem":
                pnl += amount
            elif raw.get("type") == "Buy":
                pnl -= amount

    return TraderStats(
        address=address,
        username=username,
        win_rate=wins / resolved,
        avg_daily_trades=round(avg_daily, 2),
        total_pnl_usdc=round(pnl, 2),
        resolved_trades=resolved,
        total_trades=len(all_trades),
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class TraderScanner:
    def __init__(
        self,
        min_win_rate: float = 0.70,
        min_daily_trades: float = 5.0,
        min_resolved_trades: int = 10,
        max_candidates: int = 200,
        copy_list_path: str = DEFAULT_COPY_LIST_PATH,
    ):
        self.min_win_rate = min_win_rate
        self.min_daily_trades = min_daily_trades
        self.min_resolved_trades = min_resolved_trades
        self.max_candidates = max_candidates
        self.copy_list_path = copy_list_path
        self._resolution_cache: dict = {}

    def _qualifies(self, stats: TraderStats) -> bool:
        return (
            stats.win_rate >= self.min_win_rate
            and stats.avg_daily_trades >= self.min_daily_trades
            and stats.resolved_trades >= self.min_resolved_trades
        )

    def scan(self) -> list[TraderStats]:
        logger.info("=== Polymarket Trader Scanner starting ===")
        leaderboard = fetch_leaderboard(limit=self.max_candidates)
        if not leaderboard:
            logger.warning("Leaderboard returned no entries.")
            return []

        qualifying: list[TraderStats] = []

        for i, entry in enumerate(leaderboard):
            address = _extract_address(entry)
            if not address:
                continue

            username = _extract_username(entry, address)
            logger.info("[%d/%d] Analysing %s (%s)", i + 1, len(leaderboard), username, address)

            # Try fast path first
            stats = compute_stats_from_leaderboard(entry)

            if stats is None or stats.resolved_trades < self.min_resolved_trades:
                # Fall back to computing from raw activity
                pnl_hint = float(entry.get("profit") or entry.get("pnl", 0) or 0)
                stats = compute_stats_from_activity(
                    address, username, pnl_hint, self._resolution_cache
                )

            if stats is None:
                continue

            logger.info(
                "  win_rate=%.1f%% | avg_daily=%.1f | resolved=%d | pnl=$%.2f",
                stats.win_rate * 100,
                stats.avg_daily_trades,
                stats.resolved_trades,
                stats.total_pnl_usdc,
            )

            if self._qualifies(stats):
                logger.info("  QUALIFIES ✓")
                qualifying.append(stats)
            else:
                reason = []
                if stats.win_rate < self.min_win_rate:
                    reason.append(f"win_rate {stats.win_rate:.1%} < {self.min_win_rate:.0%}")
                if stats.avg_daily_trades < self.min_daily_trades:
                    reason.append(f"daily_trades {stats.avg_daily_trades:.1f} < {self.min_daily_trades}")
                if stats.resolved_trades < self.min_resolved_trades:
                    reason.append(f"resolved {stats.resolved_trades} < {self.min_resolved_trades}")
                logger.info("  skip: %s", "; ".join(reason))

            time.sleep(0.2)  # polite pacing between traders

        qualifying.sort(key=lambda s: (-s.win_rate, -s.avg_daily_trades))
        logger.info("=== Scan complete: %d qualifying traders ===", len(qualifying))
        return qualifying

    def save(self, traders: list[TraderStats]) -> None:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "thresholds": {
                "min_win_rate": self.min_win_rate,
                "min_daily_trades": self.min_daily_trades,
                "min_resolved_trades": self.min_resolved_trades,
            },
            "traders": [asdict(t) for t in traders],
        }
        with open(self.copy_list_path, "w") as f:
            json.dump(payload, f, indent=2)
        logger.info("Saved %d traders to %s", len(traders), self.copy_list_path)

    def load(self) -> list[dict]:
        try:
            with open(self.copy_list_path) as f:
                data = json.load(f)
            return data.get("traders", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []
