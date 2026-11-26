"""Tennis parlays: do they make money where single bets do not, or more of it where they do?

A parlay pays only if every leg wins, and then pays the product of the legs' odds. Kalshi offers them as "combos"
(collection KXMVESPORTSMULTIGAMEEXTENDED accepts Challenger and ITF match legs), but a combo market exists only once
somebody asks for a quote, so there is no price history to test those prices on. What can be tested is the parlay we
build ourselves: stake on leg 1, roll everything into leg 2 when leg 1 wins, and so on. That is exactly a combo
priced at the product of the leg prices (no extra margin), with Kalshi's taker fee paid on every leg.

Legs: the lab's band rule (lab.bet, same fills as everywhere else: decided on one minute's mid, filled the next
minute at the ask high, Kalshi's fee). At minute M of the match clock, back a player whose mid is in [lo, hi).
Every leg is a different match.

Parlays, built per day in the order the legs are decided:
  rolled   leg i+1 is decided after leg i settled (Kalshi's settlement time), so the rolling is really doable
  combo    any k legs of the day in decision order (what a combo would allow; timing ignored)
Return per dollar staked: product over the legs of (payout / (price + fee)) - 1; a single: payout / cost - 1.
t statistics use days as the unit (one bad day hits every parlay of that day).

Walk-forward: each test day picks the leg pool and the number of legs with the best record on EARLIER days only.

    python3 research/tennis_parlay/study.py [out.json]
"""
import json
import math
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
from tennis import api, lab                                  # noqa: E402
from tennis.history import STORE                             # noqa: E402

POOLS = [  # (name, scope, minute, lo, hi)
    ("Challenger favourites 90-96c, 60 min before", "chal", -60, 0.90, 0.96),
    ("Challenger favourites 90-96c, 30 min before", "chal", -30, 0.90, 0.96),
    ("Challenger favourites 80-90c, 60 min before", "chal", -60, 0.80, 0.90),
    ("Challenger favourites 70-80c, 60 min before", "chal", -60, 0.70, 0.80),
    ("ITF favourites 90-96c, 60 min before", "itf", -60, 0.90, 0.96),
    ("ITF favourites 80-90c, 60 min before", "itf", -60, 0.80, 0.90),
    ("ATP/WTA favourites 80-96c, 60 min before", "tour", -60, 0.80, 0.96),
    ("Any favourite 80-96c, 60 min before", "all", -60, 0.80, 0.96),
    ("Any favourite 60-80c, 60 min before", "all", -60, 0.60, 0.80),
]
KS = (1, 2, 3, 4, 5)
SCOPE = dict(lab.SCOPES, tour={"KXATPMATCH", "KXWTAMATCH"})


def settled_times():
    out = {}
    for ln in open(STORE):
        m = json.loads(ln)
        out[m["ticker"]] = m.get("settled")
    return out


def legs(ms, settled, pool):
    """All bets of one pool -> list of dicts, one per match (the first market of a match that fires)."""
    name, scope, M, lo, hi = pool
    s = {"fam": "band", "M": M, "lo": lo, "hi": hi, "scope": "all", "id": name}
    seen, out = set(), []
    for m in ms:
        if SCOPE[scope] is not None and m["series"] not in SCOPE[scope]:
            continue
        if m["event"] in seen:
            continue
        r = lab.bet(m, s)
        if not r:
            continue
        side, p, pnl, minute = r
        cost = p + api.fee(p, 1)
        win = m["value"]
        seen.add(m["event"])
        out.append({"day": m["day"], "t": m["start"] + 60 * (minute + 1), "end": settled.get(m["ticker"]) or 1e18,
                    "cost": cost, "win": win, "mult": win / cost, "event": m["event"]})
    out.sort(key=lambda x: x["t"])
    return out


def parlays(bets, k, rolled):
    """Group one pool's bets into k-leg parlays, day by day -> list of (day, return per $1, all won)."""
    by = defaultdict(list)
    for b in bets:
        by[b["day"]].append(b)
    out = []
    for d, bs in sorted(by.items()):
        if k == 1:
            out += [(d, b["mult"] - 1, b["win"] >= 0.999) for b in bs]
            continue
        if not rolled:
            for i in range(0, len(bs) - k + 1, k):
                g = bs[i:i + k]
                out.append((d, float(np.prod([x["mult"] for x in g])) - 1, all(x["win"] >= 0.999 for x in g)))
            continue
        cur = []
        for b in bs:                                          # greedy: next leg starts after the last one settled
            if cur and b["t"] < cur[-1]["end"]:
                continue
            cur.append(b)
            if len(cur) == k:
                out.append((d, float(np.prod([x["mult"] for x in cur])) - 1, all(x["win"] >= 0.999 for x in cur)))
                cur = []
    return out


def stats(rows, days):
    if not rows:
        return {"n": 0}
    r = np.array([x[1] for x in rows])
    per = defaultdict(float)
    for d, v, _ in rows:
        per[d] += v
    w = np.array([per.get(d, 0.0) for d in days])
    t = float(w.mean() / w.std(ddof=1) * math.sqrt(len(w))) if w.std() > 0 else 0.0
    h = len(days) // 2
    first = [x[1] for x in rows if x[0] in set(days[:h])]
    second = [x[1] for x in rows if x[0] in set(days[h:])]
    eq = np.cumsum(w)
    return {"n": len(r), "per_day": round(len(r) / len(days), 2), "roi_pct": round(100 * r.mean(), 2),
            "hit": round(float(np.mean([x[2] for x in rows])), 3), "usd_per_day": round(float(w.mean()), 3),
            "t": round(t, 2), "halves_roi_pct": [round(100 * float(np.mean(first)), 2) if first else None,
                                                 round(100 * float(np.mean(second)), 2) if second else None],
            "days_up": int((w > 0).sum()), "worst_day": round(float(w.min()), 2),
            "max_drawdown": round(float((np.maximum.accumulate(eq) - eq).max()), 2)}


def walk_forward(table, days, warmup=14):
    """Each day: pick the (pool, k, mode) with the best ROI on earlier days (>= 30 parlays), bet it that day."""
    picked, rows = [], []
    for i, d in enumerate(days):
        if i < warmup:
            continue
        past = set(days[:i])
        best, score = None, -1e9
        for key, rs in table.items():
            prev = [x[1] for x in rs if x[0] in past]
            if len(prev) < 30:
                continue
            m = float(np.mean(prev))
            if m > score:
                best, score = key, m
        if best is None:
            continue
        picked.append(best)
        rows += [x for x in table[best] if x[0] == d]
    return rows, picked


def main():
    ms = lab.load()
    settled = settled_times()
    days = sorted({m["day"] for m in ms})
    print(f"{len(ms)} markets, {len({m['event'] for m in ms})} matches, {len(days)} days\n")
    res, table = {}, {}
    for pool in POOLS:
        bets = legs(ms, settled, pool)
        print(f"{pool[0]}  ({len(bets)} legs, {len(bets) / len(days):.1f} a day, "
              f"avg price {np.mean([b['cost'] for b in bets]):.3f} incl. fee, won {np.mean([b['win'] for b in bets]):.3f})")
        print(f"  {'legs':>4} {'mode':6} {'n':>5} {'a day':>6} {'hit':>6} {'ROI/$':>7} {'halves':>15} {'$/day@$1':>9} "
              f"{'t':>6} {'days up':>8} {'worst':>6} {'maxDD':>6}   product of singles")
        single = None
        for k in KS:
            for rolled in ((False,) if k == 1 else (True, False)):
                mode = "single" if k == 1 else ("rolled" if rolled else "combo")
                rows = parlays(bets, k, rolled)
                s = stats(rows, days)
                if k == 1:
                    single = s
                res[f"{pool[0]} | {k} | {mode}"] = s
                table[(pool[0], k, mode)] = rows
                if not s["n"]:
                    continue
                theo = 100 * ((1 + single["roi_pct"] / 100) ** k - 1)
                print(f"  {k:>4} {mode:6} {s['n']:>5} {s['per_day']:>6} {s['hit']:>6.3f} {s['roi_pct']:>+6.2f}% "
                      f"{str(s['halves_roi_pct']):>15} {s['usd_per_day']:>+9.3f} {s['t']:>+6.2f} "
                      f"{s['days_up']:>4}/{len(days):<3} {s['worst_day']:>+6.2f} {s['max_drawdown']:>6.2f}   {theo:+.2f}%")
        print()
    for mode_filter, label in ((None, "any pool, any k"), ("single", "singles only"), ("rolled", "rolled parlays only")):
        sub = {k: v for k, v in table.items() if mode_filter is None or k[2] == mode_filter}
        rows, picked = walk_forward(sub, days)
        s = stats(rows, days[14:])
        res[f"walk-forward {label}"] = s
        top = defaultdict(int)
        for p in picked:
            top[f"{p[0]} x{p[1]} {p[2]}"] += 1
        print(f"walk-forward ({label}), {len(days) - 14} test days: {s}")
        print("   picked:", dict(sorted(top.items(), key=lambda x: -x[1])[:4]))
    if len(sys.argv) > 1:
        json.dump(res, open(sys.argv[1], "w"), indent=1)


if __name__ == "__main__":
    main()
