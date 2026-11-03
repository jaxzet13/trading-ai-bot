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


# =========================================================================== part 2: structural / cross-market
# Data: the crypto 15-minute files (data/kalshi15m) and the hourly "above K" ladders (data/kalshi15m/hourly,
# 1-minute candles for the 4 strikes nearest spot at the start of each hour). The 15-minute market that
# closes on the hour and the hourly ladder settle on the SAME CF Benchmarks value (checked: 100% consistent).
#   xmkt_arb   15-min YES + hourly NO at a strike K >= the 15-min strike (or 15-min NO + hourly YES at K below
#              it) pays >= $1 in every outcome, $2 when the price ends between the two strikes. Trade the pair
#              when the guaranteed margin (before fees) is >= g; 10 contracts per leg, taker fee on both legs.
#   xmkt_fv    price the 15-min contract off the hourly ladder (interpolated mid at the 15-min strike) and buy
#              the 15-min side that is cheaper than that by `edge`. One bet per 15-min market.
#   ladder_arb within one hourly ladder: a higher strike's YES bid above a lower strike's YES ask -> buy YES
#              low + NO high (pays >= $1 always). 10 contracts per leg.
XCOINS = ["BTC", "ETH", "SOL", "XRP"]
XGROUP = "XALL"
PAIR_N = 10


def _fee(p, n):
    return np.ceil(B.TAKER_RATE * n * p * (1 - p) * 100 - 1e-9) / 100


def _xload(coin):
    """-> per 15-min market (closing on the hour): arrays (markets x 14) of its quotes and, for up to 4 hourly
    strikes, their quotes at the same minute; plus results."""
    from . import data as D
    mk, cd, _ = D.load(f"KX{coin}15M")
    mk = mk[mk.close_ts % 3600 == 0].reset_index(drop=True)
    hd = F.DATA_DIR / "hourly"
    hm = pd.read_csv(hd / f"KX{coin}D_markets.csv", usecols=["ticker", "close_ts", "strike", "result"])
    hc = pd.read_csv(hd / f"KX{coin}D_candles.part.csv", usecols=["ticker", "ts", "yes_bid", "yes_ask"])
    hc = hc[hc.ticker.isin(set(pd.read_csv(hd / f"KX{coin}D_selected.csv").ticker))]
    hm = hm[hm.ticker.isin(set(hc.ticker))]
    n = len(mk)
    ts = mk.open_ts.to_numpy()[:, None] + 60 * MIN[None, :]
    q15 = cd.drop_duplicates(["ticker", "ts"]).set_index(["ticker", "ts"])
    key = pd.MultiIndex.from_arrays([np.repeat(mk.ticker.to_numpy(), 14), ts.reshape(-1)])
    yb = np.array(q15.yes_bid.reindex(key).to_numpy(), float).reshape(n, 14)
    ya = np.array(q15.yes_ask.reindex(key).to_numpy(), float).reshape(n, 14)
    bad = ~((yb > 0) & (ya < 1))
    yb[bad], ya[bad] = np.nan, np.nan
    K = np.full((n, 4), np.nan)
    RK = np.full((n, 4), np.nan)
    HB = np.full((n, 4, 14), np.nan)
    HA = np.full((n, 4, 14), np.nan)
    hq = hc.drop_duplicates(["ticker", "ts"]).set_index(["ticker", "ts"])
    pos = {t: i for i, t in enumerate(mk.close_ts)}
    for T, g in hm.groupby("close_ts"):
        i = pos.get(T)
        if i is None:
            continue
        g = g.sort_values("strike").head(4)
        for k, r in enumerate(g.itertuples()):
            K[i, k], RK[i, k] = r.strike, r.result
            kk = pd.MultiIndex.from_arrays([[r.ticker] * 14, ts[i]])
            b, a = hq.yes_bid.reindex(kk).to_numpy(), hq.yes_ask.reindex(kk).to_numpy()
            ok = (b > 0) & (a < 1)
            HB[i, k] = np.where(ok, b, np.nan)
            HA[i, k] = np.where(ok, a, np.nan)
    return {"coin": coin, "ticker": mk.ticker.to_numpy(), "open_ts": mk.open_ts.to_numpy(), "s15": mk.strike.to_numpy(),
            "r15": mk.result.to_numpy(), "yb": yb, "ya": ya, "K": K, "RK": RK, "HB": HB, "HA": HA}


def _hload(coin):
    """Hourly ladders on their own: (events x 59 minutes x 4 strikes) quotes + results."""
    hd = F.DATA_DIR / "hourly"
    sel = pd.read_csv(hd / f"KX{coin}D_selected.csv")
    hc = pd.read_csv(hd / f"KX{coin}D_candles.part.csv", usecols=["ticker", "ts", "yes_bid", "yes_ask"])
    hc = hc[hc.ticker.isin(set(sel.ticker))].drop_duplicates(["ticker", "ts"]).set_index(["ticker", "ts"])
    ev = sel.groupby("event")
    E = len(ev)
    K, R = np.full((E, 4), np.nan), np.full((E, 4), np.nan)
    HB, HA = np.full((E, 4, 59), np.nan), np.full((E, 4, 59), np.nan)
    ots = np.zeros(E, np.int64)
    for e, (name, g) in enumerate(ev):
        g = g.sort_values("strike").head(4)
        ots[e] = int(g.open_ts.iloc[0])
        tsv = ots[e] + 60 * np.arange(1, 60)
        for k, r in enumerate(g.itertuples()):
            K[e, k], R[e, k] = r.strike, r.result
            kk = pd.MultiIndex.from_arrays([[r.ticker] * 59, tsv])
            b, a = hc.yes_bid.reindex(kk).to_numpy(), hc.yes_ask.reindex(kk).to_numpy()
            ok = (b > 0) & (a < 1)
            HB[e, k], HA[e, k] = np.where(ok, b, np.nan), np.where(ok, a, np.nan)
    order = np.argsort(ots)
    return {"coin": coin, "open_ts": ots[order], "K": K[order], "R": R[order], "HB": HB[order], "HA": HA[order],
            "event": np.array(list(ev.groups))[order]}


XFAMS = {
    "xmkt_arb": {"name": "15-min vs hourly pair (arbitrage)",
                 "idea": "The 15-minute market that closes on the hour and the hourly 'above K' ladder settle on the same "
                         "price. Buying 15-min YES plus hourly NO at a strike at or above the 15-min strike (or the mirror "
                         "pair) pays at least $1 whatever happens; trade it when the two quotes leave a margin.",
                 "grid": {"g": [-0.04, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03], "start": [1, 4, 8], "end": [10, 14]}},
    "xmkt_fv": {"name": "15-min priced off the hourly ladder",
                "idea": "Read the market's own probability for the 15-minute strike off the hourly ladder (interpolating "
                        "between the nearest hourly strikes) and buy the 15-minute side that is cheaper than that.",
                "grid": {"edge": [0.03, 0.05, 0.07, 0.10, 0.12, 0.15, 0.20], "start": [1, 3, 5, 8], "end": [10, 12, 14],
                         "band": L3.BANDS5}},
    "ladder_arb": {"name": "Hourly ladder monotonicity",
                   "idea": "Inside one hourly ladder a higher strike can never be more likely than a lower one. When a "
                           "higher strike's YES bid sits above a lower strike's YES ask, buy YES low + NO high (pays at least $1).",
                   "grid": {"g": [-0.03, -0.02, -0.01, 0.0, 0.01, 0.02], "start": [1, 15, 30, 45], "end": [50, 59]}},
}


def _x_trades(X, fam, c, delay=0):
    """-> DataFrame of trades (ts, pnl, cost, win, minute, ticker, series) for one coin's data X."""
    n = len(X["open_ts"])
    if fam == "ladder_arb":
        HB, HA, R = X["HB"], X["HA"], X["R"]
        M = HB.shape[2]
        best = np.full((n, M), -np.inf)
        bi = np.zeros((n, M, 2), int)
        for i in range(4):
            for j in range(i + 1, 4):
                g = HB[:, j] - HA[:, i]                       # (n, M): bid of higher strike - ask of lower strike
                better = np.nan_to_num(g, nan=-np.inf) > best
                best = np.where(better, np.nan_to_num(g, nan=-np.inf), best)
                bi[better] = (i, j)
        mins = np.arange(1, M + 1)
        win = (mins >= c["start"]) & (mins <= c["end"])
        sig = (best >= c["g"] - 1e-9) & win[None, :]
        has = sig.any(1)
        jj = np.argmax(sig, 1)
        rows = np.nonzero(has)[0]
        out = []
        for e in rows:
            j = jj[e]
            i_lo, i_hi = bi[e, j]
            fj = j + delay
            if fj >= M:
                continue
            pa, pb = HA[e, i_lo, fj], 1 - HB[e, i_hi, fj]
            if not (np.isfinite(pa) and np.isfinite(pb)):
                continue
            pay = R[e, i_lo] + (1 - R[e, i_hi])
            cost = PAIR_N * (pa + pb) + _fee(pa, PAIR_N) + _fee(pb, PAIR_N)
            pnl = PAIR_N * pay - cost
            out.append((int(X["open_ts"][e] + 60 * (fj + 1)), pnl, cost, pnl > 0, j + 1, X["event"][e]))
        df = pd.DataFrame(out, columns=["ts", "pnl", "cost", "win", "minute", "ticker"])
        df["series"] = f"KX{X['coin']}D"
        return df
    yb, ya, K, RK, HB, HA = X["yb"], X["ya"], X["K"], X["RK"], X["HB"], X["HA"]
    s15, r15 = X["s15"], X["r15"]
    win = ((MIN >= c["start"]) & (MIN <= c["end"]))[None, :]
    if fam == "xmkt_arb":
        above = K >= s15[:, None]                                    # (n,4)
        gA = HB - ya[:, None, :]                                      # YES15 + NO_K (K above)
        gB = yb[:, None, :] - HA                                      # NO15 + YES_K (K below)
        g = np.where(above[:, :, None], gA, gB)
        g = np.where(np.isfinite(g), g, -np.inf)
        k = np.argmax(g, 1)                                           # best strike per minute (n,14)
        gm = np.take_along_axis(g, k[:, None, :], 1)[:, 0, :]
        sig = (gm >= c["g"] - 1e-9) & win
        has = sig.any(1)
        j = np.argmax(sig, 1)
        out = []
        for m in np.nonzero(has)[0]:
            jj, kk = j[m], k[m, j[m]]
            fj = jj + delay
            if fj > 13:
                continue
            if above[m, kk]:
                p1, p2 = ya[m, fj], 1 - HB[m, kk, fj]
                pay = r15[m] + (1 - RK[m, kk])
            else:
                p1, p2 = 1 - yb[m, fj], HA[m, kk, fj]
                pay = (1 - r15[m]) + RK[m, kk]
            if not (np.isfinite(p1) and np.isfinite(p2)):
                continue
            cost = PAIR_N * (p1 + p2) + _fee(p1, PAIR_N) + _fee(p2, PAIR_N)
            pnl = PAIR_N * pay - cost
            out.append((int(X["open_ts"][m] + 60 * (fj + 1)), pnl, cost, pnl > 0, jj + 1, X["ticker"][m]))
        df = pd.DataFrame(out, columns=["ts", "pnl", "cost", "win", "minute", "ticker"])
        df["series"] = f"KX{X['coin']}15M"
        return df
    # xmkt_fv: implied probability of finishing >= s15 from the hourly mids (monotone ladders only)
    mid = (HB + HA) / 2                                               # (n,4,14) P(S > K)
    p = np.full((len(s15), 14), np.nan)
    for a in range(3):
        k0, k1 = K[:, a], K[:, a + 1]
        inside = (s15 >= k0) & (s15 <= k1) & (k1 > k0)
        w = np.where(inside, (s15 - k0) / np.where(k1 > k0, k1 - k0, 1), np.nan)
        pi = mid[:, a, :] + w[:, None] * (mid[:, a + 1, :] - mid[:, a, :])
        mono = mid[:, a, :] >= mid[:, a + 1, :]
        p = np.where(inside[:, None] & mono & np.isfinite(pi) & ~np.isfinite(p), pi, p)
    lo, hi = L3.BANDS[c["band"]]
    na = 1 - yb
    y = win & np.isfinite(p) & np.isfinite(ya) & (ya >= lo) & (ya <= hi) & (p - ya >= c["edge"])
    nn = win & np.isfinite(p) & np.isfinite(na) & (na >= lo) & (na <= hi) & ((1 - p) - na >= c["edge"])
    side, minute = L3.first(y, nn)
    idx = np.nonzero(side)[0]
    fj = minute[idx] - 1 + delay
    keep = fj <= 13
    idx, fj = idx[keep], fj[keep]
    yes = side[idx] == 1
    price = np.where(yes, ya[idx, fj], na[idx, fj])
    ok = np.isfinite(price) & (price > 0) & (price < 1)
    idx, fj, yes, price = idx[ok], fj[ok], yes[ok], price[ok]
    nct = np.maximum(1, np.floor(L3.STAKE / price + 1e-9))
    fee = _fee(price, nct)
    w_ = (r15[idx] == 1) == yes
    pnl = nct * (w_.astype(float) - price) - fee
    df = pd.DataFrame({"ts": X["open_ts"][idx] + 60 * (fj + 1), "pnl": pnl, "cost": nct * price + fee, "win": w_,
                       "minute": minute[idx], "ticker": X["ticker"][idx], "price": price})
    df["series"] = f"KX{X['coin']}15M"
    return df


def _xsumm(df):
    if df is None or len(df) == 0:
        return L3.summ(None)
    df = df.copy()
    for col, v in (("fee", 0.0), ("price", 0.5), ("stake", L3.STAKE)):
        if col not in df:
            df[col] = v
    s = L3.summ(df)
    daily = df.groupby(df.ts // 86400).pnl.sum()
    s["t_by_day"] = L3._tser(daily.values)
    s["days"] = int(len(daily))
    return s


def xmkt(quick=0):
    """Part 2. Common calendar cut over the crypto data used here; 25% most recent days = holdout."""
    t0 = time.time()
    try:
        os.nice(19)
    except OSError:
        pass
    XD = {c: _xload(c) for c in XCOINS}
    HD = {c: _hload(c) for c in XCOINS}
    print(f"xmkt: loaded ({time.time() - t0:.0f}s)", flush=True)
    start = int(max(max(X["open_ts"][0] for X in XD.values()), max(H["open_ts"][0] for H in HD.values())))
    end = int(min(min(X["open_ts"][-1] for X in XD.values()), min(H["open_ts"][-1] for H in HD.values())))
    hdays = int(round(HOLDOUT_FRAC * (end - start) / 86400))
    cut = end - hdays * 86400
    cut -= cut % 3600
    print(f"xmkt: search {pd.to_datetime(start, unit='s')} .. {pd.to_datetime(cut, unit='s')}, holdout {hdays} days", flush=True)
    import itertools
    cands, fam_rows, WFX = [], [], {}
    for fam, spec in XFAMS.items():
        keys = list(spec["grid"])
        cfgs = [dict(zip(keys, v)) for v in itertools.product(*(spec["grid"][k] for k in keys))]
        data = HD if fam == "ladder_arb" else XD
        agg = {c: np.zeros((len(cfgs), N_FOLDS, 3)) for c in XCOINS}
        for i, cfg in enumerate(cfgs):
            for c in XCOINS:
                df = _x_trades(data[c], fam, cfg)
                if not len(df):
                    continue
                df = df[(df.ts >= start) & (df.ts < cut)]
                f = np.clip(((df.ts.to_numpy() - start) * N_FOLDS) // (cut - start), 0, N_FOLDS - 1).astype(int)
                pn = df.pnl.to_numpy()
                agg[c][i, :, 0] = np.bincount(f, minlength=N_FOLDS)
                agg[c][i, :, 1] = np.bincount(f, weights=pn, minlength=N_FOLDS)
                agg[c][i, :, 2] = np.bincount(f, weights=pn ** 2, minlength=N_FOLDS)
        agg[XGROUP] = sum(agg[c] for c in XCOINS)
        wf = {}
        nshort = 0
        for sc in XCOINS + [XGROUP]:
            w = L3.walk(agg[sc])
            wf[sc] = w["oos"]
            WFX[(fam, sc)] = w
            if L3.shortlisted(w):
                nshort += 1
                cands.append({"id": f"{fam}:{sc}", "family": fam, "scope": sc if sc == XGROUP else f"KX{sc}",
                              "_coins": XCOINS if sc == XGROUP else [sc], "execution": "taker",
                              "rule": {"family": fam, "params": cfgs[w["final"]]},
                              "search": {**w["oos"], "insample": w["final_search"]}})
        # raw opportunity count on the search window (any margin >= 0), for the report
        n_arb = None
        if fam != "xmkt_fv":
            c0 = dict(cfgs[0], g=0.0, start=1, end=59 if fam == "ladder_arb" else 14)
            d = pd.concat([_x_trades(data[c], fam, c0) for c in XCOINS], ignore_index=True)
            d = d[(d.ts >= start) & (d.ts < cut)] if len(d) else d
            n_arb = {"pairs_with_margin_ge_0_before_fees": int(len(d)),
                     "pnl_if_all_traded": round(float(d.pnl.sum()), 2) if len(d) else 0.0}
        fam_rows.append({"id": fam, "name": spec["name"], "idea": spec["idea"], "configs": len(cfgs),
                         "scopes_tested": len(wf), "shortlisted": nshort,
                         "best_search_t": max(v["t"] for v in wf.values()),
                         "walk_forward": {("Crypto pooled (BTC/ETH/SOL/XRP)" if s == XGROUP else s): v for s, v in wf.items()},
                         "search_opportunities": n_arb})
        print(f"  {fam}: {len(cfgs)} configs, shortlisted {nshort} ({time.time() - t0:.0f}s)", flush=True)
    for c in cands:                                     # final exam, once
        fam, cfg = c["family"], c["rule"]["params"]
        data = HD if fam == "ladder_arb" else XD
        h = [_x_trades(data[k], fam, cfg) for k in c["_coins"]]
        d1 = [_x_trades(data[k], fam, cfg, delay=1) for k in c["_coins"]]
        h = pd.concat([x for x in h if len(x)], ignore_index=True) if any(len(x) for x in h) else None
        d1 = pd.concat([x for x in d1 if len(x)], ignore_index=True) if any(len(x) for x in d1) else None
        h = h[h.ts >= cut] if h is not None else None
        d1 = d1[d1.ts >= cut] if d1 is not None else None
        c["holdout"] = _xsumm(h)
        c["curve"] = L3.curve(h)
        c["delay1"] = {k: v for k, v in _xsumm(d1).items() if k in ("pnl", "t", "trades")}
        c["archive"] = None
        c["holdout_by_coin"] = ({k: round(float(g.pnl.sum()), 2) for k, g in h.groupby("series")}
                                if h is not None and len(h) and c["scope"] == XGROUP else None)
        c["label"] = f"{'Crypto pooled' if c['scope'] == XGROUP else c['scope'][2:]} · {XFAMS[fam]['name']} ({cfg})"
        del c["_coins"]
    part = {"generated": int(time.time()), "runtime_s": int(time.time() - t0), "start": start, "cut": cut,
            "holdout_days": hdays, "families": fam_rows, "candidates": cands,
            "data": "crypto 15-min markets closing on the hour + hourly ladders (4 strikes nearest spot), "
                    f"{pd.to_datetime(start, unit='s'):%Y-%m-%d} to {pd.to_datetime(end, unit='s'):%Y-%m-%d}"}
    PART_XMKT.write_text(json.dumps(part, default=L3._jd))
    print(f"xmkt done in {time.time() - t0:.0f}s: {len(cands)} candidates", flush=True)
    for c in cands:
        h = c["holdout"]
        print(f"  {c['id']:24s} ${h['pnl']:>8} n={h['trades']:>5} t={h['t']:>5} d1 t={c['delay1']['t']}", flush=True)
    return part
