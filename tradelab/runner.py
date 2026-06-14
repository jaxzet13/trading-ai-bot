from __future__ import annotations

"""
Daily execution cycle: fetch signals → combine strategies → risk check → place orders → log to DB.
Called by the APScheduler job in main.py, or via `tradelab now` for an immediate run.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from tradelab.config import UNIVERSE, HIGH_VOL_UNIVERSE, MAX_POSITION_PCT
from tradelab.data.fetcher import fetch_bars
from tradelab.db.models import EquitySnapshot, Signal, SystemState, Trade
from tradelab.execution.broker import PaperBroker
from tradelab.execution.risk import OrderIntent, RiskGate

# Sweep-winner strategies (vectorised, fast on daily bars)
from tradelab.strategies.top_intraday import ATRImpulseBreakoutStrategy, CascadeEMAStrategy

# Additional strategies that work on daily OHLCV bars
from tradelab.strategies.mean_reversion import MeanReversionStrategy
from tradelab.strategies.intraday import (
    ATRBreakoutStrategy,
    BollingerRSIStrategy,
    GapFadeStrategy,
)

logger = logging.getLogger(__name__)

STRATEGIES = [
    ATRImpulseBreakoutStrategy(),   # sweep winner: Sharpe 1.83, CAGR +127%
    CascadeEMAStrategy(),            # sweep #2:    Sharpe 1.55, CAGR +124%
    MeanReversionStrategy(),         # RSI(5) <25 oversold entries
    ATRBreakoutStrategy(),           # ATR momentum continuation (hold 6 bars)
    BollingerRSIStrategy(),          # Bollinger Band + RSI combo
    GapFadeStrategy(),               # fade panic-selling bars
]

N_STRATEGIES = len(STRATEGIES)


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

    # ── Account state ─────────────────────────────────────────────────────
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
    logger.info("Account: equity=$%.2f  cash=$%.2f  drawdown=%.2f%%", equity, cash, drawdown_pct * 100)

    if halted:
        logger.warning("System halted — skipping signal generation. Run `tradelab resume` to unlock.")
        return

    # ── Fetch bars ────────────────────────────────────────────────────────
    all_symbols = list(set(UNIVERSE + HIGH_VOL_UNIVERSE))
    logger.info("Fetching %d symbols (1 year daily bars)...", len(all_symbols))
    bars = fetch_bars(all_symbols, years=1)
    if not bars:
        logger.error("No bars fetched — aborting cycle.")
        return
    logger.info("Bars ready for %d symbols.", len(bars))

    # ── Open positions ────────────────────────────────────────────────────
    try:
        current_positions = broker.get_positions()
        open_symbols = [p["symbol"] for p in current_positions]
        logger.info("Open positions: %s", open_symbols or "none")
    except Exception as exc:
        logger.error("Could not fetch positions: %s", exc)
        return

    # ── Run every strategy, collect per-symbol signals ────────────────────
    # sym -> list of (strategy_name, weight) for strategies that want it
    sym_signals: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for strategy in STRATEGIES:
        try:
            signals = strategy.generate_signals(bars)
        except Exception as exc:
            logger.warning("Strategy %s failed — skipping: %s", strategy.name, exc)
            continue

        if signals.empty:
            logger.debug("Strategy %s returned empty signals.", strategy.name)
            continue

        last_row = signals.iloc[-1]
        n_buys = 0
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
            if val > 0:
                sym_signals[sym].append((strategy.name, val))
                n_buys += 1

        logger.info("Strategy %-22s → %d BUY signals", strategy.name, n_buys)

    session.commit()

    # ── Combine signals: average weight across ALL strategies ─────────────
    # Dividing by N_STRATEGIES keeps total portfolio allocation ≤ 1.0.
    # Symbols agreed on by multiple strategies receive proportionally larger
    # slices (each contributing strategy adds its share of the 1/N_STRATEGIES
    # budget), while single-strategy signals are small but still tradeable.
    desired_positions: dict[str, tuple[str, float, float]] = {}
    for sym, sigs in sym_signals.items():
        combined_weight = sum(w for _, w in sigs) / N_STRATEGIES
        if combined_weight < 0.01:
            continue
        # Cap each position at MAX_POSITION_PCT (e.g. 34%) before the risk gate sees it
        combined_weight = min(combined_weight, MAX_POSITION_PCT)
        label = "+".join(sorted(set(n for n, _ in sigs)))
        desired_positions[sym] = (label, combined_weight, combined_weight)

    # Strongest signals first so the risk gate fills the best ones
    desired_positions = dict(
        sorted(desired_positions.items(), key=lambda x: x[1][1], reverse=True)
    )

    n_agree_2plus = sum(1 for sigs in sym_signals.values() if len(sigs) >= 2)
    logger.info(
        "Combined: %d symbols wanted (%d with 2+ strategies agreeing)",
        len(desired_positions), n_agree_2plus,
    )

    # ── Close positions no longer signalled ───────────────────────────────
    for sym in open_symbols:
        if sym not in desired_positions:
            order_id = broker.close_position(sym)
            if order_id:
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

    # ── Place / rebalance orders ──────────────────────────────────────────
    orders_placed = 0
    for sym, (strat_name, weight, signal_val) in desired_positions.items():
        notional = equity * weight * 0.95
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
            orders_placed += 1
            open_symbols.append(sym)   # track within-cycle so risk gate sees it
            price = float(bars[sym]["close"].iloc[-1]) if sym in bars else 0.0
            session.add(
                Trade(
                    strategy=strat_name,
                    symbol=sym,
                    entry_time=datetime.now(timezone.utc).replace(tzinfo=None),
                    entry_price=price,
                    signal_value=signal_val,
                    position_size=notional / price if price > 0 else 0.0,
                    notional=notional,
                    fees_modeled=notional * 0.001,
                    is_open=True,
                    alpaca_order_id=order_id,
                )
            )
            session.commit()
            logger.info("ORDER PLACED  %-6s  $%.0f  strategies=%s", sym, notional, strat_name)
        else:
            logger.info("REJECTED  %-6s  %s", sym, decision.reason)

    logger.info(
        "Cycle complete — equity=$%.2f | %d/%d orders placed",
        equity, orders_placed, len(desired_positions),
    )
