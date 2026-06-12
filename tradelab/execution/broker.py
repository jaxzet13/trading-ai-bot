from __future__ import annotations

import logging
from typing import Optional

from tradelab.config import (
    ALPACA_API_KEY,
    ALPACA_PAPER_BASE_URL,
    ALPACA_SECRET_KEY,
)
from tradelab.execution.risk import OrderIntent, RiskDecision, RiskGate

logger = logging.getLogger(__name__)


def _assert_paper_endpoint() -> None:
    """Crash at startup if the configured URL is not the paper endpoint."""
    if "paper" not in ALPACA_PAPER_BASE_URL.lower():
        raise RuntimeError(
            f"SAFETY: ALPACA_PAPER_BASE_URL='{ALPACA_PAPER_BASE_URL}' does not contain 'paper'. "
            "TradeLab will only connect to Alpaca's paper-trading endpoint. "
            "Set ALPACA_PAPER_BASE_URL to https://paper-api.alpaca.markets in your .env"
        )


_assert_paper_endpoint()


def _get_alpaca_client():
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:
        raise ImportError("alpaca-py is not installed. Run: pip install alpaca-py") from exc

    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        raise ValueError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env for live paper trading."
        )
    # paper=True forces the paper endpoint regardless of base_url
    return TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)


class PaperBroker:
    def __init__(self) -> None:
        self._client = None
        self._risk = RiskGate()

    @property
    def client(self):
        if self._client is None:
            self._client = _get_alpaca_client()
        return self._client

    def get_account(self) -> dict:
        acct = self.client.get_account()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
        }

    def get_positions(self) -> list[dict]:
        positions = self.client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "unrealized_pl": float(p.unrealized_pl),
                "market_value": float(p.market_value),
            }
            for p in positions
        ]

    def place_order(
        self,
        intent: OrderIntent,
        equity: float,
        open_positions: list[str],
        peak_equity: float,
        halted: bool,
    ) -> tuple[Optional[str], RiskDecision]:
        decision = self._risk.check(intent, equity, open_positions, peak_equity, halted)
        if not decision.approved:
            return None, decision

        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            side = OrderSide.BUY if intent.side == "buy" else OrderSide.SELL
            # Use notional for buys (fractional), qty for sells
            req = MarketOrderRequest(
                symbol=intent.symbol,
                notional=round(intent.notional, 2),
                side=side,
                time_in_force=TimeInForce.DAY,
            )
            order = self.client.submit_order(req)
            logger.info(
                "ORDER PLACED: %s %s $%.2f order_id=%s",
                intent.side.upper(),
                intent.symbol,
                intent.notional,
                order.id,
            )
            return str(order.id), decision
        except Exception as exc:
            logger.error("Order failed for %s: %s", intent.symbol, exc)
            return None, RiskDecision(False, str(exc))

    def close_position(self, symbol: str) -> Optional[str]:
        try:
            order = self.client.close_position(symbol)
            logger.info("CLOSED position: %s order_id=%s", symbol, order.id)
            return str(order.id)
        except Exception as exc:
            logger.error("Failed to close %s: %s", symbol, exc)
            return None
