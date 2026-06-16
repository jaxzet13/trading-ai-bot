from __future__ import annotations

"""
Crypto 1-2 hour day trading execution engine.

Budget: uses the $12k cash slice kept separate from the systematic engine.
Universe: BTC-USD, ETH-USD, SOL-USD (most liquid on Alpaca paper).
Rules:
  - Max 3 simultaneous positions, up to $4k each
  - Hard stop loss:  per-trade stop_pct (strategy-specific, 1.8-2.5%)
  - Take profit:     per-trade target_pct (strategy-specific, 3-5%)
  - Time exit:       close after MAX_HOLD_HOURS regardless of P&L
  - Trailing stop:   once up 1.5%, trail at 0.8% below peak
  - Only enter during 12:00-22:00 UTC (peak volume window)
  - Tracks positions in SystemState DB so restarts don't lose state
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
# ── Config ───────────────────────────────────────────────────────────────────
# Full universe of independently-acting cryptos available on Alpaca paper.
# Deliberately avoids BTC-only proxies — includes DeFi (AAVE, LINK), L1s
# (AVAX, ADA, DOT, LTC, XRP), AI narrative (RENDER), memes (DOGE, WIF),
# and the majors (BTC, ETH, SOL). Each has distinct catalysts and momentum cycles.
CRYPTO_DAY_SYMBOLS = [
    "BTC-USD",     # digital gold, macro/ETF driven
    "ETH-USD",     # smart contracts, staking/L2 driven
    "SOL-USD",     # high-speed L1, NFT/DeFi ecosystem
    "XRP-USD",     # payments/banking, Ripple legal catalysts
    "AVAX-USD",    # L1 subnet ecosystem, independent cycles
    "LINK-USD",    # oracle network, partnership-driven
    "AAVE-USD",    # DeFi lending protocol
    "LTC-USD",     # payments L1, halving cycles
    "ADA-USD",     # Cardano L1, own roadmap
    "DOT-USD",     # Polkadot parachain ecosystem
    "DOGE-USD",    # meme/payments, high beta
    "RENDER-USD",  # AI/GPU rendering narrative
    "WIF-USD",     # meme, very high beta
]
CRYPTO_DAY_BUDGET = 12_000   # total $ allocated to this engine
MAX_POSITIONS = 5            # up to 5 simultaneous day trades across 13 coins
MAX_PER_TRADE = 3_000        # max notional per trade ($3k keeps positions diversified)
MIN_TRADE = 200              # minimum order size (Alpaca minimum)
MAX_HOLD_HOURS = 2.0
TRAIL_ACTIVATE_PCT = 0.015   # activate trailing stop once up 1.5%
TRAIL_STOP_FROM_PEAK = 0.008 # trail 0.8% below the peak


# ── State helpers (SystemState DB) ──────────────────────────────────────────

def _key(symbol: str) -> str:
    return f"crypto_day_{symbol.replace('-', '_')}"


def _load_positions(session) -> dict[str, dict]:
    from tradelab.db.models import SystemState
    out = {}
    for row in session.query(SystemState).filter(
        SystemState.key.like("crypto_day_%")
    ).all():
        sym = row.key[len("crypto_day_"):].replace("_", "-")
        try:
            out[sym] = json.loads(row.value)
        except Exception:
            pass
    return out


def _save_position(session, symbol: str, data: dict) -> None:
    from tradelab.db.models import SystemState
    key = _key(symbol)
    row = session.query(SystemState).filter_by(key=key).first()
    if row:
        row.value = json.dumps(data)
    else:
        session.add(SystemState(key=key, value=json.dumps(data)))
    session.commit()


def _delete_position(session, symbol: str) -> None:
    from tradelab.db.models import SystemState
    key = _key(symbol)
    row = session.query(SystemState).filter_by(key=key).first()
    if row:
        session.delete(row)
        session.commit()


def _update_peak(session, symbol: str, peak: float) -> None:
    positions = _load_positions(session)
    if symbol in positions:
        positions[symbol]["peak_price"] = peak
        _save_position(session, symbol, positions[symbol])


# ── Price fetch ──────────────────────────────────────────────────────────────

def _spot(symbol: str) -> Optional[float]:
    try:
        import yfinance as yf
        h = yf.Ticker(symbol).history(period="1d", interval="1m")
        return float(h["Close"].iloc[-1]) if not h.empty else None
    except Exception:
        return None


# ── Sell helper ──────────────────────────────────────────────────────────────

def _sell_crypto_day(broker, symbol: str, qty: float, reason: str) -> Optional[str]:
    """Sell an exact qty of crypto. Used for closing day trade positions."""
    import math
    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        alpaca_sym = symbol.replace("-", "/")
        # Round down to 6 decimal places to avoid oversell
        safe_qty = math.floor(qty * 1_000_000) / 1_000_000
        if safe_qty <= 0:
            logger.warning("Crypto day: qty=%g too small to sell %s", qty, symbol)
            return None
        req = MarketOrderRequest(
            symbol=alpaca_sym, qty=safe_qty,
            side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
        )
        order = broker.client.submit_order(req)
        logger.info("CRYPTO DAY CLOSE %s qty=%g | %s | order_id=%s",
                    symbol, safe_qty, reason, order.id)
        return str(order.id)
    except Exception as exc:
        logger.error("Crypto day sell failed %s: %s", symbol, exc)
        return None


# ── Manage open positions ────────────────────────────────────────────────────

def manage_crypto_day_positions(session, broker) -> dict:
    """
    Check every tracked day trade position for:
    - Stop loss hit
    - Take profit hit
    - Time exit (>= MAX_HOLD_HOURS)
    - Trailing stop hit (once up TRAIL_ACTIVATE_PCT)
    Returns {"closed": list[dict]}
    """
    positions = _load_positions(session)
    closed = []

    for sym, pos in positions.items():
        current = _spot(sym)
        if current is None:
            logger.warning("Crypto day: can't get price for %s — skipping manage", sym)
            continue

        entry = pos["entry_price"]
        qty = pos["qty"]
        stop_pct = pos.get("stop_pct", 0.020)
        target_pct = pos.get("target_pct", 0.035)
        peak = pos.get("peak_price", entry)

        pnl_pct = (current - entry) / entry
        elapsed_h = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(pos["entry_time"]).replace(tzinfo=timezone.utc)
        ).total_seconds() / 3600

        # Update peak for trailing stop
        if current > peak:
            peak = current
            _update_peak(session, sym, peak)

        reason = None

        # Hard stop loss
        if pnl_pct <= -stop_pct:
            reason = f"STOP LOSS {pnl_pct*100:+.1f}% (limit -{stop_pct*100:.1f}%)"

        # Take profit
        elif pnl_pct >= target_pct:
            reason = f"TAKE PROFIT {pnl_pct*100:+.1f}% (target +{target_pct*100:.1f}%)"

        # Trailing stop (active once up TRAIL_ACTIVATE_PCT)
        elif pnl_pct >= TRAIL_ACTIVATE_PCT:
            trail_stop_price = peak * (1 - TRAIL_STOP_FROM_PEAK)
            if current < trail_stop_price:
                reason = (
                    f"TRAIL STOP — peak ${peak:.4f}, "
                    f"current ${current:.4f} ({pnl_pct*100:+.1f}%)"
                )

        # Time exit
        elif elapsed_h >= MAX_HOLD_HOURS:
            reason = f"TIME EXIT {elapsed_h:.1f}h P&L {pnl_pct*100:+.1f}%"

        if reason:
            oid = _sell_crypto_day(broker, sym, qty, reason)
            _delete_position(session, sym)
            closed.append({
                "symbol": sym, "reason": reason,
                "pnl_pct": round(pnl_pct * 100, 2),
                "pnl_dollars": round(qty * entry * pnl_pct, 2),
                "order_id": oid,
            })

    return {"closed": closed}


# ── Main cycle ───────────────────────────────────────────────────────────────

def run_crypto_day_cycle(session, broker) -> dict:
    """
    Full crypto day trading cycle:
    1. Manage existing positions (stops, TP, time exit, trailing stop)
    2. Check trading window
    3. Scan for new signals
    4. Execute highest-conviction signals within budget
    """
    from tradelab.strategies.crypto_day import scan_crypto

    # Step 1: Manage open positions (runs 24/7 — always check stops/TP/time exits)
    mgmt = manage_crypto_day_positions(session, broker)

    # Step 3: Check capacity
    open_positions = _load_positions(session)
    slots = MAX_POSITIONS - len(open_positions)
    deployed = sum(
        p.get("qty", 0) * p.get("entry_price", 0)
        for p in open_positions.values()
    )
    available = max(0.0, CRYPTO_DAY_BUDGET - deployed)

    if slots <= 0 or available < MIN_TRADE:
        logger.info(
            "Crypto day: %d/%d slots used, $%.0f available",
            len(open_positions), MAX_POSITIONS, available,
        )
        return {"mgmt": mgmt, "bought": [], "open_count": len(open_positions)}

    # Step 4: Scan signals on symbols we don't already hold
    scan_syms = [s for s in CRYPTO_DAY_SYMBOLS if s not in open_positions]
    if not scan_syms:
        return {"mgmt": mgmt, "bought": [], "open_count": len(open_positions)}

    signals = scan_crypto(scan_syms)
    if not signals:
        logger.info("Crypto day: no signals on %s", ", ".join(scan_syms))
        return {"mgmt": mgmt, "bought": [], "signals": 0}

    # Step 5: Execute top signals
    bought = []
    per_trade = min(MAX_PER_TRADE, available / max(slots, 1))

    for sig in signals[:slots]:
        sym = sig["symbol"]
        if sym in open_positions:
            continue

        notional = round(min(per_trade, available), 2)
        if notional < MIN_TRADE:
            break

        alpaca_sym = sym.replace("-", "/")
        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            req = MarketOrderRequest(
                symbol=alpaca_sym, notional=notional,
                side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
            )
            order = broker.client.submit_order(req)
            logger.info(
                "CRYPTO DAY BUY %s $%.0f %s conv=%.2f order_id=%s",
                sym, notional, sig["strategy"], sig["conviction"], order.id,
            )

            # Wait for fill, then read actual position qty
            time.sleep(2)
            entry_price = _spot(sym) or (notional / 1)
            qty = notional / entry_price if entry_price > 0 else 0.0
            for p in broker.get_positions():
                if p["symbol"] == sym:
                    entry_price = p["current_price"]
                    # qty = total held; store only what we bought
                    qty = notional / entry_price if entry_price > 0 else qty
                    break

            _save_position(session, sym, {
                "entry_price": entry_price,
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "qty": qty,
                "notional": notional,
                "strategy": sig["strategy"],
                "stop_pct": sig["stop_pct"],
                "target_pct": sig["target_pct"],
                "peak_price": entry_price,
            })

            open_positions[sym] = {}  # mark as held so we don't double-buy
            available -= notional

            bought.append({
                "symbol": sym,
                "notional": notional,
                "qty": round(qty, 6),
                "entry_price": entry_price,
                "strategy": sig["strategy"],
                "conviction": sig["conviction"],
                "reason": sig["reason"],
                "stop_pct": sig["stop_pct"],
                "target_pct": sig["target_pct"],
            })
        except Exception as exc:
            logger.error("Crypto day BUY failed %s: %s", sym, exc)

    return {"mgmt": mgmt, "bought": bought, "signals_found": len(signals)}


# ── Scan-only (no execution) ─────────────────────────────────────────────────

def scan_only() -> list[dict]:
    """Run signal scan without placing any orders. For 'tradelab crypto-scan'."""
    from tradelab.strategies.crypto_day import scan_crypto
    return scan_crypto(CRYPTO_DAY_SYMBOLS)


# ── Print helpers ─────────────────────────────────────────────────────────────

def print_crypto_scan(signals: list[dict]) -> None:
    utc_now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    print(f"\n{'='*70}")
    print("  CRYPTO DAY SCAN — 1h signal scanner (24/7)")
    print(f"{'='*70}")
    print(f"  Scanned at {utc_now}")
    if not signals:
        print("\n  No signals right now.")
    else:
        print(f"\n  {'SYM':<10} {'STRATEGY':<14} {'CONV':>5}  REASON")
        print(f"  {'-'*66}")
        for s in signals:
            print(f"  {s['symbol']:<10} {s['strategy']:<14} {s['conviction']:>5.2f}  {s['reason']}")
    print(f"{'='*70}\n")


def print_crypto_cycle(result: dict) -> None:
    print(f"\n{'='*70}")
    print("  CRYPTO DAY CYCLE")
    print(f"{'='*70}")

    closed = result.get("mgmt", {}).get("closed", [])
    if closed:
        print(f"\n  Closed positions:")
        for c in closed:
            print(f"    {c['symbol']:<10} {c['reason']}  P&L ${c['pnl_dollars']:+.2f} ({c['pnl_pct']:+.1f}%)")

    bought = result.get("bought", [])
    if bought:
        print(f"\n  Opened positions:")
        for b in bought:
            print(
                f"    {b['symbol']:<10} ${b['notional']:,.0f}  "
                f"entry=${b['entry_price']:.4f}  "
                f"{b['strategy']}  conv={b['conviction']:.2f}"
            )
            print(f"      Stop -{b['stop_pct']*100:.1f}%  Target +{b['target_pct']*100:.1f}%")
            print(f"      {b['reason']}")

    if not closed and not bought:
        skip = result.get("skipped", "")
        if skip == "outside_window":
            print("\n  Outside trading window (12-22 UTC). No action.")
        else:
            print(f"\n  No action this cycle. Signals found: {result.get('signals_found', 0)}")
    print(f"{'='*70}\n")


def print_crypto_status(session) -> None:
    """Show current open day trade positions with live P&L."""
    positions = _load_positions(session)
    print(f"\n{'='*60}")
    print("  CRYPTO DAY — Open Positions")
    print(f"{'='*60}")
    if not positions:
        print("  No open day trade positions.")
    for sym, pos in positions.items():
        current = _spot(sym)
        entry = pos["entry_price"]
        if current and entry:
            pnl_pct = (current - entry) / entry * 100
            elapsed_h = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(pos["entry_time"]).replace(tzinfo=timezone.utc)
            ).total_seconds() / 3600
            notional = pos.get("notional", 0)
            print(
                f"  {sym:<10} ${notional:,.0f}  entry=${entry:.4f}  "
                f"now=${current:.4f}  P&L {pnl_pct:+.1f}%  "
                f"held {elapsed_h:.1f}h  [{pos['strategy']}]"
            )
    print(f"{'='*60}\n")
