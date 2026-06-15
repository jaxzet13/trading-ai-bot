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

# Crypto symbols that Alpaca paper trading supports.
# yfinance uses "BTC-USD"; Alpaca trading API uses "BTC/USD".
_CRYPTO_SUFFIXES = ("-USD", "-USDT", "-BTC")


def _is_crypto(sym: str) -> bool:
    return any(sym.endswith(s) for s in _CRYPTO_SUFFIXES) or "/" in sym


def _to_alpaca_symbol(sym: str) -> str:
    """Convert yfinance ticker (BTC-USD) → Alpaca trading symbol (BTC/USD)."""
    for suffix in _CRYPTO_SUFFIXES:
        if sym.endswith(suffix):
            base = sym[: -len(suffix)]
            quote = suffix.lstrip("-")
            return f"{base}/{quote}"
    return sym


def _from_alpaca_symbol(sym: str) -> str:
    """Convert Alpaca symbol (BTC/USD) → yfinance ticker (BTC-USD)."""
    if "/" in sym:
        return sym.replace("/", "-")
    return sym


def _assert_paper_endpoint() -> None:
    if "paper" not in ALPACA_PAPER_BASE_URL.lower():
        raise RuntimeError(
            f"SAFETY: ALPACA_PAPER_BASE_URL='{ALPACA_PAPER_BASE_URL}' does not contain 'paper'. "
            "TradeLab will only connect to Alpaca's paper-trading endpoint."
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
                # Normalise to yfinance format so the rest of the system is symbol-format-agnostic
                "symbol": _from_alpaca_symbol(p.symbol),
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
        daily_start_equity: float = 0.0,
        position_losses: Optional[dict] = None,
    ) -> tuple[Optional[str], RiskDecision]:
        decision = self._risk.check(
            intent, equity, open_positions, peak_equity, halted,
            daily_start_equity=daily_start_equity,
            position_losses=position_losses or {},
        )
        if not decision.approved:
            return None, decision

        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            side = OrderSide.BUY if intent.side == "buy" else OrderSide.SELL
            alpaca_sym = _to_alpaca_symbol(intent.symbol)
            # Crypto trades 24/7 — DAY orders expire at 4 PM; use GTC instead.
            tif = TimeInForce.GTC if _is_crypto(intent.symbol) else TimeInForce.DAY

            req = MarketOrderRequest(
                symbol=alpaca_sym,
                notional=round(intent.notional, 2),
                side=side,
                time_in_force=tif,
            )
            order = self.client.submit_order(req)
            logger.info(
                "ORDER PLACED: %s %s $%.2f order_id=%s",
                intent.side.upper(), alpaca_sym, intent.notional, order.id,
            )
            return str(order.id), decision
        except Exception as exc:
            logger.error("Order failed for %s: %s", intent.symbol, exc)
            return None, RiskDecision(False, str(exc))

    def close_position(self, symbol: str) -> Optional[str]:
        try:
            alpaca_sym = _to_alpaca_symbol(symbol)
            order = self.client.close_position(alpaca_sym)
            logger.info("CLOSED position: %s order_id=%s", symbol, order.id)
            return str(order.id)
        except Exception as exc:
            logger.error("Failed to close %s: %s", symbol, exc)
            return None

    def trim_position(self, symbol: str, percentage: float) -> Optional[str]:
        """Sell `percentage`% of an overweight position back toward target."""
        try:
            from alpaca.trading.requests import ClosePositionRequest

            alpaca_sym = _to_alpaca_symbol(symbol)
            pct = max(1.0, min(99.0, round(percentage, 2)))
            req = ClosePositionRequest(percentage=str(pct))
            order = self.client.close_position(alpaca_sym, close_options=req)
            logger.info("TRIMMED %s by %.1f%% order_id=%s", symbol, pct, order.id)
            return str(order.id)
        except Exception as exc:
            logger.error("Failed to trim %s: %s", symbol, exc)
            return None
