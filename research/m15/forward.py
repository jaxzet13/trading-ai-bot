"""Forward test of the two least-bad 15-minute groups, silver and USD/CAD (Nov 28 2026).

Account holder said "Sure" to: start a forward test of silver and USD/CAD, no betting, and only promote what keeps working on new days.

  python3 research/m15/forward.py freeze   # once: pick 5 strategies per group from ALL data so far, save research/m15/frozen.json
  python3 research/m15/forward.py score    # any time: download new windows, score ONLY days after the freeze, save forward.json

A frozen strategy = (group, minute, side, cell) with the decile edges from the original warm-up days. Picking rule: highest t over
the history with >= 60 bets and a positive result in both halves of the days. Nothing is tuned after the freeze.
Promotion bar (written now, before any forward data): >= 100 forward bets, pooled t >= 2.5 on the forward days only, positive in both
halves of the forward days; then SMALL size only.
"""
import json
import math
import os
import sys
import time

import numpy as np

os.environ["SKIP_CRYPTO"] = "1"
sys.path.insert(0, "research/m15")
sys.path.insert(0, ".")
import search as S

GROUPS = ["KXSILVER15M", "KXUSDCAD15M"]
FROZEN = "research/m15/frozen.json"
OUTF = "research/m15/forward.json"


def decode(c):
    ji, r = divmod(c, 2 * S.NCELL)
    si, cell = divmod(r, S.NCELL)
    return S.JS[ji], ("YES" if si == 0 else "NO"), cell


def cell_mask(dec, dec3, cell):
    if cell < S.NF * 10:
        f, d = divmod(cell, 10)
        return dec[:, f] == d
    if cell < S.NF * 10 + len(S.PAIRS) * 100:
        pi, ab = divmod(cell - S.NF * 10, 100)
        a, b = S.PAIRS[pi]
        return (dec[:, a] == ab // 10) & (dec[:, b] == ab % 10)
    ti, abc = divmod(cell - S.NF * 10 - len(S.PAIRS) * 100, 27)
    a, b, c = S.TRIPLES[ti]
    return (dec3[:, a] == abc // 9) & (dec3[:, b] == (abc // 3) % 3) & (dec3[:, c] == abc % 3)


def freeze():
    data = S.load_series()
    out = {"frozen_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "strategies": []}
    for g in GROUPS:
        r = S.run_group(g, [g], data, None)
        days, P, N, Q = S.STASH[g]
        Dn = len(days)
        h = Dn // 2
        t = S.tstat(P.sum(1), N.sum(1), Q.sum(1))
        ok = (N.sum(1) >= 60) & (P[:, :h].sum(1) > 0) & (P[:, h:].sum(1) > 0)
        t = np.where(ok, t, -np.inf)
        for c in np.argsort(-t)[:5]:
            c = int(c)
            j, side, cell = decode(c)
            out["strategies"].append({"group": g, "cell_id": c, "minute": j, "side": side, "cell": cell, "history_t": round(float(t[c]), 2),
                                      "history_bets": int(N[c].sum()), "history_cents": round(100 * float(P[c].sum() / N[c].sum()), 2),
                                      "desc": S.describe(c, g), "edges": {str(k): S.EDG.get((g, j, k)) for k in range(S.NF)}})
        out.setdefault("freeze_day", {})[g] = int(days[-1])
        print(g, "frozen; last history day", int(days[-1]))
    json.dump(out, open(FROZEN, "w"), indent=1)
    for s in out["strategies"]:
        print(s["desc"], "| history", s["history_cents"], "c on", s["history_bets"], "t", s["history_t"])


def score():
    os.system("python3 research/m15/download.py " + " ".join(GROUPS) + " > /dev/null 2>&1")
    fz = json.load(open(FROZEN))
    data = S.load_series()
    res = {"updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "strategies": [], "pooled": {}}
    perday = {}
    for g in GROUPS:
        bid, ask, y, day = data[g]
        m = day > fz["freeze_day"][g]
        new = {g: (bid[m], ask[m], y[m], day[m])}
        per_j = S.build_group([g], new)
        for st in [s for s in fz["strategies"] if s["group"] == g]:
            j = st["minute"]
            if j not in per_j:
                res["strategies"].append({"desc": st["desc"], "bets": 0})
                continue
            dd, F, py, pn = per_j[j]
            dec = np.full(F.shape, -1, dtype=np.int64)
            for k in range(S.NF):
                e = st["edges"].get(str(k))
                if e is None:
                    continue
                col = F[:, k]
                dec[:, k] = np.where(np.isfinite(col), np.minimum(np.searchsorted(np.array(e), col, side="right"), 9), -1)
            dec3 = np.where(dec < 0, -1, (dec >= 3).astype(np.int64) + (dec >= 7).astype(np.int64))
            pay = py if st["side"] == "YES" else pn
            hit = cell_mask(dec, dec3, st["cell"]) & np.isfinite(pay)
            p = pay[hit]
            for d, v in zip(dd[hit], p):
                perday.setdefault(g, {}).setdefault(int(d), []).append(float(v))
            res["strategies"].append({"group": g, "desc": st["desc"], "history_cents": st["history_cents"], "bets": int(hit.sum()),
                                      "cents": round(100 * float(p.mean()), 2) if len(p) else None})
    for g in GROUPS + ["BOTH"]:
        days = perday.get(g, {}) if g != "BOTH" else {}
        if g == "BOTH":
            for gg in GROUPS:
                for d, v in perday.get(gg, {}).items():
                    days.setdefault(d, []).extend(v)
        ds = sorted(days)
        allv = [v for d in ds for v in days[d]]
        dsum = np.array([sum(days[d]) for d in ds])
        h = len(ds) // 2
        t = float(dsum.mean() / dsum.std(ddof=1) * math.sqrt(len(dsum))) if len(dsum) > 2 and dsum.std(ddof=1) > 0 else 0.0
        res["pooled"][g] = {"days": len(ds), "bets": len(allv), "cents_per_bet": round(100 * float(np.mean(allv)), 2) if allv else None,
                            "t_by_day": round(t, 2), "halves_usd": [round(float(dsum[:h].sum()), 2), round(float(dsum[h:].sum()), 2)] if len(ds) > 3 else None}
    b = res["pooled"]["BOTH"]
    res["promote"] = bool(b["bets"] >= 100 and b["t_by_day"] >= 2.5 and b["halves_usd"] and min(b["halves_usd"]) > 0)
    json.dump(res, open(OUTF, "w"), indent=1)
    print(json.dumps(res["pooled"]), "promote:", res["promote"])


if __name__ == "__main__":
    {"freeze": freeze, "score": score}[sys.argv[1]]()
