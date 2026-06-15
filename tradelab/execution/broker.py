from __future__ import annotations

import logging
from typing import Optional

from tradelab.config import (
    ALPACA_API_KEY,
    ALPACA_PAPER_BASE_URL,
    ALPACA_SECRET_KEY,
    CRYPTO_TRADING_UNIVERSE,
)
from tradelab.execution.risk import OrderIntent, RiskDecision, RiskGate

logger = logging.getLogger(__name__)

# yfinance uses "BTC-USD"; Alpaca uses "BTC/USD" for ORDERS but "BTCUSD"
# (concatenated, no separator) for POSITIONS. Build a robust reverse map from
# our known crypto universe so all three forms normalise to the yfinance form.
_CRYPTO_SUFFIXES = ("-USD", "-USDT", "-BTC")
_ALPACA_TO_YF: dict[str, str] = {}
for _c in CRYPTO_TRADING_UNIVERSE:
    if "-" in _c:
        _base, _quote = _c.split("-", 1)
        _ALPACA_TO_YF[f"{_base}/{_quote}"] = _c   # ETH/USD  (order form)
        _ALPACA_TO_YF[f"{_base}{_quote}"] = _c    # ETHUSD   (position form)


def _is_crypto(sym: str) -> bool:
    return any(sym.endswith(s) for s in _CRYPTO_SUFFIXES) or "/" in sym or sym in _ALPACA_TO_YF


import re as _re
_OCC_RE = _re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")


def _is_option(sym: str) -> bool:
    """True for OCC option symbols like AAPL270115C00325000."""
    return bool(_OCC_RE.match(sym))


def _to_alpaca_symbol(sym: str) -> str:
    """Convert yfinance ticker (BTC-USD) → Alpaca order symbol (BTC/USD)."""
    for suffix in _CRYPTO_SUFFIXES:
        if sym.endswith(suffix):
            base = sym[: -len(suffix)]
            quote = suffix.lstrip("-")
            return f"{base}/{quote}"
    return sym


def _from_alpaca_symbol(sym: str) -> str:
    """Convert any Alpaca symbol form (BTC/USD or BTCUSD) → yfinance (BTC-USD)."""
    if sym in _ALPACA_TO_YF:
        return _ALPACA_TO_YF[sym]
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

    def _raw_qty(self, symbol: str) -> float:
        """Held quantity for a yfinance symbol, reading raw Alpaca positions."""
        for p in self.client.get_all_positions():
            if _from_alpaca_symbol(p.symbol) == symbol:
                return abs(float(p.qty))
        return 0.0

    def _sell_crypto(self, symbol: str, fraction: float) -> Optional[str]:
        """Sell `fraction` (0-1) of a crypto position via a market SELL order.

        Alpaca's close_position endpoint 404s on crypto because the '/' in
        'DOGE/USD' breaks the URL path, so we route crypto exits through an
        ordinary sell order (the same path the buys use, which works)."""
        import math
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        held = self._raw_qty(symbol)
        # When selling the full position (fraction=1.0), pass qty=held exactly
        # so Alpaca can settle any remaining dust itself instead of leaving a
        # sub-microcoin leftover. For partial sells, round DOWN to avoid oversell.
        if fraction >= 1.0:
            qty = held
        else:
            qty = math.floor(held * fraction * 1e6) / 1e6
        if qty <= 0:
            logger.info("Crypto sell skipped %s — nothing to sell (held=%g)", symbol, held)
            return None
        alpaca_sym = _to_alpaca_symbol(symbol)
        req = MarketOrderRequest(
            symbol=alpaca_sym, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
        )
        order = self.client.submit_order(req)
        logger.info("CRYPTO SELL %s qty=%g (%.0f%%) order_id=%s",
                    alpaca_sym, qty, fraction * 100, order.id)
        return str(order.id)

    def close_position(self, symbol: str) -> Optional[str]:
        try:
            if _is_crypto(symbol):
                return self._sell_crypto(symbol, 1.0)
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
            if _is_crypto(symbol):
                return self._sell_crypto(symbol, percentage / 100.0)
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

    # ── Options ────────────────────────────────────────────────────────────
    def find_leaps(self, underlying: str, otm_pct: float, min_dte: int) -> Optional[dict]:
        """Find the nearest-to-target OTM long-dated CALL contract for `underlying`."""
        try:
            from alpaca.trading.requests import GetOptionContractsRequest
            from alpaca.trading.enums import ContractType, AssetStatus
            from datetime import date, timedelta

            spot = self._spot_price(underlying)
            if not spot:
                return None
            target_strike = spot * (1 + otm_pct)
            req = GetOptionContractsRequest(
                underlying_symbols=[underlying],
                type=ContractType.CALL,
                status=AssetStatus.ACTIVE,
                expiration_date_gte=(date.today() + timedelta(days=min_dte)).isoformat(),
                strike_price_gte=str(round(spot)),
                limit=200,
            )
            contracts = self.client.get_option_contracts(req).option_contracts
            if not contracts:
                return None
            # nearest expiry that qualifies, then strike closest to target
            min_exp = min(c.expiration_date for c in contracts)
            same_exp = [c for c in contracts if c.expiration_date == min_exp]
            best = min(same_exp, key=lambda c: abs(float(c.strike_price) - target_strike))
            return {"symbol": best.symbol, "strike": float(best.strike_price),
                    "expiry": str(best.expiration_date), "spot": spot}
        except Exception as exc:
            logger.warning("find_leaps failed for %s: %s", underlying, exc)
            return None

    def _spot_price(self, underlying: str) -> Optional[float]:
        try:
            import yfinance as yf
            px = yf.Ticker(underlying).history(period="1d")["Close"]
            return float(px.iloc[-1]) if len(px) else None
        except Exception:
            return None

    def option_quote(self, symbol: str) -> Optional[float]:
        """Latest ask price for an option contract (per share; ×100 = contract cost)."""
        try:
            from alpaca.data.historical.option import OptionHistoricalDataClient
            from alpaca.data.requests import OptionLatestQuoteRequest

            dc = OptionHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
            q = dc.get_option_latest_quote(OptionLatestQuoteRequest(symbol_or_symbols=[symbol]))
            quote = q.get(symbol)
            if quote and quote.ask_price:
                return float(quote.ask_price)
            return None
        except Exception as exc:
            logger.warning("option_quote failed for %s: %s", symbol, exc)
            return None

    def buy_option(self, symbol: str, qty: int) -> Optional[str]:
        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            req = MarketOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
            )
            order = self.client.submit_order(req)
            logger.info("OPTION BUY %s x%d order_id=%s", symbol, qty, order.id)
            return str(order.id)
        except Exception as exc:
            logger.error("Option buy failed %s: %s", symbol, exc)
            return None

    def get_option_positions(self) -> list[dict]:
        out = []
        for p in self.client.get_all_positions():
            if _is_option(p.symbol):
                out.append({
                    "symbol": p.symbol, "qty": float(p.qty),
                    "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc),
                    "market_value": float(p.market_value),
                })
        return out

    def close_option(self, symbol: str) -> Optional[str]:
        try:
            order = self.client.close_position(symbol)
            logger.info("OPTION CLOSED %s order_id=%s", symbol, order.id)
            return str(order.id)
        except Exception as exc:
            logger.error("Failed to close option %s: %s", symbol, exc)
            return None
