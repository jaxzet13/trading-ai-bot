"""La Liga underdog bettor, REAL MONEY, small (python -m soccer laliga [dry]).

Account holder, Nov 28: "The La Liga strategy with +11c I want you to start that on live money along with the tennis bets".
What the research found (research/soccer_focus): the +11c came from the search's picks, mostly "buy the team priced 20-30c
about 30-40 minutes before kickoff". The same family lost 5c a bet on five other soccer leagues, and the +11c rested on
three upsets, so this is a bet on a hunch the evidence does not support. It runs small and stops itself, as asked.

Rule (one bet per market, 20-30c is whatever the market is: a team or the draw): between 45 and 28 minutes before kickoff, if
the live YES ask is 20-30c (2c tolerance), buy CONTRACTS contracts immediate-or-cancel at the ask + 1c. Kalshi's start field
for team sports is the expected expiration, about 3 hours after kickoff, so kickoff = occurrence time - 3h (checked against
ESPN's kickoff times). Stops new bets when realized P&L minus open cost minus this bet would reach -MAX_LOSS. Stop by hand:
touch STOP_LALIGA. Own log: data/soccer/laliga_log.jsonl. Separate process; never touches the crypto bot.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from pathlib import Path

from tennis import api as tapi, notify

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "soccer"
LOG = DATA / "laliga_log.jsonl"
STOP = ROOT / "STOP_LALIGA"
SERIES = "KXLALIGAGAME"
LO, HI, TOL = 0.20, 0.30, 0.02
WINDOW_MIN = (28, 45)                 # minutes before kickoff in which a market may be bought
KICKOFF_LAG_S = 3 * 3600
CONTRACTS = 2
MAX_LOSS = 3.0
SLACK_C = 1


def _ts(x):
    return int(dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp())


def _log(rec):
    DATA.mkdir(parents=True, exist_ok=True)
    rec = dict(rec, ts=round(time.time(), 1))
    with open(LOG, "a") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    return rec


def _events():
    try:
        return [json.loads(ln) for ln in open(LOG)]
    except OSError:
        return []


def kickoff_of(m):
    occ = m.get("occurrence_datetime") or m.get("expected_expiration_time")
    return _ts(occ) - KICKOFF_LAG_S if occ else None


def in_window(kickoff, now):
    """True while the market is 28..45 minutes before kickoff."""
    if kickoff is None:
        return False
    mins = (kickoff - now) / 60
    return WINDOW_MIN[0] <= mins <= WINDOW_MIN[1]


def in_band(ask):
    return ask is not None and LO - TOL <= ask <= HI + TOL


def realized_and_open(client):
    ev = _events()
    fills = [e for e in ev if e.get("event") == "fill" and e.get("n", 0) > 0]
    settled = {e["ticker"]: e for e in ev if e.get("event") == "settle"}
    realized = sum(e["pnl"] for e in settled.values())
    open_cost = sum(f["cost"] + f["fee"] for f in fills if f["ticker"] not in settled)
    for f in fills:
        if f["ticker"] in settled:
            continue
        try:
            ss = client.settlements(ticker=f["ticker"])
        except Exception:
            continue
        if ss:
            rev = float(ss[0].get("revenue", 0)) / 100
            pnl = round(rev - f["cost"] - f["fee"], 4)
            _log({"event": "settle", "ticker": f["ticker"], "result": ss[0].get("market_result"), "revenue": rev, "pnl": pnl})
            notify.post("⚽ La Liga bet settled", [f["ticker"], f"{'Won' if pnl > 0 else 'Lost'} {pnl:+.2f} $"], notify.GREEN if pnl > 0 else 0xEF4444)
            settled[f["ticker"]] = {"pnl": pnl}
            realized += pnl
            open_cost -= f["cost"] + f["fee"]
    return realized, max(open_cost, 0.0)


def run(log=print, dry=False):
    from kalshi15m import real as KR
    client = None if dry else KR.KalshiAPI.from_env(KR.PROD)
    _log({"event": "start", "dry": dry, "band": [LO, HI], "contracts": CONTRACTS, "max_loss": MAX_LOSS})
    log(f"La Liga underdog bettor {'(dry run)' if dry else 'LIVE'}: buy the 20-30c market {WINDOW_MIN[0]}-{WINDOW_MIN[1]} min before kickoff, "
        f"{CONTRACTS} contracts, stop at -${MAX_LOSS:.2f}")
    if not dry:
        notify.post("⚽ La Liga bettor started", [f"Buy the 20-30¢ market ~40 min before kickoff · {CONTRACTS} contracts a bet · stops at −${MAX_LOSS:.0f}"], notify.GREEN)
    done = {e["ticker"] for e in _events() if e.get("event") in ("order", "skip_limit", "skip", "would_order")}
    while True:
        now = time.time()
        if STOP.exists():
            log("STOP_LALIGA present: stopping"); _log({"event": "stop", "why": "stop file"}); break
        realized, open_cost = (0.0, 0.0) if dry else realized_and_open(client)
        try:
            ms = tapi.get("/markets", {"series_ticker": SERIES, "status": "open", "limit": 1000}).get("markets", [])
        except Exception as e:
            log(f"  market list failed: {e!r}"); time.sleep(30); continue
        for m in ms:
            t = m["ticker"]
            if t in done or not in_window(kickoff_of(m), now):
                continue
            try:
                top = tapi.orderbook_top(t)
            except Exception as e:
                _log({"event": "error", "ticker": t, "why": f"book: {e!r}"}); continue
            ask = top["yes_ask"]
            if not in_band(ask):
                if (kickoff_of(m) - now) / 60 < WINDOW_MIN[0] + 1:          # last chance passed: remember the skip once
                    done.add(t); _log({"event": "skip", "ticker": t, "why": f"live ask {ask} outside {LO}-{HI}"})
                continue
            limit = round(min(0.98, ask + SLACK_C / 100), 2)
            worst = limit * CONTRACTS + tapi.fee(limit, CONTRACTS)
            if realized - open_cost - worst <= -MAX_LOSS:
                done.add(t); _log({"event": "skip_limit", "ticker": t, "why": f"loss limit: realized {realized:+.2f}, open {open_cost:.2f}"}); continue
            done.add(t)
            if dry:
                _log({"event": "would_order", "ticker": t, "ask": ask, "limit": limit}); log(f"  would buy {t} YES at <= {limit}"); continue
            cid = str(uuid.uuid4())
            _log({"event": "order", "ticker": t, "side": "yes", "limit": limit, "n": CONTRACTS, "book_ask": ask, "client_order_id": cid,
                  "minutes_to_kickoff": round((kickoff_of(m) - now) / 60, 1)})
            try:
                resp = client.create_order(KR.order_body(t, "yes", limit, CONTRACTS, cid))
            except Exception as e:
                _log({"event": "error", "ticker": t, "why": f"order: {e!r}"}); log(f"  order failed {t}: {e!r}"); continue
            n = float(resp.get("fill_count") or resp.get("fill_count_fp") or 0)
            avg = resp.get("average_fill_price")
            px = float(avg) if avg is not None else limit
            fee = float(resp.get("average_fee_paid") or 0) * n
            rec = _log({"event": "fill", "ticker": t, "side": "yes", "n": n, "price": px, "cost": round(px * n, 4), "fee": round(fee, 4),
                        "order_id": resp.get("order_id")})
            if n > 0:
                open_cost += rec["cost"] + rec["fee"]
                notify.post("⚽ La Liga bet", [t, f"Buy YES · {n:g} @ {px * 100:.0f}¢"])
            log(f"  {t}: filled {n:g} @ {px}")
        time.sleep(20)
