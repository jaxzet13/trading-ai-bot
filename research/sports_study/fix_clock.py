"""Correct the game clock of the downloaded sports history (found Nov 28 2026).

Kalshi's `occurrence_datetime` for team-sport game markets is the EXPECTED EXPIRATION, about 3 h after kickoff, not the
start (tennis' field is the scheduled start, which is why the tennis lab was right). Every "N minutes before the start"
rule in the first sports study was therefore really N minutes before about the end of the game. Verified against ESPN's
kickoff times (NBA, NHL, NFL, college, EPL: recorded - ESPN = exactly 3.00 h) and by the price: pre-game quotes barely
move (0.04c a minute), then jump at the true kickoff.

For each series the shift is read from the price itself: the first half-hour (relative to the recorded start) where the
mean absolute 1-minute move jumps to >= 3x its early baseline. The corrected copy goes to data/sports_fixed/.

    python3 research/sports_study/fix_clock.py [series ...]
"""
import json
import sys
from pathlib import Path

import numpy as np

SRC, DST = Path("data/sports"), Path("data/sports_fixed")
VERIFIED = {"KXNBAGAME": 3.0, "KXNHLGAME": 3.0, "KXNFLGAME": 3.0, "KXNCAAFGAME": 3.0, "KXNCAAMBGAME": 3.0, "KXNCAAWBGAME": 3.0,
            "KXEPLGAME": 3.0, "KXUCLGAME": 3.0, "KXLALIGAGAME": 3.0, "KXBUNDESLIGAGAME": 3.0, "KXMLSGAME": 3.0,
            "KXLIGAMXGAME": 3.0}                # checked against ESPN's kickoff times (NBA, NHL, NFL, NCAAF, NCAAMB, EPL: exactly 3.00 h)


def detect(path, n=500):
    acc = {}
    seen = 0
    for ln in open(path):
        m = json.loads(ln)
        b = m["bars"]
        if len(b) < 60:
            continue
        seen += 1
        prev = None
        for x in b:
            if x[1] is None or x[3] is None:
                continue
            mid = (x[1] + x[3]) / 2
            if prev is not None:
                acc.setdefault(int((x[0] - m["start"]) // 1800), []).append(abs(mid - prev))
            prev = mid
        if seen >= n:
            break
    ks = sorted(k for k in acc if -12 <= k <= 0)
    if len(ks) < 6:
        return 0.0
    base = max(np.median([np.mean(acc[k]) for k in ks[:3]]), 1e-4)
    for k in ks:
        if np.mean(acc[k]) >= 3 * base and k >= -10:
            return -k * 0.5                # hours the true start is BEFORE the recorded start
    return 0.0


def main():
    DST.mkdir(exist_ok=True)
    out = {}
    for p in sorted(SRC.glob("KX*.jsonl")):
        if len(sys.argv) > 1 and p.stem not in sys.argv[1:]:
            continue
        h = VERIFIED.get(p.stem, detect(p))
        out[p.stem] = h
        with open(DST / p.name, "w") as f:
            for ln in open(p):
                m = json.loads(ln)
                m["start"] = int(m["start"] - h * 3600)
                f.write(json.dumps(m, separators=(",", ":")) + "\n")
        print(f"{p.stem}: true start is {h:.1f} h before the recorded one", flush=True)
    json.dump(out, open(DST / "shifts.json", "w"))


if __name__ == "__main__":
    main()
