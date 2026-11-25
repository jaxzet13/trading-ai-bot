"""Kalshi stock-index markets (S&P 500, Nasdaq-100; 16:00 New York events): is there an edge for a taker?

    python3 research/index_study/study.py [--no-prevol]     (after download.py; prints every table of the README)

Rows: one per market x decision time (minutes before the close) with a two-sided quote.
Execution: TAKER only. Buy YES at the ask, or buy NO at 1 - bid, plus the fee 0.07 p (1 - p). Settles at 0 / 1.
t statistics: days are the independent unit (all rows of a day are one index path).
Halves: first / second half of the calendar days.

  a  calibration by price band and time of day
  b  normal fair-value model (level, time left, realised volatility) vs Kalshi's price; walk-forward logistic
     regression with offset logit(mid); bets when the edge after the fee is >= 3c / 5c
  c  the same with momentum features (index move over 5 / 15 / 60 minutes in volatility units)
  d  bracket sums and ladder consistency (arbitrage checks)
"""
import math
import sys

import numpy as np
from scipy.special import expit, logit, ndtr

from common import FAMILY, INDEX, WIN, fee, halves, implied_level, load, tstat, two_sided, yahoo

TIMES = [(360, "10:00"), (300, "11:00"), (240, "12:00"), (180, "13:00"), (120, "14:00"), (60, "15:00"),
         (30, "15:30"), (10, "15:50")]                 # minutes before the close, New York clock time
BANDS = [(0.03, 0.10), (0.10, 0.25), (0.25, 0.40), (0.40, 0.60), (0.60, 0.75), (0.75, 0.90), (0.90, 0.97)]
VOL_DAYS = 5                                           # realised volatility: 5-minute returns of the last 5 sessions
MIN_TRAIN = 15                                         # walk-forward: first scored day has 15 days before it
SERIES = ["KXINX", "KXNASDAQ100", "KXINXU", "KXNASDAQ100U"]
# Liquidity filter known at the decision time: contracts traded in the market BEFORE that minute (within the
# downloaded window). The thresholds equal the total-volume thresholds of the download, so every market that
# passes was downloaded: no selection on what happened afterwards. (Selecting on the day's total volume is a
# look-ahead: a longshot strike gets its volume when the index moves to it. PREVOL=0 shows that biased sample.)
PREVOL = {"range": 1, "above": 50, "hourly": 300}
NO_FILTER = "--no-prevol" in sys.argv


# ---------------------------------------------------------------------------------------------------- data
def levels(events):
    """Per source ("yahoo": 5-minute bars; "implied": the 16:00 "or above" ladder of Kalshi itself) and index:
    {time: level} on the 5-minute grid of the regular session, and {time: per-minute volatility known then}
    (root mean square of the 5-minute log returns of the previous VOL_DAYS sessions and of today so far)."""
    lev = {"yahoo": {}, "implied": {}}
    sig = {"yahoo": {}, "implied": {}}
    for sym in ("GSPC", "NDX"):
        evs = [e for e in events if INDEX[e["series"]] == sym and FAMILY[e["series"]] == "above" and e["daily"]]
        y5 = yahoo(sym)
        Ly, Li, sessions = {}, {}, []
        for e in evs:
            imp = implied_level(e)
            ts = [e["close"] - k * 300 for k in range(78, -1, -1)]      # 9:30 .. 16:00 New York
            sessions.append(ts)
            for t in ts:
                if t in y5:
                    Ly[t] = y5[t]
                v = imp[WIN - (e["close"] - t) // 60]
                if np.isfinite(v):
                    Li[t] = v
        lev["yahoo"][sym], lev["implied"][sym] = Ly, Li
        for src, L in (("yahoo", Ly), ("implied", Li)):
            S, hist = {}, []                                 # hist: squared returns of earlier sessions
            for ts in sessions:
                today = []
                base = [x for h in hist[-VOL_DAYS:] for x in h]
                for a, b in zip(ts[:-1], ts[1:]):
                    if a in L and b in L:
                        today.append(math.log(L[b] / L[a]) ** 2)
                    n = len(base) + len(today)
                    if n >= 60:
                        S[b] = math.sqrt((sum(base) + sum(today)) / n / 5.0)
                if today:
                    hist.append(today)
            sig[src][sym] = S
    return lev, sig


def model_p(S, sig, mins, floor, cap):
    """Normal model: P(the index finishes in [floor, cap]) from level S, per-minute vol sig, minutes left."""
    s = sig * math.sqrt(mins)
    hi = ndtr(math.log(S / floor) / s) if floor is not None else 1.0
    lo = ndtr(math.log(S / (cap + 0.011)) / s) if cap is not None else 0.0
    return hi - lo


def rows(events, lev, sig):
    out = []
    for e in events:
        sym, fam = INDEX[e["series"]], FAMILY[e["series"]]
        for m in e["markets"]:
            ok = two_sided(m["bid"], m["ask"])
            cum = np.cumsum(m["vol"])
            kind = fam if e["daily"] else "hourly"
            for mins, label in TIMES:
                i = WIN - mins
                if not ok[i] or (not e["daily"] and mins > 60):       # hourly events: the last hour only
                    continue
                if not NO_FILTER and cum[i] < PREVOL[kind]:
                    continue
                t = e["close"] - mins * 60
                r = {"sym": sym, "fam": fam if e["daily"] else "hourly", "day": e["day"], "tk": m["tk"],
                     "mins": mins, "bid": m["bid"][i], "ask": m["ask"][i], "v": m["v"], "volume": m["volume"],
                     "prevol": cum[i]}
                for src in ("yahoo", "implied"):
                    S, sg = lev[src][sym].get(t), sig[src][sym].get(t)
                    good = S is not None and sg is not None and sg > 0
                    r["p_" + src] = model_p(S, sg, mins, m["floor"], m["cap"]) if good else np.nan
                    for lag in (5, 15, 60):
                        S0 = lev[src][sym].get(t - lag * 60)
                        r[f"mom{lag}_{src}"] = (math.log(S / S0) / (sg * math.sqrt(lag))
                                                if good and S0 is not None else np.nan)
                out.append(r)
    R = {k: np.array([r[k] for r in out]) for k in out[0]}
    R["mid"] = (R["bid"] + R["ask"]) / 2
    R["yes"] = R["v"] - R["ask"] - fee(R["ask"])                 # buy YES at the ask
    R["no"] = (1 - R["v"]) - (1 - R["bid"]) - fee(R["bid"])      # buy NO at 1 - bid
    return R


# ------------------------------------------------------------------------------------------- a. calibration
def cell(pnl, day, alldays):
    if len(pnl) < 30:
        return f"{'':>30}"
    a, b = halves(pnl, day, alldays)
    return f"{100 * pnl.mean():+6.2f}c t {tstat(pnl, day):+5.2f} [{a:+5.1f} /{b:+5.1f}]"


def calibration(R, title, mask):
    alldays = sorted(set(R["day"][mask]))
    print(f"\n{title}   ({mask.sum()} rows, {len(set(R['tk'][mask]))} markets, {len(alldays)} days)")
    print("  mid band        n  spread  value-mid (t)      buy YES at ask after fee [half1/half2]   "
          "buy NO at bid after fee [half1/half2]")
    for lo, hi in BANDS + [(0.03, 0.97)]:
        k = mask & (R["mid"] >= lo) & (R["mid"] < hi)
        if k.sum() < 30:
            continue
        d = R["day"][k]
        vm = R["v"][k] - R["mid"][k]
        print(f"  {lo:.2f}-{hi:.2f} {k.sum():7d}  {100 * (R['ask'][k] - R['bid'][k]).mean():4.1f}c  "
              f"{100 * vm.mean():+6.2f}c t {tstat(vm, d):+5.2f}   {cell(R['yes'][k], d, alldays)}   "
              f"{cell(R['no'][k], d, alldays)}")


def favourites(R, title, mask):
    """Direction-neutral view: back the favourite side (YES if mid > 50c, else NO) or the longshot side.
    If the index drifts one way all favourites on one side of the level lose and those on the other win."""
    alldays = sorted(set(R["day"][mask]))
    fav = R["mid"] > 0.5
    fp = np.maximum(R["mid"], 1 - R["mid"])
    win = np.where(fav, R["v"], 1 - R["v"])
    favpnl = np.where(fav, R["yes"], R["no"])
    lngpnl = np.where(fav, R["no"], R["yes"])
    print(f"\n{title}: favourite side vs longshot side")
    print("  favourite's mid      n  favourite wins - mid (t)   buy the favourite after fee [half1/half2]   "
          "buy the longshot after fee [half1/half2]")
    for lo, hi in ((0.50, 0.60), (0.60, 0.75), (0.75, 0.90), (0.90, 0.97), (0.50, 0.97)):
        k = mask & (fp >= lo) & (fp < hi) & (R["mid"] != 0.5)
        if k.sum() < 30:
            continue
        d = R["day"][k]
        vm = win[k] - fp[k]
        print(f"  {lo:.2f}-{hi:.2f}     {k.sum():7d}  {100 * vm.mean():+6.2f}c t {tstat(vm, d):+5.2f}        "
              f"{cell(favpnl[k], d, alldays)}   {cell(lngpnl[k], d, alldays)}")


def calibration_by_time(R, title, mask):
    alldays = sorted(set(R["day"][mask]))
    print(f"\n{title}: by time of day (New York; hourly events: minutes to their own close), three price bands; "
          "value-mid | YES after fee | NO after fee")
    for mins, label in TIMES:
        if (mask & (R["mins"] == mins)).sum() < 30:
            continue
        line = f"  {label}" if "hourly" not in title else f"  {mins:2d} min"
        for lo, hi in ((0.03, 0.25), (0.25, 0.75), (0.75, 0.97)):
            k = mask & (R["mins"] == mins) & (R["mid"] >= lo) & (R["mid"] < hi)
            if k.sum() < 30:
                line += f" | {lo:.2f}-{hi:.2f} n<30" + " " * 37
                continue
            d = R["day"][k]
            vm = R["v"][k] - R["mid"][k]
            line += (f" | {lo:.2f}-{hi:.2f} n {k.sum():5d} {100 * vm.mean():+5.1f}c (t {tstat(vm, d):+4.1f})"
                     f" Y {100 * R['yes'][k].mean():+5.1f}c (t {tstat(R['yes'][k], d):+4.1f})"
                     f" N {100 * R['no'][k].mean():+5.1f}c (t {tstat(R['no'][k], d):+4.1f})")
        print(line)


# ------------------------------------------------------------------------- b, c. fair value, walk-forward
def fit_logit(X, y, off, ridge=1e-3, iters=30):
    """Logistic regression with an offset (Newton steps, tiny ridge): P = expit(off + X b)."""
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = expit(off + X @ b)
        g = X.T @ (y - p) - ridge * b
        H = (X * (p * (1 - p))[:, None]).T @ X + ridge * np.eye(X.shape[1])
        step = np.linalg.solve(H, g)
        b += step
        if np.abs(step).max() < 1e-8:
            break
    return b


def clip(p, e=0.005):
    return np.clip(p, e, 1 - e)


def walk_forward(R, mask, feats):
    """Fit on all earlier days, score the next day. Returns out-of-sample P(YES) (nan where not scored).
    "one" is an intercept: for "or above" contracts that is a bet on the direction of the index."""
    days = sorted(set(R["day"][mask]))
    off = logit(R["mid"])
    X = np.column_stack([np.ones(len(off)) if f == "one" else R[f] for f in feats])
    phat = np.full(len(off), np.nan)
    coefs = []
    for k in range(MIN_TRAIN, len(days)):
        tr = mask & (R["day"] < days[k])
        te = mask & (R["day"] == days[k])
        b = fit_logit(X[tr], R["v"][tr], off[tr])
        phat[te] = expit(off[te] + X[te] @ b)
        coefs.append(b)
    return phat, np.array(coefs), days[MIN_TRAIN:]


def logloss(p, v):
    p = clip(p, 1e-4)
    return -(v * np.log(p) + (1 - v) * np.log(1 - p))


def bets(R, mask, p, thr, once=True):
    """Take the better side when its edge after the fee is >= thr; at most one bet per market (the first)."""
    ey = p - R["ask"] - fee(R["ask"])
    en = (1 - p) - (1 - R["bid"]) - fee(R["bid"])
    side_yes = ey >= en
    edge = np.where(side_yes, ey, en)
    pnl = np.where(side_yes, R["yes"], R["no"])
    k = np.where(mask & np.isfinite(p) & (edge >= thr))[0]
    if once:
        k = k[np.argsort(-R["mins"][k], kind="stable")]      # earliest decision time first
        _, first = np.unique(R["tk"][k], return_index=True)
        k = k[np.sort(first)]
    return k, pnl[k], side_yes[k]


def bet_line(R, name, k, pnl, yes, testdays):
    if len(k) < 5:
        return f"  {name:<34} {len(k):5d} bets"
    d = R["day"][k]
    a, b = halves(pnl, d, testdays)
    by = {}
    for x, dd in zip(pnl, d):
        by[dd] = by.get(dd, 0) + x
    return (f"  {name:<34} {len(k):5d} bets {len(k) / len(testdays):5.1f}/day on {len(by):2d} of {len(testdays)} days"
            f"  {100 * pnl.mean():+6.2f}c/bet  t {tstat(pnl, d):+5.2f}  halves [{a:+5.1f} /{b:+5.1f}]"
            f"  YES share {yes.mean():.0%}  winning days {np.mean([x > 0 for x in by.values()]):.0%}")


def fair_value(R, src, fam="above"):
    p = R["p_" + src]
    base = (R["fam"] == fam) & np.isfinite(p) & (R["mid"] >= 0.03) & (R["mid"] <= 0.97)
    for lag in (5, 15, 60):
        base &= np.isfinite(R[f"mom{lag}_{src}"])
    R["gap"] = logit(clip(p)) - logit(R["mid"])
    days = sorted(set(R["day"][base]))
    print(f"\n=== fair-value model, index level from {src.upper()}, '{fam}' markets: {base.sum()} rows, "
          f"{len(set(R['tk'][base]))} markets, {len(days)} days ===")
    if len(days) < MIN_TRAIN + 5:
        print("  too few days")
        return
    # raw model vs market, all days (no fitting involved)
    d = R["day"][base]
    diff = logloss(R["mid"][base], R["v"][base]) - logloss(p[base], R["v"][base])
    print(f"  raw normal model: mean |model - mid| {100 * np.abs(p[base] - R['mid'][base]).mean():.1f}c; "
          f"log-loss gain over the mid {diff.mean():+.4f} (t {tstat(diff, d):+.2f}; negative = the market is better)")
    for thr in (0.03, 0.05):
        k, pnl, yes = bets(R, base, p, thr)
        print(bet_line(R, f"raw model, edge >= {int(thr * 100)}c (all days)", k, pnl, yes, days))
    # walk-forward
    R["lmid"] = logit(R["mid"])
    mom = [f"mom{lag}_{src}" for lag in (5, 15, 60)]
    if fam == "range":                # a bracket has no direction: intercept allowed, momentum has no fixed sign
        variants = [("intercept + logit(mid)", ["one", "lmid"]), ("b: + model gap", ["one", "lmid", "gap"])]
    else:                             # no intercept: every term changes sign when YES and NO are swapped
        variants = [("favourite-longshot only: logit(mid)", ["lmid"]),
                    ("b: logit(mid) + model gap", ["lmid", "gap"]),
                    ("c: logit(mid) + gap + momentum 5/15/60", ["lmid", "gap"] + mom),
                    ("momentum only", mom),
                    ("DIRECTION ONLY (intercept; a bet that the index keeps falling, see text)", ["one"])]
    for name, feats in variants:
        ph, coefs, testdays = walk_forward(R, base, feats)
        te = base & np.isfinite(ph)
        d = R["day"][te]
        gain = logloss(R["mid"][te], R["v"][te]) - logloss(ph[te], R["v"][te])
        ga, gb = halves(gain, d, testdays)
        print(f"\n  walk-forward {name}: {te.sum()} rows on {len(testdays)} test days; last coefficients "
              f"{np.round(coefs[-1], 3).tolist()}")
        print(f"    out-of-sample log-loss gain over Kalshi's mid {gain.mean():+.5f}  t {tstat(gain, d):+.2f}  "
              f"halves [{ga / 100:+.5f} / {gb / 100:+.5f}]   (positive = the model adds information)")
        for thr in (0.03, 0.05):
            k, pnl, yes = bets(R, te, ph, thr)
            print("  " + bet_line(R, f"edge after fee >= {int(thr * 100)}c", k, pnl, yes, testdays))


# ------------------------------------------------------------------------------------- d. arbitrage checks
def bracket_sums(events):
    print("\n=== d. bracket sums of the range events (every minute of the last 390 before the close) ===")
    print("  buy every bracket at the ask (pays exactly $1): cost = sum(ask + fee). Sell every bracket at the bid "
          "(= buy every NO): proceeds = sum(bid - fee).")
    for series in ("KXINX", "KXNASDAQ100"):
        evs = [e for e in events if e["series"] == series]
        costs, proc, sa, sb, nmin, narb_b, narb_s, days_b, days_s, best_b, best_s = [], [], [], [], 0, 0, 0, set(), set(), 9, 0
        evs = [e for e in evs if len(e["markets"]) >= 30]        # days for which the whole ladder was downloaded
        for e in evs:
            B = np.array([m["bid"] for m in e["markets"]])
            A = np.array([m["ask"] for m in e["markets"]])
            for i in range(WIN - 390, WIN - 1):
                a, b = A[:, i], B[:, i]
                if not (np.isfinite(a).all() and np.isfinite(b).all()):
                    continue
                nmin += 1
                # an ask of 1.00 means nobody offers: the full set cannot be bought
                buyable = (a < 1).all()
                c = float((a + fee(a)).sum()) if buyable else np.nan
                p = float((b - fee(b)).sum())
                sa.append(a.sum() if buyable else np.nan)
                sb.append(b.sum())
                costs.append(c)
                proc.append(p)
                if buyable and c < 1 - 1e-9:
                    narb_b += 1
                    days_b.add(e["day"])
                    best_b = min(best_b, c)
                if p > 1 + 1e-9:
                    narb_s += 1
                    days_s.add(e["day"])
                    best_s = max(best_s, p)
        sa, sb, costs, proc = map(np.array, (sa, sb, costs, proc))
        print(f"  {series}: {len(evs)} days with the whole ladder, {nmin} minutes with all 30 quotes; full set buyable in "
              f"{np.isfinite(sa).mean():.0%} of them")
        print(f"    sum of asks  mean {np.nanmean(sa):.3f}  5%..95% {np.nanpercentile(sa, 5):.3f}..{np.nanpercentile(sa, 95):.3f}"
              f"   with fees mean {np.nanmean(costs):.3f}  min {np.nanmin(costs):.3f}")
        print(f"    sum of bids  mean {sb.mean():.3f}  5%..95% {np.percentile(sb, 5):.3f}..{np.percentile(sb, 95):.3f}"
              f"   after fees mean {proc.mean():.3f}  max {proc.max():.3f}")
        print(f"    buy-all cost < $1 after fees: {narb_b} minutes on {len(days_b)} days (lowest cost {np.nanmin(costs):.3f});  "
              f"sell-all > $1 after fees: {narb_s} minutes on {len(days_s)} days (highest {proc.max():.3f})")
        print(f"    before fees: sum of asks < 1 in {np.nansum(sa < 1 - 1e-9)} minutes, sum of bids > 1 in "
              f"{(sb > 1 + 1e-9).sum()} minutes")


def ladder_checks(events):
    print("\n=== d2. 'or above' ladder: a higher strike bid above a lower strike's ask (buy YES low + NO high pays >= $1) ===")
    for series in ("KXINXU", "KXNASDAQ100U"):
        evs = [e for e in events if e["series"] == series]
        npair, narb, days, best = 0, 0, set(), 0.0
        for e in evs:
            ms = [m for m in e["markets"] if m["floor"] is not None]
            B, A = np.array([m["bid"] for m in ms]), np.array([m["ask"] for m in ms])
            for i in range(WIN - 390, WIN - 1, 5):
                for j in range(len(ms) - 1):
                    a, b = A[j, i], B[j + 1, i]                 # ask of the lower strike, bid of the next higher one
                    if not (np.isfinite(a) and np.isfinite(b)) or a >= 1 or b <= 0:
                        continue
                    npair += 1
                    gain = 1 - (a + fee(a)) - ((1 - b) + fee(b))
                    if gain > 1e-9:
                        narb += 1
                        days.add(e["day"])
                        best = max(best, gain)
        print(f"  {series}: {npair} neighbouring pairs x 5-minute snapshots, {narb} with a locked gain after fees "
              f"on {len(days)} days (best {100 * best:.1f}c)")
    print("\n=== d3. range bracket vs the same range built from two 'or above' strikes (5-minute snapshots) ===")
    print("  synthetic YES of [a, b) = YES above(a) + NO above(b) - $1. Arbitrage if a bracket's bid - fee exceeds "
          "the synthetic cost with fees, or the bracket's ask + fee is below what selling the synthetic yields.")
    for rs, us in (("KXINX", "KXINXU"), ("KXNASDAQ100", "KXNASDAQ100U")):
        ue = {e["day"]: e for e in events if e["series"] == us}
        n, n1, n2, days, best, gaps = 0, 0, 0, set(), 0.0, []
        for e in [e for e in events if e["series"] == rs]:
            u = ue.get(e["day"])
            if not u:
                continue
            byk = {round(m["floor"]): m for m in u["markets"] if m["floor"] is not None}
            for m in e["markets"]:
                if m["type"] != "between":
                    continue
                lo, hi = byk.get(round(m["floor"])), byk.get(round(m["cap"] + 0.011))
                if not lo or not hi:
                    continue
                for i in range(WIN - 390, WIN - 1, 5):
                    q = [m["bid"][i], m["ask"][i], lo["bid"][i], lo["ask"][i], hi["bid"][i], hi["ask"][i]]
                    if not np.isfinite(q).all() or min(q) <= 0 or max(q) >= 1:
                        continue
                    n += 1
                    buy_syn = lo["ask"][i] + fee(lo["ask"][i]) + (1 - hi["bid"][i]) + fee(hi["bid"][i]) - 1
                    sell_syn = lo["bid"][i] - fee(lo["bid"][i]) - hi["ask"][i] - fee(hi["ask"][i])
                    g1 = (m["bid"][i] - fee(m["bid"][i])) - buy_syn       # sell bracket, buy synthetic
                    g2 = sell_syn - (m["ask"][i] + fee(m["ask"][i]))      # buy bracket, sell synthetic
                    gaps.append((m["bid"][i] + m["ask"][i]) / 2 - ((lo["bid"][i] + lo["ask"][i]) / 2 - (hi["bid"][i] + hi["ask"][i]) / 2))
                    if max(g1, g2) > 1e-9:
                        n1 += g1 > 1e-9
                        n2 += g2 > 1e-9
                        days.add(e["day"])
                        best = max(best, g1, g2)
        gaps = np.array(gaps) if gaps else np.array([0.0])
        print(f"  {rs} vs {us}: {n} bracket x snapshot with all six quotes; mid gap mean {100 * gaps.mean():+.2f}c, "
              f"sd {100 * gaps.std():.2f}c; locked gain after fees in {n1} (sell bracket) + {n2} (buy bracket) "
              f"on {len(days)} days (best {100 * best:.1f}c)")


# ---------------------------------------------------------------------------------------------------- main
def main():
    events = [e for s in SERIES for e in load(s, hourly=None)]
    for s in SERIES:
        for daily in (True, False):
            ev = [e for e in events if e["series"] == s and e["daily"] == daily]
            if ev:
                vols = [sum(m["volume"] for m in e["markets"]) for e in ev]
                print(f"{s} {'16:00 events' if daily else 'hourly events'}: {len(ev)} events on {len({e['day'] for e in ev})} days "
                      f"{ev[0]['event'].split('-')[1][:7]}..{ev[-1]['event'].split('-')[1][:7]}, "
                      f"{sum(len(e['markets']) for e in ev)} markets, volume per event mean {np.mean(vols):,.0f} "
                      f"median {np.median(vols):,.0f} contracts")
    lev, sig = levels(events)
    for sym in ("GSPC", "NDX"):
        Ly, Li = lev["yahoo"][sym], lev["implied"][sym]
        ds = np.array([abs(Li[t] / Ly[t] - 1) for t in Li if t in Ly])
        print(f"{sym}: Yahoo 5-minute level on {len({t // 86400 for t in Ly})} days, Kalshi-implied level on "
              f"{len({t // 86400 for t in Li})} days; implied vs Yahoo: median |difference| {1e4 * np.median(ds):.1f} bp, "
              f"95% {1e4 * np.percentile(ds, 95):.1f} bp")
    for sym in ("GSPC", "NDX"):
        line = f"{sym}: index move from the decision time to the 16:00 close (Yahoo):"
        cl = {e["close"]: e["exp"] for e in events if INDEX[e["series"]] == sym and e["daily"] and e["exp"]}
        for mins, label in TIMES[::2]:
            r = np.array([math.log(x / lev["yahoo"][sym][c - mins * 60]) for c, x in sorted(cl.items())
                          if c - mins * 60 in lev["yahoo"][sym]])
            line += (f"  {label}: up on {(r > 0).mean():.0%} of {len(r)} days, mean {1e4 * r.mean():+.0f} bp "
                     f"(t {r.mean() / r.std(ddof=1) * math.sqrt(len(r)):+.1f})")
        print(line)
    R = rows(events, lev, sig)
    print(f"{len(R['v'])} market x time rows with a two-sided quote"
          + (" (NO liquidity filter: look-ahead selection on total volume)" if NO_FILTER else
             f" and volume before the decision time >= {PREVOL}"))
    daily = [e for e in events if e["daily"]]

    print("\n=== a. calibration ===")
    for fam in ("above", "hourly", "range"):
        for sym in ("GSPC", "NDX"):
            if ((R["fam"] == fam) & (R["sym"] == sym)).sum() > 100:
                calibration(R, f"{fam} / {sym}, all decision times", (R["fam"] == fam) & (R["sym"] == sym))
        if (R["fam"] == fam).sum() > 100:
            calibration(R, f"{fam}, both indices, all decision times", R["fam"] == fam)
            calibration_by_time(R, f"{fam}, both indices", R["fam"] == fam)
            if fam != "range":
                favourites(R, f"{fam}, both indices, all decision times", R["fam"] == fam)
                favourites(R, f"{fam}, both indices, 60 minutes or less to go", (R["fam"] == fam) & (R["mins"] <= 60))
    calibration(R, "above (16:00), both indices, 10:00-13:00", (R["fam"] == "above") & (R["mins"] >= 180))
    calibration(R, "above (16:00), both indices, 14:00-15:50", (R["fam"] == "above") & (R["mins"] < 180))

    print("\n=== b / c. fair-value model and momentum ===")
    for fam, src in (("above", "yahoo"), ("above", "implied"), ("hourly", "yahoo"), ("range", "yahoo")):
        if (R["fam"] == fam).sum() > 100:
            fair_value(R, src, fam)

    bracket_sums(daily)
    ladder_checks(daily)


if __name__ == "__main__":
    sys.exit(main())
