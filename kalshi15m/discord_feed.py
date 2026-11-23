"""Live Discord feed of the real-money picks (python -m kalshi15m discord [test|once|run]).

One custom bet-slip image (kalshi15m/pick_card.py) per pick: coin, side, entry price, contracts, cost, strategy, when it settles. When the
pick settles the same message gets the redrawn slip: WON in green with the profit, LOST in red. Nothing else is posted
(restarts, totals and research stay in the Claude chat). Account holder, Nov 23: "shown as like a professional
html ... only shows which picks it took and all the important details".

It is a separate process that only READS the runner's log (data/kalshi15m/real_top5_live_log.jsonl), so a Discord
outage or a bug here can never stop or change trading.

Setup: kalshi15m/discord.json {"trades_channel_id": "<channel id>"} (no secrets). Auth: a Discord bot token saved as
a network secret for discord.com (Authorization: Bot <token>), injected by the proxy; the header below is a
placeholder. Progress and the card of each open pick are kept in data/kalshi15m/discord_offset.json (git-ignored)
so a restart never re-posts and can still update the cards of picks placed before it.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "kalshi15m" / "real_top5_live_log.jsonl"
CFG = ROOT / "kalshi15m" / "discord.json"
STATE = ROOT / "data" / "kalshi15m" / "discord_offset.json"
API = "https://discord.com/api/v10"
COIN = {"KXNEAR15M": "NEAR", "KXSOL15M": "SOL", "KXZEC15M": "ZEC", "KXETH15M": "ETH", "KXBTC15M": "BTC",
        "KXXRP15M": "XRP", "KXDOGE15M": "DOGE", "KXHYPE15M": "HYPE", "KXBNB15M": "BNB"}
STYLE = {"fv_drift": "Drift", "fv_jump": "Jump", "fv_tau": "Time decay", "fv_prev": "Previous window",
         "fv_dyn": "Dynamic vol", "fv_vol": "Volatility", "fv_season": "Seasonal", "fv_lag": "Lag", "fv_emp": "Empirical"}
BLUE, GREEN, RED = 0x3B82F6, 0x22C55E, 0xEF4444
HEADERS = {"Authorization": "Bot proxy-injects-the-real-token"}


def _coin(series):
    return COIN.get(series, series or "?")


def _strategy(rule):
    fam = (rule or "?").split(":")[0]
    return STYLE.get(fam, fam)


def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


class Feed:
    """Builds the card of each pick from the log events (order intent, fills, settlement)."""

    def __init__(self):
        self.intent = {}                # ticker -> order_intent event
        self.picks = {}                 # ticker -> {"n", "cost", "side", "series", "ts"}

    def learn(self, e):
        k, tk = e.get("event"), e.get("ticker")
        if k == "order_intent" and tk:
            self.intent[tk] = e
        elif k == "fill" and tk:
            p = self.picks.setdefault(tk, {"n": 0.0, "cost": 0.0, "side": e.get("side"),
                                           "series": e.get("series"), "ts": e.get("ts", 0)})
            p["n"] += float(e.get("n") or e.get("count") or 0)
            p["cost"] += float(e.get("cost") or 0) + float(e.get("fees") or 0)

    def card(self, tk, result=None):
        """What the slip for pick `tk` shows (pick_card.render arguments); `result` = its settle event."""
        p, it = self.picks.get(tk), self.intent.get(tk, {})
        if not p:
            return None
        c = {"coin": _coin(p["series"]), "side": str(p["side"] or "?"), "price": p["cost"] / p["n"] if p["n"] else 0.0,
             "stake": p["cost"], "payout": p["n"], "settles_ts": it.get("close_ts"), "status": "live", "pnl": None}
        if result is not None:
            pnl = float(result.get("pnl_kalshi", result.get("pnl")) or 0)
            c.update(status="won" if pnl > 0 else "lost", pnl=pnl)
        return c


def _send(method, url, png, session=requests, tries=4):
    """POST/PATCH a message whose only content is the slip image -> its id, or None if it could not be sent."""
    payload = json.dumps({"attachments": [{"id": 0, "filename": "pick.png"}], "embeds": [], "content": ""})
    for i in range(tries):
        try:
            r = session.request(method, url, data={"payload_json": payload},
                                files={"files[0]": ("pick.png", png, "image/png")}, headers=HEADERS, timeout=20)
        except requests.RequestException:
            time.sleep(2 ** i)
            continue
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 1.0)) + 0.1)
            continue
        if r.status_code < 300:
            return str(r.json().get("id", "")) or "ok"
        if r.status_code in (401, 403):
            raise RuntimeError(f"Discord refused the post ({r.status_code}): {r.text[:200]}")
        if r.status_code == 404:
            return None
        time.sleep(2 ** i)
    return None


def post(channel, card, edit_id=None):
    from .pick_card import render
    png = render(**card)
    if edit_id:
        return _send("PATCH", f"{API}/channels/{channel}/messages/{edit_id}", png)
    return _send("POST", f"{API}/channels/{channel}/messages", png)


def _channel():
    if not CFG.exists():
        sys.exit(f"missing {CFG}: put {{\"trades_channel_id\": \"<channel id>\"}} in it")
    return str(json.loads(CFG.read_text())["trades_channel_id"])


def _events(start):
    """(offset after line, event) for every complete line from byte offset `start`."""
    if not LOG.exists():
        return
    with open(LOG, "rb") as f:
        f.seek(start)
        while True:
            ln = f.readline()
            if not ln or not ln.endswith(b"\n"):
                return
            try:
                yield f.tell(), json.loads(ln)
            except ValueError:
                continue


def run(once=False, send=post, poll_s=5.0, log=print):
    channel = _channel()
    feed = Feed()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    size = LOG.stat().st_size if LOG.exists() else 0
    off = min(int(state.get("offset", size)), size)        # first run: start at the end, never flood old picks
    msgs = dict(state.get("msgs", {}))                    # ticker -> Discord message id of its card
    save = lambda: STATE.write_text(json.dumps({"offset": off, "msgs": dict(list(msgs.items())[-300:])}))
    save()
    for pos, e in _events(0):                             # rebuild the picks' context up to the offset
        if pos > off:
            break
        feed.learn(e)
    log(f"discord feed: following {LOG.name} from byte {off}, {len(msgs)} cards known")
    while True:
        for pos, e in _events(off):
            k, tk = e.get("event"), e.get("ticker")
            feed.learn(e)
            ok = True
            if k == "fill" and tk:                        # new pick, or a second fill of the same pick
                mid = send(channel, feed.card(tk), msgs.get(tk))
                ok = mid is not None
                if ok and tk not in msgs:
                    msgs[tk] = mid
            elif k == "settle" and tk and tk in msgs:     # turn its card green or red
                ok = send(channel, feed.card(tk, result=e), msgs[tk]) is not None
            if not ok:
                log("discord feed: send failed, will retry this event")
                break
            off = pos
            save()
        if once:
            return feed
        time.sleep(poll_s)


def main(args=None):
    args = list(args or [])
    if args and args[0] == "test":
        demo = {"coin": "NEAR", "side": "no", "price": 0.29, "stake": 0.86, "payout": 3.0,
                "settles_ts": int(time.time()) + 600, "status": "live", "pnl": None}
        print("test slip posted" if post(_channel(), demo) else "test slip failed")
        return
    run(once=bool(args and args[0] == "once"))


if __name__ == "__main__":
    main(sys.argv[1:])
