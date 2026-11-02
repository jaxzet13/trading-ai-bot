"""Lab 2: blind tests of the frozen fair_value rule on never-used data, plus a small,
pre-registered set of improvements tuned only on the old search window.

    python -m kalshi15m lab2 download-archive   # Kalshi archive (Apr-Sep 2026) -> data/kalshi15m/archive/
    python -m kalshi15m lab2 download-fresh     # markets settled after the old holdout -> data/kalshi15m/fresh/
    python -m kalshi15m lab2 probe              # which other 15-min series exist now
    python -m kalshi15m lab2 run                # all tests -> data/lab/lab2_results.json

Nothing here touches the files used by the live bot / dashboard (data/kalshi15m/{series}_*.csv).

FROZEN RULE (written down before looking at any archive / fresh data):
    fair_value, taker, start=2, end=13, edge=0.12, vol_mult=1.0, min_price=0.05, max_price=0.95,
    $10 per trade. Pass = P&L > 0 and t >= 2.
"""
from __future__ import annotations

import json
import math
import sys
import time
from contextlib import contextmanager
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import backtest as B
from . import data as D
from .strategies import MIN, _first, _valid, fair_value, ndtr

ARCH = D.DATA_DIR / "archive"
FRESH = D.DATA_DIR / "fresh"
OUT = D.DATA_DIR.parent / "lab"
STAKE = 10.0
FROZEN = {"start": 2, "end": 13, "edge": 0.12, "vol_mult": 1.0}
SEARCH_END = 1792195200        # 2026-10-17 00:00 UTC: old search window ends / old holdout starts
SINCE = "2026-04-01"
ARCHIVE_PLAN = [("KXNEAR15M", 2), ("KXBNB15M", 2), ("KXXRP15M", 3), ("KXDOGE15M", 3)]
EXTRA_SERIES = {"KXDOGE15M": "DOGE-USD", "KXADA15M": "ADA-USD", "KXBCH15M": "BCH-USD",
                "KXZEC15M": "ZEC-USD", "KXTON15M": None}
PRODUCT = {**D.SERIES, **EXTRA_SERIES}


# =========================================================================== downloads
def download_archive(plan=ARCHIVE_PLAN, rate=2.8):
    ARCH.mkdir(parents=True, exist_ok=True)
    since_ts = int(pd.Timestamp(SINCE, tz="UTC").timestamp())
    for series, every in plan:
        mpath = ARCH / f"{series}_markets.csv"
        allm = ARCH / f"{series}_markets_all.csv"
        if allm.exists():
            mh = pd.read_csv(allm)
        else:
            mh = D.fetch_markets_hist(series, since_ts)
            mh.to_csv(allm, index=False)
        # keep the archive disjoint from anything used before (the recent files start ~Aug 31)
        used = D.DATA_DIR / f"{series}_markets.csv"
        if used.exists():
            u = pd.read_csv(used, usecols=["ticker", "open_ts"])
            mh = mh[~mh.ticker.isin(u.ticker) & (mh.open_ts < u.open_ts.min())]
        mh = mh.sort_values("open_ts").iloc[::every].reset_index(drop=True)
        mh.to_csv(mpath, index=False)
        part = ARCH / f"{series}_candles.part.csv"
        print(f"{series}: {len(mh)} archive markets (every {every})", flush=True)
        D.fetch_candles_hist(series, mh, part, workers=4, rate=rate)
        spath = ARCH / f"{series}_spot.csv"
        if not spath.exists():
            lo, hi = int(mh.open_ts.min()) - 5 * 3600, int(mh.close_ts.max()) + 120
            sp = D.fetch_spot(PRODUCT[series], lo, hi)
            sp.to_csv(spath, index=False)
            print(f"  {series}: {len(sp)} spot bars", flush=True)


def download_fresh(series_list=None, days=3):
    """Markets settled after each coin's last market in the files used so far."""
    FRESH.mkdir(parents=True, exist_ok=True)
    for series in series_list or list(D.SERIES):
        used = D.DATA_DIR / f"{series}_markets.csv"
        last = int(pd.read_csv(used, usecols=["open_ts"]).open_ts.max()) if used.exists() else 0
        mk = D.fetch_markets(series, days)
        mk = mk[mk.open_ts > last].reset_index(drop=True)
        if mk.empty:
            print(f"{series}: no new markets")
            continue
        cd = D.fetch_candles(series, mk)
        sp = D.fetch_spot(PRODUCT[series], int(mk.open_ts.min()) - 5 * 3600, int(mk.close_ts.max()) + 120)
        mk.to_csv(FRESH / f"{series}_markets.csv", index=False)
        cd.to_csv(FRESH / f"{series}_candles.csv", index=False)
        sp.to_csv(FRESH / f"{series}_spot.csv", index=False)
        print(f"{series}: {len(mk)} fresh markets {pd.to_datetime(mk.open_ts.min(), unit='s')} .. "
              f"{pd.to_datetime(mk.open_ts.max(), unit='s')}")


def probe(series_list=("KXADA15M", "KXBCH15M", "KXTON15M", "KXZEC15M")):
    out = {}
    for s in series_list:
        o = D._get(f"{D.KALSHI}/markets", {"series_ticker": s, "status": "open", "limit": 100})
        try:
            st = D.fetch_markets(s, 62)
        except KeyError:  # no settled markets
            st = pd.DataFrame(columns=["open_ts"])
        try:
            h = D._get(f"{D.KALSHI}/historical/markets", {"series_ticker": s, "limit": 5})
            nh = len(h.get("markets", []))
        except Exception:
            nh = -1
        out[s] = {"open": len(o.get("markets", [])), "settled_62d": len(st),
                  "first": str(pd.to_datetime(st.open_ts.min(), unit="s")) if len(st) else None,
                  "last": str(pd.to_datetime(st.open_ts.max(), unit="s")) if len(st) else None,
                  "archive_sample": nh}
        print(s, out[s], flush=True)
    return out


# =========================================================================== panels
@contextmanager
def _source(folder, candles_name="candles"):
    old = B.load

    def load(series):
        mk = pd.read_csv(folder / f"{series}_markets.csv")
        cd = pd.read_csv(folder / f"{series}_{candles_name}.csv")
        sp = pd.read_csv(folder / f"{series}_spot.csv")
        return mk[mk.ticker.isin(cd.ticker)].reset_index(drop=True), cd, sp
    B.load = load
    try:
        yield
    finally:
        B.load = old


def panel(series, where="search"):
    """where: 'search' (the files used so far, < SEARCH_END), 'oldhold' (>= SEARCH_END in the same files),
    'archive', 'fresh'."""
    if where in ("search", "oldhold", "used"):
        p = B.Panel(B.build_panel(series))
        if where == "search":
            p = p.subset(p.open_ts < SEARCH_END)
        elif where == "oldhold":
            p = p.subset(p.open_ts >= SEARCH_END)
    elif where == "archive":
        with _source(ARCH, "candles.part"):
            p = B.Panel(B.build_panel(series))
    else:
        with _source(FRESH):
            p = B.Panel(B.build_panel(series))
    _extras(p)
    return p


def _extras(p):
    """Extra fields the variants need: EWMA vol and 1/2-minute spot moves (all known at that minute)."""
    pass  # filled lazily by the variant functions from P["spot"]; kept for clarity


def delayed(fn, lag=1):
    """Decide at minute m, fill at the ask of minute m+lag (models a slow bot)."""
    def wrapped(P, **kw):
        side, minute = fn(P, **kw)
        m2 = minute + lag
        side = np.where(m2 <= 14, side, 0)
        return side, np.minimum(m2, 14)
    return wrapped


# =========================================================================== variants
def _ewma_vol(P, lam):
    """Per-market vol estimate: start from the trailing-60m vol at minute 1, then EWMA-update with
    each in-market 1-minute log return as it becomes known (no look-ahead)."""
    v0 = P["vol1m"][:, 0] ** 2
    r = np.full(P["spot"].shape, np.nan)
    r[:, 1:] = np.log(P["spot"][:, 1:] / P["spot"][:, :-1])
    var = np.empty_like(r)
    cur = v0.copy()
    for j in range(14):
        rj = r[:, j]
        ok = np.isfinite(rj) & np.isfinite(cur)
        cur = np.where(ok, lam * cur + (1 - lam) * rj ** 2, cur)
        var[:, j] = cur
    return np.sqrt(var)


def _prob(P, vol):
    tau = 15 - MIN[None, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        return ndtr(np.log(P["spot"] / P["strike"]) / (vol * np.sqrt(tau)))


def fv_x(P, start=2, end=13, edge=0.12, vol="60", rel_edge=None, recent=None, recent_k=0.5,
         min_price=0.05, max_price=0.95, min_vol_ratio=None):
    """Generalised fair_value. vol: '60' | 'blend' | 'ewma90' | 'max'.
    rel_edge: also require gap/price >= rel_edge.  recent: require the model's probability to have moved by
    >= recent_k x edge in the last `recent` minutes in the direction of the trade (spot moved, quote lagged)."""
    v = {"60": P["vol1m"], "blend": np.sqrt((P["vol1m"] ** 2 + P["vol240"] ** 2) / 2),
         "max": np.fmax(P["vol1m"], P["vol240"])}.get(vol)
    if v is None:
        v = _ewma_vol(P, float(vol.replace("ewma", "")) / 100)
    p = _prob(P, v)
    ya, na = P["yes_ask"], P["no_ask"]
    ok = np.isfinite(p) & ((MIN >= start) & (MIN <= end))[None, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        gy, gn = p - ya, (1 - p) - na
        y = ok & _valid(ya) & (ya >= min_price) & (ya <= max_price) & (gy >= edge)
        n = ok & _valid(na) & (na >= min_price) & (na <= max_price) & (gn >= edge)
        if rel_edge is not None:
            y &= gy / ya >= rel_edge
            n &= gn / na >= rel_edge
        if recent:
            dp = np.full_like(p, np.nan)
            dp[:, recent:] = p[:, recent:] - p[:, :-recent]
            y &= dp >= recent_k * edge
            n &= -dp >= recent_k * edge
        if min_vol_ratio is not None:
            r = P["vol1m"] / P["vol240"]
            y &= r >= min_vol_ratio
            n &= r >= min_vol_ratio
    return _first(y, n)


# Pre-registered variant list (fixed before tuning; each is tried on the search window only).
VARIANTS = {
    "frozen":           {},
    "end11":            {"end": 11},
    "vol_blend":        {"vol": "blend"},
    "vol_max":          {"vol": "max"},
    "vol_ewma90":       {"vol": "ewma90"},
    "vol_ewma80":       {"vol": "ewma80"},
    "rel30":            {"rel_edge": 0.30},
    "rel50":            {"rel_edge": 0.50},
    "recent1":          {"recent": 1, "recent_k": 0.5},
    "recent2":          {"recent": 2, "recent_k": 0.5},
    "recent1_full":     {"recent": 1, "recent_k": 1.0},
    "edge10":           {"edge": 0.10},
    "edge15":           {"edge": 0.15},
    "price15_85":       {"min_price": 0.15, "max_price": 0.85},
    "price25_75":       {"min_price": 0.25, "max_price": 0.75},
    "recent1_end11":    {"recent": 1, "recent_k": 0.5, "end": 11},
}


# =========================================================================== reporting
def tstat(pnl):
    pnl = np.asarray(pnl, float)
    if len(pnl) < 3 or pnl.std(ddof=1) == 0:
        return 0.0
    return float(pnl.mean() / (pnl.std(ddof=1) / math.sqrt(len(pnl))))


def summarize(tr, monthly=False):
    m = B.metrics(tr)
    out = {k: m[k] for k in ("trades", "pnl", "t_stat", "win_rate", "roi", "avg_price", "max_dd")}
    if len(tr):
        out["per_trade"] = round(m["pnl"] / m["trades"], 3)
        if monthly:
            mo = pd.to_datetime(tr.ts, unit="s").dt.strftime("%Y-%m")
            g = tr.groupby(mo).pnl
            out["monthly"] = {k: {"pnl": round(float(v.sum()), 2), "trades": int(len(v)), "t": round(tstat(v), 2)}
                              for k, v in g}
        out["passed"] = bool(m["pnl"] > 0 and m["t_stat"] >= 2)
    return out


def _run(p, fn, lag=0, **kw):
    f = delayed(fn, lag) if lag else fn
    return B.run(p, f, stake=STAKE, execution="taker", **kw)


def run_all(fresh_series=None):
    t0 = time.time()
    res = {"generated": int(time.time()), "frozen_rule": {"strategy": "fair_value", "execution": "taker",
                                                         "stake": STAKE, **FROZEN},
           "pass_rule": "pnl > 0 and t >= 2"}
    arch_series = [s for s, _ in ARCHIVE_PLAN if (ARCH / f"{s}_candles.part.csv").exists()
                   and (ARCH / f"{s}_spot.csv").exists()]
    fresh_series = fresh_series or sorted(p.name.replace("_markets.csv", "") for p in FRESH.glob("*_markets.csv"))
    panels = {}
    # ---------------------------------------------------------------- 1. archive, frozen rule
    res["archive"] = {}
    for s in arch_series:
        p = panels[("archive", s)] = panel(s, "archive")
        r = {"markets": len(p), "from": str(pd.to_datetime(p.open_ts.min(), unit="s")),
             "to": str(pd.to_datetime(p.open_ts.max(), unit="s")),
             "frozen": summarize(_run(p, fair_value, **FROZEN), monthly=True),
             "frozen_delay1": summarize(_run(p, fair_value, lag=1, **FROZEN), monthly=True)}
        res["archive"][s] = r
        print(f"ARCHIVE {s}: {r['markets']} mkts  frozen ${r['frozen'].get('pnl')} n={r['frozen'].get('trades')} "
              f"t={r['frozen'].get('t_stat')} | delay1 ${r['frozen_delay1'].get('pnl')} t={r['frozen_delay1'].get('t_stat')}",
              flush=True)
    # ---------------------------------------------------------------- 2. fresh, frozen rule
    res["fresh"] = {}
    for s in fresh_series:
        try:
            p = panels[("fresh", s)] = panel(s, "fresh")
        except Exception as e:
            print(f"FRESH {s}: {e}")
            continue
        r = {"markets": len(p), "from": str(pd.to_datetime(p.open_ts.min(), unit="s")),
             "to": str(pd.to_datetime(p.open_ts.max(), unit="s")),
             "frozen": summarize(_run(p, fair_value, **FROZEN)),
             "frozen_delay1": summarize(_run(p, fair_value, lag=1, **FROZEN))}
        res["fresh"][s] = r
        print(f"FRESH {s}: {r['markets']} mkts  frozen ${r['frozen'].get('pnl')} n={r['frozen'].get('trades')} "
              f"t={r['frozen'].get('t_stat')}", flush=True)
    # ---------------------------------------------------------------- 3. variants on the search window only
    design = ["KXNEAR15M", "KXHYPE15M", "KXBNB15M"]   # thin coins the rule is aimed at
    res["variants_search"] = {}
    for s in design:
        p = panels[("search", s)] = panel(s, "search")
        for name, kw in VARIANTS.items():
            tr = _run(p, fv_x, **{**FROZEN_X, **kw})
            res["variants_search"].setdefault(name, {})[s] = summarize(tr)
    for name, d in res["variants_search"].items():
        tot = sum(v.get("pnl", 0) for v in d.values())
        ts = [v.get("t_stat", 0) for v in d.values()]
        d["_pooled_pnl"] = round(tot, 2)
        print(f"SEARCH {name:15s} " + "  ".join(f"{s[2:-3]} ${v.get('pnl')} t={v.get('t_stat')}"
                                                 for s, v in d.items() if not s.startswith("_")), flush=True)
    res["n_variants_tried"] = len(VARIANTS) - 1
    res["runtime_s"] = int(time.time() - t0)
    return res, panels


FROZEN_X = {"start": 2, "end": 13, "edge": 0.12, "vol": "60"}
# Chosen 2026-11-02 20:08 UTC from the search-window table ONLY (before any archive/fresh data was read):
#   rel30        best pooled search P&L of the 15 variants (NEAR+HYPE+BNB $11,332 vs frozen $11,177)
#   recent1_full best pooled t / per-trade P&L (BNB t 6.5, HYPE 5.1, NEAR 2.3; fewer trades)
CANDIDATES = ["rel30", "recent1_full"]


def judge(res, panels, candidates=None):
    """Run the pre-registered candidates ONCE on the blind sets (archive, fresh) and, for reference,
    the old holdout (used to pick the frozen rule, never used for the variants)."""
    candidates = candidates or CANDIDATES
    n_tests = len(VARIANTS) - 1
    res["t_bar_bonferroni"] = round(NormalDist().inv_cdf(1 - 0.05 / n_tests), 2)
    res["candidates"] = {}
    for name in ["frozen"] + candidates:
        kw = {**FROZEN_X, **VARIANTS[name]}
        out = {"params": kw}
        for (where, s), p in panels.items():
            if where == "search":
                continue
            tr = _run(p, fv_x, **kw)
            r = summarize(tr, monthly=(where == "archive"))
            r["delay1"] = summarize(_run(p, fv_x, lag=1, **kw))
            out.setdefault(where, {})[s] = r
        res["candidates"][name] = out
        for where in ("archive", "fresh", "oldhold"):
            print(f"CAND {name:13s} {where:8s} " + "  ".join(
                f"{s[2:-3]} ${v.get('pnl')} n={v.get('trades')} t={v.get('t_stat')}" for s, v in out.get(where, {}).items()),
                flush=True)
    return res


def main(argv):
    cmd = argv[0] if argv else "run"
    if cmd == "download-archive":
        plan = ARCHIVE_PLAN
        if len(argv) > 1:
            plan = [(x.split(":")[0], int(x.split(":")[1])) for x in argv[1:]]
        download_archive(plan)
    elif cmd == "download-fresh":
        download_fresh(argv[1:] or None)
    elif cmd == "probe":
        print(json.dumps(probe(), indent=1))
    elif cmd == "run":
        res, panels = run_all()
        for s in ("KXNEAR15M", "KXHYPE15M", "KXBNB15M"):
            panels[("oldhold", s)] = panel(s, "oldhold")
        judge(res, panels)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "lab2_results.json").write_text(json.dumps(res, indent=1, default=str))
        print(f"-> {OUT / 'lab2_results.json'}")


if __name__ == "__main__":
    main(sys.argv[1:])
