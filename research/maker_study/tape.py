"""Step 2 of the resting-bid (maker) study: Kalshi's public trade tape for every market where the model saw a
possible resting-bid bet (model probability at least MIN_EDGE above the bid on either side, minutes 4-13), from the
first such minute to minute 14. Throttled (GAP seconds between calls) so it cannot crowd the live bot.

    python3 research/maker_study/tape.py <rows.pkl> <tape.pkl> [days] [coins,comma]
"""
import calendar
import pickle
import sys
import time

import numpy as np
import requests

URL = "https://api.elections.kalshi.com/trade-api/v2/markets/trades"
MIN_EDGE, GAP = 0.03, 0.34
LIVE = ["KXDOGE15M", "KXNEAR15M", "KXSOL15M", "KXXRP15M", "KXZEC15M"]


def ts(s):
    """'2026-11-25T11:25:30.309Z' -> epoch seconds (the fraction has a varying number of digits)."""
    base, _, frac = s.rstrip("Z").partition(".")
    return calendar.timegm(time.strptime(base, "%Y-%m-%dT%H:%M:%S")) + (float("0." + frac) if frac else 0.0)


def fetch(http, ticker, t0, t1):
    out, cursor = [], None
    while True:
        p = {"ticker": ticker, "limit": 1000, "min_ts": int(t0), "max_ts": int(t1)}
        if cursor:
            p["cursor"] = cursor
        for attempt in range(8):
            time.sleep(GAP)
            try:
                r = http.get(URL, params=p, timeout=15)
            except requests.RequestException:
                time.sleep(3)
                continue
            if r.status_code == 200:
                break
            time.sleep(5 if r.status_code == 429 else 2)
        else:
            raise RuntimeError(f"{ticker}: no answer")
        d = r.json()
        out += d.get("trades") or []
        cursor = d.get("cursor")
        if not cursor or not d.get("trades"):
            return out


def main():
    rows, out = sys.argv[1], sys.argv[2]
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    coins = sys.argv[4].split(",") if len(sys.argv) > 4 else LIVE
    T = pickle.load(open(rows, "rb"))
    p, ya, yb = T["p"], T["ya"], T["yb"]
    ok = np.isin(T["coin"], coins) & (T["j"] >= 4) & (T["j"] <= 13) & np.isin(T["day"], np.unique(T["day"])[-days:])
    ok &= ((p - yb >= MIN_EDGE) & (yb >= 0.05) & (yb <= 0.95)) | ((ya - p >= MIN_EDGE) & (ya >= 0.05) & (ya <= 0.95))
    first = {}
    for tk, ots, j in zip(T["ticker"][ok], T["ots"][ok], T["j"][ok]):
        if tk not in first or j < first[tk][1]:
            first[tk] = (int(ots), int(j))
    try:
        tape = pickle.load(open(out, "rb"))
    except OSError:
        tape = {}
    todo = [tk for tk in sorted(first, key=lambda k: -first[k][0]) if tk not in tape]
    print(f"{len(first)} markets wanted, {len(tape)} saved, {len(todo)} to fetch", flush=True)
    http, t_start = requests.Session(), time.time()
    for n, tk in enumerate(todo, 1):
        ots, j = first[tk]
        tr = fetch(http, tk, ots + 60 * j - 5, ots + 840)
        tape[tk] = {"t": np.array([ts(x["created_time"]) for x in tr]),
                    "yes": np.array([float(x["yes_price_dollars"]) for x in tr], np.float32),
                    "n": np.array([float(x["count_fp"]) for x in tr], np.float32),
                    "buy_yes": np.array([x["taker_side"] == "yes" for x in tr], bool)}
        if n % 100 == 0 or n == len(todo):
            pickle.dump(tape, open(out + ".tmp", "wb"))
            import os
            os.replace(out + ".tmp", out)
            print(f"{n}/{len(todo)} markets, {time.time() - t_start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
