from __future__ import annotations

"""
Intraday trading engine — stocks (long+short) and crypto (long only).
THE primary and only trading engine (LEAPS options engine is disabled).

Strategy: scan a high-volatility stock universe + 13 crypto symbols on 5m bars
every 5-10 minutes for entries. Enter on pattern signals (EMA cross, VWAP
cross, 3-bar momentum, engulfing candle). Each position is a quick round
trip — exit via stop/TP or a hard 2-hour time limit, never longer.

Small size per trade, many concurrent positions, constant rotation —
this is meant to be buying and selling all day/night, not parking capital.

Stocks: long AND short via MarketOrderRequest.
Crypto: long only (Alpaca paper cannot short crypto).
"""

import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Universe ─────────────────────────────────────────────────────────────────

# High-beta, high-volume stocks ideal for 5m day trading
INTRADAY_STOCK_SYMBOLS = [
    "TSLA", "NVDA", "AMD", "COIN", "MSTR",
    "SMCI", "PLTR", "META", "SOXL", "TQQQ",
    "SPY",  "QQQ",  "MSFT", "AMZN",
]

# Same universe as the 1h crypto engine — signals are independent
INTRADAY_CRYPTO_SYMBOLS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "AVAX-USD",
    "LINK-USD", "AAVE-USD", "LTC-USD", "ADA-USD", "DOT-USD",
    "DOGE-USD", "RENDER-USD", "WIF-USD",
]

# ── Risk config ───────────────────────────────────────────────────────────────
# Now the ONLY engine running — budget is a fraction of total equity, not a
# fixed dollar pool, computed live in run_intraday_cycle().
INTRADAY_BUDGET_PCT  = 0.90    # up to 90% of equity deployed across small trades
MAX_POSITIONS        = 12      # many small concurrent positions, not a few big ones
MAX_PER_TRADE        = 3_000   # cap per position — keeps trades small & diversified
MIN_TRADE            = 200     # Alpaca minimum
MAX_HOLD_MINUTES     = 120     # hard time exit at 2h — every trade is a 1-2h round trip
TRAIL_ACTIVATE_PCT   = 0.010   # arm trailing stop once up 1%
TRAIL_STOP_FROM_PEAK = 0.006   # trail 0.6% below/above peak


# ── DB state helpers ─────────────────────────────────────────────────────────

def _key(symbol: str) -> str:
    return f"intraday_{symbol.replace('-', '_').replace('/', '_')}"


def _load_positions(session) -> dict[str, dict]:
    from tradelab.db.models import SystemState
    out: dict[str, dict] = {}
    for row in session.query(SystemState).filter(
        SystemState.key.like("intraday_%")
    ).all():
        raw = row.key[len("intraday_"):]
        # Restore original symbol: TSLA stays TSLA, BTC_USD → BTC-USD
        sym = raw.replace("_USD", "-USD").replace("_BTC", "-BTC")  # handle crypto
        # Fallback: if no dash restored, it's a stock symbol (may contain _)
        # Actually simpler: just store symbol → key mapping in JSON
        try:
            data = json.loads(row.value)
            sym = data.get("symbol", sym)
            out[sym] = data
        except Exception:
            pass
    return out


def _save_position(session, symbol: str, data: dict) -> None:
    from tradelab.db.models import SystemState
    data["symbol"] = symbol  # always store symbol inside JSON for reliable restore
    key = _key(symbol)
    row = session.query(SystemState).filter_by(key=key).first()
    if row:
        row.value = json.dumps(data)
    else:
        session.add(SystemState(key=key, value=json.dumps(data)))
    session.commit()


def _delete_position(session, symbol: str) -> None:
    from tradelab.db.models import SystemState
    row = session.query(SystemState).filter_by(key=_key(symbol)).first()
    if row:
        session.delete(row)
        session.commit()


def _update_best(session, symbol: str, best: float) -> None:
    positions = _load_positions(session)
    if symbol in positions:
        positions[symbol]["best_price"] = best
        _save_position(session, symbol, positions[symbol])


# ── Price fetch ───────────────────────────────────────────────────────────────

def _spot(symbol: str) -> Optional[float]:
    try:
        import yfinance as yf
        h = yf.Ticker(symbol).history(period="1d", interval="1m")
        return float(h["Close"].iloc[-1]) if not h.empty else None
    except Exception:
        return None


# ── Order helpers ─────────────────────────────────────────────────────────────

def _open_long(broker, symbol: str, notional: float, is_crypto: bool) -> Optional[str]:
    """Buy long: notional for crypto (fractional), qty for stocks."""
    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        if is_crypto:
            alpaca_sym = symbol.replace("-", "/")
            req = MarketOrderRequest(
                symbol=alpaca_sym, notional=notional,
                side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
            )
        else:
            price = _spot(symbol) or 1.0
            qty = math.floor(notional / price)
            if qty < 1:
                return None
            req = MarketOrderRequest(
                symbol=symbol, qty=qty,
                side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
            )
        order = broker.client.submit_order(req)
        return str(order.id)
    except Exception as exc:
        logger.error("Intraday LONG open %s failed: %s", symbol, exc)
        return None


def _open_short(broker, symbol: str, notional: float) -> tuple[Optional[str], float]:
    """Sell short a stock. Returns (order_id, qty_shorted)."""
    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        price = _spot(symbol) or 1.0
        qty = math.floor(notional / price)
        if qty < 1:
            return None, 0.0
        req = MarketOrderRequest(
            symbol=symbol, qty=qty,
            side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
        )
        order = broker.client.submit_order(req)
        logger.info("Intraday SHORT open %s qty=%d order_id=%s", symbol, qty, order.id)
        return str(order.id), float(qty)
    except Exception as exc:
        logger.error("Intraday SHORT open %s failed: %s", symbol, exc)
        return None, 0.0


def _close_long(broker, symbol: str, qty: float, is_crypto: bool, reason: str) -> Optional[str]:
    """Close a long position (sell)."""
    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        if is_crypto:
            alpaca_sym = symbol.replace("-", "/")
            safe_qty = math.floor(qty * 1_000_000) / 1_000_000
            if safe_qty <= 0:
                return None
            req = MarketOrderRequest(
                symbol=alpaca_sym, qty=safe_qty,
                side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
            )
        else:
            int_qty = int(math.floor(qty))
            if int_qty < 1:
                return None
            req = MarketOrderRequest(
                symbol=symbol, qty=int_qty,
                side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
            )
        order = broker.client.submit_order(req)
        logger.info("Intraday LONG close %s qty=%g | %s | order_id=%s",
                    symbol, qty, reason, order.id)
        return str(order.id)
    except Exception as exc:
        logger.error("Intraday LONG close %s failed: %s", symbol, exc)
        return None


def _close_short(broker, symbol: str, qty: float, reason: str) -> Optional[str]:
    """Cover a short (buy to close)."""
    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        int_qty = int(math.floor(qty))
        if int_qty < 1:
            return None
        req = MarketOrderRequest(
            symbol=symbol, qty=int_qty,
            side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
        )
        order = broker.client.submit_order(req)
        logger.info("Intraday SHORT cover %s qty=%d | %s | order_id=%s",
                    symbol, int_qty, reason, order.id)
        return str(order.id)
    except Exception as exc:
        logger.error("Intraday SHORT cover %s failed: %s", symbol, exc)
        return None


# ── Position management ───────────────────────────────────────────────────────

def manage_intraday_positions(session, broker) -> dict:
    """
    Check every tracked intraday position for exit conditions:
    - Stop loss
    - Take profit
    - Time exit (>= MAX_HOLD_MINUTES)
    - Trailing stop (after TRAIL_ACTIVATE_PCT gain)
    """
    positions = _load_positions(session)
    closed = []

    for sym, pos in positions.items():
        current = _spot(sym)
        if current is None:
            logger.warning("Intraday manage: no price for %s", sym)
            continue

        side      = pos.get("side", "buy")      # "buy" = long, "sell" = short
        entry     = pos["entry_price"]
        qty       = pos["qty"]
        stop_pct  = pos.get("stop_pct", 0.008)
        target_pct = pos.get("target_pct", 0.015)
        best      = pos.get("best_price", entry)
        is_crypto = pos.get("is_crypto", False)

        # pnl_pct: positive = winning, negative = losing
        if side == "buy":
            pnl_pct = (current - entry) / entry
            # track highest seen price
            if current > best:
                best = current
                _update_best(session, sym, best)
        else:
            pnl_pct = (entry - current) / entry
            # track lowest seen price (best for a short)
            if current < best:
                best = current
                _update_best(session, sym, best)

        elapsed_min = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(pos["entry_time"]).replace(tzinfo=timezone.utc)
        ).total_seconds() / 60

        reason = None

        if pnl_pct <= -stop_pct:
            reason = f"STOP {pnl_pct*100:+.1f}% (limit -{stop_pct*100:.1f}%)"
        elif pnl_pct >= target_pct:
            reason = f"TARGET {pnl_pct*100:+.1f}% (goal +{target_pct*100:.1f}%)"
        elif pnl_pct >= TRAIL_ACTIVATE_PCT:
            if side == "buy":
                trail_stop = best * (1 - TRAIL_STOP_FROM_PEAK)
                if current < trail_stop:
                    reason = f"TRAIL {pnl_pct*100:+.1f}% (peak ${best:.4f}→dropped)"
            else:
                trail_stop = best * (1 + TRAIL_STOP_FROM_PEAK)
                if current > trail_stop:
                    reason = f"TRAIL {pnl_pct*100:+.1f}% (trough ${best:.4f}→bounced)"
        elif elapsed_min >= MAX_HOLD_MINUTES:
            reason = f"TIME {elapsed_min:.0f}min P&L {pnl_pct*100:+.1f}%"

        if reason:
            if side == "buy":
                oid = _close_long(broker, sym, qty, is_crypto, reason)
            else:
                oid = _close_short(broker, sym, qty, reason)

            _delete_position(session, sym)
            notional = pos.get("notional", qty * entry)
            closed.append({
                "symbol": sym, "side": side, "reason": reason,
                "pnl_pct": round(pnl_pct * 100, 2),
                "pnl_dollars": round(notional * pnl_pct, 2),
                "order_id": oid,
                "elapsed_min": round(elapsed_min, 1),
            })

    return {"closed": closed}


# ── Main cycle ────────────────────────────────────────────────────────────────

def run_intraday_cycle(session, broker) -> dict:
    """
    Full 5-minute intraday cycle:
    1. Manage open positions (stops / TP / time / trailing)
    2. Check capacity and available cash
    3. Scan stocks + crypto for 5m signals
    4. Execute highest-conviction signals within budget
    """
    from tradelab.strategies.intraday_5m import (
        generate_5m_signals, fetch_5m_bars, is_market_open,
    )

    mgmt = manage_intraday_positions(session, broker)

    acct = broker.get_account()
    budget = acct["equity"] * INTRADAY_BUDGET_PCT
    cash_room = max(acct.get("cash", 0.0) * 0.97, 0.0)

    open_positions = _load_positions(session)
    slots = MAX_POSITIONS - len(open_positions)
    deployed = sum(p.get("notional", 0) for p in open_positions.values())
    available = max(0.0, min(budget - deployed, cash_room))

    if slots <= 0 or available < MIN_TRADE:
        logger.info(
            "Intraday: %d/%d slots used, $%.0f available — no new entries",
            len(open_positions), MAX_POSITIONS, available,
        )
        return {"mgmt": mgmt, "bought": [], "open_count": len(open_positions)}

    # ── Scan stocks (only during market hours) ───────────────────────────
    all_signals: list[dict] = []

    if is_market_open():
        scan_stocks = [s for s in INTRADAY_STOCK_SYMBOLS if s not in open_positions]
        for sym in scan_stocks:
            bars = fetch_5m_bars(sym, days=3)
            sigs = generate_5m_signals(sym, bars, is_crypto=False)
            all_signals.extend(sigs)
            for s in sigs:
                logger.info("5m SIGNAL %s %s %s conv=%.2f  %s",
                            sym, s["side"].upper(), s["strategy"],
                            s["conviction"], s["reason"])
    else:
        logger.info("Intraday stocks: market closed — crypto only")

    # ── Scan crypto (24/7, long only) ────────────────────────────────────
    scan_crypto = [s for s in INTRADAY_CRYPTO_SYMBOLS if s not in open_positions]
    for sym in scan_crypto:
        bars = fetch_5m_bars(sym, days=3)
        sigs = generate_5m_signals(sym, bars, is_crypto=True)
        all_signals.extend(sigs)
        for s in sigs:
            logger.info("5m SIGNAL %s %s %s conv=%.2f  %s",
                        sym, s["side"].upper(), s["strategy"],
                        s["conviction"], s["reason"])

    if not all_signals:
        logger.info("Intraday: no 5m signals found")
        return {"mgmt": mgmt, "bought": [], "signals_found": 0}

    # Sort by conviction descending
    all_signals.sort(key=lambda s: s["conviction"], reverse=True)

    # ── Execute signals ───────────────────────────────────────────────────
    bought = []
    per_trade = min(MAX_PER_TRADE, available / max(slots, 1))

    for sig in all_signals:
        if len(bought) >= slots:
            break

        sym = sig["symbol"]
        side = sig["side"]          # "buy" or "sell"
        if sym in open_positions:
            continue

        notional = round(min(per_trade, available), 2)
        if notional < MIN_TRADE:
            break

        is_crypto = sym in INTRADAY_CRYPTO_SYMBOLS
        entry_time = datetime.now(timezone.utc).isoformat()

        if side == "buy":
            oid = _open_long(broker, sym, notional, is_crypto)
            if oid is None:
                continue
            time.sleep(1)  # let fill settle
            entry_price = _spot(sym) or (notional / 1.0)
            qty = notional / entry_price if not is_crypto else notional / entry_price
            # refine qty from actual position if available
            try:
                for p in broker.get_positions():
                    if p["symbol"].replace("/", "-") == sym or p["symbol"] == sym:
                        entry_price = float(p["current_price"])
                        qty = notional / entry_price
                        break
            except Exception:
                pass
        else:
            # Short: need qty upfront
            price_now = _spot(sym) or 1.0
            qty_to_short = math.floor(notional / price_now)
            if qty_to_short < 1:
                continue
            oid, qty_filled = _open_short(broker, sym, notional)
            if oid is None:
                continue
            time.sleep(1)
            entry_price = _spot(sym) or price_now
            qty = float(qty_to_short)

        _save_position(session, sym, {
            "symbol": sym,
            "side": side,
            "entry_price": entry_price,
            "entry_time": entry_time,
            "qty": qty,
            "notional": notional,
            "strategy": sig["strategy"],
            "stop_pct": sig["stop_pct"],
            "target_pct": sig["target_pct"],
            "best_price": entry_price,
            "is_crypto": is_crypto,
        })

        open_positions[sym] = {}
        available -= notional

        bought.append({
            "symbol": sym, "side": side,
            "notional": notional,
            "qty": round(qty, 6 if is_crypto else 2),
            "entry_price": entry_price,
            "strategy": sig["strategy"],
            "conviction": sig["conviction"],
            "reason": sig["reason"],
            "stop_pct": sig["stop_pct"],
            "target_pct": sig["target_pct"],
            "is_crypto": is_crypto,
        })
        logger.info(
            "Intraday %s %s $%.0f %s conv=%.2f order=%s",
            side.upper(), sym, notional, sig["strategy"], sig["conviction"], oid,
        )

    return {"mgmt": mgmt, "bought": bought, "signals_found": len(all_signals)}


# ── Scan-only ─────────────────────────────────────────────────────────────────

def scan_only(market_open_override: Optional[bool] = None) -> list[dict]:
    """Return all 5m signals without placing orders."""
    from tradelab.strategies.intraday_5m import (
        generate_5m_signals, fetch_5m_bars, is_market_open,
    )

    mkt_open = is_market_open() if market_open_override is None else market_open_override
    all_signals: list[dict] = []

    if mkt_open:
        for sym in INTRADAY_STOCK_SYMBOLS:
            bars = fetch_5m_bars(sym, days=3)
            all_signals.extend(generate_5m_signals(sym, bars, is_crypto=False))

    for sym in INTRADAY_CRYPTO_SYMBOLS:
        bars = fetch_5m_bars(sym, days=3)
        all_signals.extend(generate_5m_signals(sym, bars, is_crypto=True))

    all_signals.sort(key=lambda s: s["conviction"], reverse=True)
    return all_signals


# ── Print helpers ─────────────────────────────────────────────────────────────

def print_intraday_scan(signals: list[dict]) -> None:
    from tradelab.strategies.intraday_5m import is_market_open
    utc_now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    mkt = "OPEN" if is_market_open() else "CLOSED"
    print(f"\n{'='*76}")
    print("  5m INTRADAY SIGNAL SCAN — stocks (L/S) + crypto (L)")
    print(f"{'='*76}")
    print(f"  Scanned at {utc_now}  |  Market: {mkt}")
    if not signals:
        print("\n  No signals right now.")
    else:
        print(f"\n  {'SYM':<8} {'SIDE':<5} {'STRATEGY':<16} {'CONV':>5}  REASON")
        print(f"  {'-'*70}")
        for s in signals:
            side_tag = "LONG " if s["side"] == "buy" else "SHORT"
            print(
                f"  {s['symbol']:<8} {side_tag}  {s['strategy']:<16} {s['conviction']:>5.2f}"
                f"  stop={s['stop_pct']*100:.1f}% tgt={s['target_pct']*100:.1f}%  "
                f"{s['reason']}"
            )
    print(f"{'='*76}\n")


def print_intraday_cycle(result: dict) -> None:
    print(f"\n{'='*70}")
    print("  5m INTRADAY CYCLE")
    print(f"{'='*70}")

    closed = result.get("mgmt", {}).get("closed", [])
    if closed:
        print(f"\n  Closed {len(closed)} position(s):")
        for c in closed:
            tag = "L" if c["side"] == "buy" else "S"
            print(
                f"    [{tag}] {c['symbol']:<8}  {c['reason']:<40}"
                f"  P&L ${c['pnl_dollars']:+.2f} ({c['pnl_pct']:+.1f}%)"
                f"  held {c['elapsed_min']:.0f}min"
            )

    bought = result.get("bought", [])
    if bought:
        print(f"\n  Opened {len(bought)} position(s):")
        for b in bought:
            tag = "LONG " if b["side"] == "buy" else "SHORT"
            print(
                f"    {tag} {b['symbol']:<8}  ${b['notional']:,.0f}  "
                f"entry=${b['entry_price']:.4f}  {b['strategy']}  conv={b['conviction']:.2f}"
            )
            print(
                f"           stop -{b['stop_pct']*100:.1f}%  target +{b['target_pct']*100:.1f}%"
                f"  max {MAX_HOLD_MINUTES}min"
            )
            print(f"           {b['reason']}")

    if not closed and not bought:
        n = result.get("signals_found", 0)
        print(f"\n  No action. Signals scanned: {n}")
    print(f"{'='*70}\n")


def print_intraday_status(session) -> None:
    """Show open intraday positions with live P&L."""
    positions = _load_positions(session)
    print(f"\n{'='*70}")
    print("  5m INTRADAY — Open Positions")
    print(f"{'='*70}")
    if not positions:
        print("  No open intraday positions.")
    for sym, pos in positions.items():
        current = _spot(sym)
        entry = pos["entry_price"]
        side = pos.get("side", "buy")
        if current and entry:
            if side == "buy":
                pnl_pct = (current - entry) / entry * 100
            else:
                pnl_pct = (entry - current) / entry * 100
            elapsed_min = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(pos["entry_time"]).replace(tzinfo=timezone.utc)
            ).total_seconds() / 60
            tag = "LONG " if side == "buy" else "SHORT"
            print(
                f"  {tag} {sym:<8}  ${pos.get('notional',0):,.0f}  "
                f"entry=${entry:.4f}  now=${current:.4f}  "
                f"P&L {pnl_pct:+.1f}%  held {elapsed_min:.0f}min  "
                f"[{pos.get('strategy','?')}]"
            )
    time_left = MAX_HOLD_MINUTES
    print(f"  (max hold: {time_left}min)")
    print(f"{'='*70}\n")
