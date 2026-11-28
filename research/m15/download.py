"""Every Kalshi 15-minute market (non-crypto-coin ones): settled windows and their 1-minute bid/ask quotes (Nov 28 2026).

Account holder: "Backtest all those 15m coins, and backtest with millions of strategies and find the most profitable and make a
new artifact for it". One file per series in data/m15/<series>.jsonl: ticker, close time, strike, result and the 1-minute
bid/ask closes (+ minute volume) from 16 minutes before the close to the close. Consecutive windows go in one batch call.

    python3 research/m15/download.py [series ...]
"""
import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

API = "https://api.elections.kalshi.com/trade-api/v2"
OUT = Path("data/m15")
SERIES = ["KXGOLD15M", "KXWTI15M", "KXSILVER15M", "KXNATGAS15M", "KXCOPPER15M", "KXUSDJPY15M", "KXEURUSD15M", "KXBRENT15M",
          "KXPLATINUM15M", "KXAUDUSD15M", "KXGBPUSD15M", "KXUSDCAD15M", "KXPALLADIUM15M", "KXINX15M", "KX2YRRATE15M",
          "KX10YRRATE15M", "KX30YRRATE15M", "KX5YRRATE15M", "KXUSDMXN15M"]


def get(path, params):
    for i in range(7):
        try:
            r = requests.get(API + path, params=params, timeout=45)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2 + 3 * i)
                continue
        except Exception:
            pass
        time.sleep(1 + i)
    return {}


def ts(x):
    return int(dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp())


def one(s):
    ms, cur = [], None
    while True:
        p = {"series_ticker": s, "status": "settled", "limit": 1000, "min_close_ts": int(time.time()) - 150 * 86400}
        if cur:
            p["cursor"] = cur
        d = get("/markets", p)
        ms += [m for m in d.get("markets", []) if m.get("result") in ("yes", "no")]
        cur = d.get("cursor")
        if not cur:
            break
        time.sleep(0.2)
    ms.sort(key=lambda m: m["close_time"])
    path = OUT / f"{s}.jsonl"
    have = {json.loads(ln)["t"] for ln in open(path)} if path.exists() else set()
    ms = [m for m in ms if m["ticker"] not in have]
    chunks, c = [], []
    for m in ms:
        if c and (ts(m["close_time"]) - ts(c[-1]["close_time"]) > 1800 or len(c) >= 12):
            chunks.append(c); c = []
        c.append(m)
    if c:
        chunks.append(c)
    print(f"{s}: {len(ms)} new settled markets, {len(chunks)} calls", flush=True)
    with open(path, "a") as f:
        for n, part in enumerate(chunks):
            end = max(ts(m["close_time"]) for m in part)
            start = min(ts(m["close_time"]) for m in part) - 16 * 60
            d = get("/markets/candlesticks", {"market_tickers": ",".join(m["ticker"] for m in part), "start_ts": start, "end_ts": end, "period_interval": 1})
            by = {m["ticker"]: m for m in part}
            for r in d.get("markets", []):
                m = by.get(r.get("market_ticker"))
                if not m:
                    continue
                bars = []
                for c2 in r.get("candlesticks") or []:
                    try:
                        bars.append([int(c2["end_period_ts"]), float(c2["yes_bid"]["close_dollars"]), float(c2["yes_ask"]["close_dollars"]), round(float(c2.get("volume_fp") or 0), 1)])
                    except (KeyError, TypeError, ValueError):
                        pass
                f.write(json.dumps({"t": m["ticker"], "close": ts(m["close_time"]), "strike": m.get("floor_strike"), "result": m["result"], "bars": bars}, separators=(",", ":")) + "\n")
            time.sleep(0.25)
            if n % 100 == 0:
                f.flush()
                print(f"  {s}: {n}/{len(chunks)}", flush=True)
    print(f"{s}: done", flush=True)
    return s


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    todo = sys.argv[1:] or SERIES
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(one, todo))
    print("download done", flush=True)
