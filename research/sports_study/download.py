"""Settled game-winner markets for other sports, with Kalshi's 1-minute quotes, for per-sport backtests.

Same format and code path as the tennis history (tennis/history.py): for every settled market of a series, its
scheduled start, result, settlement value and the 1-minute candlesticks from 6 h before the start to settlement
(at most 12 h). One file per series in data/sports/<series>.jsonl (not in git), appended, so reruns only fetch new
markets. Requests are paced (PACE_S) and skip the seconds around each minute boundary, when the live crypto bot reads
candles from the same rate-limit bucket.

    python3 research/sports_study/download.py [days] [series ...]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from tennis import history as H                              # noqa: E402

OUT = Path("data/sports")
SERIES = ["KXNBAGAME", "KXNFLGAME", "KXNCAAFGAME", "KXNCAAMBGAME", "KXNHLGAME", "KXEPLGAME", "KXUCLGAME",
          "KXLALIGAGAME", "KXCS2GAME", "KXUFCFIGHT", "KXNCAAWBGAME", "KXLIGAMXGAME", "KXMLSGAME", "KXBUNDESLIGAGAME",
          "KXLOLGAME", "KXDOTA2GAME"]
PACE_S = 0.35


def quiet_wait():
    s = time.time() % 60
    if s > 57 or s < 4:                                          # the live bot's minute-boundary reads
        time.sleep((64 - s) % 60)


def update(series, days):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{series}.jsonl"
    have = {json.loads(ln)["ticker"] for ln in open(path)} if path.exists() else set()
    since = int(time.time()) - days * 86400
    try:
        ms = H.settled(series, since)
    except Exception as e:
        print(f"{series}: {e!r}", flush=True)
        return 0
    todo = [m for m in ms if m["ticker"] not in have and m.get("occurrence_datetime")]
    print(f"{series}: {len(ms)} settled in {days} d, {len(todo)} to fetch", flush=True)
    new = 0
    with open(path, "a") as f:
        for m in todo:
            start, end = H._ts(m["occurrence_datetime"]), H._ts(m.get("settlement_ts") or m["close_time"])
            if not start or not end or end <= start - H.PRE_S + 120:
                continue
            quiet_wait()
            try:
                b = H.bars(series, m["ticker"], start - H.PRE_S, min(end, start + H.MAX_S))
            except Exception as e:
                print(f"  {m['ticker']}: {e!r}", flush=True)
                time.sleep(5)
                continue
            f.write(json.dumps({"ticker": m["ticker"], "event": m["event_ticker"], "series": series,
                                "player": m.get("yes_sub_title"), "start": start, "settled": end,
                                "result": m.get("result"), "value": H._f(m, "settlement_value_dollars"),
                                "volume": H._f(m, "volume_fp"), "bars": b}, separators=(",", ":")) + "\n")
            new += 1
            if new % 200 == 0:
                f.flush()
                print(f"  {series}: {new}/{len(todo)}", flush=True)
            time.sleep(PACE_S)
    print(f"{series}: +{new}", flush=True)
    return new


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    for s in (sys.argv[2:] or SERIES):
        update(s, days)
    print("download done", flush=True)
