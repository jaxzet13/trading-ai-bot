"""Tennis real-money TEST (python -m tennis realtest): the top 3 frozen strategies, smallest stake, 2 hours.

Account holder, Nov 24: "Just for a test start running the top 3 strategies with the lowest amount of money for 2
hours 4 dollars loss and you stop it, this is only for the tennis arbitrage not for the 15m market".

  * Strategies: the first 3 of the newest forward batch (leaders that also made money on the hold-out).
  * Decisions: the practice runner's live minute bars and lab.bet(), the code the lab scores with. A rule acts
    only when its decision minute is the bar that just closed, never on an old one.
  * Orders: 1 contract, immediate-or-cancel, at the live order book's ask plus SLACK_C cents at most (the lab
    assumes the next minute's worst price), through kalshi15m.real.KalshiAPI (the crypto bot's tested client).
  * Limits: no new bet after RUN_S; no new bet when realized P&L minus the cost of open bets minus this bet's
    cost would reach -MAX_LOSS. Stop by hand: touch STOP_TENNIS_REAL.
  * Every order, fill and settlement goes to data/tennis/real_test_log.jsonl and, briefly, to the tennis channel.
It never touches the crypto bot: separate process, separate log, its own positions.

AUTO mode (python -m tennis auto; account holder, Nov 24: "instead of arbitrage ... a regular tennis auto better
that has consistent profitability", then "start them with real money with the same 5 dollar stop loss"): the same
code, betting the strategies that passed their forward test (50+ bets on new matches, t >= 2.5) or, until one
does, the top AUTO_N of the newest frozen batch; re-reads that list every 10 minutes, runs until stopped (touch
STOP_TENNIS_AUTO), keeps its own log (data/tennis/auto_log.jsonl) and stops new bets once its realized P&L minus
open cost would reach -AUTO_MAX_LOSS.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import numpy as np

from . import api as tapi, lab, notify, paper
from .collect import DATA

ROOT = Path(__file__).resolve().parent.parent
LOG = DATA / "real_test_log.jsonl"
STOP = ROOT / "STOP_TENNIS_REAL"
RUN_S = 2 * 3600
MAX_LOSS = 4.0
AUTO_MAX_LOSS = 5.0              # account holder, Nov 24: "start them with real money with the same 5 dollar stop loss"
TOP_N = 3
AUTO_N = 50                      # account holder, Nov 25: "use more tennis strategies at once": the whole frozen batch
BAND_TOL = 0.03                                    # live ask may be this far outside a band strategy's prices
SLACK_C = 2


def _log(rec):
    rec = {"ts": round(time.time(), 1), **rec}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _events():
    return [json.loads(ln) for ln in open(LOG)] if LOG.exists() else []


def strategies(auto=False):
    if auto:
        # strategies that passed the forward test if any; until then the top AUTO_N of the newest frozen batch
        # (the leaderboard's best that also made money on the hold-out third), as the account holder asked
        strats, passed = paper._strategies()
        return strats if passed else strats[:AUTO_N]
    bs = sorted((DATA / "forward").glob("batch_*.json"))
    return json.loads(bs[-1].read_text())["strategies"][:TOP_N] if bs else []


def decide_now(m, s, now):
    """lab.bet's decision on the bar that just closed -> side or None. bet() needs a next bar to price the fill;
    live that bar is the order we are about to send, so a placeholder bar one minute later stands in for it."""
    if len(m["rel"]) < 2:
        return None
    last_end = m["start"] + m["rel"][-1] * 60
    if now - last_end > 90:                                   # the newest closed bar must be fresh
        return None
    m2 = dict(m, value=0.0, rel=np.append(m["rel"], m["rel"][-1] + 1), mid=np.append(m["mid"], m["mid"][-1]),
              askhi=np.append(m["askhi"], min(0.98, m["askhi"][-1])), bidlo=np.append(m["bidlo"], max(0.02, m["bidlo"][-1])))
    r = lab.bet(m2, s)
    if not r:
        return None
    side, _, _, minute = r
    return side if abs(minute - m["rel"][-1]) < 0.01 else None   # decided on THIS bar, not an older one


def realized_and_open(client):
    """(realized P&L of settled test bets, cost of test bets still open) from our own log + Kalshi settlements."""
    ev = _events()
    fills = [e for e in ev if e.get("event") == "fill" and e.get("n", 0) > 0]
    settled = {e["ticker"]: e for e in ev if e.get("event") == "settle"}
    realized = sum(e["pnl"] for e in settled.values())
    open_cost = sum(f["cost"] + f["fee"] for f in fills if f["ticker"] not in settled)
    for f in fills:                                            # look up settlements for open tickers
        if f["ticker"] in settled:
            continue
        try:
            ss = client.settlements(ticker=f["ticker"])
        except Exception:
            continue
        if ss:
            s = ss[0]
            rev = float(s.get("revenue", 0)) / 100
            pnl = round(rev - f["cost"] - f["fee"], 4)
            _log({"event": "settle", "ticker": f["ticker"], "strategy": f["strategy"], "result": s.get("market_result"),
                  "revenue": rev, "pnl": pnl})
            notify.post("🎾 Tennis bet settled", [f"{f['ticker']}", f"{'Won' if pnl > 0 else 'Lost'} {pnl:+.2f} $"],
                        notify.GREEN if pnl > 0 else 0xEF4444)
            settled[f["ticker"]] = {"pnl": pnl}
            realized += pnl
            open_cost -= f["cost"] + f["fee"]
    return realized, max(open_cost, 0.0)


def run(log=print, auto=False):
    global LOG, STOP, MAX_LOSS
    if auto:
        LOG, STOP, MAX_LOSS = DATA / "auto_log.jsonl", ROOT / "STOP_TENNIS_AUTO", AUTO_MAX_LOSS
    from kalshi15m import real as KR
    client = KR.KalshiAPI.from_env(KR.PROD)
    strats = strategies(auto)
    total, crypto = client.balances()
    start = time.time()
    refreshed = start
    _log({"event": "start", "auto": auto, "strategies": [s["id"] for s in strats], "balance_total": total,
          "balance_crypto": crypto, "run_s": None if auto else RUN_S, "max_loss": MAX_LOSS})
    log(f"tennis {'auto-better' if auto else 'real test'}: {len(strats)} strategies, balance ${total:.2f} "
        f"(crypto shard ${crypto:.2f}), stop at -${MAX_LOSS:.2f}")
    if auto:
        notify.post("🎾 Tennis auto-better started", [f"{len(strats)} strategies · 1 contract a bet · stops at −${MAX_LOSS:.0f}",
                                                      *[lab_desc(s) for s in strats]], notify.GREEN)
    else:
        notify.post("🎾 Real-money test started", [f"Top {len(strats)} strategies · 1 contract a bet · 2 hours · stops at −${MAX_LOSS:.0f}",
                                                   *[lab_desc(s) for s in strats]])
    done = {(e["ticker"], e["strategy"]) for e in _events() if e.get("event") in ("order", "skip_limit")}
    held = {e["ticker"] for e in _events() if e.get("event") == "fill" and e.get("n", 0) > 0}
    while True:
        now = time.time()
        if STOP.exists():
            log("STOP_TENNIS_REAL present: stopping"); _log({"event": "stop", "why": "stop file"}); break
        realized, open_cost = realized_and_open(client)
        if auto and now - refreshed > 600:
            new = strategies(True)
            if {s["id"] for s in new} != {s["id"] for s in strats}:
                _log({"event": "strategies", "strategies": [s["id"] for s in new]})
                added = [s for s in new if s["id"] not in {x["id"] for x in strats}]
                if added:
                    notify.post("🎾 Auto-better: strategy added", [lab_desc(s) for s in added] + ["1 contract a bet"], notify.GOLD)
                strats = new
            refreshed = now
        if auto and not strats:
            time.sleep(60)
            continue
        if not auto and now - start > RUN_S:
            if open_cost <= 0:
                _log({"event": "stop", "why": "2 hours over, no open bets", "realized": realized})
                notify.post("🎾 Real-money test finished", [f"Result {realized:+.2f} $"])
                break
            time.sleep(60)
            continue
        try:
            starts = paper._start_times()
            markets = paper.live_markets(starts, now)
        except Exception as e:
            log(f"  market data failed: {e!r}"); time.sleep(30); continue
        for m in markets:
            # auto mode bets Challenger matches only: in the Nov 24 pooled test of 28,590 markets the one persistent
            # bias was Challenger favourites (80-95c winning 2-3c more often than priced); ITF favourites at the
            # same prices won LESS often than priced and ATP/WTA were noise
            if auto and m.get("series") not in lab.SCOPES["chal"]:
                continue
            for s in strats:
                key = (m["ticker"], s["id"])
                if key in done or m["ticker"] in held:
                    continue
                side = decide_now(m, s, now)
                if not side:
                    continue
                done.add(key)
                try:
                    top = tapi.orderbook_top(m["ticker"])
                except Exception as e:
                    _log({"event": "error", "ticker": m["ticker"], "strategy": s["id"], "why": f"book: {e!r}"}); continue
                ask = top["yes_ask"] if side == "yes" else top["no_ask"]
                if not ask or not 0.02 <= ask <= 0.96:
                    _log({"event": "skip", "ticker": m["ticker"], "strategy": s["id"], "why": f"no usable ask ({ask})"}); continue
                # the decision is made on the last closed candle; the live book can be far from it when the match has
                # already started (Kalshi's "scheduled start" is often late). A price well outside the band is a
                # different bet from the one that was tested: leave it
                if s.get("fam") == "band" and not s["lo"] - BAND_TOL <= ask <= s["hi"] + BAND_TOL:
                    _log({"event": "skip", "ticker": m["ticker"], "strategy": s["id"],
                          "why": f"live ask {ask:.2f} outside the band"}); continue
                limit = round(min(0.98, ask + SLACK_C / 100), 2)
                worst = limit + tapi.fee(limit, 1)
                if realized - open_cost - worst <= -MAX_LOSS:
                    _log({"event": "skip_limit", "ticker": m["ticker"], "strategy": s["id"],
                          "why": f"loss limit: realized {realized:+.2f}, open {open_cost:.2f}, this bet up to {worst:.2f}"})
                    continue
                cid = str(uuid.uuid4())
                body = KR.order_body(m["ticker"], side, limit, 1, cid)
                _log({"event": "order", "ticker": m["ticker"], "strategy": s["id"], "side": side, "limit": limit,
                      "book_ask": ask, "client_order_id": cid, "minute": round(float(m["rel"][-1]), 1)})
                try:
                    resp = client.create_order(body)
                except Exception as e:
                    _log({"event": "error", "ticker": m["ticker"], "strategy": s["id"], "why": f"order: {e!r}"})
                    log(f"  order failed {m['ticker']}: {e!r}")
                    continue
                n = float(resp.get("fill_count") or resp.get("fill_count_fp") or 0)
                avg = resp.get("average_fill_price")
                px = float(avg) if avg is not None else limit
                if side == "no" and avg is not None:
                    px = round(1 - float(avg), 4)             # V2 quotes the YES book
                fee = float(resp.get("average_fee_paid") or 0) * n
                rec = _log({"event": "fill", "ticker": m["ticker"], "strategy": s["id"], "side": side, "n": n,
                            "price": px, "cost": round(px * n, 4), "fee": round(fee, 4), "order_id": resp.get("order_id"),
                            "raw": {k: resp.get(k) for k in ("fill_count", "remaining_count", "average_fill_price", "average_fee_paid")}})
                if n > 0:
                    held.add(m["ticker"])
                    open_cost += rec["cost"] + rec["fee"]
                    notify.post("🎾 Auto bet" if auto else "🎾 Real test bet", [f"{m['ticker']}", f"Buy {side.upper()} · {n:g} @ {px * 100:.0f}¢ · {lab_desc(s)}"])
                log(f"  {m['ticker']} {side} limit {limit}: filled {n:g} @ {px}")
        time.sleep(15)


def lab_desc(s):
    from .learn import describe
    return describe(s)
