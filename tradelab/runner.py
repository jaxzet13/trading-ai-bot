from __future__ import annotations

"""
Daily execution cycle: fetch signals → risk check → place orders → log to DB.
Called by the APScheduler job in main.py.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from tradelab.config import UNIVERSE
from tradelab.data.fetcher import fetch_bars
from tradelab.db.models import EquitySnapshot, Signal, SystemState, Trade
from tradelab.execution.broker import PaperBroker
from tradelab.execution.risk import OrderIntent, RiskGate
from tradelab.strategies.mean_reversion import MeanReversionStrategy
from tradelab.strategies.momentum import MomentumStrategy

logger = logging.getLogger(__name__)

STRATEGIES = [MomentumStrategy(), MeanReversionStrategy()]


def _is_halted(session: Session) -> bool:
    row = session.query(SystemState).filter_by(key="halted").first()
    return row is not None and row.value == "true"


def _set_halted(session: Session) -> None:
    row = session.query(SystemState).filter_by(key="halted").first()
    if row:
        row.value = "true"
    else:
        session.add(SystemState(key="halted", value="true"))
    session.commit()
    logger.error("TRADING HALTED — drawdown limit reached. Run `tradelab resume` to restart.")


def _get_peak_equity(session: Session) -> float:
    from sqlalchemy import func
    result = session.query(func.max(EquitySnapshot.equity)).scalar()
    return float(result) if result else 0.0


def run_daily_cycle(session: Session) -> None:
    broker = PaperBroker()
    risk = RiskGate()

    # Refresh account state
    try:
        acct = broker.get_account()
    except Exception as exc:
        logger.error("Could not fetch account: %s", exc)
        return

    equity = acct["equity"]
    cash = acct["cash"]
    peak = _get_peak_equity(session)
    peak = max(peak, equity)
    halted = _is_halted(session)

    # Check drawdown halt
    if risk.should_halt(equity, peak):
        _set_halted(session)
        halted = True

    drawdown_pct = (equity - peak) / peak if peak > 0 else 0.0
    session.add(
        EquitySnapshot(
            ts=datetime.now(timezone.utc).replace(tzinfo=None),
            equity=equity,
            cash=cash,
            peak_equity=peak,
            drawdown_pct=drawdown_pct,
        )
    )
    session.commit()

    if halted:
        logger.warning("System halted, skipping signal generation.")
        return

    # Fetch bars
    bars = fetch_bars(UNIVERSE, years=1)

    # Current open positions for risk tracking
    try:
        current_positions = broker.get_positions()
        open_symbols = [p["symbol"] for p in current_positions]
    except Exception as exc:
        logger.error("Could not fetch positions: %s", exc)
        return

    desired_positions: dict[str, tuple[str, float, float]] = {}   # symbol -> (strategy, weight, signal)

    for strategy in STRATEGIES:
        signals = strategy.generate_signals(bars)
        if signals.empty:
            continue
        last_row = signals.iloc[-1]
        for sym in signals.columns:
            weight = float(last_row.get(sym, 0.0))
            if weight > 0:
                desired_positions[sym] = (strategy.name, weight, weight)

        # Log signals
        for sym in signals.columns:
            val = float(last_row.get(sym, 0.0))
            action = "BUY" if val > 0 else "HOLD"
            session.add(
                Signal(
                    ts=datetime.now(timezone.utc).replace(tzinfo=None),
                    strategy=strategy.name,
                    symbol=sym,
                    signal_value=val,
                    action=action,
                )
            )
    session.commit()

    # Close positions no longer desired
    for sym in open_symbols:
        if sym not in desired_positions:
            order_id = broker.close_position(sym)
            if order_id:
                # Mark open trade as closed
                trade = (
                    session.query(Trade)
                    .filter_by(symbol=sym, is_open=True)
                    .first()
                )
                if trade:
                    trade.is_open = False
                    trade.exit_time = datetime.now(timezone.utc).replace(tzinfo=None)
                    trade.alpaca_order_id = order_id
                    session.commit()

    # Open / rebalance desired positions
    for sym, (strat_name, weight, signal_val) in desired_positions.items():
        notional = equity * weight * 0.95   # small buffer for fees
        intent = OrderIntent(
            symbol=sym,
            strategy=strat_name,
            side="buy",
            notional=notional,
            signal_value=signal_val,
        )
        order_id, decision = broker.place_order(
            intent, equity, open_symbols, peak, halted
        )
        if order_id:
            price = bars[sym]["close"].iloc[-1] if sym in bars else 0.0
            session.add(
                Trade(
                    strategy=strat_name,
                    symbol=sym,
                    entry_time=datetime.now(timezone.utc).replace(tzinfo=None),
                    entry_price=float(price),
                    signal_value=signal_val,
                    position_size=notional / price if price > 0 else 0,
                    notional=notional,
                    fees_modeled=notional * 0.001,
                    is_open=True,
                    alpaca_order_id=order_id,
                )
            )
            session.commit()
        else:
            logger.info("Order rejected [%s %s]: %s", sym, strat_name, decision.reason)

    logger.info("Daily cycle complete. Equity=$%.2f", equity)
