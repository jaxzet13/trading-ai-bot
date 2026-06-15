from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from tradelab.config import (
    CRYPTO_MAX_POSITION_PCT,
    DAILY_LOSS_LIMIT_PCT,
    DRAWDOWN_HALT_PCT,
    MAX_OPEN_POSITIONS,
    MAX_POSITION_PCT,
    PROFIT_TARGET_PCT,
    SYMBOL_LOSS_LIMIT_PCT,
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
    Enforces prop-firm style rules:
      - Max total drawdown (static balance based)
      - Max daily loss
      - Max position size
      - Max open positions
      - Per-symbol loss limit
    """

    def check(
        self,
        intent: OrderIntent,
        equity: float,
        open_positions: list[str],
        peak_equity: float,
        halted: bool,
        daily_start_equity: float = 0.0,
        position_losses: Optional[dict[str, float]] = None,
    ) -> RiskDecision:
        if halted:
            msg = "Trading halted — manual resume required (tradelab resume)"
            logger.warning("RISK REJECT [%s %s]: %s", intent.side, intent.symbol, msg)
            return RiskDecision(False, msg)

        # ── Total drawdown (static balance based) ─────────────────────────
        drawdown = (equity - peak_equity) / peak_equity if peak_equity > 0 else 0.0
        if drawdown <= -DRAWDOWN_HALT_PCT:
            msg = f"Total loss {drawdown*100:.1f}% >= limit {DRAWDOWN_HALT_PCT*100:.0f}%"
            logger.error("RISK HALT triggered: %s", msg)
            return RiskDecision(False, f"HALT: {msg}")

        # ── Daily loss limit ───────────────────────────────────────────────
        if daily_start_equity > 0:
            daily_loss = (equity - daily_start_equity) / daily_start_equity
            if daily_loss <= -DAILY_LOSS_LIMIT_PCT:
                msg = (
                    f"Daily loss {daily_loss*100:.1f}% >= limit {DAILY_LOSS_LIMIT_PCT*100:.0f}%. "
                    "No more trades today."
                )
                logger.warning("RISK REJECT [%s %s]: %s", intent.side, intent.symbol, msg)
                return RiskDecision(False, msg)

        # ── Per-symbol loss limit ──────────────────────────────────────────
        if position_losses and intent.symbol in position_losses:
            sym_loss_pct = position_losses[intent.symbol] / peak_equity if peak_equity > 0 else 0.0
            if sym_loss_pct <= -SYMBOL_LOSS_LIMIT_PCT:
                msg = (
                    f"{intent.symbol} already down ${abs(position_losses[intent.symbol]):.0f} "
                    f"({sym_loss_pct*100:.1f}% of account) — symbol loss limit {SYMBOL_LOSS_LIMIT_PCT*100:.0f}%"
                )
                logger.warning("RISK REJECT [%s %s]: %s", intent.side, intent.symbol, msg)
                return RiskDecision(False, msg)

        # ── Max position size (tighter cap for crypto) ────────────────────
        from tradelab.execution.broker import _is_crypto
        cap = CRYPTO_MAX_POSITION_PCT if _is_crypto(intent.symbol) else MAX_POSITION_PCT
        max_notional = equity * cap
        if intent.notional > max_notional and intent.side == "buy":
            msg = (
                f"Order notional ${intent.notional:.2f} exceeds max "
                f"${max_notional:.2f} ({MAX_POSITION_PCT*100:.0f}% of equity)"
            )
            logger.warning("RISK REJECT [%s %s]: %s", intent.side, intent.symbol, msg)
            return RiskDecision(False, msg)

        # ── Max open positions ─────────────────────────────────────────────
        if intent.side == "buy" and intent.symbol not in open_positions:
            if len(open_positions) >= MAX_OPEN_POSITIONS:
                msg = (
                    f"Max open positions {MAX_OPEN_POSITIONS} reached "
                    f"(current: {len(open_positions)})"
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

    def daily_loss_breached(self, equity: float, daily_start_equity: float) -> bool:
        if daily_start_equity <= 0:
            return False
        return (equity - daily_start_equity) / daily_start_equity <= -DAILY_LOSS_LIMIT_PCT

    def profit_target_reached(self, equity: float, starting_equity: float) -> bool:
        if starting_equity <= 0:
            return False
        return (equity - starting_equity) / starting_equity >= PROFIT_TARGET_PCT
