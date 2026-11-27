"""Kalshi's hourly (and 5pm daily) crypto "above $X" markets, for a backtest like the 15-minute one (Nov 27 2026).

Series KXBTCD, KXETHD, KXSOLD, KXXRPD, KXDOGED. Each event settles on the hour and lists many strikes. For every
settled event: each strike's floor price, result, and Kalshi's 1-minute candles for the last 60 minutes before the
close, fetched with the batch candlestick endpoint (100 markets a call). Strikes whose ask never sat between 3c and
97c in that hour are dropped. One line per event in data/crypto_hourly/<series>.jsonl (not in git), appended, so reruns only fetch new
events. Paced, and quiet around each minute boundary when the live bot reads candles.

    python3 research/crypto_hourly/download.py [days] [series ...]
"""
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from tennis import history as H                              # noqa: E402

OUT = Path("data/crypto_hourly")
SERIES = ["KXBTCD", "KXETHD", "KXSOLD", "KXXRPD"]          # KXDOGED skipped: ~no trading (median 33 contracts an event)
PACE_S = 0.35
LOOK_S = 3600


def quiet_wait():
    s = time.time() % 60
    if s > 57 or s < 4:
        time.sleep((64 - s) % 60)


def bar(c):
    a, b = c.get("yes_ask") or {}, c.get("yes_bid") or {}
    return [int(c["end_period_ts"]), H._f(b, "close_dollars"), H._f(a, "close_dollars"), round(float(c.get("volume_fp") or 0), 2)]


def update(series, days):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{series}.jsonl"
    have = {json.loads(ln)["event"] for ln in open(path)} if path.exists() else set()
    try:
        ms = H.settled(series, int(time.time()) - days * 86400)
    except Exception as e:
        print(f"{series}: {e!r}", flush=True)
        return 0
    ev = collections.defaultdict(list)
    for m in ms:
        ev[m["event_ticker"]].append(m)
    todo = sorted(e for e in ev if e not in have)
    print(f"{series}: {len(ms)} markets, {len(ev)} events, {len(todo)} to fetch", flush=True)
    new = 0
    with open(path, "a") as f:
        for e in todo:
            mk = ev[e]
            close = H._ts(mk[0]["close_time"])
            if not close:
                continue
            out = {}
            for i in range(0, len(mk), 100):
                part = mk[i:i + 100]
                quiet_wait()
                try:
                    d = H.api.get("/markets/candlesticks", {"market_tickers": ",".join(m["ticker"] for m in part),
                                                            "start_ts": close - LOOK_S, "end_ts": close, "period_interval": 1})
                except Exception as ex:
                    print(f"  {e}: {ex!r}", flush=True)
                    time.sleep(5)
                    continue
                info = {m["ticker"]: m for m in part}
                for r in (d or {}).get("markets") or []:
                    if not isinstance(r, dict):
                        continue
                    cs = r.get("candlesticks") or []
                    m = info.get(r.get("market_ticker"))
                    if not cs or not m:
                        continue
                    bs = [bar(c) for c in cs]
                    if not any(0.03 <= (x[2] or 0) <= 0.97 for x in bs):     # never tradeable in the last hour
                        continue
                    tail = m["ticker"].rsplit("-", 1)[-1]
                    out[m["ticker"]] = {"strike": float(tail[1:]) if tail[:1] == "T" else m.get("floor_strike"),
                                        "result": m.get("result"), "bars": bs}
                time.sleep(PACE_S)
            f.write(json.dumps({"event": e, "series": series, "close": close, "n_strikes": len(mk), "markets": out},
                               separators=(",", ":")) + "\n")
            new += 1
            if new % 100 == 0:
                f.flush()
                print(f"  {series}: {new}/{len(todo)}", flush=True)
    print(f"{series}: +{new}", flush=True)
    return new


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    for s in (sys.argv[2:] or SERIES):
        update(s, days)
    print("download done", flush=True)
