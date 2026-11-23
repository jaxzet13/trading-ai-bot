"""Short updates to the tennis Discord channel (separate from the crypto feed).

Only three kinds, each a small embed: a lab digest at most every DIGEST_S (3 lines), a strategy passing its
forward test, a confirmed risk-free arb. Channel id in tennis/discord.json; the bot token is the discord.com
network secret the proxy injects (the header below is a placeholder). Failures are logged and never raise.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CFG = Path(__file__).resolve().parent / "discord.json"
STATE = ROOT / "data" / "tennis" / "notify_state.json"
API = "https://discord.com/api/v10"
DIGEST_S = 6 * 3600
GREEN, BLUE, GOLD = 0x22C55E, 0x3B82F6, 0xF5B301


def _channel():
    try:
        return str(json.loads(CFG.read_text())["channel_id"])
    except (OSError, ValueError, KeyError):
        return None


def post(title, lines, color=BLUE, log=print):
    ch = _channel()
    if not ch:
        return False
    embed = {"title": title[:250], "description": "\n".join(lines)[:1800], "color": color}
    for i in range(3):
        try:
            r = requests.post(f"{API}/channels/{ch}/messages", json={"embeds": [embed]},
                              headers={"Authorization": "Bot proxy-injects-the-real-token"}, timeout=15)
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 1)) + 0.1)
                continue
            if r.status_code < 300:
                return True
            log(f"  tennis discord: {r.status_code} {r.text[:120]}")
            return False
        except requests.RequestException as e:
            log(f"  tennis discord: {e!r}")
            time.sleep(2 ** i)
    return False


def _state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s))


def digest(row, force=False, log=print):
    """At most every DIGEST_S: matches/strategies, best strategy, walk-forward verdict."""
    st = _state()
    if not force and time.time() - st.get("digest", 0) < DIGEST_S:
        return False
    beat = row["top5_cents"] > row["all_cents"]
    lines = [f"{row['markets']:,} matches · {row['strategies']:,} strategies tested",
             f"Best: {row['best']} · {row['best_bets']} bets" if row.get("best") else "Best: not enough bets yet",
             f"Top picks on unseen days: {row['top5_cents']:+.1f}¢ a bet vs {row['all_cents']:+.1f}¢ for all"
             + (" ✅" if beat else "")]
    ok = post("🎾 Tennis lab", lines, GREEN if beat else BLUE, log)
    if ok:
        st["digest"] = time.time()
        _save(st)
    return ok


def promoted(name, n, pnl, t, log=print):
    st = _state()
    key = f"promo:{name}"
    if st.get(key):
        return False
    ok = post("📈 Passed its forward test", [name, f"{n} bets on new matches · {pnl:+.2f} $ · t {t:.1f}",
                                              "Candidate for the practice runner"], GOLD, log)
    if ok:
        st[key] = time.time()
        _save(st)
    return ok


def arb(match, kind, n, profit, log=print):
    return post("✅ Arb confirmed", [match, f"Buy {kind} · {n} contracts · locks in ${profit:.2f}"], GREEN, log)
