from __future__ import annotations

"""
Daily execution cycle: fetch signals → combine strategies → risk check → place orders → log to DB.
Called by the APScheduler job in main.py, or via `tradelab now` for an immediate run.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from tradelab.config import (
    UNIVERSE, HIGH_VOL_UNIVERSE, CRYPTO_TRADING_UNIVERSE,
    MAX_POSITION_PCT, CRYPTO_MAX_POSITION_PCT, MAX_OPEN_POSITIONS,
    DAILY_LOSS_LIMIT_PCT, PROFIT_TARGET_PCT, TARGET_DEPLOYMENT,
    PARTIAL_TP_PCT, PARTIAL_TP_FRACTION, TRAILING_STOP_PCT,
)
from tradelab.execution.broker import _is_crypto, _is_option
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


def _get_daily_start_equity(session: Session) -> float:
    """Equity at the start of today (first snapshot of calendar day)."""
    from sqlalchemy import func
    today = datetime.now(timezone.utc).date()
    today_start = datetime(today.year, today.month, today.day)
    row = (
        session.query(EquitySnapshot)
        .filter(EquitySnapshot.ts >= today_start)
        .order_by(EquitySnapshot.ts)
        .first()
    )
    return float(row.equity) if row else 0.0


def _get_starting_equity(session: Session) -> float:
    """Very first equity snapshot — used to track challenge progress."""
    row = session.query(EquitySnapshot).order_by(EquitySnapshot.ts).first()
    return float(row.equity) if row else 0.0


def _get_position_losses(positions: list[dict]) -> dict[str, float]:
    """Return unrealized P&L per symbol (negative = loss)."""
    return {p["symbol"]: p["unrealized_pl"] for p in positions}


# ── per-symbol state (partial-TP flag + trailing-stop high-water mark) ──────
def _state_get(session: Session, key: str) -> str | None:
    row = session.query(SystemState).filter_by(key=key).first()
    return row.value if row else None


def _state_set(session: Session, key: str, value: str) -> None:
    row = session.query(SystemState).filter_by(key=key).first()
    if row:
        row.value = value
    else:
        session.add(SystemState(key=key, value=value))
    session.commit()


def _state_del(session: Session, key: str) -> None:
    session.query(SystemState).filter_by(key=key).delete()
    session.commit()


def _clear_symbol_state(session: Session, sym: str) -> None:
    _state_del(session, f"ptp:{sym}")
    _state_del(session, f"peak:{sym}")


def manage_open_positions(session: Session, broker: PaperBroker,
                          positions: list[dict]) -> dict:
    """
    Partial take-profit + trailing stop. Returns a dict with:
      riding     – symbols now banked + trailing (rebalancer leaves them alone)
      partial_tp – symbols that just had half banked this cycle
      trail_stop – symbols whose remainder was just closed by the trailing stop

    Rule:
      • Position up >= PARTIAL_TP_PCT and not yet banked → sell PARTIAL_TP_FRACTION,
        mark as riding, record the high-water price.
      • Riding position → update high-water mark; if price falls TRAILING_STOP_PCT
        from the peak, close the remainder and free the capital.
    """
    riding: set[str] = set()
    partial_tp: list[str] = []
    trail_stop: list[str] = []
    for p in positions:
        sym = p["symbol"]
        ep = p["avg_entry_price"]
        cp = p["current_price"]
        if ep <= 0 or cp <= 0:
            continue
        gain = (cp - ep) / ep
        banked = _state_get(session, f"ptp:{sym}") == "1"

        if not banked:
            if gain >= PARTIAL_TP_PCT:
                order_id = broker.trim_position(sym, PARTIAL_TP_FRACTION * 100)
                if order_id:
                    _state_set(session, f"ptp:{sym}", "1")
                    _state_set(session, f"peak:{sym}", str(cp))
                    riding.add(sym)
                    partial_tp.append(sym)
                    logger.info(
                        "PARTIAL TP  %-6s +%.2f%% → banked %.0f%%, rest trailing",
                        sym, gain * 100, PARTIAL_TP_FRACTION * 100,
                    )
        else:
            peak = float(_state_get(session, f"peak:{sym}") or cp)
            if cp > peak:
                peak = cp
                _state_set(session, f"peak:{sym}", str(peak))
            drop = (cp - peak) / peak if peak > 0 else 0.0
            if drop <= -TRAILING_STOP_PCT:
                order_id = broker.close_position(sym)
                if order_id:
                    _clear_symbol_state(session, sym)
                    trail_stop.append(sym)
                    logger.info(
                        "TRAIL STOP  %-6s -%.2f%% from peak → closed remainder",
                        sym, abs(drop) * 100,
                    )
            else:
                riding.add(sym)
    return {"riding": riding, "partial_tp": partial_tp, "trail_stop": trail_stop}


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
    daily_start = _get_daily_start_equity(session)
    starting_equity = _get_starting_equity(session) or equity

    if risk.should_halt(equity, peak):
        _set_halted(session)
        halted = True

    drawdown_pct = (equity - peak) / peak if peak > 0 else 0.0
    daily_pnl_pct = (equity - daily_start) / daily_start * 100 if daily_start > 0 else 0.0
    challenge_pct = (equity - starting_equity) / starting_equity * 100 if starting_equity > 0 else 0.0

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
    logger.info(
        "Account: equity=$%.2f  daily=%+.2f%%  challenge=%+.2f%%  drawdown=%.2f%%",
        equity, daily_pnl_pct, challenge_pct, drawdown_pct * 100,
    )

    # ── Prop-firm challenge status ─────────────────────────────────────────
    if risk.profit_target_reached(equity, starting_equity):
        logger.info(
            "CHALLENGE TARGET REACHED! Up %.2f%% from $%.0f start. "
            "Step 1 (7%%) complete — move to Step 2.",
            challenge_pct, starting_equity,
        )

    if risk.daily_loss_breached(equity, daily_start):
        logger.warning(
            "Daily loss limit %.0f%% hit (today: %+.2f%%). No more trades today.",
            DAILY_LOSS_LIMIT_PCT * 100, daily_pnl_pct,
        )
        return

    if halted:
        logger.warning("System halted — skipping signal generation. Run `tradelab resume` to unlock.")
        return

    # ── Fetch bars (stocks + crypto) ─────────────────────────────────────
    all_symbols = list(set(UNIVERSE + HIGH_VOL_UNIVERSE + CRYPTO_TRADING_UNIVERSE))
    logger.info("Fetching %d symbols incl. crypto (1 year daily bars)...", len(all_symbols))
    bars = fetch_bars(all_symbols, years=1)
    if not bars:
        logger.error("No bars fetched — aborting cycle.")
        return
    logger.info("Bars ready for %d symbols.", len(bars))

    # ── Open positions ────────────────────────────────────────────────────
    # Options are managed by the separate options engine — exclude them here so
    # the systematic stock/crypto engine never touches leveraged contracts.
    try:
        current_positions = [p for p in broker.get_positions()
                             if not _is_option(p["symbol"])]
        logger.info("Open positions: %s",
                    [p["symbol"] for p in current_positions] or "none")
    except Exception as exc:
        logger.error("Could not fetch positions: %s", exc)
        return

    # ── Partial take-profit + trailing stop (bank gains, let winners run) ──
    mgmt = manage_open_positions(session, broker, current_positions)
    riding = mgmt["riding"]
    if riding:
        logger.info("Riding (profit banked, trailing): %s", sorted(riding))

    # Re-read positions after any partial sells / trail stops fired
    try:
        current_positions = [p for p in broker.get_positions()
                             if not _is_option(p["symbol"])]
    except Exception as exc:
        logger.error("Could not re-fetch positions: %s", exc)
        return
    open_symbols = [p["symbol"] for p in current_positions]
    position_losses = _get_position_losses(current_positions)
    current_value = {p["symbol"]: p["market_value"] for p in current_positions}

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

    # ── Combine signals into a near-fully-deployed portfolio ──────────────
    # Conviction score = number of strategies agreeing (whole points) plus the
    # summed raw weight (fractional tiebreaker). Symbols multiple strategies
    # agree on rank highest. We then take the top MAX_OPEN_POSITIONS names and
    # split TARGET_DEPLOYMENT of equity across them in proportion to conviction,
    # capping any single name at MAX_POSITION_PCT. This puts the previously
    # idle cash to work instead of leaving half the account unused.
    conviction: dict[str, float] = {}
    for sym, sigs in sym_signals.items():
        conviction[sym] = len(sigs) + sum(w for _, w in sigs)

    ranked = sorted(conviction.items(), key=lambda x: x[1], reverse=True)
    ranked = ranked[:MAX_OPEN_POSITIONS]
    total_score = sum(score for _, score in ranked) or 1.0

    desired_positions: dict[str, tuple[str, float, float]] = {}
    for sym, score in ranked:
        weight = (score / total_score) * TARGET_DEPLOYMENT
        cap = CRYPTO_MAX_POSITION_PCT if _is_crypto(sym) else MAX_POSITION_PCT
        weight = min(weight, cap)
        if weight < 0.01:
            continue
        label = "+".join(sorted(set(n for n, _ in sym_signals[sym])))
        desired_positions[sym] = (label, weight, weight)

    deployed = sum(w for _, w, _ in desired_positions.values())
    n_agree_2plus = sum(1 for sigs in sym_signals.values() if len(sigs) >= 2)
    logger.info(
        "Combined: %d positions, %.0f%% of equity deployed (%d with 2+ strategies agreeing)",
        len(desired_positions), deployed * 100, n_agree_2plus,
    )

    # ── Close positions no longer signalled ───────────────────────────────
    # Riding positions (profit banked, trailing) are exempt — their exit is
    # owned by the trailing stop, not the signal.
    closed_syms: list[str] = []
    for sym in open_symbols:
        if sym not in desired_positions and sym not in riding:
            order_id = broker.close_position(sym)
            if order_id:
                closed_syms.append(sym)
                _clear_symbol_state(session, sym)
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

    # ── Trim overweight positions back toward target ──────────────────────
    # Sell the excess on any held name that has drifted >15% above its target
    # weight. Riding positions are left alone — we want the winner to run.
    trimmed_syms: list[str] = []
    for sym, (_, weight, _) in desired_positions.items():
        if sym in riding:
            continue
        held = current_value.get(sym, 0.0)
        target = equity * weight
        if held > target * 1.15 and (held - target) > 25.0:
            pct = (held - target) / held * 100.0
            if broker.trim_position(sym, pct):
                trimmed_syms.append(sym)

    # ── Place / rebalance orders ──────────────────────────────────────────
    # For names we already hold, only buy the *difference* up to target so we
    # don't stack a full new slice on top of the existing position. A running
    # cash budget guarantees buys never exceed available cash — i.e. NO margin
    # / leverage, which keeps the simulation clean for a funded-account
    # challenge. Sell proceeds from this cycle's closes aren't counted until
    # they settle, so the system simply tops up deployment on the next run.
    MIN_ORDER = 25.0   # skip dust orders below $25
    cash_budget = max(cash, 0.0)
    orders_placed = 0
    bought_syms: list[str] = []
    for sym, (strat_name, weight, signal_val) in desired_positions.items():
        if sym in riding:
            # Profit already banked — don't buy it back up, let the rest run.
            logger.info("SKIP %-6s riding (trailing stop active)", sym)
            continue
        target_notional = equity * weight
        held = current_value.get(sym, 0.0)
        notional = target_notional - held
        if notional < MIN_ORDER:
            logger.info("SKIP %-6s already at target ($%.0f held, $%.0f target)",
                        sym, held, target_notional)
            continue
        # Never spend more than the cash we actually have on hand
        notional = min(notional, cash_budget)
        if notional < MIN_ORDER:
            logger.info("SKIP %-6s — cash budget exhausted ($%.0f left)", sym, cash_budget)
            continue
        cash_budget -= notional
        intent = OrderIntent(
            symbol=sym,
            strategy=strat_name,
            side="buy",
            notional=notional,
            signal_value=signal_val,
        )
        order_id, decision = broker.place_order(
            intent, equity, open_symbols, peak, halted,
            daily_start_equity=daily_start,
            position_losses=position_losses,
        )
        if order_id:
            orders_placed += 1
            bought_syms.append(sym)
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

    # ── Journal: append a readable record of this cycle ───────────────────
    try:
        from tradelab.journal import log_cycle
        log_cycle({
            "equity": equity,
            "daily_pct": daily_pnl_pct,
            "challenge_pct": challenge_pct,
            "drawdown_pct": drawdown_pct * 100,
            "n_positions": len(desired_positions),
            "deployed_pct": deployed * 100,
            "bought": bought_syms,
            "closed": closed_syms,
            "trimmed": trimmed_syms,
            "partial_tp": mgmt["partial_tp"],
            "trail_stop": mgmt["trail_stop"],
            "riding": riding,
        })
    except Exception as exc:
        logger.warning("Journal write failed: %s", exc)
