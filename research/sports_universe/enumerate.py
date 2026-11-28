"""Step 1 of the whole-sports scan (Nov 28 2026): every settled Kalshi sports market of the last N days.

Account holder: "test even more and expand upon these strategies and make even better ones for sportsbetting".
Kalshi lists ~4,300 sports series (winners, spreads, totals, player props, corners, both-teams-to-score, minor leagues).
The thin ones, run by retail traders, are the likeliest to be mispriced, and none of them has been looked at. This lists
their settled markets (ticker, series, expected expiration, result, volume). prices.py then adds hourly quotes.

    python3 research/sports_universe/enumerate.py [days]    -> data/sports_universe/markets.jsonl (not in git)
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

API = "https://api.elections.kalshi.com/trade-api/v2"
OUT = Path("data/sports_universe")
CAP = 6000                 # markets per series (the biggest series are crypto-like volumes of near-identical strikes)
T0 = time.time()


def get(path, params):
    for i in range(6):
        try:
            r = requests.get(API + path, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2 + 3 * i)
                continue
        except Exception:
            pass
        time.sleep(1 + i)
    return {}


def series_markets(s, since):
    out, cur = [], None
    while len(out) < CAP:
        p = {"series_ticker": s, "status": "settled", "limit": 1000, "min_close_ts": since}
        if cur:
            p["cursor"] = cur
        d = get("/markets", p)
        for m in d.get("markets", []):
            if m.get("result") in ("yes", "no"):
                out.append({"t": m["ticker"], "s": s, "e": m["event_ticker"], "x": m.get("expected_expiration_time"),
                            "c": m.get("close_time"), "r": m["result"], "v": float(m.get("volume_fp") or 0),
                            "o": m.get("occurrence_datetime"), "n": m.get("yes_sub_title"), "k": m.get("strike_type"),
                            "f": m.get("floor_strike"), "u": m.get("cap_strike")})
        cur = d.get("cursor")
        if not cur:
            break
        time.sleep(0.15)
    time.sleep(0.15)
    return out


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    since = int(time.time()) - days * 86400
    OUT.mkdir(parents=True, exist_ok=True)
    ser = [s["ticker"] for s in get("/series", {"category": "Sports"}).get("series", [])]
    print(f"{len(ser)} sports series", flush=True)
    n = k = 0
    with open(OUT / "markets.jsonl", "w") as f, ThreadPoolExecutor(3) as ex:
        for i, ms in enumerate(ex.map(lambda s: series_markets(s, since), ser)):
            for m in ms:
                f.write(json.dumps(m, separators=(",", ":")) + "\n")
            n += len(ms)
            k += bool(ms)
            if i % 200 == 0:
                print(f"[{time.time() - T0:5.0f}s] {i}/{len(ser)} series, {k} with markets, {n:,} markets", flush=True)
    print(f"done: {k} series with settled markets, {n:,} markets", flush=True)


if __name__ == "__main__":
    main()
