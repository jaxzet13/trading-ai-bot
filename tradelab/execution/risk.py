from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from tradelab.config import (
    DRAWDOWN_HALT_PCT,
    MAX_OPEN_POSITIONS,
    MAX_POSITION_PCT,
)

logger = logging.getLogger(__name__)


@dataclass
class OrderIntent:
    symbol: str
    strategy: str
    side: str           # "buy" | "sell"
    notional: float     # dollar amount
    signal_value: float


@dataclass
class RiskDecision:
    approved: bool
    reason: str


class RiskGate:
    """
    Every order must pass through check() before being sent to the broker.
    """

    def check(
        self,
        intent: OrderIntent,
        equity: float,
        open_positions: list[str],
        peak_equity: float,
        halted: bool,
    ) -> RiskDecision:
        if halted:
            msg = "Trading halted — manual resume required (tradelab resume)"
            logger.warning("RISK REJECT [%s %s]: %s", intent.side, intent.symbol, msg)
            return RiskDecision(False, msg)

        # Drawdown check
        drawdown = (equity - peak_equity) / peak_equity if peak_equity > 0 else 0.0
        if drawdown <= -DRAWDOWN_HALT_PCT:
            msg = f"Drawdown {drawdown*100:.1f}% >= halt threshold {DRAWDOWN_HALT_PCT*100:.0f}%"
            logger.error("RISK HALT triggered: %s", msg)
            return RiskDecision(False, f"HALT: {msg}")

        # Max position size
        max_notional = equity * MAX_POSITION_PCT
        if intent.notional > max_notional and intent.side == "buy":
            msg = (
                f"Order notional ${intent.notional:.2f} exceeds max "
                f"${max_notional:.2f} (2% of equity ${equity:.2f})"
            )
            logger.warning("RISK REJECT [%s %s]: %s", intent.side, intent.symbol, msg)
            return RiskDecision(False, msg)

        # Max open positions (only applies to new buys)
        if intent.side == "buy" and intent.symbol not in open_positions:
            if len(open_positions) >= MAX_OPEN_POSITIONS:
                msg = (
                    f"Max open positions {MAX_OPEN_POSITIONS} reached "
                    f"(current: {open_positions})"
                )
                logger.warning("RISK REJECT [%s %s]: %s", intent.side, intent.symbol, msg)
                return RiskDecision(False, msg)

        logger.info(
            "RISK APPROVED [%s %s] notional=$%.2f equity=$%.2f",
            intent.side,
            intent.symbol,
            intent.notional,
            equity,
        )
        return RiskDecision(True, "approved")

    def should_halt(self, equity: float, peak_equity: float) -> bool:
        if peak_equity <= 0:
            return False
        return (equity - peak_equity) / peak_equity <= -DRAWDOWN_HALT_PCT
