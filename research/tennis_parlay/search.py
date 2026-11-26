"""Wider tennis parlay search: every rule of the lab's grid as parlay legs, judged walk-forward.

Leg rules: lab.strategies() (about 15,000: price bands at every minute from 3 h before to 3 h into play, in-play
swing rules, pre-match drift rules; five tour scopes), with the lab's fills (next minute, worst ask, Kalshi's fee).
One leg per match per rule (the first of the two markets to fire).

Per rule, parlay modes: single; combo of 2, 3, 4 legs (consecutive legs of the day, timing ignored, as a Kalshi combo
priced at the product of the legs would pay); rolled 2 and 3 (next leg only after the previous one settled).

Walk-forward (the only numbers that count): from day 15 on, each day picks, using EARLIER days only,
  A  the single best (rule, mode) by t (days as the unit, at least 30 bets before)
  B  the best rule by t, then each mode of it
  C  mixed parlays: the legs of that day from the 5 best single rules (by earlier t), one per match, rolled into
     2- and 3-leg parlays in time order
and bets it that day. Also: do favourites' results on the same day move together (the one thing that would let a
rolled parlay beat its legs)?

    python3 research/tennis_parlay/search.py [out.json]
"""
import json
import math
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
from tennis import lab                                       # noqa: E402
from tennis.history import STORE                             # noqa: E402

MODES = [("single", 1, False), ("combo", 2, False), ("combo", 3, False), ("combo", 4, False),
         ("rolled", 2, True), ("rolled", 3, True)]
WARMUP, MIN_BETS = 14, 30


def fee(p):
    return np.ceil(0.07 * p * (1 - p) * 100 - 1e-9) / 100


def fill_at(m, i, side):
    """Fill one bar after i: -> (cost incl. fee, decision time) or None."""
    rel = m["rel"]
    if i + 1 >= len(rel) or rel[i + 1] - rel[i] > 3.01:
        return None
    if side == "yes":
        p = m["askhi"][i + 1]
    else:
        b = m["bidlo"][i + 1]
        p = 1 - b if np.isfinite(b) else np.nan
    if not (np.isfinite(p) and 0.02 <= p <= 0.98):
        return None
    return float(p + fee(p)), m["start"] + 60 * float(rel[i + 1])


class Legs:
    """Per market arrays for one rule configuration: ok, cost, payout, decision time."""

    def __init__(self, n):
        self.ok = np.zeros(n, bool)
        self.cost = np.ones(n)
        self.win = np.zeros(n)
        self.t = np.zeros(n)

    def set(self, k, m, side, i):
        f = fill_at(m, i, side)
        if f is None:
            return
        self.ok[k], self.cost[k], self.t[k] = True, f[0], f[1]
        self.win[k] = m["value"] if side == "yes" else 1 - m["value"]


def band_legs(ms, M):
    L, mid = Legs(len(ms)), np.full(len(ms), np.nan)
    for k, m in enumerate(ms):
        rel = m["rel"]
        i = np.searchsorted(rel, M, side="right") - 1
        if i < 0 or M - rel[i] > 10 or not np.isfinite(m["mid"][i]):
            continue
        mid[k] = m["mid"][i]
        L.set(k, m, "yes", i)
    return L, mid


def swing_legs(ms, phase, w, d, direction):
    a, b = lab.PHASES[phase]
    Y, N = Legs(len(ms)), Legs(len(ms))
    for k, m in enumerate(ms):
        rel, mid = m["rel"], m["mid"]
        idx = np.arange(len(rel))
        j = np.searchsorted(rel, rel - w, side="left")
        jj = np.minimum(j, len(rel) - 1)
        refok = (j < idx) & np.isfinite(mid[jj])
        ch = mid - mid[jj]
        with np.errstate(invalid="ignore"):
            cond = ((rel >= a) & (rel < b) & np.isfinite(mid) & (mid >= 0.10) & (mid <= 0.90) & refok
                    & ((ch <= -d) if direction == "down" else (ch >= d)))
        hit = np.nonzero(cond)[0]
        if len(hit):
            Y.set(k, m, "yes", hit[0])
            N.set(k, m, "no", hit[0])
    return Y, N


def drift_legs(ms, M, L):
    Y, N = Legs(len(ms)), Legs(len(ms))
    mid_i, ch = np.full(len(ms), np.nan), np.full(len(ms), np.nan)
    for k, m in enumerate(ms):
        rel, mid = m["rel"], m["mid"]
        i, j = lab._bar_at(rel, M), lab._bar_at(rel, M - L)
        if i is None or j is None or j >= i or not (np.isfinite(mid[i]) and np.isfinite(mid[j])):
            continue
        mid_i[k], ch[k] = mid[i], mid[i] - mid[j]
        Y.set(k, m, "yes", i)
        N.set(k, m, "no", i)
    return Y, N, mid_i, ch


def rule_masks(ms):
    """Yield (rule id, Legs, mask) for every lab rule."""
    strats = lab.strategies()
    scope = lab._scope_masks(ms)
    by_m, by_sw, by_dr = defaultdict(list), defaultdict(list), defaultdict(list)
    for s in strats:
        if s["fam"] == "band":
            by_m[s["M"]].append(s)
        elif s["fam"] == "drift":
            by_dr[(s["M"], s["L"])].append(s)
        else:
            by_sw[(s["phase"], s["w"], s["d"], s["dir"])].append(s)
    for M, ss in by_m.items():
        L, mid = band_legs(ms, M)
        with np.errstate(invalid="ignore"):
            for s in ss:
                yield s["id"], L, L.ok & (mid >= s["lo"]) & (mid < s["hi"]) & scope[s.get("scope", "all")]
    for (ph, w, d, dr), ss in by_sw.items():
        Y, N = swing_legs(ms, ph, w, d, dr)
        for s in ss:
            back = (dr == "down") == (s["act"] == "rev")
            L = Y if back else N
            yield s["id"], L, L.ok & scope[s.get("scope", "all")]
    for (M, LL), ss in by_dr.items():
        Y, N, mid_i, ch = drift_legs(ms, M, LL)
        with np.errstate(invalid="ignore"):
            band = (mid_i >= 0.10) & (mid_i <= 0.90)
            for s in ss:
                moved = (ch >= s["d"]) if s["dir"] == "up" else (ch <= -s["d"])
                back = (s["dir"] == "up") == (s["act"] == "mom")
                L = Y if back else N
                yield s["id"], L, band & moved & L.ok & scope[s.get("scope", "all")]


def build(idx, L, ev, dix, end, k, rolled):
    """Parlays of one rule -> (day index, return per $1, won) arrays. idx = its markets, one per match, by time."""
    if k == 1:
        r = L.win[idx] / L.cost[idx] - 1
        return dix[idx], r
    days_out, rets = [], []
    cur, cd = [], -1
    for i in idx:
        d = dix[i]
        if d != cd:
            cur, cd = [], d
        if rolled and cur and L.t[i] < end[cur[-1]]:
            continue
        cur.append(i)
        if len(cur) == k:
            days_out.append(d)
            rets.append(float(np.prod(L.win[cur] / L.cost[cur])) - 1)
            cur = []
    return np.array(days_out, int), np.array(rets)


def tstat(S1, S2, n_days):
    """Day-clustered t from per-day sums (S1 = sum of day totals, S2 = sum of squared day totals)."""
    mean = S1 / n_days
    var = np.maximum(S2 / n_days - mean ** 2, 1e-12) * n_days / max(n_days - 1, 1)
    return mean / np.sqrt(var) * math.sqrt(n_days)


def summary(day_ret, test_days, label):
    rs = [r for d in test_days for r in day_ret.get(d, [])]
    if not rs:
        return {"label": label, "n": 0}
    w = np.array([sum(day_ret.get(d, [])) for d in test_days])
    h = len(test_days) // 2
    a = [r for d in test_days[:h] for r in day_ret.get(d, [])]
    b = [r for d in test_days[h:] for r in day_ret.get(d, [])]
    t = float(w.mean() / w.std(ddof=1) * math.sqrt(len(w))) if w.std() > 0 else 0.0
    return {"label": label, "n": len(rs), "per_day": round(len(rs) / len(test_days), 2),
            "roi_pct": round(100 * float(np.mean(rs)), 2), "usd_per_day_at_1": round(float(w.mean()), 3), "t": round(t, 2),
            "halves_roi_pct": [round(100 * float(np.mean(a)), 2) if a else None, round(100 * float(np.mean(b)), 2) if b else None],
            "days_up": int((w > 0).sum()), "test_days": len(test_days)}


def main():
    t0 = time.time()
    ms = lab.load()
    settled = {}
    for ln in open(STORE):
        r = json.loads(ln)
        settled[r["ticker"]] = r.get("settled") or 1e18
    days = np.array(sorted({m["day"] for m in ms}))
    D = len(days)
    dix = np.searchsorted(days, np.array([m["day"] for m in ms]))
    ev = np.array([m["event"] for m in ms])
    end = np.array([settled.get(m["ticker"], 1e18) for m in ms], float)
    print(f"{len(ms)} markets, {D} days")

    ids, per_mode = [], {mk: [] for mk in MODES}            # per candidate: day x (sum, n, sumsq)
    store = {}                                               # (rule, mode) -> (day idx array, returns array)
    legs_by_rule = {}                                        # rule -> (idx, L) for mixed parlays
    for rid, L, mask in rule_masks(ms):
        idx = np.nonzero(mask)[0]
        if len(idx) < MIN_BETS:
            continue
        idx = idx[np.lexsort((L.t[idx], dix[idx]))]          # by day, then decision time
        _, first = np.unique(ev[idx], return_index=True)     # one leg per match: the first to fire
        idx = idx[np.sort(first)]
        idx = idx[np.lexsort((L.t[idx], dix[idx]))]
        ids.append(rid)
        legs_by_rule[rid] = (idx, L)
        for mk in MODES:
            dd, rr = build(idx, L, ev, dix, end, mk[1], mk[2])
            S = np.zeros((D, 3), np.float32)
            if len(rr):
                S[:, 0] = np.bincount(dd, rr, D)
                S[:, 1] = np.bincount(dd, None, D)
            per_mode[mk].append(S)
            store[(rid, mk)] = (dd, rr)
        if len(ids) % 2000 == 0:
            print(f"  {len(ids)} rules ({time.time() - t0:.0f}s)")
    print(f"{len(ids)} rules with >= {MIN_BETS} bets ({time.time() - t0:.0f}s)")
    R = len(ids)
    arr = {mk: np.stack(per_mode[mk]) for mk in MODES}       # R x D x 3

    # same-day dependence: do (win - cost) residuals of legs of the same day move together?
    corr = {}
    for name, rid in (("Challenger favourites 90-96c", "band:m-60:0.90-0.95:chal"),
                      ("any favourite 80-90c", "band:m-60:0.80-0.90"), ("any favourite 60-80c", "band:m-60:0.60-0.70")):
        if rid not in legs_by_rule:
            continue
        idx, L = legs_by_rule[rid]
        res = L.win[idx] - L.cost[idx]
        dd = dix[idx]
        num = den = 0.0
        pairs = 0
        for d in np.unique(dd):
            x = res[dd == d]
            if len(x) < 2:
                continue
            s, s2 = x.sum(), (x ** 2).sum()
            num += s * s - s2                              # sum over ordered pairs i != j of x_i x_j
            den += (len(x) - 1) * s2
            pairs += len(x) * (len(x) - 1) // 2
        corr[name] = {"rule": rid, "same_day_correlation": round(num / den, 3) if den else None, "pairs": pairs}
    print("same-day correlation of leg results:", corr)

    # in-sample leaderboard (for the record: with this many candidates the best t by chance alone is about 4)
    full = []
    for mk in MODES:
        S1 = arr[mk][:, :, 0].sum(1)
        S2 = (arr[mk][:, :, 0] ** 2).sum(1)
        n = arr[mk][:, :, 1].sum(1)
        t = tstat(S1, S2, D)
        for r in np.argsort(-t)[:40]:
            if n[r] >= MIN_BETS:
                full.append((float(t[r]), ids[r], f"{mk[0]}{mk[1]}", int(n[r]), round(100 * float(S1[r] / n[r]), 2)))
    full.sort(reverse=True)
    print("\nbest in-sample (all 64 days; NOT a result, just what a search over this many candidates finds):")
    for row in full[:15]:
        print(f"  t {row[0]:5.2f}  {row[1]:40s} {row[2]:8s} {row[3]:5d} bets  {row[4]:+6.2f}% per $")

    # walk-forward
    test_days = list(range(WARMUP, D))
    out = defaultdict(lambda: defaultdict(list))
    picks = defaultdict(lambda: defaultdict(int))
    cum = {mk: (np.cumsum(arr[mk][:, :, 0], 1), np.cumsum(arr[mk][:, :, 0] ** 2, 1), np.cumsum(arr[mk][:, :, 1], 1))
           for mk in MODES}
    for di in test_days:
        best_all, best_rule = (-1e9, None), {}
        for mk in MODES:
            S1, S2, N = (c[:, di - 1] for c in cum[mk])
            t = np.where(N >= MIN_BETS, tstat(S1, S2, di), -1e9)
            r = int(np.argmax(t))
            if t[r] > best_all[0]:
                best_all = (float(t[r]), (ids[r], mk))
            if mk == MODES[0]:
                order = np.argsort(-t)
                best_rule = [ids[i] for i in order[:5] if t[i] > -1e8]
        if best_all[1]:                                     # A
            rid, mk = best_all[1]
            dd, rr = store[(rid, mk)]
            out["A best rule and mode"][di] += list(rr[dd == di])
            picks["A best rule and mode"][f"{rid} {mk[0]}{mk[1]}"] += 1
        if best_rule:                                       # B
            rid = best_rule[0]
            picks["B best single rule"][rid] += 1
            for mk in MODES:
                dd, rr = store[(rid, mk)]
                out[f"B best single rule, {mk[0]} {mk[1]}"][di] += list(rr[dd == di])
            # C: mixed parlays from the top-5 rules' legs of the day
            pool, seen = [], set()
            for rid in best_rule:
                idx, L = legs_by_rule[rid]
                for i in idx[dix[idx] == di]:
                    if ev[i] not in seen:
                        seen.add(ev[i])
                        pool.append((L.t[i], i, L))
            pool.sort(key=lambda x: x[0])
            out["C top-5 rules, singles"][di] += [L.win[i] / L.cost[i] - 1 for _, i, L in pool]
            for k in (2, 3):
                cur = []
                for tt, i, L in pool:
                    if cur and tt < end[cur[-1][0]]:
                        continue
                    cur.append((i, L))
                    if len(cur) == k:
                        out[f"C top-5 rules, rolled {k}"][di].append(float(np.prod([LL.win[j] / LL.cost[j] for j, LL in cur])) - 1)
                        cur = []
    res = {"days": int(D), "rules": R, "candidates": R * len(MODES), "same_day_correlation": corr,
           "in_sample_top": full[:15], "walk_forward": {}}
    print(f"\nwalk-forward, {len(test_days)} test days (each day chosen on earlier days only):")
    for label in sorted(out):
        s = summary(out[label], test_days, label)
        res["walk_forward"][label] = s
        print(f"  {label:38s} n {s.get('n', 0):5d}  {s.get('per_day', 0):5.2f}/day  ROI {s.get('roi_pct', 0):+7.2f}%  "
              f"t {s.get('t', 0):+5.2f}  halves {s.get('halves_roi_pct')}  days up {s.get('days_up', 0)}/{len(test_days)}  "
              f"$/day@$1 {s.get('usd_per_day_at_1', 0):+.3f}")
    for k, v in picks.items():
        top = sorted(v.items(), key=lambda x: -x[1])[:5]
        print(f"  picks {k}: {top}")
        res["walk_forward"][f"picks {k}"] = top
    print(f"({time.time() - t0:.0f}s)")
    if len(sys.argv) > 1:
        json.dump(res, open(sys.argv[1], "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
