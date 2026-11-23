"""Live Discord feed of the real-money picks (python -m kalshi15m discord [test|once|run]).

One card (a Discord embed) per pick: coin, side, entry price, contracts, cost, strategy, when it settles. When the
pick settles the same card is edited in place: green with the profit, red with the loss. Nothing else is posted
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
        """The embed for pick `tk`; `result` = the settle event once it has settled."""
        p, it = self.picks.get(tk), self.intent.get(tk, {})
        if not p:
            return None
        coin, side = _coin(p["series"]), str(p["side"] or "?").upper()
        price = p["cost"] / p["n"] if p["n"] else 0.0
        close = it.get("close_ts")
        fields = [
            {"name": "Pick", "value": f"**{side}**", "inline": True},
            {"name": "Entry", "value": f"{price * 100:.0f}¢", "inline": True},
            {"name": "Contracts", "value": f"{p['n']:g}", "inline": True},
            {"name": "Cost", "value": f"${p['cost']:.2f}", "inline": True},
            {"name": "Pays if right", "value": f"${p['n']:.2f}", "inline": True},
            {"name": "Settles", "value": f"<t:{int(close)}:t>" if close else "—", "inline": True},
        ]
        if result is None:
            title, color = f"{coin} · {side}", BLUE
            desc = f"{_strategy(it.get('rule'))} strategy · 15-minute market"
        else:
            pnl = float(result.get("pnl_kalshi", result.get("pnl")) or 0)
            won = pnl > 0
            title = f"{coin} · {side} · {'WON' if won else 'LOST'} {'+' if pnl >= 0 else '−'}${abs(pnl):.2f}"
            color = GREEN if won else RED
            desc = f"{_strategy(it.get('rule'))} strategy · settled {str(result.get('result', '')).upper() or '—'}"
        return {"title": title, "description": desc, "color": color, "fields": fields,
                "footer": {"text": f"Kalshi {p['series']} · {tk}"}, "timestamp": _iso(p["ts"] or time.time())}


def _send(method, url, payload, session=requests, tries=4):
    """POST/PATCH a message -> its id, or None if it could not be sent."""
    for i in range(tries):
        try:
            r = session.request(method, url, json=payload, headers=HEADERS, timeout=15)
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


def post(channel, embed, edit_id=None):
    if edit_id:
        return _send("PATCH", f"{API}/channels/{channel}/messages/{edit_id}", {"embeds": [embed]})
    return _send("POST", f"{API}/channels/{channel}/messages", {"embeds": [embed]})


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
        demo = Feed()
        demo.intent["DEMO"] = {"rule": "fv_drift:KXNEAR15M:14", "close_ts": int(time.time()) + 600}
        demo.learn({"event": "fill", "ticker": "DEMO", "series": "KXNEAR15M", "side": "no", "n": 3, "cost": 0.84,
                    "fees": 0.02, "ts": time.time()})
        e = demo.card("DEMO")
        e["title"] = "Example card · " + e["title"]
        print("test card posted" if post(_channel(), e) else "test card failed")
        return
    run(once=bool(args and args[0] == "once"))


if __name__ == "__main__":
    main(sys.argv[1:])
