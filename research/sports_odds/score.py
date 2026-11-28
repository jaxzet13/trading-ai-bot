"""Score the Kalshi-vs-DraftKings recordings (research/sports_odds/record.py) once the games have settled.

Each market uses its LAST snapshot taken at least 10 minutes before the start. Buy YES at Kalshi's ask when the
no-vig DraftKings win chance minus the ask minus Kalshi's fee is >= the bar; buy NO at 1 - bid on the mirror
condition. Result per $1 contract after fees, by bar, by sport, and by whether it was the favourite side.

    python3 research/sports_odds/score.py
"""
import collections
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import requests

SNAP = Path("data/sports_odds/snap.jsonl")
CACHE = Path("data/sports_odds/results.json")
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def fee(p):
    return 0.07 * p * (1 - p)


def main():
    last = {}
    for ln in open(SNAP):
        r = json.loads(ln)
        if r["start"] - r["ts"] >= 600 and r["start"] - r["ts"] <= 3 * 3600:
            k = r["ticker"]
            if k not in last or r["ts"] > last[k]["ts"]:
                last[k] = r
    res = json.load(open(CACHE)) if CACHE.exists() else {}
    now = time.time()
    for k, r in last.items():
        if k in res or now < r["start"] + 4 * 3600:
            continue
        try:
            m = requests.get(f"{KALSHI}/markets/{k}", timeout=15).json().get("market", {})
            if m.get("result") in ("yes", "no"):
                res[k] = m["result"]
        except Exception:
            pass
        time.sleep(0.2)
    json.dump(res, open(CACHE, "w"))
    rows = [(r, res[k]) for k, r in last.items() if k in res]
    print(f"{len(last)} markets recorded, {len(rows)} settled")
    if not rows:
        return
    for bar in (0.0, 0.02, 0.04, 0.06):
        out = collections.defaultdict(list)
        for r, rs in rows:
            y = float(rs == "yes")
            ey = r["book_p"] - r["ask"] - fee(r["ask"])
            na = 1 - r["bid"]
            en = (1 - r["book_p"]) - na - fee(na)
            if ey >= bar and 0.05 <= r["ask"] <= 0.95:
                p = y - r["ask"] - fee(r["ask"])
            elif en >= bar and 0.05 <= na <= 0.95:
                p = (1 - y) - na - fee(na)
            else:
                continue
            out[r["series"]].append(p); out["ALL"].append(p)
        print(f"-- bar {bar:.2f}")
        for s, v in sorted(out.items()):
            v = np.array(v)
            t = v.mean() / v.std(ddof=1) * math.sqrt(len(v)) if len(v) > 2 and v.std() > 0 else 0
            print(f"   {s:18} bets {len(v):4}  {100 * v.mean():+.2f}c/bet  t {t:+.2f}")
    # how far apart are they at all?
    d = np.array([(r["bid"] + r["ask"]) / 2 - r["book_p"] for r, _ in rows])
    print(f"Kalshi mid minus book: mean {100 * d.mean():+.2f}c, abs mean {100 * np.abs(d).mean():.2f}c")
    # calibration of the book vs Kalshi on the same games
    y = np.array([float(rs == "yes") for _, rs in rows]); b = np.array([r["book_p"] for r, _ in rows]); k = np.array([(r["bid"] + r["ask"]) / 2 for r, _ in rows])
    ll = lambda p: float(-np.mean(y * np.log(np.clip(p, 1e-3, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-3, 1))))
    print(f"log loss: DraftKings {ll(b):.4f}  Kalshi mid {ll(k):.4f}  (lower is better)")


if __name__ == "__main__":
    main()
