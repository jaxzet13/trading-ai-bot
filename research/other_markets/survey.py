"""Which non-sports Kalshi markets look like the 15-minute crypto ones? (Nov 28 2026)

Account holder: "What can we do to add a variety of profitability to Kalshi, are there any other prediction markets like
the 15m that we can profit from since sportsbetting doesn't work".
For every series outside Sports: settled markets and contracts traded in the last 14 days, so the busy, frequent ones
(a daily or hourly cycle, a public data source to model) stand out. This only counts them; it is not a profit test.

    python3 research/other_markets/survey.py        -> research/other_markets/survey.json
"""
import collections
import json
import time
from concurrent.futures import ThreadPoolExecutor

import requests

API = "https://api.elections.kalshi.com/trade-api/v2"
SINCE = int(time.time()) - 14 * 86400


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


def count(s):
    n, vol, ev, cur = 0, 0.0, set(), None
    while n < 20000:
        p = {"series_ticker": s["ticker"], "status": "settled", "limit": 1000, "min_close_ts": SINCE}
        if cur:
            p["cursor"] = cur
        d = get("/markets", p)
        for m in d.get("markets", []):
            n += 1
            vol += float(m.get("volume_fp") or 0)
            ev.add(m["event_ticker"])
        cur = d.get("cursor")
        if not cur:
            break
        time.sleep(0.1)
    time.sleep(0.1)
    return {"ticker": s["ticker"], "title": s.get("title"), "category": s.get("category"), "freq": s.get("frequency"),
            "markets": n, "events": len(ev), "contracts": round(vol)}


def main():
    ser = get("/series", {}).get("series", [])
    cats = collections.Counter(s.get("category") for s in ser)
    print(cats.most_common(), flush=True)
    todo = [s for s in ser if s.get("category") not in ("Sports",)]
    out = []
    with ThreadPoolExecutor(3) as ex:
        for i, r in enumerate(ex.map(count, todo)):
            if r["markets"]:
                out.append(r)
            if i % 300 == 0:
                print(i, len(todo), flush=True)
    json.dump(out, open("research/other_markets/survey.json", "w"), indent=0)
    byc = collections.defaultdict(lambda: [0, 0, 0])
    for r in out:
        b = byc[r["category"]]; b[0] += 1; b[1] += r["markets"]; b[2] += r["contracts"]
    for c, v in sorted(byc.items(), key=lambda kv: -kv[1][2]):
        print(f"{str(c):28} {v[0]:4} series {v[1]:8} markets {v[2]:14,} contracts")
    print("top series by contracts traded (14 days):")
    for r in sorted(out, key=lambda r: -r["contracts"])[:40]:
        print(f"  {r['ticker']:22} {str(r['category'])[:14]:14} {str(r['freq'])[:9]:9} {r['markets']:6} mkts {r['events']:5} events {r['contracts']:>12,} contracts  {str(r['title'])[:50]}")


main()
