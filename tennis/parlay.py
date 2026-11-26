"""Tennis 3-leg parlays on Kalshi combos, REAL MONEY (python -m tennis parlay).

Account holder, Nov 26: "Use that best 3 leg parlay strategy", then chose "Kalshi combos, move $10": $10 moved from
the crypto balance (shard 2) to the combo balance (shard 1); $1 a parlay; stops itself at -$5.

The strategy is the best of the Nov 26 parlay search (research/tennis_parlay): legs = Challenger players priced
90-95c (mid) 120 minutes before the scheduled start (lab rule band:m-120:0.90-0.95:chal, decided on the bar that just
closed, like the auto-better). Three legs from three different matches, all still before their start, make one combo.
Backtest, buying only while every match is still pre-match: 21 combos in 64 days, +11.4% a dollar, t 2.1. Picked out
of about 80,000 candidates, so the result may be luck; the walk-forward search did not confirm it. Run as an
experiment the account holder asked for.

Buying a combo (Kalshi RFQ flow, checked live on Nov 26):
  1. POST /multivariate_event_collections/KXMVESPORTSMULTIGAMEEXTENDED-R with the three legs (side yes)
  2. POST /communications/rfqs for STAKE dollars of contracts; market makers answer within seconds
  3. buying YES = accepting a quote's NO side, at price 1 - no_bid (a 0.10-contract test confirmed it)
  4. accept only if that price plus the taker fee is no worse than the backtest's price: the product of the three
     legs' live asks plus their fees
Stop: touch STOP_TENNIS_PARLAY. Log: data/tennis/parlay_log.jsonl. Separate from the crypto bot and the auto-better.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from . import api as tapi, lab, notify, paper
from .collect import DATA

ROOT = Path(__file__).resolve().parent.parent
LOG = DATA / "parlay_log.jsonl"
STOP = ROOT / "STOP_TENNIS_PARLAY"
COLLECTION = "KXMVESPORTSMULTIGAMEEXTENDED-R"
RULE = {"id": "band:m-120:0.90-0.95:chal", "fam": "band", "M": -120, "lo": 0.90, "hi": 0.95, "scope": "chal"}
LEGS = 3
STAKE = 1.00                   # dollars a parlay
MAX_LOSS = 5.0                 # no new parlay once realized P&L minus open cost would reach -MAX_LOSS
BAND_TOL = 0.03                # the live ask may be this far outside the rule's band
MIN_LEAD_S = 300               # a leg must be at least this long before its scheduled start when the combo is bought
QUOTE_WAIT_S = 45
RETRY_S = 180                  # between quote requests for the same pending legs
SHARD = 1                      # combos are paid from exchange shard 1


def fee(p):
    return 0.07 * p * (1 - p)


def _log(rec):
    rec = {"ts": round(time.time(), 1), **rec}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _events():
    return [json.loads(ln) for ln in open(LOG)] if LOG.exists() else []


def shard_balance(client):
    bd = {int(x["exchange_index"]): float(x["balance"])
          for x in client.get("/portfolio/balance").get("balance_breakdown") or []}
    return bd.get(SHARD, 0.0)


def realized_and_open(client):
    ev = _events()
    fills = [e for e in ev if e.get("event") == "fill"]
    settled = {e["ticker"]: e for e in ev if e.get("event") == "settle"}
    realized = sum(e["pnl"] for e in settled.values())
    open_cost = 0.0
    for f in fills:
        if f["ticker"] in settled:
            continue
        try:
            ss = client.settlements(ticker=f["ticker"])
        except Exception:
            ss = []
        if ss:
            s = ss[0]
            rev = float(s.get("revenue", 0)) / 100
            pnl = round(rev - f["cost"] - f["fee"], 4)
            _log({"event": "settle", "ticker": f["ticker"], "result": s.get("market_result"), "revenue": rev, "pnl": pnl})
            notify.post("🎾 Parlay settled", [f"{' + '.join(f['players'])}", f"{'Won' if pnl > 0 else 'Lost'} {pnl:+.2f} $"],
                        notify.GREEN if pnl > 0 else 0xEF4444)
            realized += pnl
        else:
            open_cost += f["cost"] + f["fee"]
    return realized, open_cost


def buy_combo(client, legs, log=print):
    """Price the combo, request quotes, buy if no worse than the product of the legs. -> fill record or None."""
    tops = []
    for lg in legs:
        top = tapi.orderbook_top(lg["ticker"])
        ask = top.get("yes_ask")
        if not ask or not (RULE["lo"] - BAND_TOL <= ask <= RULE["hi"] + BAND_TOL):
            _log({"event": "drop_leg", "ticker": lg["ticker"], "why": f"live ask {ask} outside the band"})
            lg["dead"] = True
            return None
        tops.append(ask)
    fair = math.prod(a + fee(a) for a in tops)               # what the backtest paid per contract
    combo = client._send("POST", f"/multivariate_event_collections/{COLLECTION}", body={
        "selected_markets": [{"market_ticker": lg["ticker"], "event_ticker": lg["event"], "side": "yes"} for lg in legs]})
    tk = combo["market_ticker"]
    n = math.floor(STAKE / fair * 100) / 100
    rid = client._send("POST", "/communications/rfqs", body={
        "market_ticker": tk, "contracts_fp": f"{n:.2f}", "rest_remainder": False, "replace_existing": True})["id"]
    _log({"event": "rfq", "ticker": tk, "rfq_id": rid, "contracts": n, "legs": [lg["ticker"] for lg in legs],
          "leg_asks": tops, "fair": round(fair, 4)})
    try:
        best, t0 = None, time.time()
        while time.time() - t0 < QUOTE_WAIT_S:
            time.sleep(4)
            qs = [q for q in client.get("/communications/quotes", {"rfq_id": rid, "rfq_user_filter": "self"}).get("quotes", [])
                  if q.get("status") == "open" and float(q.get("no_bid_dollars") or 0) > 0]
            if qs:
                best = max(qs, key=lambda q: float(q["no_bid_dollars"]))
                price = 1 - float(best["no_bid_dollars"])
                if price + fee(price) <= fair + 1e-9:
                    break
        if not best:
            _log({"event": "no_quote", "ticker": tk, "rfq_id": rid})
            return None
        price = round(1 - float(best["no_bid_dollars"]), 4)
        if price + fee(price) > fair + 1e-9:
            _log({"event": "too_expensive", "ticker": tk, "price": price, "with_fee": round(price + fee(price), 4),
                  "fair": round(fair, 4)})
            log(f"  combo quote {price:.3f} (+fee {price + fee(price):.3f}) worse than legs {fair:.3f}: skipped")
            return None
        client._send("PUT", f"/communications/rfqs/{rid}/quotes/{best['id']}/accept", body={"accepted_side": "no"})
        for _ in range(10):
            time.sleep(2)
            pos = [p for p in client.positions(ticker=tk) if float(p.get("position_fp") or 0) != 0]
            if pos:
                got = float(pos[0]["position_fp"])
                fills = client.fills(ticker=tk)
                fees = sum(float(f.get("fee_cost") or 0) for f in fills)
                rec = _log({"event": "fill", "ticker": tk, "contracts": got, "price": price, "cost": round(got * price, 4),
                            "fee": round(fees, 4), "fair": round(fair, 4), "legs": [lg["ticker"] for lg in legs],
                            "players": [lg["player"] for lg in legs], "leg_asks": tops})
                notify.post("🎾 Parlay bought", [" + ".join(lg["player"] for lg in legs),
                                                 f"{got:g} @ {price * 100:.1f}¢ (legs {fair * 100:.1f}¢) · pays ${got:.2f} if all 3 win"],
                            notify.GOLD)
                log(f"  parlay bought: {got:g} @ {price:.3f} ({' + '.join(lg['player'] for lg in legs)})")
                return rec
        _log({"event": "not_filled", "ticker": tk, "rfq_id": rid, "quote": best["id"]})
        return None
    finally:
        try:
            client._send("DELETE", f"/communications/rfqs/{rid}")
        except Exception:
            pass


def run(log=print):
    from kalshi15m import real as KR
    client = KR.KalshiAPI.from_env(KR.PROD)
    bal = shard_balance(client)
    _log({"event": "start", "rule": RULE["id"], "stake": STAKE, "max_loss": MAX_LOSS, "balance_shard1": bal})
    log(f"tennis parlays: {LEGS} legs of {RULE['id']}, ${STAKE:.2f} a parlay, combo balance ${bal:.2f}, stop at -${MAX_LOSS:.0f}")
    used = {t for e in _events() if e.get("event") == "fill" for t in e["legs"]}
    used_events = {t.rsplit("-", 1)[0] for t in used}
    pending, last_try = [], 0.0
    for e in _events():                                       # legs found before a restart, still pre-match
        if e.get("event") == "leg" and e["start"] - time.time() > MIN_LEAD_S and e["event_ticker"] not in used_events:
            pending.append({"ticker": e["ticker"], "event": e["event_ticker"], "start": e["start"], "player": e["player"]})
    while True:
        if STOP.exists():
            log("STOP_TENNIS_PARLAY present: stopping"); _log({"event": "stop", "why": "stop file"}); break
        now = time.time()
        try:
            starts = paper._start_times()
            markets = paper.live_markets(starts, now)
        except Exception as e:
            log(f"  market data failed: {e!r}"); time.sleep(30); continue
        names = {}
        for m in markets:
            if m.get("series") not in lab.SCOPES["chal"] or m["event"] in used_events:
                continue
            if any(p["event"] == m["event"] for p in pending):
                continue
            from .realtest import decide_now
            if decide_now(m, RULE, now) != "yes":
                continue
            if not names:
                names = {mk["ticker"]: mk.get("yes_sub_title") or mk["ticker"].rsplit("-", 1)[-1]
                         for s in lab.SCOPES["chal"] for mk in tapi.open_markets(s)}
            lg = {"ticker": m["ticker"], "event": m["event"], "start": m["start"], "player": names.get(m["ticker"], m["ticker"])}
            pending.append(lg)
            _log({"event": "leg", "ticker": lg["ticker"], "event_ticker": lg["event"], "start": lg["start"],
                  "player": lg["player"], "mid": round(float(m["mid"][-1]), 4)})
            log(f"  leg: {lg['player']} ({lg['ticker']}) mid {m['mid'][-1]:.3f}")
        pending = [p for p in pending if not p.get("dead") and p["start"] - now > MIN_LEAD_S]
        if len(pending) >= LEGS and now - last_try >= RETRY_S:
            last_try = now
            realized, open_cost = realized_and_open(client)
            if realized - open_cost - STAKE <= -MAX_LOSS:
                _log({"event": "skip_limit", "realized": realized, "open": open_cost})
            elif shard_balance(client) < STAKE * 1.05:
                _log({"event": "skip_balance", "balance_shard1": shard_balance(client)})
                log("  combo balance too low for a parlay")
            else:
                legs = pending[:LEGS]
                try:
                    rec = buy_combo(client, legs, log)
                except Exception as e:
                    _log({"event": "error", "why": repr(e)[:300]}); log(f"  combo failed: {e!r}"); rec = None
                if rec:
                    for lg in legs:
                        used_events.add(lg["event"])
                    pending = [p for p in pending if p["event"] not in used_events]
        elif now - last_try >= 600:
            realized_and_open(client)                          # settle finished parlays
            last_try = max(last_try, now - RETRY_S + 60)
        time.sleep(30)
