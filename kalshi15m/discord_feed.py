"""Live Discord feed of the real-money trades (python -m kalshi15m discord [test|once|run]).

Follows the runner's log (data/kalshi15m/real_top5_live_log.jsonl) and posts every bet (fill), every result
(settle) and every runner restart to a Discord channel. It is a separate process: it only READS the log, so a Discord
outage or a bug here can never stop or change trading.

Setup (kalshi15m/discord.json, committed, no secrets): {"trades_channel_id": "<channel id>"}.
Auth: a Discord bot token, saved as a network secret for discord.com (Authorization: Bot <token>); the proxy adds it
to every request, so the token is never in this repo, the logs or the chat. The header sent below is a placeholder.
Progress is kept in data/kalshi15m/discord_offset.json (git-ignored) so a restart never re-posts old trades.
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


def _coin(series):
    return COIN.get(series, series)


def _hhmm(ts):
    return time.strftime("%H:%M UTC", time.gmtime(ts))


class Feed:
    """Turns log events into messages. Keeps the context a message needs (the order behind a fill, totals)."""

    def __init__(self):
        self.intent = {}            # ticker -> order_intent event
        self.cost = {}              # ticker -> paid so far
        self.total = 0.0            # real P&L since the start of the log
        self.n = 0
        self.day = {}               # UTC day -> P&L
        self.balance = None

    def learn(self, e):
        """Update the context from an event without producing a message (used to catch up on old log lines)."""
        k, tk = e.get("event"), e.get("ticker")
        if k == "order_intent" and tk:
            self.intent[tk] = e
            self.balance = e.get("balance_crypto", self.balance)
        elif k == "fill" and tk:
            self.cost[tk] = self.cost.get(tk, 0.0) + float(e.get("cost") or 0)
        elif k == "settle" and tk:
            p = float(e.get("pnl_kalshi", e.get("pnl")) or 0)
            self.total += p
            self.n += 1
            d = int(e.get("ts", 0) // 86400)
            self.day[d] = self.day.get(d, 0.0) + p

    def message(self, e):
        """The Discord text for a new event, or None if it is not worth a message. Call learn() after."""
        k, tk = e.get("event"), e.get("ticker")
        if k == "fill" and tk:
            it = self.intent.get(tk, {})
            n = float(e.get("n") or e.get("count") or 0)
            cost = float(e.get("cost") or 0) + float(e.get("fees") or 0)
            px = e.get("avg_price")
            px = float(px) if isinstance(px, (int, float)) else (float(e.get("cost") or 0) / n if n else 0.0)
            closes = it.get("close_ts")
            return (f"🟦 **BET** {_coin(e.get('series'))} **{str(e.get('side', '?')).upper()}** "
                    f"{n:g} @ {px:.2f} = ${cost:.2f}  ·  {it.get('rule', '?')}"
                    + (f"  ·  minute {it['minute']}" if it.get("minute") else "")
                    + (f"  ·  settles {_hhmm(closes)}" if closes else ""))
        if k == "settle" and tk:
            p = float(e.get("pnl_kalshi", e.get("pnl")) or 0)
            d = int(e.get("ts", 0) // 86400)
            today = self.day.get(d, 0.0) + p
            total = self.total + p
            icon, word = ("✅", "WIN") if p > 0 else ("❌", "LOSS")
            rule = self.intent.get(tk, {}).get("rule", "?")
            return (f"{icon} **{word}** {_coin(e.get('series'))} {p:+.2f}  ·  {rule}  ·  "
                    f"today {today:+.2f}  ·  all {self.n + 1} bets {total:+.2f}")
        return None


def _post(channel, text, session=requests, tries=4):
    for i in range(tries):
        try:
            r = session.post(f"{API}/channels/{channel}/messages", json={"content": text[:1990]},
                             headers={"Authorization": "Bot proxy-injects-the-real-token"}, timeout=15)
        except requests.RequestException:
            time.sleep(2 ** i)
            continue
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 1.0)) + 0.1)
            continue
        if r.status_code < 300:
            return True
        if r.status_code in (401, 403, 404):
            raise RuntimeError(f"Discord refused the post ({r.status_code}): {r.text[:200]}")
        time.sleep(2 ** i)
    return False


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
            pos = f.tell()
            ln = f.readline()
            if not ln or not ln.endswith(b"\n"):
                return
            try:
                yield f.tell(), json.loads(ln)
            except ValueError:
                continue


def run(once=False, post=_post, poll_s=5.0, log=print):
    channel = _channel()
    feed = Feed()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    size = LOG.stat().st_size if LOG.exists() else 0
    off = min(int(state.get("offset", size)), size)        # first run: start at the end, never flood old trades
    STATE.write_text(json.dumps({"offset": off}))
    for pos, e in _events(0):                             # rebuild totals and order context up to the offset
        if pos > off:
            break
        feed.learn(e)
    starts = set()
    log(f"discord feed: following {LOG.name} from byte {off}, {feed.n} past bets, total {feed.total:+.2f}")
    while True:
        for pos, e in _events(off):
            msg = feed.message(e)
            if e.get("event") == "start":                 # one message per restart, not one per coin
                key = int(e.get("ts", 0))
                msg = None if key in starts else "🔄 Bot (re)started"
                starts.add(key)
            if msg and not post(channel, msg):
                log("discord feed: post failed, will retry this event")
                break
            feed.learn(e)
            off = pos
            STATE.write_text(json.dumps({"offset": off}))
        if once:
            return feed
        time.sleep(poll_s)


def main(args=None):
    args = list(args or [])
    if args and args[0] == "test":
        ok = _post(_channel(), "👋 Kalshi bot feed connected. Every real-money bet and result will show up here.")
        print("test message posted" if ok else "test message failed")
        return
    run(once=bool(args and args[0] == "once"))


if __name__ == "__main__":
    main(sys.argv[1:])
