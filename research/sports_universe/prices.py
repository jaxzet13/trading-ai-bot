"""Step 2 of the whole-sports scan: hourly quotes before each market's expected expiration (Nov 28 2026).

For every settled market from enumerate.py that traded (volume > 0), the hourly bid/ask/volume from 14 h before its
expected expiration until 2.5 h before it. For game markets the expected expiration is ~3 h after kickoff, so this is
the pre-game stretch (kickoff itself is at expiration - 3 h). Batch endpoint: 100 markets a call. Resumable.

    python3 research/sports_universe/prices.py          -> data/sports_universe/prices.jsonl (not in git)
"""
import collections
import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

API = "https://api.elections.kalshi.com/trade-api/v2"
D = Path("data/sports_universe")
BEFORE_S, AFTER_S = 14 * 3600, int(2.5 * 3600)
T0 = time.time()


def ts(x):
    return int(dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp())


def fetch(job):
    end, ms = job
    p = {"market_tickers": ",".join(m["t"] for m in ms), "start_ts": end - BEFORE_S - 3600, "end_ts": end, "period_interval": 60}
    d = {}
    for i in range(6):
        try:
            r = requests.get(API + "/markets/candlesticks", params=p, timeout=40)
            if r.status_code == 200:
                d = r.json()
                break
            if r.status_code == 429:
                time.sleep(2 + 3 * i)
                continue
        except Exception:
            pass
        time.sleep(1 + i)
    time.sleep(0.3)
    by = {m["t"]: m for m in ms}
    out = []
    for r in d.get("markets", []):
        m = by.get(r.get("market_ticker"))
        if not m:
            continue
        x = m["xs"]
        bars = []
        for c in r.get("candlesticks") or []:
            e = int(c["end_period_ts"])
            if x - BEFORE_S <= e <= x - AFTER_S:
                b, a = c.get("yes_bid") or {}, c.get("yes_ask") or {}
                try:
                    bars.append([e, float(b["close_dollars"]), float(a["close_dollars"]), round(float(c.get("volume_fp") or 0), 1)])
                except (KeyError, TypeError, ValueError):
                    continue
        out.append({"t": m["t"], "x": x, "b": bars})
    return out


def main():
    have = set()
    pf = D / "prices.jsonl"
    if pf.exists():
        have = {json.loads(ln)["t"] for ln in open(pf)}
    groups = collections.defaultdict(list)
    n = 0
    for ln in open(D / "markets.jsonl"):
        m = json.loads(ln)
        if not m.get("x") or m["v"] <= 0 or m["t"] in have:
            continue
        m["xs"] = ts(m["x"])
        groups[(m["xs"] // 3600 + 1) * 3600].append(m)
        n += 1
    jobs = []
    for end, ms in sorted(groups.items()):
        for i in range(0, len(ms), 100):
            jobs.append((end, ms[i:i + 100]))
    print(f"{n:,} markets to price, {len(jobs)} calls", flush=True)
    done = 0
    with open(pf, "a") as f, ThreadPoolExecutor(3) as ex:
        for rows in ex.map(fetch, jobs):
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
            done += 1
            if done % 100 == 0:
                f.flush()
                print(f"[{time.time() - T0:5.0f}s] {done}/{len(jobs)} calls", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
