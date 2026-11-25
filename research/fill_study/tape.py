"""Trade tape around every walk-forward taker signal (2 s before to 12 s after the minute boundary), to measure
what a late order really pays and how often it can still be filled.

    python3 research/fill_study/tape.py <rows.pkl> <out.pkl> [coins,comma]
"""
import os
import pickle
import sys
import time

import numpy as np
import requests

sys.path.insert(0, "research/maker_study")
import sim   # noqa: E402
import tape  # noqa: E402

LIVE = ["KXDOGE15M", "KXNEAR15M", "KXSOL15M", "KXXRP15M", "KXZEC15M"]


def main():
    rows, out = sys.argv[1], sys.argv[2]
    coins = sys.argv[3].split(",") if len(sys.argv) > 3 else LIVE
    T = pickle.load(open(rows, "rb"))
    ok = np.isin(T["coin"], coins) & (T["j"] >= sim.START) & (T["j"] <= sim.END)
    order = np.lexsort((T["j"][ok], T["ticker"][ok]))
    sig = {}
    idx = np.nonzero(ok)[0][order]
    for i in idx:
        tk = str(T["ticker"][i])
        if tk in sig:
            continue
        s, price, edge = sim.taker_pick(float(T["p"][i]), float(T["ya"][i]), float(T["yb"][i]))
        if s:
            sig[tk] = {"T": int(T["ots"][i]) + 60 * int(T["j"][i]), "side": s, "price": price, "edge": edge,
                       "q": float(T["p"][i]) if s == 1 else 1 - float(T["p"][i]), "y": float(T["y"][i]),
                       "ya": float(T["ya"][i]), "yb": float(T["yb"][i]), "coin": str(T["coin"][i]),
                       "day": int(T["day"][i])}
    try:
        done = pickle.load(open(out, "rb"))
    except OSError:
        done = {}
    todo = [tk for tk in sorted(sig, key=lambda k: -sig[k]["T"]) if tk not in done]
    print(f"{len(sig)} taker signals, {len(done)} saved, {len(todo)} to fetch", flush=True)
    http, t0 = requests.Session(), time.time()
    for n, tk in enumerate(todo, 1):
        s = sig[tk]
        tr = tape.fetch(http, tk, s["T"] - 2, s["T"] + 12)
        done[tk] = dict(s, t=np.array([tape.ts(x["created_time"]) for x in tr]),
                        yes=np.array([float(x["yes_price_dollars"]) for x in tr], np.float32),
                        n=np.array([float(x["count_fp"]) for x in tr], np.float32),
                        buy_yes=np.array([x["taker_side"] == "yes" for x in tr], bool))
        if n % 100 == 0 or n == len(todo):
            pickle.dump(done, open(out + ".tmp", "wb"))
            os.replace(out + ".tmp", out)
            print(f"{n}/{len(todo)} signals, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
