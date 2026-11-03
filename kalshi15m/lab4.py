"""Lab 4: golden hunt on Kalshi markets beyond the 9 crypto 15-minute coins.

    nice -n 19 python -m kalshi15m lab4 survey      # what exists, how much history/volume
    nice -n 19 python -m kalshi15m lab4 download    # Kalshi candles + underlying 1-min prices
    nice -n 19 python -m kalshi15m lab4 models      # lab3 families on every testable 15-min series
    nice -n 19 python -m kalshi15m lab4 xmkt        # structural / cross-market families (crypto data)
    nice -n 19 python -m kalshi15m lab4 range       # range sums on the 15-minute coin race (KXCRYPTOLEAD15M)
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

Underlying prices are NOT the settlement source (Pyth): Yahoo 1-minute bars (see data_fx; Dukascopy was
unreachable), which only go back ~30 days. The model's "strike" is the feed's own price at the market open
(Pyth's opening print is the real strike; the venues' levels differ, returns agree), so x = log(price now /
price at open). Treasury yields use inverted Treasury futures of the same tenor (yield up <=> price down).
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
MIN_DAYS = 14                   # a series needs this many days of Kalshi markets to be tested (yields: 15)
MIN_MED_VOLUME = 100            # median contracts traded per market
MIN_PER_TRADE, MIN_PER_DAY = 0.10, 2.0   # "economically meaningful" at $10 a trade

FX = ["KXEURUSD15M", "KXUSDJPY15M", "KXGBPUSD15M", "KXAUDUSD15M", "KXUSDCAD15M", "KXUSDMXN15M"]
RATES = ["KX2YRRATE15M", "KX5YRRATE15M", "KX10YRRATE15M", "KX30YRRATE15M"]
INDEX = ["KXINX15M", "KXNDQ15M", "KXDJIA15M"]
METALS = ["KXGOLD15M", "KXSILVER15M", "KXCOPPER15M", "KXPLATINUM15M", "KXPALLADIUM15M"]
ENERGY = ["KXWTI15M", "KXBRENT15M", "KXNATGAS15M"]
XCRYPTO = ["KXBCH15M", "KXADA15M", "KXTON15M"]
GROUPS_ALL = {"FX": FX, "RATES": RATES, "INDEX": INDEX, "METALS": METALS, "ENERGY": ENERGY, "XCRYPTO": XCRYPTO}
GROUP_NAMES = {"FX": "All FX pooled", "RATES": "All yields pooled", "INDEX": "All indices pooled",
               "METALS": "All metals pooled", "ENERGY": "All energy pooled", "XCRYPTO": "New crypto pooled"}
NAMES = {"KXEURUSD15M": "EUR/USD", "KXUSDJPY15M": "USD/JPY", "KXGBPUSD15M": "GBP/USD", "KXAUDUSD15M": "AUD/USD",
         "KXUSDCAD15M": "USD/CAD", "KXUSDMXN15M": "USD/MXN", "KX2YRRATE15M": "2Y yield", "KX5YRRATE15M": "5Y yield",
         "KX10YRRATE15M": "10Y yield", "KX30YRRATE15M": "30Y yield", "KXINX15M": "S&P 500", "KXNDQ15M": "Nasdaq-100",
         "KXDJIA15M": "Dow", "KXGOLD15M": "Gold", "KXPLATINUM15M": "Platinum", "KXPALLADIUM15M": "Palladium", "KXSILVER15M": "Silver", "KXCOPPER15M": "Copper", "KXWTI15M": "WTI",
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
    return F.UNDERLYING.get(series)


def anchor_own(series):
    return underlying(series)[0].startswith(("duka", "yahoo"))


def spot_path(series):
    return F.LDIR / f"{series}_spot.csv"


def build_panel4(series, where="main"):
    """Same as backtest.build_panel, but from data_fx files; strike = feed price at the open for
    Dukascopy-priced series (see module doc)."""
    mk, cd, sp = F.load(series) if where == "main" else F.load_archive(series)
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


ARCH_BEFORE = 1788480000          # 2026-09-04 00:00 UTC, Kalshi's historical cutoff: older markets = blind archive


def split(full):
    """One common holdout cut for every series. Each series' search window runs from its own first market
    (after the archive boundary) to the cut; folds are calendar slices of [earliest start, cut) so pooled
    scopes stay aligned. Holdout length = HOLDOUT_FRAC of (end - median series start), whole days."""
    starts = {s: int(np.min(np.asarray(p.open_ts)[np.asarray(p.open_ts) >= ARCH_BEFORE])) for s, p in full.items()}
    start = int(min(starts.values()))
    end = int(min(p.open_ts.max() for p in full.values()))
    ref = float(np.median(list(starts.values())))
    hdays = max(5, int(round(HOLDOUT_FRAC * (end - ref) / 86400)))
    cut = end - hdays * 86400
    cut = cut - cut % 900
    L3.G.update({"search": {}, "hold": {}, "arch": {}, "start": start, "cut": cut, "quick": L3.G.get("quick", 0)})
    for s, p in full.items():
        ots = np.asarray(p.open_ts, np.int64)
        sm = (ots >= ARCH_BEFORE) & (ots < cut)
        sp_ = p.subset(sm)
        fold = np.clip(((np.asarray(sp_.open_ts, np.int64) - start) * N_FOLDS) // (cut - start), 0, N_FOLDS - 1)
        L3.G["search"][s] = L3.Ctx(s, sp_, fold.astype(int))
        L3.G["hold"][s] = L3.Ctx(s, p.subset(ots >= cut))
        older = ots < ARCH_BEFORE - 900
        if older.sum() >= 350:                       # Kalshi archive data downloaded -> blind archive test
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
           "_wsum": _wsum(hold), "_norms": norms}
    return cand["id"], out


def control_rule(WF, scope):
    w = WF.get(("fv_ref", scope))
    if not w or w["final"] is None:
        return None
    return {"family": "fv_ref", "params": L3.grid_list(L3.FAMILIES["fv_ref"]["grid"])[w["final"]]}


# =========================================================================== part 1: lab3 families
def models(workers=2, quick=0, families=None, series_only=None, out=None):
    t0 = time.time()
    L3.G["quick"] = quick or 0
    L3._GRID_CACHE.clear()
    try:
        os.nice(19)
    except OSError:
        pass
    ser, why = testable_list()
    if series_only:
        ser = [s for s in ser if s in series_only]
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
    dest = Path(out) if out else PART_MODELS
    dest.write_text(json.dumps(part, default=L3._jd))
    print(f"models part done in {time.time() - t0:.0f}s -> {dest}", flush=True)
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


# =========================================================================== part 3: range sums (coin race)
# None of the non-crypto 15-minute series has more than one market per 15-minute window (one 'at or above the
# open' contract each), so there are no strike ladders or range buckets to check against each other. The only
# 15-minute series with mutually exclusive outcomes is KXCRYPTOLEAD15M ("which of BTC/ETH/SOL/XRP/HYPE rises
# most in the next 15 minutes"): exactly one outcome pays, so
#   all YES: buy YES on every outcome; pays $1 per set whatever happens, worth it when the asks sum below $1;
#   all NO : buy NO on every outcome; pays $(n-1) per set, worth it when the NO asks sum below n-1.
# Fills only at the quoted asks of the same minute, 10 contracts per leg, taker fee on every leg.
RANGE_SERIES = "KXCRYPTOLEAD15M"
RFAMS = {
    "range_sum": {"name": "Coin-race outcomes summing to $1 (arbitrage)",
                  "idea": "In Kalshi's 15-minute 'which coin rises most' race exactly one of the five outcomes pays. "
                          "If the five YES asks add up to less than $1 (or the five NO asks to less than $4), buying the "
                          "whole set locks in the difference; trade when that margin after fees is at least g.",
                  "grid": {"g": [-0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.05], "start": [1, 5, 10], "end": [10, 14],
                           "side": ["yes", "no", "both"]}},
}
PART_RANGE = LAB / "lab4_part_range.json"


def _rload():
    mk = pd.read_csv(F.LDIR / f"{RANGE_SERIES}_markets.csv")
    cd = pd.read_csv(F.LDIR / f"{RANGE_SERIES}_candles.part.csv", usecols=["ticker", "ts", "yes_bid", "yes_ask"])
    cd = cd[cd.ts > 0].drop_duplicates(["ticker", "ts"]).set_index(["ticker", "ts"])
    mk = mk[(mk.close_ts - mk.open_ts) == 900]
    ev = [(e, g) for e, g in mk.groupby("event") if len(g) == 5]
    E = len(ev)
    YB, YA = np.full((E, 5, 14), np.nan), np.full((E, 5, 14), np.nan)
    R, ots = np.zeros((E, 5)), np.zeros(E, np.int64)
    for i, (e, g) in enumerate(ev):
        ots[i] = int(g.open_ts.iloc[0])
        tsv = ots[i] + 60 * MIN
        for k, r in enumerate(g.itertuples()):
            R[i, k] = r.result
            kk = pd.MultiIndex.from_arrays([[r.ticker] * 14, tsv])
            YB[i, k] = cd.yes_bid.reindex(kk).to_numpy()
            YA[i, k] = cd.yes_ask.reindex(kk).to_numpy()
    o = np.argsort(ots)
    return {"open_ts": ots[o], "YB": YB[o], "YA": YA[o], "R": R[o], "event": np.array([e for e, _ in ev])[o]}


def _r_trades(X, c, delay=0):
    YB, YA, R = X["YB"], X["YA"], X["R"]
    n = 5
    ya = np.where((YA > 0) & (YA < 1), YA, np.nan)              # YES ask must be a real quote
    na = np.where(YB > 0, 1 - YB, 1.0)                           # no bid -> NO costs $1 (equivalent to skipping it)
    na = np.where(np.isnan(YB), np.nan, na)
    feeY = np.ceil(B.TAKER_RATE * PAIR_N * ya * (1 - ya) * 100 - 1e-9) / 100
    feeN = np.ceil(B.TAKER_RATE * PAIR_N * na * (1 - na) * 100 - 1e-9) / 100
    costY = PAIR_N * ya.sum(1) + feeY.sum(1)                     # (E,14); NaN if any leg missing
    costN = PAIR_N * na.sum(1) + feeN.sum(1)
    mY = (PAIR_N * 1 - costY) / PAIR_N                           # guaranteed margin per set, after fees
    mN = (PAIR_N * (n - 1) - costN) / PAIR_N
    win = ((MIN >= c["start"]) & (MIN <= c["end"]))[None, :]
    sY = (np.nan_to_num(mY, nan=-9) >= c["g"] - 1e-9) & win & (c["side"] in ("yes", "both"))
    sN = (np.nan_to_num(mN, nan=-9) >= c["g"] - 1e-9) & win & (c["side"] in ("no", "both"))
    out = []
    for e in np.nonzero((sY | sN).any(1))[0]:
        j = int(np.argmax(sY[e] | sN[e]))
        yes = bool(sY[e, j])
        fj = j + delay
        if fj > 13:
            continue
        cost = costY[e, fj] if yes else costN[e, fj]
        if not np.isfinite(cost):
            continue
        pay = PAIR_N * (R[e].sum() if yes else (n - R[e].sum()))
        pnl = pay - cost
        out.append((int(X["open_ts"][e] + 60 * (fj + 1)), pnl, cost, pnl > 0, j + 1, X["event"][e], "yes" if yes else "no"))
    df = pd.DataFrame(out, columns=["ts", "pnl", "cost", "win", "minute", "ticker", "set"])
    df["series"] = RANGE_SERIES
    return df


def range_arb():
    """Part 3: range sums on the coin race. Own calendar cut: most recent 25% of days = holdout."""
    import itertools
    t0 = time.time()
    try:
        os.nice(19)
    except OSError:
        pass
    X = _rload()
    start, end = int(X["open_ts"][0]), int(X["open_ts"][-1])
    hdays = int(round(HOLDOUT_FRAC * (end - start) / 86400))
    cut = end - hdays * 86400
    cut -= cut % 900
    print(f"range: {len(X['open_ts'])} events, search {pd.to_datetime(start, unit='s')} .. {pd.to_datetime(cut, unit='s')}, "
          f"holdout {hdays} days", flush=True)
    cands, fam_rows = [], []
    for fam, spec in RFAMS.items():
        keys = list(spec["grid"])
        cfgs = [dict(zip(keys, v)) for v in itertools.product(*(spec["grid"][k] for k in keys))]
        agg = np.zeros((len(cfgs), N_FOLDS, 3))
        for i, cfg in enumerate(cfgs):
            df = _r_trades(X, cfg)
            df = df[(df.ts >= start) & (df.ts < cut)] if len(df) else df
            if not len(df):
                continue
            f = np.clip(((df.ts.to_numpy() - start) * N_FOLDS) // (cut - start), 0, N_FOLDS - 1).astype(int)
            pn = df.pnl.to_numpy()
            agg[i, :, 0] = np.bincount(f, minlength=N_FOLDS)
            agg[i, :, 1] = np.bincount(f, weights=pn, minlength=N_FOLDS)
            agg[i, :, 2] = np.bincount(f, weights=pn ** 2, minlength=N_FOLDS)
        w = L3.walk(agg)
        # raw opportunities on the search window: any set whose asks leave a margin >= 0 before fees
        YA, YB = X["YA"], X["YB"]
        sm = X["open_ts"] < cut
        sy = np.where((YA > 0) & (YA < 1), YA, np.nan).sum(1)
        sn = np.where(np.isnan(YB), np.nan, np.where(YB > 0, 1 - YB, 1.0)).sum(1)
        opp = {"events_in_search": int(sm.sum()),
               "events_with_yes_set_under_1_before_fees": int((np.nan_to_num(sy[sm], nan=9) <= 1).any(1).sum()),
               "events_with_no_set_under_4_before_fees": int((np.nan_to_num(sn[sm], nan=9) <= 4).any(1).sum()),
               "median_min_yes_set_cost": round(float(np.nanmedian(np.nanmin(np.where(np.isfinite(sy[sm]), sy[sm], np.nan), 1))), 3),
               "median_min_no_set_cost": round(float(np.nanmedian(np.nanmin(np.where(np.isfinite(sn[sm]), sn[sm], np.nan), 1))), 3)}
        short = L3.shortlisted(w)
        if short:
            cands.append({"id": f"{fam}:{RANGE_SERIES}", "family": fam, "scope": RANGE_SERIES, "execution": "taker",
                          "rule": {"family": fam, "params": cfgs[w["final"]]},
                          "search": {**w["oos"], "insample": w["final_search"]}})
        fam_rows.append({"id": fam, "name": spec["name"], "idea": spec["idea"], "configs": len(cfgs), "scopes_tested": 1,
                         "shortlisted": int(short), "best_search_t": w["oos"]["t"],
                         "walk_forward": {"Coin race": w["oos"]}, "search_opportunities": opp,
                         "final_search": w["final_search"],
                         "final_params": None if w["final"] is None else cfgs[w["final"]]})
        print(f"  {fam}: {len(cfgs)} configs WF {w['oos']} shortlisted={short} opp={opp} ({time.time() - t0:.0f}s)", flush=True)
    for c in cands:                                       # final exam, once
        h = _r_trades(X, c["rule"]["params"])
        d1 = _r_trades(X, c["rule"]["params"], delay=1)
        h, d1 = h[h.ts >= cut], d1[d1.ts >= cut]
        c["holdout"] = _xsumm(h)
        c["curve"] = L3.curve(h) if len(h) else []
        c["delay1"] = {k: v for k, v in _xsumm(d1).items() if k in ("pnl", "t", "trades")}
        c["archive"] = None
        c["label"] = f"Coin race · {RFAMS[c['family']]['name']} ({c['rule']['params']})"
    part = {"generated": int(time.time()), "runtime_s": int(time.time() - t0), "start": start, "cut": cut,
            "holdout_days": hdays, "families": fam_rows, "candidates": cands,
            "data": f"KXCRYPTOLEAD15M (5 outcomes per 15-minute race), {pd.to_datetime(start, unit='s'):%Y-%m-%d} to "
                    f"{pd.to_datetime(end, unit='s'):%Y-%m-%d}"}
    PART_RANGE.write_text(json.dumps(part, default=L3._jd))
    print(f"range done in {time.time() - t0:.0f}s: {len(cands)} candidates", flush=True)
    for c in cands:
        h = c["holdout"]
        print(f"  {c['id']:24s} ${h['pnl']:>8} n={h['trades']:>5} t={h['t']:>5} d1 t={c['delay1']['t']}", flush=True)
    return part


# =========================================================================== judge (one strict bar for both parts)
def RULES(t_bar):
    return [
        "Only data from before the holdout was used to pick any setting; the holdout (the most recent ~25% of days, one "
        "calendar cut for every series in a part) was run once per candidate with frozen settings.",
        f"Golden needs ALL of the following. (1) Made money on the holdout with a t-stat of at least {t_bar}, the strict "
        "bar that corrects for every candidate taken to the holdout in lab4 (one-sided Bonferroni, 5%).",
        "(2) There is no live strategy on these markets, so the comparison is the CONTROL: the live bell-curve fair-value "
        "model re-tuned on the same search window (lab3 family fv_ref) and run on the same holdout. A new family must beat "
        "the control on the same scope on BOTH holdout profit and t-stat. The control itself is judged on the other tests.",
        "(3) Where older Kalshi archive data was downloaded for the series (before Sep 4), it also made money there with "
        "t >= 2 on at least 50 trades, with no re-tuning.",
        "(4) No more than 40% of its holdout profit came from a single day.",
        f"(5) Economically meaningful after fees: at least ${MIN_PER_TRADE:.2f} per $10 trade and at least "
        f"${MIN_PER_DAY:.0f} a day on the holdout.",
        "Pass = made money on the holdout with t >= 2 but missed at least one golden test. Fail = anything else.",
        "Every result assumes $10 per trade (10 contracts per leg for the two-leg pair trades), Kalshi taker fees "
        "ceil(0.07*C*P*(1-P)) on every leg (maker 0.0175 for maker rules), fills only at the quoted ask/bid at the end of "
        "the decision minute, one bet per market. 'One minute late' re-runs the frozen rule with a 1-minute delay; "
        "reported, not graded.",
    ]


CAVEATS = [
    "Short histories. Free 1-minute prices (Yahoo) only go back about 30 days, so every series is tested on roughly "
    "Oct 6 - Nov 3 2026 (about 20 trading days) even where Kalshi has older markets: search ~3 weeks, holdout the last 7 "
    "days. Treasury yields have only 15 days of Kalshi markets at all (search ~1 week). A t-stat on 7 days is fragile even "
    "when it clears the bar; treat anything that passes as 'worth paper trading', never as proven.",
    "The underlying prices are NOT the settlement feed. Kalshi settles these markets on Pyth, whose history API needs a "
    "key; Dukascopy's free feed was unreachable from this machine. Yahoo 1-minute bars are used instead: spot quotes for "
    "FX, front-month futures for metals/energy, Treasury futures of the matching tenor (inverted) for yields. The model's "
    "strike is the feed's own price at the market open. coins[*].feed_sign_agreement_search shows how often the feed's "
    "15-minute move has the same sign as Kalshi's result (e.g. ~96% for EUR/USD): every disagreement is a likely loss for "
    "a fair-value rule, so these backtests understate what a bot with a Pyth feed could do, and a failure here does not "
    "prove there is no edge with the right feed.",
    "Yahoo's AUD/USD and some futures (palladium, platinum) skip minutes; gaps are forward-filled, so the 'price now' "
    "can be up to a minute or two stale on those series.",
    "Backtest fills assume the quoted ask had enough size for a $10 order (10 contracts a leg for set trades). The "
    "yields are thin (median ~200 contracts per market, 11-15% of markets never trade), so real fills would be worse. "
    "The one-minute-late column shows how much survives if the bot acts a minute later.",
    "Structural arbitrage: every non-crypto 15-minute series has exactly one market per 15-minute window (one 'at or "
    "above the open' contract), so there is no ladder or range to arbitrage. The range-sum test was run on the only "
    "15-minute series with mutually exclusive outcomes, Kalshi's crypto 'coin race' (KXCRYPTOLEAD15M). The 15-min vs "
    "hourly pair and hourly-ladder tests (xmkt_arb, xmkt_fv, ladder_arb) were run earlier on crypto data and are kept "
    "for completeness.",
    "Stock-index 15-minute series (S&P 500, Nasdaq-100, Dow) and USD/MXN are listed by Kalshi but had no settled "
    "markets, so they could not be tested. Brent has only 13 days of markets (< 14) and was not tested.",
    "To fit the time budget the lab3 parameter grids were thinned to every 3rd configuration (method.grid_thinning); "
    "neighbouring configurations in those grids are near-duplicates.",
]

PLAIN = {"KXEURUSD15M": "Euro vs US dollar", "KXUSDJPY15M": "US dollar vs Japanese yen",
         "KXGBPUSD15M": "British pound vs US dollar", "KXAUDUSD15M": "Australian dollar vs US dollar",
         "KXUSDCAD15M": "US dollar vs Canadian dollar", "KXUSDMXN15M": "US dollar vs Mexican peso",
         "KX2YRRATE15M": "2-year Treasury yield", "KX5YRRATE15M": "5-year Treasury yield",
         "KX10YRRATE15M": "10-year Treasury yield", "KX30YRRATE15M": "30-year Treasury yield",
         "KXINX15M": "S&P 500", "KXNDQ15M": "Nasdaq-100", "KXDJIA15M": "Dow Jones Industrial Average",
         "KXGOLD15M": "Gold", "KXSILVER15M": "Silver", "KXCOPPER15M": "Copper", "KXPLATINUM15M": "Platinum",
         "KXPALLADIUM15M": "Palladium", "KXWTI15M": "WTI crude oil", "KXBRENT15M": "Brent crude oil",
         "KXNATGAS15M": "Natural gas", "KXBCH15M": "Bitcoin Cash", "KXADA15M": "Cardano", "KXTON15M": "Toncoin",
         "KXCOFFEE15M": "Coffee", "KXCRYPTOCOMP15M": "Crypto comparison", "KXCRYPTOLEAD15M": "Crypto coin race (which coin rises most)",
         "KXKPOWMID15M": "KPOW midterms", "KXGBPUSD15MTEST": "GBP/USD test series"}


def _paired(a, b):
    ks = set(a) | set(b)
    if not ks:
        return {"extra_pnl": 0.0, "t": 0.0}
    d = np.array([a.get(k, 0.0) - b.get(k, 0.0) for k in sorted(ks)])
    return {"extra_pnl": round(float(d.sum()), 2), "t": L3._tser(d)}


def _why4(c, ch, t_bar, ctl):
    h = c["holdout"]
    if h["pnl"] <= 0:
        return f"Lost ${-h['pnl']:,.0f} on the holdout ({h['trades']} trades)."
    if h["t"] < 2:
        return f"Made ${h['pnl']:,.0f} on the holdout but t = {h['t']} is too weak to rule out luck (needs 2)."
    miss = []
    if not ch["strict_t"]:
        miss.append(f"t = {h['t']} is below the strict bar of {t_bar}")
    if ch.get("beats_control_pnl") is False:
        miss.append(f"made less than the re-tuned control (${h['pnl']:,.0f} vs ${ctl['holdout']['pnl']:,.0f})")
    if ch.get("beats_control_t") is False:
        miss.append(f"t-stat below the re-tuned control ({h['t']} vs {ctl['holdout']['t']})")
    if ch.get("archive") is False:
        a = c["archive"]
        miss.append(f"did not hold up on the older archive data (${a['pnl']:,.0f}, t = {a['t']}, {a['trades']} trades)")
    if not ch["not_one_day"]:
        miss.append(f"{(h.get('top_day_share') or 0) * 100:.0f}% of the profit came from one day")
    if not ch["economic"]:
        miss.append(f"too small to matter (${h['per_trade']:.2f} a trade, ${c['per_day']:.2f} a day)")
    if not miss:
        a = c.get("archive")
        return (f"Cleared every test: ${h['pnl']:,.0f} at t = {h['t']} on the holdout (strict bar {t_bar}"
                + (f", archive t = {a['t']}" if a else "") + f"), ${c['per_day']:.2f} a day at $10 a trade.")
    return f"Made ${h['pnl']:,.0f} (t = {h['t']}) but " + "; ".join(miss) + "."


def judge(out_path=None):
    pm = json.loads(PART_MODELS.read_text()) if PART_MODELS.exists() else None
    px = json.loads(PART_XMKT.read_text()) if PART_XMKT.exists() else None
    pr = json.loads(PART_RANGE.read_text()) if PART_RANGE.exists() else None
    if px:                                            # crypto data: say so in every name
        for fr in px["families"]:
            if not fr["name"].startswith("Crypto"):
                fr["name"] = "Crypto: " + fr["name"]
    cands = (pm["candidates"] if pm else []) + (px["candidates"] if px else []) + (pr["candidates"] if pr else [])
    k = max(1, len(cands))
    t_bar = round(NormalDist().inv_cdf(1 - 0.05 / k), 2)
    base = {b["scope"]: b for b in (pm["baselines"] if pm else [])}
    for c in cands:
        is_x = c["family"] in XFAMS or c["family"] in RFAMS
        part = (px if c["family"] in XFAMS else pr) if is_x else pm
        h = c["holdout"]
        c["per_day"] = round(h["pnl"] / max(1, part["holdout_days"]), 2)
        ctl = None if is_x else base.get(c["scope"])
        own_ctl = (not is_x) and c["family"] == "fv_ref"
        arch = c.get("archive")
        arch_ok = None if not arch else bool(arch["trades"] >= L3.MIN_ARCH_TRADES and arch["pnl"] > 0 and arch["t"] >= 2)
        top = h.get("top_day_share")
        ch = {"holdout_profit": h["pnl"] > 0, "strict_t": h["t"] >= t_bar,
              "beats_control_pnl": None if (ctl is None or own_ctl) else h["pnl"] > ctl["holdout"]["pnl"],
              "beats_control_t": None if (ctl is None or own_ctl) else h["t"] > ctl["holdout"]["t"],
              "archive": arch_ok, "not_one_day": top is not None and top <= 0.40,
              "economic": h.get("per_trade", 0) >= MIN_PER_TRADE and c["per_day"] >= MIN_PER_DAY}
        c["checks"] = ch
        golden = all(v for v in ch.values() if v is not None)
        c["status"] = "golden" if golden else ("pass" if h["pnl"] > 0 and h["t"] >= 2 else "fail")
        c["why"] = _why4(c, ch, t_bar, ctl)
        if not is_x:
            c["label"] = L3.label(c["family"], c["scope"], c["rule"].get("params") if "params" in c["rule"] else None)
            if ctl and not own_ctl:
                c["paired_vs_control"] = {"control_id": ctl["id"], **_paired(c.get("_wsum") or {}, ctl.get("_wsum") or {})}
            c["vs_baseline"] = None if not ctl else {"baseline_id": ctl["id"], "pnl_diff": round(h["pnl"] - ctl["holdout"]["pnl"], 2),
                                                     "t_diff": round(h["t"] - ctl["holdout"]["t"], 2)}
            if c["status"] == "golden" and (c.get("paired_vs_control") or {}).get("t", 99) < 2:
                c["why"] += (f" Caution: the extra ${c['paired_vs_control']['extra_pnl']:,.0f} over the control on the same "
                             f"markets is not statistically clear (paired t = {c['paired_vs_control']['t']}).")
        else:
            c["vs_baseline"] = None
    pub = []
    for c in cands:
        rule = c["rule"]
        if "members" in rule:
            params, strategy = {"members": [{"family": m["family"], "params": m["params"]} for m in rule["members"]]}, "ens_best"
        elif rule.get("per_coin"):
            params, strategy = {cname(kk): v for kk, v in rule["params"].items()}, "fv_ref (per series)"
        else:
            params, strategy = rule["params"], rule["family"]
        pub.append({"id": f"{c['id']}:{c['execution']}", "label": c["label"], "family": c["family"], "scope": c["scope"],
                    "strategy": strategy, "execution": c["execution"], "params": params, "search": c["search"],
                    "holdout": c["holdout"], "per_day": c["per_day"], "archive": c.get("archive"), "delay1": c["delay1"],
                    "vs_baseline": c.get("vs_baseline"), "paired_vs_control": c.get("paired_vs_control"),
                    "holdout_by_coin": c.get("holdout_by_coin"), "status": c["status"], "why": c["why"],
                    "checks": c["checks"], "curve": c["curve"]})
    pub.sort(key=lambda c: ({"golden": 0, "pass": 1, "fail": 2}[c["status"]], -c["holdout"]["t"]))
    fams = []
    for part in (pm, px, pr):
        if not part:
            continue
        for fr in part["families"]:
            mine = [c for c in pub if c["family"] == fr["id"]]
            st = "golden" if any(c["status"] == "golden" for c in mine) else (
                "pass" if any(c["status"] == "pass" for c in mine) else "fail")
            best = max(mine, key=lambda c: c["holdout"]["t"], default=None)
            fams.append({**fr, "best_holdout_t": best["holdout"]["t"] if best else None, "status": st,
                         "finding": ("Nothing reached the holdout: no scope had a good enough walk-forward record."
                                     if not best else f"Best: {best['label']}: ${best['holdout']['pnl']:,.0f} at "
                                     f"t = {best['holdout']['t']} on the holdout ({best['status']}).")})
    sv = json.loads(SURVEY.read_text()) if SURVEY.exists() else {}
    why = (pm or {}).get("why", {})
    coins = (pm or {}).get("coins", {})
    surveyed = []
    for sname, r in sv.items():
        if sname in L3.COINS or sname in ("KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXHYPE15M", "KXBNB15M",
                                          "KXNEAR15M", "KXDOGE15M", "KXZEC15M"):
            continue
        w = why.get(sname)
        n_mk = int(r.get("markets") or 0)
        if sname == RANGE_SERIES:
            testable = bool(pr)
            note = ("Not an up/down market: a 5-way race (which of BTC/ETH/SOL/XRP/HYPE rises most). Used only for the "
                    "range-sum arbitrage test" + (f" ({pr['data']})." if pr else ".") +
                    f" Thin: median {r.get('median_volume', 0):,.0f} contracts per outcome.")
        elif w == "testable":
            testable = True
            cinfo = coins.get(sname, {})
            t_from = max(str(r.get("first") or ""), f"{pd.to_datetime(pm['start'], unit='s'):%Y-%m-%d}")
            note = (f"Tested on {cinfo.get('markets', '?')} markets from {t_from}"
                    + (" (all of its history)" if str(r.get("first") or "") >= t_from else
                       " (free 1-minute prices only go back ~30 days, so older markets could not be used)")
                    + f"; Yahoo {F.UNDERLYING[sname][1]} as the price feed"
                    + (f", same up/down sign as Kalshi's result {cinfo['feed_sign_agreement_search'] * 100:.1f}% of the time"
                       if cinfo.get("feed_sign_agreement_search") else "") + ".")
        elif sname == "KXKPOWMID15M":
            testable = False
            note = (f"Not a price up/down market (a political-event series); only {r.get('span_days')} days of markets and "
                    f"{(r.get('zero_volume_frac') or 0) * 100:.0f}% of them never traded.")
        elif n_mk == 0:
            testable = False
            note = "Kalshi lists this series but has not opened a single market in it (checked Nov 3 2026), so there is nothing to test."
        else:
            testable = False
            note = (w or "not one of the hunt's target markets") + "."
            note = note[0].upper() + note[1:]
        surveyed.append({"series": sname, "name": PLAIN.get(sname, cname(sname)), "markets": n_mk,
                         "history_days": r.get("span_days", 0), "median_volume": r.get("median_volume"),
                         "testable": testable, "note": note, "first": r.get("first"), "last": r.get("last"),
                         "markets_per_day": r.get("markets_per_day_recent"), "yes_rate": r.get("yes_rate"),
                         "tested_markets": coins.get(sname, {}).get("markets") if testable else None})
    order = FX + RATES + INDEX + METALS + ENERGY
    surveyed.sort(key=lambda x: (order.index(x["series"]) if x["series"] in order else 99, x["series"]))
    gold = [c for c in pub if c["status"] == "golden"]
    summary = [f"{len(gold)} of {len(pub)} candidates that reached the holdout are golden, "
               f"{sum(c['status'] == 'pass' for c in pub)} pass, {sum(c['status'] == 'fail' for c in pub)} fail "
               f"(strict bar t >= {t_bar} over {k} holdout tests)."]
    for b in (pm["baselines"] if pm else []):
        summary.append(f"Control {cname(b['scope'])}: ${b['holdout']['pnl']:,.0f} (t {b['holdout']['t']}, "
                       f"{b['holdout']['trades']} trades) on the holdout.")
    res = {
        "generated": int(time.time()),
        "runtime_s": int((pm or {}).get("runtime_s", 0) + (px or {}).get("runtime_s", 0) + (pr or {}).get("runtime_s", 0)),
        "method": {
            "search_window": (f"{pd.to_datetime(pm['start'], unit='s'):%Y-%m-%d %H:%M} to "
                              f"{pd.to_datetime(pm['cut'], unit='s'):%Y-%m-%d %H:%M} UTC") if pm else None,
            "search_start": pm["start"] if pm else None, "holdout_start": pm["cut"] if pm else None,
            "holdout_days": pm["holdout_days"] if pm else None, "n_folds": N_FOLDS,
            "n_families": len(fams), "n_grid_configs": (pm or {}).get("n_grid"),
            "n_configs_tested": ((pm or {}).get("n_grid", 0) * (pm or {}).get("n_scopes", 0)
                                 + sum(f["configs"] * f["scopes_tested"] for f in (px or {}).get("families", []))
                                 + sum(f["configs"] * f["scopes_tested"] for f in (pr or {}).get("families", []))),
            "n_walk_forwards": (pm or {}).get("n_walk_forwards", 0) + sum(f["scopes_tested"] for f in (px or {}).get("families", [])),
            "n_holdout_tests": k, "t_bar_strict": t_bar, "stake": L3.STAKE,
            "grid_thinning": (pm or {}).get("quick") or 1,
            "shortlist": f"walk-forward P&L > 0, t >= {L3.T_SHORT}, >= {L3.SHORT_TRADES} trades, >= half of test folds profitable",
            "rules": RULES(t_bar), "caveats": CAVEATS, "summary": summary,
            "parts": {
                "models": None if not pm else {"what": "lab3 families on new 15-minute series", "start": pm["start"],
                                               "cut": pm["cut"], "holdout_days": pm["holdout_days"],
                                               "groups": {g: [cname(x) for x in v] for g, v in pm["groups"].items()},
                                               "quick": pm.get("quick")},
                "xmkt": None if not px else {"what": "structural / cross-market families on crypto 15-min + hourly data",
                                             "start": px["start"], "cut": px["cut"], "holdout_days": px["holdout_days"],
                                             "data": px["data"]},
                "range": None if not pr else {"what": "range sums on the 15-minute coin race", "start": pr["start"],
                                              "cut": pr["cut"], "holdout_days": pr["holdout_days"], "data": pr["data"]}},
            "data_sources": {"kalshi": "public trade API (markets, 1-minute candlesticks)",
                             "fx_metals_energy_index": "Yahoo Finance 1-minute bars: FX spot (EURUSD=X ...), front-month "
                                                       "futures for metals/energy (GC=F, SI=F, HG=F, PL=F, PA=F, CL=F, NG=F); "
                                                       "not Pyth, see caveats",
                             "yields": "Yahoo 1-minute Treasury futures, inverted, as the yield proxy: ZT=F (2Y), ZF=F (5Y), "
                                       "ZN=F (10Y), ZB=F (30Y)",
                             "crypto": "Coinbase 1-minute candles (existing lab data)",
                             "tried_and_failed": ["Pyth Benchmarks TradingView shim (404, sunset Aug 2026)",
                                                  "Pyth Pro history API (401, needs an API key)",
                                                  "Hermes historical price updates (401)",
                                                  "Dukascopy datafeed (TLS connection reset from this machine)"]},
        },
        "coins": (pm or {}).get("coins", {}),
        "markets_surveyed": surveyed,
        "families": fams,
        "baselines": [{kk: v for kk, v in b.items() if kk != "_wsum"} for b in (pm["baselines"] if pm else [])],
        "candidates": pub,
        "heatmaps": (pm or {}).get("heatmaps", []),
    }
    dest = Path(out_path) if out_path else OUT
    dest.write_text(json.dumps(res, default=L3._jd))
    print(f"strict bar t >= {t_bar} over {k} holdout tests")
    for c in pub[:60]:
        h = c["holdout"]
        print(f"  {c['status']:6s} {c['id']:36s} ${h['pnl']:>8} n={h['trades']:>5} t={h['t']:>5} ${c['per_day']:>7}/day "
              f"d1 t={c['delay1']['t']} | {c['why'][:110]}")
    print(f"-> {dest}")
    return res


def archive_step():
    """Blind archive test of every frozen model candidate whose scope contains a series with downloaded
    Kalshi archive data (markets before Sep 4). Writes into the models part file; no settings change."""
    pm = json.loads(PART_MODELS.read_text())
    GROUPS.clear()
    GROUPS.update(pm["groups"])
    have = [s for s in pm["coins"] if (F.LDIR / f"{s}_markets_arch.csv").exists()
            and (F.LDIR / f"{s}_candles_hist.part.csv").exists() and (F.LDIR / f"{s}_spot_arch.csv").exists()]
    L3.G.update({"arch": {}, "quick": pm.get("quick", 0)})
    for s in have:
        L3._SPOT[(s, "archive")] = L3.Spot(F.LDIR / f"{s}_spot_arch.csv")
        df, _ = build_panel4(s, "archive")
        p = B.Panel(df)
        L3.add_features(p, s, "archive")
        L3.G["arch"][s] = L3.Ctx(s, p)
        print(f"  archive {s}: {len(p)} markets {pd.to_datetime(p.open_ts.min(), unit='s'):%m-%d}.."
              f"{pd.to_datetime(p.open_ts.max(), unit='s'):%m-%d}", flush=True)
    for c in pm["candidates"]:
        ac = [x for x in _coins_of(c["scope"]) if x in L3.G["arch"]]
        if not ac:
            continue
        rule = c["rule"]
        if rule.get("per_coin"):
            rule = {**rule, "params": {k: v for k, v in rule["params"].items()}}
        norms = c.get("_norms")
        a = L3.run_rule("arch", c["scope"], rule, norms=norms)
        c["archive"] = {**L3.summ(a), "coins": [cname(x) for x in ac]}
        if len(a):
            mo = pd.to_datetime(a.ts, unit="s").dt.strftime("%Y-%m")
            c["archive"]["monthly_pnl"] = {k: round(float(v), 2) for k, v in a.groupby(mo).pnl.sum().items()}
        print(f"  {c['id']:32s} archive ${c['archive']['pnl']:>8} n={c['archive']['trades']:>5} t={c['archive']['t']}", flush=True)
    for s in have:
        pm["coins"][s]["archive_markets"] = len(L3.G["arch"][s])
        pm["coins"][s]["archive_span"] = (f"{pd.to_datetime(L3.G['arch'][s].open_ts.min(), unit='s'):%Y-%m-%d} to "
                                          f"{pd.to_datetime(L3.G['arch'][s].open_ts.max(), unit='s'):%Y-%m-%d}")
    pm["archive_series"] = have
    PART_MODELS.write_text(json.dumps(pm, default=L3._jd))


def main(args):
    cmd = args[0] if args else "help"
    if cmd == "survey":
        ser = [s for s in sum(GROUPS_ALL.values(), [])]
        F.survey(ser, out=SURVEY)
    elif cmd == "download":
        ser = args[1:] or testable_candidates()
        for s in ser:
            F.download(s)
    elif cmd == "models":
        quick = int(args[1]) if len(args) > 1 else 0
        models(quick=quick)
    elif cmd == "xmkt":
        xmkt()
    elif cmd == "range":
        range_arb()
    elif cmd == "archive":
        archive_step()
    elif cmd == "judge":
        judge()
    else:
        print(__doc__)


def testable_candidates():
    sv = json.loads(SURVEY.read_text()) if SURVEY.exists() else {}
    return [s for s, r in sv.items() if r.get("markets") and r.get("span_days", 0) >= MIN_DAYS
            and r.get("median_volume", 0) >= MIN_MED_VOLUME and underlying(s) is not None]
