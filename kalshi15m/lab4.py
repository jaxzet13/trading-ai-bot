"""Lab 4: golden hunt on Kalshi markets beyond the 9 crypto 15-minute coins.

    nice -n 19 python -m kalshi15m lab4 survey      # what exists, how much history/volume
    nice -n 19 python -m kalshi15m lab4 download    # Kalshi candles + underlying 1-min prices
    nice -n 19 python -m kalshi15m lab4 models      # lab3 families on every testable 15-min series
    nice -n 19 python -m kalshi15m lab4 xmkt        # structural / cross-market families (crypto data)
    nice -n 19 python -m kalshi15m lab4 judge       # one strict bar over everything -> lab4_results.json

Protocol = lab3's, applied to new markets (fixed in code before any holdout number is computed):
 1. One common calendar cut for every series in a part: holdout = the most recent HOLDOUT_FRAC (25%) of
    the common span (rounded to whole days). Search window = common start .. cut, cut into 5 calendar
    folds. Series that started later than the common start are not used (too short) unless noted.
 2. Every lab3 family that does not need BTC/ETH reference prices, with lab3's grids, per series and
    pooled over similar series (all FX, all yields, ...) with one parameter set. Walk-forward: for folds
    2..5 the config with the best P&L on all earlier folds (>= 30 trades) trades that fold untouched.
 3. Shortlist = walk-forward P&L > 0, t >= 1.5, >= 50 trades, >= half of test folds profitable.
 4. Tune on the whole search window, freeze, run ONCE on the holdout; also one minute late.
 5. Strict bar = one-sided Bonferroni at 5% over every candidate (both parts) that reached the holdout.
 6. There is no live strategy on these markets, so the comparison is the CONTROL: lab3's fv_ref family
    (the live bell-curve fair-value model) re-tuned on the same search window, run on the same holdout.

Underlying prices are NOT the settlement source (Pyth): Dukascopy 1-minute BID candles (see data_fx).
For Dukascopy series the model's "strike" is the feed's own price at the market open (Pyth's opening
print is the real strike; the two venues' levels differ, returns agree), so x = log(price now / price
at open). Treasury yields use the inverted US T-bond CFD price as a proxy (yield up <=> bond down).
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import backtest as B
from . import data_fx as F
from . import lab3 as L3
from .strategies import MIN

LAB = F.DATA_DIR.parent / "lab"
OUT = LAB / "lab4_results.json"
PART_MODELS = LAB / "lab4_part_models.json"
PART_XMKT = LAB / "lab4_part_xmkt.json"
SURVEY = LAB / "lab4_survey15.json"
HOLDOUT_FRAC, N_FOLDS = 0.25, L3.N_FOLDS
MIN_DAYS = 20                   # a series needs this many days of data to be tested
MIN_MED_VOLUME = 100            # median contracts traded per market
MIN_PER_TRADE, MIN_PER_DAY = 0.10, 2.0   # "economically meaningful" at $10 a trade

FX = ["KXEURUSD15M", "KXUSDJPY15M", "KXGBPUSD15M", "KXAUDUSD15M", "KXUSDCAD15M", "KXUSDMXN15M"]
RATES = ["KX2YRRATE15M", "KX5YRRATE15M", "KX10YRRATE15M", "KX30YRRATE15M"]
INDEX = ["KXINX15M", "KXNDQ15M", "KXDJIA15M"]
METALS = ["KXGOLD15M", "KXSILVER15M", "KXCOPPER15M"]
ENERGY = ["KXWTI15M", "KXBRENT15M", "KXNATGAS15M"]
XCRYPTO = ["KXBCH15M", "KXADA15M", "KXTON15M"]
GROUPS_ALL = {"FX": FX, "RATES": RATES, "INDEX": INDEX, "METALS": METALS, "ENERGY": ENERGY, "XCRYPTO": XCRYPTO}
GROUP_NAMES = {"FX": "All FX pooled", "RATES": "All yields pooled", "INDEX": "All indices pooled",
               "METALS": "All metals pooled", "ENERGY": "All energy pooled", "XCRYPTO": "New crypto pooled"}
NAMES = {"KXEURUSD15M": "EUR/USD", "KXUSDJPY15M": "USD/JPY", "KXGBPUSD15M": "GBP/USD", "KXAUDUSD15M": "AUD/USD",
         "KXUSDCAD15M": "USD/CAD", "KXUSDMXN15M": "USD/MXN", "KX2YRRATE15M": "2Y yield", "KX5YRRATE15M": "5Y yield",
         "KX10YRRATE15M": "10Y yield", "KX30YRRATE15M": "30Y yield", "KXINX15M": "S&P 500", "KXNDQ15M": "Nasdaq-100",
         "KXDJIA15M": "Dow", "KXGOLD15M": "Gold", "KXSILVER15M": "Silver", "KXCOPPER15M": "Copper", "KXWTI15M": "WTI",
         "KXBRENT15M": "Brent", "KXNATGAS15M": "Nat gas", "KXBCH15M": "BCH", "KXADA15M": "ADA", "KXTON15M": "TON"}
RATE_PROXY = ("duka", "USTBONDTRUSD", 1e-3)      # inverted T-bond CFD as the yield proxy
SKIP_FAMILIES = {f for f, v in L3.FAMILIES.items() if v["needs_ref"]}   # need BTC/ETH reference prices
GROUPS: dict = {}                                 # testable members per group (filled by load4)

np.seterr(all="ignore")


def cname(s):
    if s in GROUP_NAMES:
        return GROUP_NAMES[s]
    return NAMES.get(s, s[2:-3] if s.startswith("KX") else s)


def _coins_of(scope):
    return GROUPS.get(scope, [scope])


# lab3's helpers look these up as module globals at call time: point them at lab4's scopes/names
L3._coins_of = _coins_of
L3.cname = cname


# =========================================================================== panel
def underlying(series):
    if series in RATES:
        return RATE_PROXY
    return F.UNDERLYING.get(series)


def anchor_own(series):
    return underlying(series)[0] == "duka"


def spot_path(series):
    return F.LDIR / f"{series}_spot.csv"


def build_panel4(series):
    """Same as backtest.build_panel, but from data_fx files; strike = feed price at the open for
    Dukascopy-priced series (see module doc)."""
    mk, cd, sp = F.load(series)
    mk = mk[(mk.close_ts - mk.open_ts) == 900].copy()
    spot = sp.drop_duplicates("ts").set_index("ts")["close"].sort_index()
    spot = spot.reindex(np.arange(spot.index.min(), spot.index.max() + 60, 60)).ffill()
    lr = np.log(spot).diff()
    vol60 = lr.rolling(60, min_periods=30).std()
    vol240 = lr.rolling(240, min_periods=120).std()
    at = lambda t: spot.reindex(np.asarray(t) - 60).to_numpy()
    if anchor_own(series):
        mk["kalshi_strike"] = mk.strike
        mk["strike"] = at(mk.open_ts)
    mk = mk[np.isfinite(mk.strike) & (mk.strike > 0)].reset_index(drop=True)
    n = len(mk)
    df = pd.DataFrame({
        "ticker": np.repeat(mk.ticker.to_numpy(), 14), "open_ts": np.repeat(mk.open_ts.to_numpy(), 14),
        "strike": np.repeat(mk.strike.to_numpy(), 14), "result": np.repeat(mk.result.to_numpy(), 14),
        "minute": np.tile(np.arange(1, 15), n)})
    df["series"] = series
    df["ts"] = df.open_ts + 60 * df.minute
    for c in ("ask_low", "bid_high", "trade_low", "trade_high"):
        if c not in cd.columns:
            cd[c] = np.nan
    q = cd[["ticker", "ts", "yes_bid", "yes_ask", "ask_low", "bid_high", "trade_low", "trade_high", "volume"]]
    df = df.merge(q.drop_duplicates(["ticker", "ts"]), on=["ticker", "ts"], how="left")
    df["spot"] = at(df.ts)
    df["vol1m"] = vol60.reindex(df.ts - 60).to_numpy()
    df["vol240"] = vol240.reindex(df.ts - 60).to_numpy()
    p_prev0, p_open = at(df.open_ts - 900), at(df.open_ts)
    df["prev_ret"] = p_open / p_prev0 - 1
    df["ret_from_open"] = df.spot / p_open - 1
    bad = (df.yes_bid <= 0) | (df.yes_ask >= 1) | df.yes_ask.isna() | df.yes_bid.isna()
    df.loc[bad, ["yes_bid", "yes_ask"]] = np.nan
    df["no_ask"] = 1 - df.yes_bid
    df = df.sort_values(["open_ts", "minute"]).reset_index(drop=True)
    # drop markets that never had a two-sided quote (nothing to trade)
    has = df.groupby("ticker").yes_ask.transform(lambda s: s.notna().any())
    return df[has].reset_index(drop=True), mk


def fidelity(series, mk, sp_close):
    """How often the feed's own 15-minute move has the same sign as Kalshi's settlement."""
    at = lambda t: sp_close.reindex(np.asarray(t) - 60).to_numpy()
    o, c = at(mk.open_ts), at(mk.close_ts)
    up = c >= o
    ok = np.isfinite(o) & np.isfinite(c) & (c != o)
    if ok.sum() == 0:
        return None
    return round(float((up[ok] == (mk.result.to_numpy()[ok] == 1)).mean()), 4)


# =========================================================================== load + split
def testable_list(verbose=True):
    sv = json.loads(SURVEY.read_text()) if SURVEY.exists() else {}
    out, why = [], {}
    for s in sum(GROUPS_ALL.values(), []):
        r = sv.get(s, {})
        if not r.get("markets"):
            why[s] = "no settled markets on Kalshi"
        elif r.get("span_days", 0) < MIN_DAYS:
            why[s] = f"only {r.get('span_days')} days of markets (< {MIN_DAYS})"
        elif r.get("median_volume", 0) < MIN_MED_VOLUME:
            why[s] = f"too thin: median {r.get('median_volume')} contracts per market (< {MIN_MED_VOLUME})"
        elif underlying(s) is None:
            why[s] = "no free 1-minute price history for the underlying"
        elif not (F.LDIR / f"{s}_candles.part.csv").exists() or not spot_path(s).exists():
            why[s] = "not downloaded"
        else:
            out.append(s)
            why[s] = "testable"
    return out, why


def load4(series_list, verbose=True):
    full, info = {}, {}
    for s in series_list:
        L3._SPOT[(s, "main")] = L3.Spot(spot_path(s))
        df, mk = build_panel4(s)
        if df.empty:
            continue
        p = B.Panel(df)
        L3.add_features(p, s, "main")
        full[s] = p
        sp = pd.read_csv(spot_path(s)).drop_duplicates("ts").set_index("ts")["close"].sort_index()
        sp = sp.reindex(np.arange(sp.index.min(), sp.index.max() + 60, 60)).ffill()
        info[s] = {"mk": mk, "sp": sp}
        if verbose:
            print(f"  {s}: {len(p)} markets {pd.to_datetime(p.open_ts.min(), unit='s'):%m-%d}.."
                  f"{pd.to_datetime(p.open_ts.max(), unit='s'):%m-%d}", flush=True)
    return full, info


def split(full):
    start = int(max(p.open_ts.min() for p in full.values()))
    end = int(min(p.open_ts.max() for p in full.values()))
    hdays = max(5, int(round(HOLDOUT_FRAC * (end - start) / 86400)))
    cut = end - hdays * 86400
    cut = cut - cut % 900
    L3.G.update({"search": {}, "hold": {}, "arch": {}, "start": start, "cut": cut, "quick": L3.G.get("quick", 0)})
    for s, p in full.items():
        ots = np.asarray(p.open_ts, np.int64)
        sm = (ots >= start) & (ots < cut)
        sp_ = p.subset(sm)
        fold = np.clip(((np.asarray(sp_.open_ts, np.int64) - start) * N_FOLDS) // (cut - start), 0, N_FOLDS - 1)
        L3.G["search"][s] = L3.Ctx(s, sp_, fold.astype(int))
        L3.G["hold"][s] = L3.Ctx(s, p.subset(ots >= cut))
        older = ots < start - 900
        if older.sum() >= 7 * 50:                    # a week+ of older data -> blind archive test
            L3.G["arch"][s] = L3.Ctx(s, p.subset(older))
    return start, cut, hdays


# =========================================================================== final exam
def _wsum(df):
    if df is None or len(df) == 0:
        return {}
    w = (df.ts - 60 * df.minute) // 900 * 900          # window = market open time
    return {int(k): float(v) for k, v in df.groupby(w).pnl.sum().items()}


def _final4(cand):
    """lab3._final_task plus per-series split, per-window sums (for paired tests) and daily t."""
    rule, scope = cand["rule"], cand["scope"]
    norms = L3._sized_norms(rule, scope) if rule.get("family") == "sized" else None
    hold = L3.run_rule("hold", scope, rule, norms=norms)
    d1 = L3.run_rule("hold", scope, rule, delay=1, norms=norms)
    arch_coins = [c for c in _coins_of(scope) if c in L3.G["arch"]]
    arch = L3.run_rule("arch", scope, rule, norms=norms) if arch_coins else None
    h = L3.summ(hold)
    if len(hold):
        daily = hold.groupby(hold.ts // 86400).pnl.sum()
        h["t_by_day"] = L3._tser(daily.values)
        h["t_by_window"] = L3._tser(list(_wsum(hold).values()))
        h["days"] = int(len(daily))
    out = {"holdout": h, "curve": L3.curve(hold),
           "delay1": {k: v for k, v in L3.summ(d1).items() if k in ("pnl", "t", "trades")},
           "archive": None if arch is None else {**L3.summ(arch), "coins": [cname(c) for c in arch_coins]},
           "holdout_by_coin": ({cname(c): round(float(g.pnl.sum()), 2) for c, g in hold.groupby("series")}
                               if scope in GROUPS and len(hold) else None),
           "_wsum": _wsum(hold)}
    return cand["id"], out


def control_rule(WF, scope):
    w = WF.get(("fv_ref", scope))
    if not w or w["final"] is None:
        return None
    return {"family": "fv_ref", "params": L3.grid_list(L3.FAMILIES["fv_ref"]["grid"])[w["final"]]}


# =========================================================================== part 1: lab3 families
def models(workers=2, quick=0, families=None):
    t0 = time.time()
    L3.G["quick"] = quick or 0
    L3._GRID_CACHE.clear()
    try:
        os.nice(19)
    except OSError:
        pass
    ser, why = testable_list()
    print(f"lab4 models: testable {ser}", flush=True)
    full, info = load4(ser)
    for g, mem in GROUPS_ALL.items():
        m = [s for s in mem if s in full]
        if len(m) >= 2:
            GROUPS[g] = m
    start, cut, hdays = split(full)
    fams = [f for f in L3.FAMILIES if f not in SKIP_FAMILIES and (not families or f in families)]
    if "fv_ref" not in fams:
        fams = ["fv_ref"] + fams
    series = list(full)
    print(f"search {pd.to_datetime(start, unit='s')} .. {pd.to_datetime(cut, unit='s')}, holdout {hdays} days; "
          f"{len(fams)} families, {sum(len(L3.grid_list(L3.FAMILIES[f]['grid'])) for f in fams)} configs per series "
          f"({time.time() - t0:.0f}s)", flush=True)
    L3.COINS = series                                  # used by lab3 helpers that iterate 'all coins'
    tasks = sorted([(f, c) for f in fams for c in series], key=lambda t: -len(L3.grid_list(L3.FAMILIES[t[0]]["grid"])))
    AGG = {}
    for fam, coin, agg in L3._pmap(L3._search_task, tasks, workers, "search"):
        AGG[(fam, coin)] = agg
    for fam in fams:
        for g, mem in GROUPS.items():
            AGG[(fam, g)] = sum(AGG[(fam, c)] for c in mem)
    print(f"search done ({time.time() - t0:.0f}s)", flush=True)
    scopes = series + list(GROUPS)
    WF, cands = {}, []
    for fam in fams:
        cfgs = L3.grid_list(L3.FAMILIES[fam]["grid"])
        for sc in scopes:
            w = L3.walk(AGG[(fam, sc)])
            WF[(fam, sc)] = w
            if L3.shortlisted(w):
                cands.append({"id": f"{fam}:{sc}", "family": fam, "scope": sc, "execution": L3._exec(fam),
                              "rule": {"family": fam, "params": cfgs[w["final"]]},
                              "search": {**w["oos"], "insample": w["final_search"]}})
    for g, mem in GROUPS.items():                     # per-series tuning with shrinkage, per group
        w = L3.walk_pertune({c: AGG[("fv_ref", c)] for c in mem})
        WF[("pertune", g)] = w
        cfgs = L3.grid_list(L3.FAMILIES["fv_ref"]["grid"])
        if L3.shortlisted(w):
            cands.append({"id": f"pertune:{g}", "family": "pertune", "scope": g, "execution": "taker",
                          "rule": {"family": "fv_ref", "per_coin": True, "params": {c: cfgs[i] for c, i in w["final"].items()}},
                          "search": {**w["oos"], "insample": None}})
    for sc in scopes:                                  # ensembles of the best survivors (search only)
        surv = sorted([c for c in cands if c["scope"] == sc and L3.FAMILIES.get(c["family"], {}).get("single")],
                      key=lambda c: -c["search"]["t"])[:3]
        if len(surv) < 2:
            continue
        w = L3.walk_ens(sc, [s["family"] for s in surv], WF)
        WF[("ens_best", sc)] = w
        if L3.shortlisted(w):
            cands.append({"id": f"ens_best:{sc}", "family": "ens_best", "scope": sc, "execution": "taker",
                          "rule": {"members": [s["rule"] for s in surv]}, "search": {**w["oos"], "insample": None}})
    print(f"shortlist: {len(cands)} candidates reach the holdout ({time.time() - t0:.0f}s)", flush=True)
    for c in sorted(cands, key=lambda c: -c["search"]["t"]):
        s = c["search"]
        print(f"  {c['id']:32s} WF ${s['pnl']:>9} n={s['trades']:>5} t={s['t']:>5} folds+={s['fold_win']}", flush=True)
    # controls: fv_ref tuned on the search window for every scope, run on the holdout as the baseline
    ctrl = []
    for sc in scopes:
        r = control_rule(WF, sc)
        if r:
            ctrl.append({"id": f"control:{sc}", "family": "fv_ref", "scope": sc, "rule": r})
    # ------------------------------------------------------------------ holdout, once
    res = dict(L3._pmap(_final4, cands + ctrl, workers, "final"))
    for c in cands:
        c.update(res[c["id"]])
    baselines = []
    for c in ctrl:
        r = res[c["id"]]
        baselines.append({"id": c["id"], "label": f"{cname(c['scope'])} · control: live model re-tuned on the search window",
                          "scope": c["scope"], "strategy": "fv_ref", "execution": "taker", "params": c["rule"]["params"],
                          "holdout": r["holdout"], "curve": r["curve"], "delay1": r["delay1"], "_wsum": r["_wsum"],
                          "search_wf": WF[("fv_ref", c["scope"])]["oos"]})
    fam_rows = []
    for fam in fams + ["pertune", "ens_best"]:
        mine = [c for c in cands if c["family"] == fam]
        if fam in L3.FAMILIES:
            name, idea, ncfg = L3.FAMILIES[fam]["name"], L3.FAMILIES[fam]["idea"], len(L3.grid_list(L3.FAMILIES[fam]["grid"]))
        else:
            name, idea = L3.EXTRA_FAMILIES[fam]
            ncfg = len(L3.grid_list(L3.FAMILIES["fv_ref"]["grid"])) if fam == "pertune" else None
        wf = {sc: WF[(fam, sc)]["oos"] for sc in scopes if (fam, sc) in WF}
        fam_rows.append({"id": fam, "name": name, "idea": idea, "configs": ncfg, "scopes_tested": len(wf),
                         "shortlisted": len(mine), "best_search_t": max([v["t"] for v in wf.values()], default=None),
                         "walk_forward": {cname(s): v for s, v in wf.items()}})
    heats = []
    for fam in fams:
        if not L3.FAMILIES[fam]["heat"]:
            continue
        mine = [c for c in cands if c["family"] == fam]
        if not mine:
            continue
        best = max(mine, key=lambda c: c["search"]["t"])      # chosen by SEARCH t (not holdout)
        h = L3.heatmap(fam, best["scope"], WF[(fam, best["scope"])]["final"], AGG[(fam, best["scope"])])
        if h:
            heats.append(h)
    heats = sorted(heats, key=lambda h: -max([v for r in h["z"] for v in r if v is not None], default=-9))[:6]
    coins = {}
    for s in series:
        mk, sp = info[s]["mk"], info[s]["sp"]
        sm = mk[mk.open_ts < cut]
        coins[s] = {"name": cname(s), "markets": len(full[s]), "search_markets": len(L3.G["search"][s]),
                    "holdout_markets": len(L3.G["hold"][s]),
                    "archive_markets": len(L3.G["arch"][s]) if s in L3.G["arch"] else 0,
                    "underlying": "/".join(str(x) for x in underlying(s)[:2]),
                    "strike_anchor": "feed price at open" if anchor_own(s) else "Kalshi strike",
                    "feed_sign_agreement_search": fidelity(s, sm, sp)}
    part = {"generated": int(time.time()), "runtime_s": int(time.time() - t0), "start": start, "cut": cut,
            "holdout_days": hdays, "families": fam_rows, "candidates": cands, "baselines": baselines,
            "heatmaps": heats, "coins": coins, "groups": GROUPS, "why": why,
            "n_grid": sum(len(L3.grid_list(L3.FAMILIES[f]["grid"])) for f in fams), "n_scopes": len(scopes),
            "n_walk_forwards": len(WF), "quick": quick}
    PART_MODELS.write_text(json.dumps(part, default=L3._jd))
    print(f"models part done in {time.time() - t0:.0f}s -> {PART_MODELS}", flush=True)
    for c in sorted(cands, key=lambda c: -c["holdout"]["t"])[:30]:
        h = c["holdout"]
        print(f"  {c['id']:32s} ${h['pnl']:>8} n={h['trades']:>5} t={h['t']:>5} d1 t={c['delay1']['t']}", flush=True)
    return part
