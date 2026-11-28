"""Kalshi vs the sportsbook: does Kalshi's price ever sit far enough from DraftKings' line to pay the fee? (Nov 28 2026)

Account holder: "find out more strategies and ways to be profitable with other sports in any way possible".

Sportsbook lines are sharper than most traders and ESPN's public scoreboard carries DraftKings' moneyline, spread and
total for upcoming games. Every INTERVAL seconds this records, for each game starting in the next 36 h that has both
a DraftKings moneyline and a Kalshi game-winner market, Kalshi's bid/ask next to the DraftKings no-vig win chance.
It only records; score.py judges it once the games are over (a real test needs the results, so it takes days).

    python3 research/sports_odds/record.py            # loop
    python3 research/sports_odds/record.py once       # one pass, prints how many games matched
"""
import json
import re
import sys
import time
import datetime as dt
from pathlib import Path

import requests

OUT = Path("data/sports_odds/snap.jsonl")
STOP = Path("STOP_SPORTS_ODDS")
INTERVAL = 600
LEAGUES = {                       # ESPN path -> Kalshi series
    "basketball/nba": "KXNBAGAME", "hockey/nhl": "KXNHLGAME", "basketball/mens-college-basketball": "KXNCAAMBGAME",
    "football/college-football": "KXNCAAFGAME", "football/nfl": "KXNFLGAME", "soccer/eng.1": "KXEPLGAME",
    "soccer/uefa.champions": "KXUCLGAME", "soccer/esp.1": "KXLALIGAGAME", "basketball/womens-college-basketball": "KXNCAAWBGAME",
    "soccer/ger.1": "KXBUNDESLIGAGAME", "soccer/usa.1": "KXMLSGAME", "soccer/mex.1": "KXLIGAMXGAME",
}
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
ES = "https://site.api.espn.com/apis/site/v2/sports"


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower().replace("&", "and").replace("st.", "state")).strip()


def prob(odds):
    """American odds string -> implied probability (with the book's margin)."""
    try:
        o = str(odds).strip().upper()
        if o in ("EVEN", "PK"):
            return 0.5
        v = float(o)
    except ValueError:
        return None
    return 100 / (v + 100) if v > 0 else -v / (-v + 100)


def book_games(path):
    games = []
    now = dt.datetime.now(dt.timezone.utc)
    for k in range(0, 3):
        d = (now + dt.timedelta(days=k)).strftime("%Y%m%d")
        try:
            r = requests.get(f"{ES}/{path}/scoreboard", params={"dates": d, "limit": 300, "groups": "50" if "college" in path and "basketball" in path else None}, timeout=20)
            ev = r.json().get("events", [])
        except Exception:
            continue
        for e in ev:
            try:
                c = e["competitions"][0]
                start = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
                if not (now < start < now + dt.timedelta(hours=36)) or e["status"]["type"]["state"] != "pre":
                    continue
                o = (c.get("odds") or [None])[0]
                ml = (o or {}).get("moneyline") or {}
                ph, pa = prob(((ml.get("home") or {}).get("close") or {}).get("odds")), prob(((ml.get("away") or {}).get("close") or {}).get("odds"))
                if ph is None or pa is None:
                    continue
                pd_ = prob((((ml.get("draw") or {}).get("close")) or {}).get("odds")) or 0.0
                z = ph + pa + pd_
                teams = {t["homeAway"]: t["team"] for t in c["competitors"]}
                games.append({"id": e["id"], "start": start.timestamp(), "p": {"home": ph / z, "away": pa / z, "draw": pd_ / z},
                              "names": {s: {norm(teams[s].get(x)) for x in ("location", "shortDisplayName", "displayName", "name", "abbreviation")}
                                        for s in ("home", "away")},
                              "spread": o.get("spread"), "total": o.get("overUnder")})
            except Exception:
                continue
    return games


def kalshi_markets(series):
    out, cur = [], None
    while True:
        p = {"series_ticker": series, "status": "open", "limit": 1000}
        if cur:
            p["cursor"] = cur
        try:
            d = requests.get(f"{KALSHI}/markets", params=p, timeout=20).json()
        except Exception:
            break
        out += d.get("markets", [])
        cur = d.get("cursor")
        if not cur:
            break
    return out


def once():
    ts, rows, matched = time.time(), [], 0
    for path, series in LEAGUES.items():
        games = book_games(path)
        if not games:
            continue
        ms = kalshi_markets(series)
        by_ev = {}
        for m in ms:
            by_ev.setdefault(m["event_ticker"], []).append(m)
        for g in games:
            hit = None
            for ev, mk in by_ev.items():
                side = {}
                for m in mk:
                    n = norm(m.get("yes_sub_title"))
                    if n in ("tie", "draw"):
                        side[m["ticker"]] = "draw"
                    for s in ("home", "away"):
                        if n and n in g["names"][s]:
                            side[m["ticker"]] = s
                if {"home", "away"} <= set(side.values()):
                    hit = (ev, mk, side)
                    break
            if not hit:
                continue
            ev, mk, side = hit
            matched += 1
            for m in mk:
                s = side.get(m["ticker"])
                if not s:
                    continue
                try:
                    bid, ask = float(m["yes_bid_dollars"]), float(m["yes_ask_dollars"])
                except (TypeError, ValueError, KeyError):
                    continue
                rows.append({"ts": ts, "series": series, "ticker": m["ticker"], "event": ev, "side": s, "start": g["start"],
                             "book_p": round(g["p"][s], 4), "bid": bid, "ask": ask, "spread": g["spread"], "total": g["total"], "espn": g["id"]})
                # drop markets whose result is already decided or nonsense
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    print(time.strftime("%H:%M:%S"), f"{matched} games matched, {len(rows)} rows", flush=True)
    return rows


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        rows = once()
        for r in sorted(rows, key=lambda r: -abs(r["book_p"] - (r["bid"] + r["ask"]) / 2))[:12]:
            print(r["ticker"], r["side"], "book", r["book_p"], "kalshi bid/ask", r["bid"], r["ask"])
    else:
        while not STOP.exists():
            try:
                once()
            except Exception as e:
                print("error", repr(e), flush=True)
            time.sleep(INTERVAL)
