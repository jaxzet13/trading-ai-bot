"""Walk-forward test of the SELECTION itself (python -m kalshi15m fwdlab walk).

The forward lab scores thousands of frozen strategies on new days. Picking the leaders and trading them only makes
sense if leaders keep leading. This replays that choice day by day on the saved per-day results
(data/lab/fwd_daily.json, written by fwdlab score): on each day, rank candidates using only the days before it, pick
the top K, and score the picks on that day alone. Compared with the average of all eligible candidates and with
ranking whole coins instead of single strategies. Nothing here looks ahead. -> data/lab/fwd_walk.json
"""
from __future__ import annotations

import json
import math
import statistics as st
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABDIR = ROOT / "data" / "lab"
WARMUP_DAYS, MIN_BETS = 5, 30


def _agg(v, ds):
    n = s = q = 0.0
    for d in ds:
        x = v.get(str(d))
        if x:
            s += x[0]; n += x[1]; q += x[2]
    return n, s, q


def _t(n, s, q):
    if n < 3:
        return -9.0
    m = s / n
    var = (q - n * m * m) / (n - 1)
    return m / math.sqrt(var / n) if var > 0 else -9.0


def walk(daily_path=LABDIR / "fwd_daily.json", cands_path=LABDIR / "fwd_candidates.json", log=print):
    D = json.loads(Path(daily_path).read_text())["days"]
    C = {c["id"]: c for c in json.loads(Path(cands_path).read_text())["candidates"]}
    days = sorted({int(d) for v in D.values() for d in v})
    out = {"generated": int(time.time()), "days": len(days), "test_days": max(len(days) - WARMUP_DAYS, 0), "methods": {}}
    for K in (5, 20, 100):
        for crit in ("t", "pnl"):
            pick_day, base_day = [], []
            for i, d in enumerate(days):
                if i < WARMUP_DAYS:
                    continue
                sc = []
                for c, v in D.items():
                    n, s, q = _agg(v, days[:i])
                    if n >= MIN_BETS:
                        sc.append((_t(n, s, q) if crit == "t" else s, c))
                if not sc:
                    continue
                sc.sort(reverse=True)
                pick_day.append(sum(_agg(D[c], [d])[1] for _, c in sc[:K]) / K)
                base_day.append(sum(_agg(D[c], [d])[1] for _, c in sc) / len(sc))
            if pick_day:
                out["methods"][f"top{K}_by_{crit}"] = {
                    "pick_per_day": round(st.mean(pick_day), 4), "pick_days_up": sum(x > 0 for x in pick_day),
                    "all_per_day": round(st.mean(base_day), 4), "all_days_up": sum(x > 0 for x in base_day),
                    "n_days": len(pick_day), "beats_all": st.mean(pick_day) > st.mean(base_day)}
    scope = defaultdict(list)
    for c in D:
        if c in C:
            scope[C[c]["scope"]].append(c)
    sday = lambda s, d: st.mean(D[c].get(str(d), [0])[0] for c in scope[s])
    for K in (3, 5):
        top, allc = [], []
        for i, d in enumerate(days):
            if i < WARMUP_DAYS:
                continue
            rank = sorted(scope, key=lambda s: -sum(sday(s, x) for x in days[:i]))
            top.append(st.mean(sday(s, d) for s in rank[:K]))
            allc.append(st.mean(sday(s, d) for s in scope))
        if top:
            now = sorted(scope, key=lambda s: -sum(sday(s, x) for x in days))[:K]  # what this method picks today
            out["methods"][f"top{K}_coins"] = {"pick_per_day": round(st.mean(top), 4), "pick_days_up": sum(x > 0 for x in top),
                                               "all_per_day": round(st.mean(allc), 4), "n_days": len(top),
                                               "beats_all": st.mean(top) > st.mean(allc), "current_pick": now}
    # Families: one strategy type on one coin (e.g. fv_dyn:KXZEC15M), all its parameter settings averaged. Ranking
    # families instead of single settings asks whether the IDEA keeps working, which is less noisy than one setting.
    fam = defaultdict(list)
    for c in D:
        fam[c.rsplit(":", 1)[0]].append(c)
    fday = lambda f, d: st.mean(D[c].get(str(d), [0])[0] for c in fam[f])
    fbets = lambda f, ds: sum(_agg(D[c], ds)[0] for c in fam[f]) / len(fam[f])
    for K in (3, 10):
        top, allf = [], []
        for i, d in enumerate(days):
            if i < WARMUP_DAYS:
                continue
            elig = [f for f in fam if fbets(f, days[:i]) >= MIN_BETS / 3]
            if len(elig) < K:
                continue
            rank = sorted(elig, key=lambda f: -sum(fday(f, x) for x in days[:i]))
            top.append(st.mean(fday(f, d) for f in rank[:K]))
            allf.append(st.mean(fday(f, d) for f in elig))
        if top:
            elig = [f for f in fam if fbets(f, days) >= MIN_BETS / 3]
            now = sorted(elig, key=lambda f: -sum(fday(f, x) for x in days))[:K]
            out["methods"][f"top{K}_families"] = {"pick_per_day": round(st.mean(top), 4), "pick_days_up": sum(x > 0 for x in top),
                                                  "all_per_day": round(st.mean(allf), 4), "n_days": len(top),
                                                  "beats_all": st.mean(top) > st.mean(allf), "current_pick": now}
    won = sum(m["beats_all"] for m in out["methods"].values())
    out["summary"] = (f"{won} of {len(out['methods'])} selection methods beat the plain average of all candidates "
                      f"over {out['test_days']} walk-forward test days")
    (LABDIR / "fwd_walk.json").write_text(json.dumps(out, indent=1))
    for k, m in out["methods"].items():
        log(f"  {k:16s} picks {m['pick_per_day']:+.3f}/day ({m['pick_days_up']}/{m['n_days']} up)  vs all {m['all_per_day']:+.3f}"
            f"  {'BEATS' if m['beats_all'] else 'worse'}" + (f"  now: {', '.join(m['current_pick'])}" if m.get("current_pick") else ""))
    log("fwdlab walk: " + out["summary"])
    return out
