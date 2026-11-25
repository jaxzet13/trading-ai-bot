"""Trade tape before the start for Challenger markets whose mid was 0.78-0.97 at 120, 60 or 30 minutes before the
start (favourites), so resting bids can be replayed against real trades.

    python3 research/tennis_maker/tape.py <rows.pkl> <out.pkl> [tour]
"""
import json
import os
import pickle
import sys
import time

import numpy as np
import requests

sys.path.insert(0, "research/maker_study")
import tape  # noqa: E402  (fetch, ts: the throttled public trade-tape reader)

STORE = "data/tennis/hist/markets.jsonl"


def main():
    rows, out = sys.argv[1], sys.argv[2]
    tour = sys.argv[3] if len(sys.argv) > 3 else "chal"
    R = pickle.load(open(rows, "rb"))
    k = (R["tour"] == tour) & np.isin(R["M"], (-120, -60, -30)) & (R["mid"] >= 0.78) & (R["mid"] < 0.97)
    want = set(R["tk"][k])
    start = {}
    for ln in open(STORE):
        i = ln.find('"ticker":"')
        tk = ln[i + 10:ln.find('"', i + 10)]
        if tk in want:
            start[tk] = json.loads(ln)["start"]
    try:
        done = pickle.load(open(out, "rb"))
    except OSError:
        done = {}
    todo = [tk for tk in sorted(start, key=lambda t: -start[t]) if tk not in done]
    print(f"{len(want)} markets wanted, {len(done)} saved, {len(todo)} to fetch", flush=True)
    http, t0 = requests.Session(), time.time()
    for n, tk in enumerate(todo, 1):
        tr = tape.fetch(http, tk, start[tk] - 125 * 60, start[tk])
        done[tk] = {"start": start[tk], "t": np.array([tape.ts(x["created_time"]) for x in tr]),
                    "yes": np.array([float(x["yes_price_dollars"]) for x in tr], np.float32),
                    "n": np.array([float(x["count_fp"]) for x in tr], np.float32),
                    "buy_yes": np.array([x["taker_side"] == "yes" for x in tr], bool)}
        if n % 100 == 0 or n == len(todo):
            pickle.dump(done, open(out + ".tmp", "wb"))
            os.replace(out + ".tmp", out)
            print(f"{n}/{len(todo)} markets, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
