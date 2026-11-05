"""Lab 3: hunt for strategies that beat the live ones, under a strict protocol.

    nice -n 19 python -m kalshi15m lab3 --workers 2      -> data/lab/lab3_results.json

Protocol (fixed in code before any holdout number is computed):
 1. Same locked holdout as lab.py: markets opening in the last 15 days, one calendar cut for
    every coin (cut = earliest "last market" across coins minus 15 days). The search window is
    the common span before it (from the latest "first market" across coins to the cut).
 2. Each idea is a FAMILY with a parameter grid. For every family and scope (each of the 9 coins
    on its own, and all 9 pooled with one parameter set) every config is scored on the search
    window, cut into 5 calendar folds. Walk-forward: for folds 2..5 the config with the best P&L
    on all earlier folds (>= 30 trades) is traded untouched on that fold.
 3. Shortlist = walk-forward P&L > 0, t >= 1.5, >= 50 trades, >= half the test folds profitable.
 4. Final exam: tune on the whole search window, freeze, run ONCE on the holdout; also run the
    frozen rule one minute late (latency check) and on older blind "archive" data (NEAR, DOGE,
    BNB Apr-Aug archive files, SOL Apr-Aug from its own file).
 5. Strict bar = one-sided Bonferroni at 5% over every candidate that reached the exam.

Everything is per market (one bet per market, decided only from columns <= the decision minute),
so the per-market P&L of a config can be computed once and split by fold / pooled over coins.
Nothing in here is used by the live bot.
"""
from __future__ import annotations

import itertools
import json
import math
import os
import time
from multiprocessing import Pool
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import backtest as B
from . import data as D
from . import lab2
from .lab import SESSIONS, _session_wrap
from .strategies import MIN, STRATEGIES, _first, _valid, ndtr

OUT = D.DATA_DIR.parent / "lab" / "lab3_results.json"
ARCH_DIR = D.DATA_DIR / "archive"
COINS = list(D.SERIES)
HOLDOUT_DAYS, N_FOLDS, MIN_TRADES = 15, 5, 30
T_SHORT, SHORT_TRADES, STAKE = 1.5, 50, 10.0
MIN_ARCH_TRADES = 50
ARCH_COINS = ("KXNEAR15M", "KXDOGE15M", "KXBNB15M", "KXSOL15M")
BANDS = {"05-95": (0.05, 0.95), "10-90": (0.10, 0.90), "15-85": (0.15, 0.85), "20-80": (0.20, 0.80),
         "25-75": (0.25, 0.75)}
TAU = (15 - MIN).astype(float)[None, :]          # minutes left after column j
SQMIN = np.sqrt(MIN.astype(float))[None, :]
MAX_WORKERS = 2                                    # the live bots share this machine
BOT_LOG = D.DATA_DIR / "bot_log.jsonl"

np.seterr(all="ignore")


def cname(s):
    return "All 9 coins" if s == "ALL" else s[2:-3]


# =========================================================================== spot + features
class Spot:
    """1-minute spot bars on a full minute grid (gaps forward-filled, as build_panel does)."""

    def __init__(self, path):
        sp = pd.read_csv(path).drop_duplicates("ts").sort_values("ts")
        self.t0 = int(sp.ts.iloc[0])
        n = int((int(sp.ts.iloc[-1]) - self.t0) // 60) + 1
        grid = self.t0 + 60 * np.arange(n, dtype=np.int64)
        sp = sp.set_index("ts").reindex(grid).ffill()
        self.ts = grid
        self.c = sp.close.to_numpy(float)
        self.h = sp.high.to_numpy(float)
        self.l = sp.low.to_numpy(float)
        self.lc = np.log(self.c)
        self.lr = np.r_[np.nan, np.diff(self.lc)]
        self.v60 = pd.Series(self.lr).rolling(60, min_periods=30).std().to_numpy()

    def at(self, arr, ts):
        """Value of a per-bar array for the bar starting at `ts` (NaN outside the data)."""
        ts = np.asarray(ts, np.int64)
        idx = (ts - self.t0) // 60
        ok = (idx >= 0) & (idx < len(arr))
        out = np.full(ts.shape, np.nan)
        out[ok] = arr[idx[ok]]
        return out

    def idx(self, ts):
        return int(min(max((ts - self.t0) // 60, 0), len(self.c)))


_SPOT = {}


def spot(series, where="main"):
    key = (series, where)
    if key not in _SPOT:
        folder = ARCH_DIR if where == "archive" else D.DATA_DIR
        _SPOT[key] = Spot(folder / f"{series}_spot.csv")
    return _SPOT[key]


def _tod_ratio(sp: Spot, open_ts, lookback=14):
    """Time-of-day volatility: f(15-min slot) = trailing-14-day mean squared 1-min return in that
    slot / overall mean (only days BEFORE the market's day). Returns forward/backward ratio so that
    vol60 * sqrt(ratio) estimates the vol of the market's own slot instead of the last hour."""
    g = sp.ts // 900
    df = pd.DataFrame({"g": g, "r2": sp.lr ** 2}).dropna()
    agg = df.groupby("g").r2.agg(["sum", "count"])
    d0 = int(g.min() // 96)
    d1 = int(g.max() // 96) + 1
    S = np.zeros(((d1 - d0) * 96,))
    C = np.zeros_like(S)
    S[agg.index.to_numpy() - d0 * 96] = agg["sum"].to_numpy()
    C[agg.index.to_numpy() - d0 * 96] = agg["count"].to_numpy()
    S, C = S.reshape(-1, 96), C.reshape(-1, 96)
    cs, cc = np.cumsum(np.r_[np.zeros((1, 96)), S], 0), np.cumsum(np.r_[np.zeros((1, 96)), C], 0)
    nd = S.shape[0]
    f = np.ones((nd, 96))
    for d in range(nd):
        lo = max(0, d - lookback)
        ws, wc = cs[d] - cs[lo], cc[d] - cc[lo]       # days lo..d-1
        if wc.sum() < 3 * 1440:
            continue
        slot = ws / np.maximum(wc, 1)
        slot = (np.roll(slot, 1) + slot + np.roll(slot, -1)) / 3   # smooth neighbouring slots
        f[d] = slot / (ws.sum() / wc.sum())
    flat = f.reshape(-1)

    def F(gg):
        k = gg - d0 * 96
        ok = (k >= 0) & (k < len(flat))
        out = np.ones(gg.shape)
        out[ok] = flat[k[ok]]
        return out
    g0 = np.asarray(open_ts, np.int64) // 900
    fwd = F(g0)
    b1, b2, b3, b4 = F(g0 - 1), F(g0 - 2), F(g0 - 3), F(g0 - 4)
    m = MIN[None, :].astype(float)
    back = (m * fwd[:, None] + 15 * (b1 + b2 + b3)[:, None] + (15 - m) * b4[:, None]) / 60
    return fwd[:, None] / back


def _emp_probs(sp: Spot, panel, lookbacks=(7, 21), vms=(0.7, 0.8, 0.9, 1.0, 1.1, 1.25)):
    """Bootstrap fair value: P(YES) from the empirical distribution of this coin's own
    vol-standardised tau-minute returns over the trailing `lookback` days (samples end before the
    market's day starts, so nothing from the future)."""
    P = panel.P
    n = len(panel)
    x = np.log(P["spot"] / P["strike"])
    sig = P["vol1m"]
    days = np.asarray(panel.open_ts, np.int64) // 86400
    N = len(sp.lc)
    U = {}
    for tau in range(1, 15):
        u = np.full(N, np.nan)
        u[:N - tau] = (sp.lc[tau:] - sp.lc[:-tau]) / (sp.v60[:N - tau] * math.sqrt(tau))
        U[tau] = u
    out = {(lb, vm): np.full((n, 14), np.nan) for lb in lookbacks for vm in vms}
    for d in np.unique(days):
        rows = np.nonzero(days == d)[0]
        dstart = int(d) * 86400
        for lb in lookbacks:
            lo, hi = sp.idx(dstart - lb * 86400), sp.idx(dstart - 900)
            if hi - lo < 1440:
                continue
            for j in range(14):
                tau = 14 - j
                s = U[tau][lo:hi:2]
                s = np.sort(s[np.isfinite(s)])
                if len(s) < 500:
                    continue
                xz = x[rows, j] / (sig[rows, j] * math.sqrt(tau))
                for vm in vms:
                    z = xz / vm
                    p = 1 - np.searchsorted(s, -z, side="right") / len(s)
                    p[~np.isfinite(z)] = np.nan
                    out[(lb, vm)][rows, j] = p
    return out


def add_features(panel, series, where="main"):
    """Extra per market x minute arrays. All use only data up to the end of that minute."""
    P = panel.P
    sp = spot(series, where)
    ref_series = "KXETH15M" if series == "KXBTC15M" else "KXBTC15M"
    ref = spot(ref_series, "main")
    ots = np.asarray(panel.open_ts, np.int64)
    T = ots[:, None] + 60 * MIN[None, :].astype(np.int64)
    bar = T - 60
    P["hour"] = np.repeat(((ots % 86400) // 3600)[:, None], 14, axis=1).astype(float)
    P["dow"] = np.repeat((((ots // 86400) + 3) % 7)[:, None], 14, axis=1).astype(float)  # 0 = Monday
    s = pd.Series(sp.lr)
    r2 = s ** 2
    hl = pd.Series(np.log(sp.h / sp.l) ** 2 / (4 * math.log(2)))
    bp = pd.Series(np.abs(sp.lr) * np.abs(np.r_[np.nan, sp.lr[:-1]]))
    vols = {
        "v15": s.rolling(15, min_periods=10).std(),
        "v30": s.rolling(30, min_periods=20).std(),
        "ewma30": np.sqrt(r2.ewm(halflife=30, min_periods=30).mean()),
        "ewma60": np.sqrt(r2.ewm(halflife=60, min_periods=60).mean()),
        "ewma120": np.sqrt(r2.ewm(halflife=120, min_periods=120).mean()),
        "park": np.sqrt(hl.rolling(60, min_periods=30).mean()),
        "bpv": np.sqrt(math.pi / 2 * bp.rolling(60, min_periods=30).mean()),
    }
    for k, v in vols.items():
        P["vol_" + k] = sp.at(np.asarray(v, float), bar)
    lc_now = sp.at(sp.lc, bar)
    for L in (1, 2, 3, 5, 10, 15):
        P[f"r{L}"] = lc_now - sp.at(sp.lc, bar - 60 * L)
    rl_now = ref.at(ref.lc, bar)
    for L in (1, 2, 3, 5):
        P[f"ref_r{L}"] = rl_now - ref.at(ref.lc, bar - 60 * L)
    P["ref_v60"] = ref.at(ref.v60, bar)
    P["ref_z"] = (rl_now - ref.at(ref.lc, ots - 60)[:, None]) / (P["ref_v60"] * SQMIN)
    P["tod_ratio"] = _tod_ratio(sp, ots)
    for (lb, vm), arr in _emp_probs(sp, panel).items():
        P[f"emp{lb}_{vm}"] = arr
    return panel


# =========================================================================== context + models
class Ctx:
    """A panel plus a per-task cache of model probabilities and masks."""

    def __init__(self, series, panel, fold=None):
        self.series, self.panel, self.P = series, panel, panel.P
        self.result = np.asarray(panel.result, int)
        self.open_ts = np.asarray(panel.open_ts, np.int64)
        self.fold = fold
        self.cache = {}

    def __len__(self):
        return len(self.open_ts)

    def vol(self, key):
        P = self.P
        if key == "60":
            return P["vol1m"]
        if key == "240":
            return P["vol240"]
        if key == "blend":
            return np.sqrt((P["vol1m"] ** 2 + P["vol240"] ** 2) / 2)
        if key == "max":
            return np.fmax(P["vol1m"], P["vol240"])
        if key == "blend_ewma":
            return np.sqrt((P["vol_ewma60"] ** 2 + P["vol240"] ** 2) / 2)
        if key == "inmkt90":
            ck = ("vol", key)
            if ck not in self.cache:
                self.cache[ck] = lab2._ewma_vol(P, 0.9)
            return self.cache[ck]
        if key == "tod":
            return P["vol1m"] * np.sqrt(P["tod_ratio"])
        if key == "tod_ewma60":
            return P["vol_ewma60"] * np.sqrt(P["tod_ratio"])
        return P["vol_" + key]

    def drift(self, d):
        kind, L, a = d
        P = self.P
        if kind == "mom":                     # a share of the last L-minute move continues
            return a * P[f"r{L}"]
        sig = P["vol1m"]                      # residual catch-up to BTC (ETH for BTC)
        if L == "open":
            x = np.log(P["spot"] / P["strike"])
            return a * (P["ref_z"] * sig * SQMIN - x)
        return a * (P[f"ref_r{L}"] * sig / P["ref_v60"] - P[f"r{L}"])

    def prob(self, model="norm", vol="60", vm=1.0, tau_adj=0.0, nu=None, shape=None, drift=None, lb=None):
        key = ("p", model, vol, vm, tau_adj, nu, shape, drift, lb)
        if key in self.cache:
            return self.cache[key]
        P = self.P
        if model == "emp":
            p = P[f"emp{lb}_{vm}"]
        else:
            x = np.log(P["spot"] / P["strike"])
            if drift is not None:
                x = x + self.drift(drift)
            tau = np.maximum(TAU - tau_adj, 0.25)
            z = x / (self.vol(vol) * vm * np.sqrt(tau))
            if model == "norm":
                p = ndtr(z)
            else:
                p = tcdf(z * math.sqrt(nu / (nu - 2)), nu)
        if shape is not None:
            q = np.clip(p, 1e-9, 1 - 1e-9)
            p = 1 / (1 + np.exp(-shape * np.log(q / (1 - q))))
        self.cache[key] = p
        return p

    def band(self, band, ref="ask"):
        key = ("band", band, ref)
        if key not in self.cache:
            P = self.P
            lo, hi = BANDS[band]
            if ref == "ask":
                ya, na = P["yes_ask"], P["no_ask"]
            else:
                ya, na = P["yes_bid"], 1 - P["yes_ask"]
            self.cache[key] = (_valid(ya) & (ya >= lo) & (ya <= hi), _valid(na) & (na >= lo) & (na <= hi), ya, na)
        return self.cache[key]

    def gaps(self, pkey, p, ref="ask"):
        key = ("gap", pkey, ref)
        if key not in self.cache:
            _, _, ya, na = self.band("05-95", ref)
            self.cache[key] = (p - ya, (1 - p) - na)
        return self.cache[key]


def tcdf(x, nu):
    """Student-t CDF for integer nu (closed form, Abramowitz & Stegun 26.7.3/26.7.4)."""
    nu = int(nu)
    th = np.arctan(x / math.sqrt(nu))
    s, c2 = np.sin(th), np.cos(th) ** 2
    if nu % 2 == 1:
        acc, term = np.ones_like(th), np.ones_like(th)
        for k in range(1, (nu - 3) // 2 + 1):
            term = term * (2 * k) / (2 * k + 1) * c2
            acc = acc + term
        out = 0.5 + (th + (s * np.cos(th) * acc if nu >= 3 else 0)) / math.pi
    else:
        acc, term = np.ones_like(th), np.ones_like(th)
        for k in range(1, (nu - 2) // 2 + 1):
            term = term * (2 * k - 1) / (2 * k) * c2
            acc = acc + term
        out = 0.5 + 0.5 * s * acc
    return out


def fv_masks(ctx, p, pkey, start, end, edge, band, ref="ask", req=None):
    """YES/NO masks: quote inside the band and cheaper than the model by the required edge."""
    by, bn, _, _ = ctx.band(band, ref)
    gy, gn = ctx.gaps(pkey, p, ref)
    win = ((MIN >= start) & (MIN <= end))[None, :]
    e = edge if req is None else req
    y = win & by & (gy >= e)
    n = win & bn & (gn >= e)
    return y, n


def first(y, n):
    both = y & n
    if both.any():
        y, n = y & ~both, n & ~both
    return _first(y, n)


# =========================================================================== families
FAMILIES: dict = {}
BASE = {"start": [2, 3, 4, 5, 7], "end": [10, 11, 12, 13],
        "edge": [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.16, 0.18, 0.20, 0.24],
        "band": ["05-95", "10-90", "15-85", "20-80", "25-75"]}
VM6 = [0.7, 0.8, 0.9, 1.0, 1.1, 1.25]
BANDS5 = ["05-95", "10-90", "15-85", "20-80", "25-75"]


def family(fid, name, idea, grid, kind="hold", heat=None, single=True, needs_ref=False):
    """Register a family. kind: hold (taker, hold to settlement) | maker | makerfv | scalp | sized.
    heat: (x, y) parameter names for the sensitivity heatmap. single: a single-model signal that
    may join an ensemble of survivors."""
    def deco(fn):
        FAMILIES[fid] = {"id": fid, "name": name, "idea": idea, "grid": grid, "kind": kind, "fn": fn,
                         "heat": heat, "single": single and kind == "hold", "needs_ref": needs_ref}
        return fn
    return deco


def _std(ctx, c, model="norm", **kw):
    pk = (model, tuple(sorted(kw.items())))
    p = ctx.prob(model=model, **kw)
    return p, pk


@family("fv_ref", "Live model, re-tuned (control)",
        "The model already live (bell-curve fair value vs the ask), re-tuned on a wider grid. It is the "
        "control: a new idea has to do better than simply re-tuning what we have.",
        {**BASE, "vol": ["60", "blend", "240", "max"], "vm": [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5]},
        heat=("edge", "vm"))
def f_ref(ctx, c):
    p, pk = _std(ctx, c, vol=c["vol"], vm=c["vm"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("fv_t", "Fat-tail fair value",
        "Price the contract with a fat-tailed (Student-t) distribution instead of the bell curve, so "
        "big moves before the close count as more likely. Long shots have been winning live.",
        {**BASE, "nu": [3, 4, 5, 7, 10, 20], "vol": ["60", "blend"], "vm": VM6}, heat=("edge", "nu"))
def f_t(ctx, c):
    p, pk = _std(ctx, c, model="t", nu=c["nu"], vol=c["vol"], vm=c["vm"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("fv_emp", "Bootstrap fair value",
        "No formula: the chance of finishing above the strike is read off this coin's own recent "
        "history of similar-sized moves (last 7 or 21 days of 1-minute prices).",
        {**BASE, "lb": [7, 21], "vm": VM6}, heat=("edge", "vm"))
def f_emp(ctx, c):
    p, pk = _std(ctx, c, model="emp", lb=c["lb"], vm=c["vm"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("fv_shape", "Recalibrated fair value",
        "Stretch or squash the model's probabilities toward or away from 50% (a calibration slope) "
        "to correct a model that is systematically over- or under-confident.",
        {**BASE, "a": [0.6, 0.7, 0.8, 0.9, 1.1, 1.25, 1.5], "vm": [0.8, 1.0, 1.25]}, heat=("edge", "a"))
def f_shape(ctx, c):
    p, pk = _std(ctx, c, vm=c["vm"], shape=c["a"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("fv_vol", "Better volatility",
        "Same model, but measure volatility better: exponentially weighted, high/low range "
        "(Parkinson), jump-robust (bipower), shorter windows, or the larger of 1h and 4h.",
        {**BASE, "vol": ["v15", "v30", "ewma30", "ewma60", "ewma120", "park", "bpv", "max", "inmkt90",
                         "blend_ewma"], "vm": VM6}, heat=("edge", "vm"))
def f_vol(ctx, c):
    p, pk = _std(ctx, c, vol=c["vol"], vm=c["vm"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("fv_season", "Time-of-day volatility",
        "Crypto is calmer at some hours than others. Scale volatility by how this 15-minute slot of "
        "the day has behaved over the previous two weeks.",
        {**BASE, "vol": ["tod", "tod_ewma60"], "vm": VM6}, heat=("edge", "vm"))
def f_season(ctx, c):
    p, pk = _std(ctx, c, vol=c["vol"], vm=c["vm"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("fv_tau", "Settlement-average timing",
        "Kalshi settles on an average of the final minute, which leaves less real time for the price "
        "to move than the clock says. Shorten (or lengthen) the time left in the model.",
        {**BASE, "tau_adj": [-1.0, -0.5, 0.33, 0.67, 1.0], "vm": [0.8, 1.0, 1.25]}, heat=("edge", "tau_adj"))
def f_tau(ctx, c):
    p, pk = _std(ctx, c, vm=c["vm"], tau_adj=c["tau_adj"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("fv_drift", "Momentum-aware fair value",
        "Assume part of the coin's last few minutes of movement carries on (or reverses) and build "
        "that drift into the fair value.",
        {**BASE, "L": [1, 2, 3, 5, 10, 15], "a": [-0.5, -0.25, 0.25, 0.5, 1.0], "vm": [0.8, 1.0]}, heat=("edge", "a"))
def f_drift(ctx, c):
    p, pk = _std(ctx, c, vm=c["vm"], drift=("mom", c["L"], c["a"]))
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("fv_btcdrift", "BTC catch-up fair value",
        "If BTC (ETH for BTC itself) has just moved more than this coin, assume the coin partly catches "
        "up and build that into the fair value.",
        {**BASE, "L": [1, 2, 3, 5, "open"], "a": [-0.5, 0.25, 0.5, 1.0], "vm": [0.8, 1.0]}, heat=("edge", "a"),
        needs_ref=True)
def f_btcdrift(ctx, c):
    p, pk = _std(ctx, c, vm=c["vm"], drift=("res", c["L"], c["a"]))
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("fv_dyn", "Dynamic edge",
        "Ask for a bigger (or smaller) mispricing depending on minutes left, the bid-ask spread and "
        "the price level, instead of one fixed 12-cent gap.",
        {"start": [2, 3, 5], "end": [11, 13], "band": BANDS5,
         "e0": [0.04, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16], "e_tau": [-0.06, -0.03, 0.0, 0.03, 0.06, 0.10],
         "k_spr": [0.0, 0.5, 1.0, 1.5], "rel": [0.0, 0.2, 0.35, 0.5], "vm": [0.8, 1.0]}, heat=("e0", "e_tau"))
def f_dyn(ctx, c):
    P = ctx.P
    p, pk = _std(ctx, c, vm=c["vm"])
    spr = P["yes_ask"] - P["yes_bid"]
    req = np.maximum(c["e0"] + c["e_tau"] * (TAU - 1) / 12 + c["k_spr"] * spr, 0.02)
    y, n = fv_masks(ctx, p, pk, c["start"], c["end"], 0, c["band"], req=req)
    if c["rel"]:
        gy, gn = ctx.gaps(pk, p)
        y &= gy >= c["rel"] * P["yes_ask"]
        n &= gn >= c["rel"] * P["no_ask"]
    return y, n, p


@family("fv_vreg", "Volatility-regime filter",
        "Only trade when short-term volatility is clearly above (rising) or below (calming) the "
        "4-hour level.",
        {**BASE, "reg": ["<0.7", "<0.85", "<1.0", ">1.0", ">1.15", ">1.3"], "vm": [0.8, 1.0, 1.25]})
def f_vreg(ctx, c):
    P = ctx.P
    p, pk = _std(ctx, c, vm=c["vm"])
    y, n = fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"])
    r, th = P["vol1m"] / P["vol240"], float(c["reg"][1:])
    keep = r < th if c["reg"][0] == "<" else r > th
    return y & keep, n & keep, p


@family("fv_liq", "Spread / stale-quote filter",
        "Only trade when the Kalshi spread is tight, and/or only when the quote has (or has not) just "
        "moved, and/or contracts actually traded that minute.",
        {**BASE, "max_spr": [0.01, 0.02, 0.03, 0.05, 0.10], "quote": ["any", "stale", "moved"],
         "min_vol": [0, 1], "vm": [0.8, 1.0]}, heat=("edge", "max_spr"))
def f_liq(ctx, c):
    P = ctx.P
    p, pk = _std(ctx, c, vm=c["vm"])
    y, n = fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"])
    keep = (P["yes_ask"] - P["yes_bid"]) <= c["max_spr"] + 1e-9
    if c["quote"] != "any":
        mid = (P["yes_ask"] + P["yes_bid"]) / 2
        dm = np.full_like(mid, np.nan)
        dm[:, 1:] = np.abs(mid[:, 1:] - mid[:, :-1])
        keep &= (dm < 0.005) if c["quote"] == "stale" else (dm >= 0.01)
    if c["min_vol"]:
        keep &= np.nan_to_num(P["volume"]) >= c["min_vol"]
    return y & keep, n & keep, p


@family("fv_lag", "Fresh spot move, lagging quote",
        "Only trade when the gap was opened by a spot move in the last 1-2 minutes (the model jumped) "
        "and, optionally, the Kalshi quote has not yet followed.",
        {**BASE, "r": [1, 2], "k": [0.25, 0.5, 1.0], "qlag": ["any", "lag"], "vm": [0.8, 1.0]}, heat=("edge", "k"))
def f_lag(ctx, c):
    P = ctx.P
    p, pk = _std(ctx, c, vm=c["vm"])
    y, n = fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"])
    r = c["r"]
    dp = np.full_like(p, np.nan)
    dp[:, r:] = p[:, r:] - p[:, :-r]
    y &= dp >= c["k"] * c["edge"]
    n &= -dp >= c["k"] * c["edge"]
    if c["qlag"] == "lag":
        mid = (P["yes_ask"] + P["yes_bid"]) / 2
        dm = np.full_like(mid, np.nan)
        dm[:, r:] = mid[:, r:] - mid[:, :-r]
        y &= dm < 0.5 * dp
        n &= dm > 0.5 * dp
    return y, n, p


@family("fv_cross", "BTC confirmation",
        "Only take the trade when BTC (ETH for BTC) has moved the same way since the open, or only "
        "when it has moved the other way (contrarian).",
        {**BASE, "mode": ["agree", "disagree"], "thr": [0.0, 0.5, 1.0, 1.5], "vm": [0.8, 1.0]}, heat=("edge", "thr"),
        needs_ref=True)
def f_cross(ctx, c):
    P = ctx.P
    p, pk = _std(ctx, c, vm=c["vm"])
    y, n = fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"])
    z, t = P["ref_z"], c["thr"]
    if c["mode"] == "agree":
        y &= (z > 0) & (z >= t)
        n &= (z < 0) & (z <= -t)
    else:
        y &= (z < 0) & (z <= -t)
        n &= (z > 0) & (z >= t)
    return y, n, p


@family("fv_jump", "Jump trigger",
        "Only trade right after a sudden 1-minute jump in spot (when Kalshi is most likely to lag), "
        "or only in calm minutes.",
        {**BASE, "jmode": [">1", ">1.5", ">2", ">3", "<0.5", "<1"], "vm": [0.8, 1.0]})
def f_jump(ctx, c):
    P = ctx.P
    p, pk = _std(ctx, c, vm=c["vm"])
    y, n = fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"])
    jz = np.abs(P["r1"]) / P["vol1m"]
    th = float(c["jmode"][1:])
    keep = jz > th if c["jmode"][0] == ">" else jz < th
    return y & keep, n & keep, p


_SESS = {"asia": (0, 8), "europe": (8, 14), "us": (14, 21), "late": (21, 24)}


@family("fv_session", "Session / weekday filter",
        "Live model limited to certain hours of the day (Asia, Europe, US, late US) or to weekdays or "
        "weekends only.",
        {**BASE, "sess": ["asia", "europe", "us", "late", "weekday", "weekend", "not_us", "asia_late"],
         "vm": [0.8, 1.0, 1.25]})
def f_session(ctx, c):
    P = ctx.P
    p, pk = _std(ctx, c, vm=c["vm"])
    y, n = fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"])
    h, dw, s = P["hour"], P["dow"], c["sess"]
    if s in _SESS:
        lo, hi = _SESS[s]
        keep = (h >= lo) & (h < hi)
    elif s == "weekday":
        keep = dw < 5
    elif s == "weekend":
        keep = dw >= 5
    elif s == "not_us":
        keep = (h < 14) | (h >= 21)
    else:  # asia_late
        keep = (h >= 21) | (h < 8)
    return y & keep, n & keep, p


@family("fv_prev", "Previous-window filter",
        "Only take the fair-value trade when the previous 15-minute window moved the same way as the bet "
        "(trend) or the opposite way (reversal), by at least a set number of standard deviations.",
        {**BASE, "pmode": ["with", "against"], "pz": [0.0, 1.0, 2.0], "vm": [0.8, 1.0]}, heat=("edge", "pz"))
def f_prev(ctx, c):
    P = ctx.P
    p, pk = _std(ctx, c, vm=c["vm"])
    y, n = fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"])
    z = P["prev_ret"] / (P["vol1m"] * math.sqrt(15))
    t = c["pz"]
    up, dn = (z > 0) & (z >= t), (z < 0) & (z <= -t)
    if c["pmode"] == "with":
        return y & up, n & dn, p
    return y & dn, n & up, p


_MEMBERS = {"fv+v2": ("fv", "v2"), "fv+bid": ("fv", "bid"), "fv+v2+bid": ("fv", "v2", "bid"),
            "fv+t4": ("fv", "t4"), "all4": ("fv", "v2", "bid", "t4")}


@family("ens_fixed", "Ensemble of live-style models",
        "Run several fair-value models side by side (bell curve, blended volatility, edge vs the bid, "
        "fat-tail) and take the first signal, or only signals two models agree on. One bet per market.",
        {**BASE, "members": list(_MEMBERS), "mode": ["first", "vote2"], "vm": [0.8, 1.0]}, single=False)
def f_ens(ctx, c):
    ms = []
    for m in _MEMBERS[c["members"]]:
        if m == "fv":
            p, pk = _std(ctx, c, vm=c["vm"])
            ms.append(fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]))
            p0 = p
        elif m == "v2":
            p, pk = _std(ctx, c, vol="blend", vm=c["vm"])
            ms.append(fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]))
        elif m == "bid":
            p, pk = _std(ctx, c, vm=c["vm"])
            ms.append(fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"], ref="bid"))
        else:
            p, pk = _std(ctx, c, model="t", nu=4, vm=c["vm"])
            ms.append(fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]))
    if c["mode"] == "first":
        y = np.logical_or.reduce([m[0] for m in ms])
        n = np.logical_or.reduce([m[1] for m in ms])
    else:
        y = np.sum([m[0] for m in ms], axis=0) >= 2
        n = np.sum([m[1] for m in ms], axis=0) >= 2
    return y, n, p0


@family("scalp", "Exit before settlement",
        "Buy on the same mispricing, then sell back at the bid once the price has converged to fair "
        "value, hit a profit target, or at a set minute, instead of holding to the close. Pays the "
        "taker fee both ways.",
        {"vm": [0.8, 1.0, 1.25], "edge": [0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.20], "start": [2, 3, 5],
         "end": [11, 13], "band": BANDS5,
         "exit": ["conv0", "conv2", "conv4", "conv6", "tp5", "tp10", "tp15", "tp20", "t8", "t10", "t12", "t14"]},
        kind="scalp", heat=("edge", "vm"))
def f_scalp(ctx, c):
    p, pk = _std(ctx, c, vm=c["vm"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("maker_fv", "Limit order at fair value minus edge",
        "Instead of paying the ask, rest a bid at (fair value - edge) for a few minutes; filled only "
        "if a seller comes down to it. Cheaper fee, but misses trades and risks bad fills.",
        {"vm": [0.8, 1.0, 1.25], "edge": [0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16], "wait": [1, 2, 3, 4],
         "start": [2, 3, 5], "end": [11, 13], "band": BANDS5},
        kind="makerfv", heat=("edge", "wait"))
def f_makerfv(ctx, c):
    p, pk = _std(ctx, c, vm=c["vm"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"], ref="bid"), p)


@family("fv_maker", "Live model as a maker",
        "The live model's signal, but executed by resting a bid at the best bid (+1c) for 1-3 minutes "
        "instead of buying at the ask.",
        {**BASE, "vm": [0.8, 1.0, 1.25], "wait": [1, 2, 3]}, kind="maker", heat=("edge", "wait"))
def f_maker(ctx, c):
    p, pk = _std(ctx, c, vm=c["vm"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


@family("sized", "Edge-scaled stakes",
        "Live model, but bet more when the model's edge is bigger (fractional Kelly), capped at 2-5x "
        "the average stake. Stakes are scaled so the average is about $10, to stay comparable.",
        {**BASE, "vm": [0.8, 1.0, 1.25], "cap": [2, 3, 5]}, kind="sized", heat=("edge", "cap"))
def f_sized(ctx, c):
    p, pk = _std(ctx, c, vm=c["vm"])
    return (*fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"]), p)


EXTRA_FAMILIES = {
    "pertune": ("Per-coin tuning with shrinkage",
                "One rule for all 9 coins, but each coin gets its own settings, chosen by that coin's own "
                "results plus the all-coin average (shrinkage), so thin data can't drive it alone."),
    "ens_best": ("Ensemble of the best survivors",
                 "For each coin, combine the 2-3 families with the best walk-forward record into one "
                 "first-to-fire rule (one bet per market)."),
}


_GRID_CACHE: dict = {}


def grid_list(grid):
    key = id(grid)
    if key not in _GRID_CACHE:
        keys = list(grid)
        full = [dict(zip(keys, v)) for v in itertools.product(*(grid[k] for k in keys))]
        _GRID_CACHE[key] = full[::G["quick"]] if G.get("quick") else full
    return _GRID_CACHE[key]


# =========================================================================== execution
def signal(ctx, fam, cfg):
    y, n, p = FAMILIES[fam]["fn"](ctx, cfg)
    side, minute = first(y, n)
    return side, minute, p


def _taker_fill(ctx, side, minute, delay):
    P = ctx.P
    idx = np.nonzero(side)[0]
    j = minute[idx] - 1
    fj = j + delay
    keep = fj <= 13
    idx, j, fj = idx[keep], j[keep], fj[keep]
    yes = side[idx] == 1
    price = np.where(yes, P["yes_ask"][idx, fj], P["no_ask"][idx, fj])
    good = np.isfinite(price) & (price > 0) & (price < 1)
    return idx[good], j[good], fj[good], yes[good], price[good]


def _fee(price, n, rate):
    return np.ceil(rate * n * price * (1 - price) * 100 - 1e-9) / 100


# --------------------------------------------------------------------------- real-money mode (LAB3_REAL=1)
# Every trade is scored the way the owner's real account would trade it: a $0.50 base stake (whole contracts,
# at least 1, at most 10, Kalshi's fee rounding at that size) and, for taker entries, weighted by the
# probability that the IOC order really fills and adjusted by how real fills differ from the candle backtest
# (data/lab/labx_fill_model.json, learned from 11,009 entries checked against Kalshi's trade tape).
REAL = os.environ.get("LAB3_REAL") == "1"
REAL_STAKE, REAL_MAX_N = 0.5, 10
_FM = None


def _fill_model():
    global _FM
    if _FM is None:
        _FM = json.loads((D.DATA_DIR.parent / "lab" / "labx_fill_model.json").read_text())
    return _FM


def _real_adjust(series, yes, j, price, n):
    """-> (fill probability, real - backtest $ per contract) per trade, from the fill model's cells."""
    fm = _fill_model()
    pb = np.clip(np.digitize(price, fm["price_bins"]) - 1, 0, len(fm["price_bins"]) - 2)
    mb = np.clip(np.digitize(j + 1, fm["minute_bins"]) - 1, 0, len(fm["minute_bins"]) - 2)
    grp = "thin" if series in fm["thin"] else "liquid"
    fill, gap = np.empty(len(price)), np.empty(len(price))
    for i in range(len(price)):
        side = "yes" if yes[i] else "no"
        c = (fm["cells"].get(f"{grp}|{side}|{pb[i]}|{mb[i]}") or fm["mid"].get(f"{grp}|{side}|{pb[i]}")
             or fm["top"].get(f"{side}|{pb[i]}") or fm["overall"])
        fill[i] = c["fill"] if c.get("fill") is not None else fm["overall"]["fill"]
        gap[i] = c["gap"] if c.get("gap") is not None else 0.0
    return fill, gap


def execute(ctx, fam, cfg, side, minute, p, delay=0, norm=None):
    """-> dict of per-trade arrays (m, j, fj, yes, price, n, fee, pnl, win, cost, stake)."""
    kind = FAMILIES[fam]["kind"] if fam in FAMILIES else "hold"
    P = ctx.P
    if kind in ("maker", "makerfv"):
        idx = np.nonzero(side)[0]
        j = minute[idx] - 1
        qj = j + delay
        keep = qj <= 13
        idx, j, qj = idx[keep], j[keep], qj[keep]
        yes = side[idx] == 1
        bid = np.where(yes, P["yes_bid"][idx, qj], 1 - P["yes_ask"][idx, qj])
        ask = np.where(yes, P["yes_ask"][idx, qj], P["no_ask"][idx, qj])
        if kind == "maker":
            better = np.round(bid + 0.01, 4)
            alone = better < ask - 1e-9
            price = np.where(alone, better, bid)
        else:
            q = np.where(yes, p[idx, j], 1 - p[idx, j])
            lim = np.floor((q - cfg["edge"]) * 100 + 1e-6) / 100
            price = np.round(np.minimum(lim, np.round(ask - 0.01, 2)), 4)
            alone = price > bid + 1e-9
        fill = np.full(len(idx), -1)
        for w in range(1, cfg.get("wait", 2) + 1):
            jj = np.minimum(qj + w, 13)
            inr = (qj + w) <= 13
            q_yes = np.fmin(P["ask_low"][idx, jj], P["trade_low"][idx, jj])
            q_no = 1 - np.fmax(P["bid_high"][idx, jj], P["trade_high"][idx, jj])
            reach = np.where(yes, q_yes, q_no)
            hit = np.where(alone, reach <= price + 1e-9, reach < price - 1e-9)
            new = inr & hit & (fill < 0) & np.isfinite(reach)
            fill = np.where(new, jj, fill)
        good = np.isfinite(price) & (price > 0) & (price < 1) & (fill >= 0)
        idx, j, fj, yes, price = idx[good], j[good], fill[good], yes[good], price[good]
        rate = B.MAKER_RATE
    else:
        idx, j, fj, yes, price = _taker_fill(ctx, side, minute, delay)
        rate = B.TAKER_RATE
    base = REAL_STAKE if REAL else STAKE
    stake = np.full(len(idx), base)
    if kind == "sized" and len(idx):
        q = np.where(yes, p[idx, j], 1 - p[idx, j])
        kel = np.clip((q - price) / (1 - price), 1e-4, None)
        nrm = norm if norm is not None else float(kel.mean())
        stake = base * np.minimum(kel / nrm, cfg["cap"])
    n = np.maximum(1, np.floor(stake / price + 1e-9))
    if REAL:
        n = np.minimum(n, REAL_MAX_N)
    fee = _fee(price, n, rate)
    win = (ctx.result[idx] == 1) == yes
    pnl = n * (win.astype(float) - price) - fee
    cost = n * price + fee
    exit_j = np.full(len(idx), -1)
    if kind == "scalp" and len(idx):
        ex = cfg["exit"]
        cols = np.arange(14)[None, :]
        sb = np.where(yes[:, None], P["yes_bid"][idx], 1 - P["yes_ask"][idx])
        ok = (cols > fj[:, None]) & np.isfinite(sb) & (sb > 0) & (sb < 1)
        if ex.startswith("conv"):
            q = np.where(yes[:, None], p[idx], 1 - p[idx])
            cond = sb >= q - int(ex[4:]) / 100
        elif ex.startswith("tp"):
            cond = sb >= price[:, None] + int(ex[2:]) / 100 - 1e-9
        else:
            cond = np.broadcast_to(cols == int(ex[1:]) - 1, sb.shape)
        hitm = ok & cond
        has = hitm.any(1)
        ej = np.argmax(hitm, 1)
        rows = np.arange(len(idx))
        sell = sb[rows, ej]
        f2 = _fee(sell, n, B.TAKER_RATE)
        pnl = np.where(has, n * (sell - price) - fee - f2, pnl)
        win = np.where(has, pnl > 0, win)
        exit_j = np.where(has, ej, -1)
    if REAL and len(idx) and kind not in ("maker", "makerfv"):
        fp, gap = _real_adjust(ctx.series, yes, j, price, n)
        pnl = fp * (pnl + n * gap)            # expected real result: it only counts when the order fills
        cost = fp * cost
    return {"m": idx, "j": j, "fj": fj, "yes": yes, "price": price, "n": n, "fee": fee, "pnl": pnl,
            "win": win, "cost": cost, "stake": stake, "exit_j": exit_j}


def to_df(ctx, tr):
    m = tr["m"]
    return pd.DataFrame({"ticker": ctx.panel.ticker[m], "series": ctx.series,
                         "ts": ctx.open_ts[m] + 60 * (tr["fj"] + 1), "side": np.where(tr["yes"], "yes", "no"),
                         "minute": tr["j"] + 1, "price": tr["price"], "contracts": tr["n"], "fee": tr["fee"],
                         "cost": tr["cost"], "win": tr["win"].astype(bool), "pnl": tr["pnl"], "stake": tr["stake"]})


def fold_agg(ctx, tr):
    """(N_FOLDS, 3): trades, sum P&L, sum P&L^2 per search fold."""
    f = ctx.fold[tr["m"]]
    out = np.zeros((N_FOLDS, 3))
    out[:, 0] = np.bincount(f, minlength=N_FOLDS)
    out[:, 1] = np.bincount(f, weights=tr["pnl"], minlength=N_FOLDS)
    out[:, 2] = np.bincount(f, weights=tr["pnl"] ** 2, minlength=N_FOLDS)
    return out


# =========================================================================== globals (fork-shared)
G = {"search": {}, "hold": {}, "arch": {}, "start": None, "cut": None}


def _search_task(args):
    fam, coin = args
    ctx = G["search"][coin]
    ctx.cache = {}
    cfgs = grid_list(FAMILIES[fam]["grid"])
    agg = np.zeros((len(cfgs), N_FOLDS, 3))
    for i, c in enumerate(cfgs):
        side, minute, p = signal(ctx, fam, c)
        agg[i] = fold_agg(ctx, execute(ctx, fam, c, side, minute, p))
    ctx.cache = {}
    return fam, coin, agg


# =========================================================================== walk-forward on aggregates
def tstat_agg(a):
    n, s, ss = a
    if n < 2:
        return 0.0
    var = (ss - s * s / n) / (n - 1)
    return float(s / n / math.sqrt(var / n)) if var > 0 else 0.0


def walk(agg, min_trades=MIN_TRADES):
    """Expanding-window walk-forward over the 5 search folds. Returns OOS stats, picks per fold,
    and the config tuned on the whole search window."""
    oos = np.zeros(3)
    picks, fold_pnl = [], []
    for k in range(1, N_FOLDS):
        tr = agg[:, :k, :].sum(1)
        score = np.where(tr[:, 0] >= min_trades, tr[:, 1], -np.inf)
        if not np.isfinite(score).any():
            picks.append(None)
            fold_pnl.append(0.0)
            continue
        c = int(np.argmax(score))
        picks.append(c)
        oos += agg[c, k]
        fold_pnl.append(float(agg[c, k, 1]))
    full = agg.sum(1)
    score = np.where(full[:, 0] >= min_trades, full[:, 1], -np.inf)
    final = int(np.argmax(score)) if np.isfinite(score).any() else None
    return {"oos": {"pnl": round(float(oos[1]), 2), "trades": int(oos[0]), "t": round(tstat_agg(oos), 2),
                    "fold_win": round(float(np.mean([x > 0 for x in fold_pnl])), 2)},
            "picks": picks, "final": final,
            "final_search": None if final is None else {"pnl": round(float(full[final, 1]), 2),
                                                        "trades": int(full[final, 0]),
                                                        "t": round(tstat_agg(full[final]), 2)}}


def shortlisted(w):
    o = w["oos"]
    return o["pnl"] > 0 and o["t"] >= T_SHORT and o["trades"] >= SHORT_TRADES and o["fold_win"] >= 0.5 \
        and w["final"] is not None


# =========================================================================== final exam
def summ(df):
    if df is None or len(df) == 0:
        return {"pnl": 0.0, "trades": 0, "t": 0.0, "win_rate": 0.0, "roi": 0.0, "per_trade": 0.0, "max_dd": 0.0,
                "sharpe_daily": 0.0, "days_positive": 0.0, "top_day_share": None}
    m = B.metrics(df)
    daily = df.groupby(df.ts // 86400).pnl.sum()
    pnl = float(df.pnl.sum())
    return {"pnl": round(pnl, 2), "trades": int(len(df)), "t": m["t_stat"], "win_rate": m["win_rate"],
            "roi": m["roi"], "per_trade": round(pnl / len(df), 3), "max_dd": m["max_dd"],
            "sharpe_daily": m["sharpe"], "days_positive": round(float((daily > 0).mean()), 3),
            "top_day_share": round(float(daily.max() / pnl), 3) if pnl > 0 else None,
            "avg_price": m["avg_price"], "avg_stake": round(float(df.stake.mean()), 2) if "stake" in df else STAKE}


def curve(df, n=300):
    if df is None or len(df) == 0:
        return []
    d = df.sort_values("ts")
    eq, ts = d.pnl.cumsum().round(2).to_numpy(), d.ts.to_numpy()
    idx = np.unique(np.r_[np.linspace(0, len(eq) - 1, min(n, len(eq))).astype(int), len(eq) - 1])
    return [[int(ts[i]), float(eq[i])] for i in idx]


def _coins_of(scope):
    return COINS if scope == "ALL" else [scope]


def run_rule(where, scope, rule, delay=0, norms=None):
    """rule: {"family", "params"} (params may be per-coin for pertune) or {"members": [...]} for
    ensembles of survivors. -> trades DataFrame pooled over the scope's coins."""
    pool = G[where]
    dfs = []
    for coin in _coins_of(scope):
        if coin not in pool or (rule.get("per_coin") and coin not in rule["params"]):
            continue
        ctx = pool[coin]
        ctx.cache = {}
        if "members" in rule:
            side, minute = ens_combine(ctx, rule["members"])
            tr = execute(ctx, "_ens", {}, side, minute, None, delay=delay)
        else:
            fam = rule["family"]
            cfg = rule["params"][coin] if rule.get("per_coin") else rule["params"]
            side, minute, p = signal(ctx, fam, cfg)
            nrm = (norms or {}).get(coin) if norms else None
            tr = execute(ctx, fam, cfg, side, minute, p, delay=delay, norm=nrm)
        dfs.append(to_df(ctx, tr))
        ctx.cache = {}
    dfs = [d for d in dfs if len(d)]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=["ts", "pnl"])


def ens_combine(ctx, members):
    """First-to-fire over member rules; same-minute disagreement -> no trade."""
    sides, mins = [], []
    for mb in members:
        s, m, _ = signal(ctx, mb["family"], mb["params"])
        sides.append(s)
        mins.append(np.where(s != 0, m, 99))
    S, M = np.array(sides), np.array(mins)
    best = M.min(0)
    at = (M == best[None, :]) & (S != 0)
    ys, ns = (at & (S == 1)).any(0), (at & (S == -1)).any(0)
    side = np.where(ys & ~ns, 1, np.where(ns & ~ys, -1, 0))
    return side.astype(int), np.where(best == 99, 1, best)


def _sized_norms(rule, scope):
    """Average Kelly fraction on the SEARCH window (pooled over the scope) -> stake normaliser."""
    fam, cfg = rule["family"], rule["params"]
    kels = []
    for coin in _coins_of(scope):
        ctx = G["search"][coin]
        ctx.cache = {}
        side, minute, p = signal(ctx, fam, cfg)
        idx, j, fj, yes, price = _taker_fill(ctx, side, minute, 0)
        q = np.where(yes, p[idx, j], 1 - p[idx, j])
        kels.append(np.clip((q - price) / (1 - price), 1e-4, None))
        ctx.cache = {}
    k = np.concatenate(kels) if kels else np.array([1.0])
    v = float(k.mean()) if len(k) else 1.0
    return {c: v for c in _coins_of(scope)}


def _final_task(cand):
    rule, scope = cand["rule"], cand["scope"]
    norms = _sized_norms(rule, scope) if rule.get("family") == "sized" else None
    hold = run_rule("hold", scope, rule, norms=norms)
    d1 = run_rule("hold", scope, rule, delay=1, norms=norms)
    arch_coins = [c for c in _coins_of(scope) if c in G["arch"]]
    fams = [m["family"] for m in rule["members"]] if "members" in rule else [rule["family"]]
    no_ref = any(FAMILIES[f]["needs_ref"] for f in fams)
    arch = run_rule("arch", scope, rule, norms=norms) if arch_coins and not no_ref else None
    out = {"holdout": summ(hold), "curve": curve(hold), "delay1": {k: v for k, v in summ(d1).items()
                                                                     if k in ("pnl", "t", "trades")},
           "archive": None if arch is None else {**summ(arch), "coins": [cname(c) for c in arch_coins]}}
    if arch_coins and no_ref:
        out["archive"] = {**summ(None), "coins": [cname(c) for c in arch_coins],
                          "note": "needs BTC/ETH prices, which the archive period lacks"}
    if arch is not None and len(arch):
        mo = pd.to_datetime(arch.ts, unit="s").dt.strftime("%Y-%m")
        out["archive"]["monthly_pnl"] = {k: round(float(v), 2) for k, v in arch.groupby(mo).pnl.sum().items()}
    out["holdout_by_coin"] = ({cname(c): round(float(g.pnl.sum()), 2) for c, g in hold.groupby("series")}
                              if scope == "ALL" and len(hold) else None)
    return cand["id"], out


# =========================================================================== baselines (the live book)
LIVE = [
    ("KXNEAR15M", "fair_value", {"start": 2, "end": 13, "edge": 0.12, "vol_mult": 1.0}, "NEAR fair value (live)"),
    ("KXHYPE15M", "fair_value", {"start": 2, "end": 13, "edge": 0.12, "vol_mult": 1.0}, "HYPE fair value (live)"),
    ("KXDOGE15M", "fair_value", {"start": 2, "end": 13, "edge": 0.12, "vol_mult": 1.0}, "DOGE fair value (live)"),
    ("KXDOGE15M", "fair_value_v2", {"start": 2, "end": 13, "edge": 0.12, "vol": "blend", "min_price": 0.2,
                                    "max_price": 0.8}, "DOGE fair value v2 (live)"),
    ("KXDOGE15M", "fair_value_bid", {"start": 5, "end": 13, "edge": 0.10, "vol_mult": 0.8, "min_price": 0.1,
                                     "max_price": 0.75}, "DOGE fair value vs bid (live)"),
    ("KXDOGE15M", "fair_value_bid@asia", {"start": 5, "end": 10, "edge": 0.10, "vol_mult": 0.8, "min_price": 0.1,
                                          "max_price": 0.9}, "DOGE fair value vs bid, Asia hours (live)"),
    ("KXHYPE15M", "fair_value@asia", {"start": 2, "end": 13, "edge": 0.16, "vol_mult": 1.0},
     "HYPE fair value, Asia hours (live)"),
    ("ALL", "fair_value", {"start": 2, "end": 13, "edge": 0.12, "vol_mult": 0.8}, "All 9 coins fair value (live)"),
    ("ALL", "fair_value_v2", {"start": 2, "end": 13, "edge": 0.12, "vol": "60", "min_price": 0.2, "max_price": 0.8},
     "All 9 coins fair value v2 (live)"),
]


def _strategy_fn(name):
    if "@" in name:
        base, sess = name.split("@")
        lo, hi = SESSIONS[sess]
        return _session_wrap(STRATEGIES[base][0], lo, hi)
    return STRATEGIES[name][0]


def _bt(where, coins, name, params, delay=0):
    fn = _strategy_fn(name)
    if delay:
        fn = lab2.delayed(fn, delay)
    dfs = [B.run(G[where][c].panel, fn, stake=STAKE, execution="taker", **params) for c in coins if c in G[where]]
    dfs = [d for d in dfs if len(d)]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=["ts", "pnl"])


def baselines():
    out = []

    def one(bid, label, scope, coins, name, params):
        h = _bt("hold", coins, name, params)
        s = _bt("search", coins, name, params)
        ac = [c for c in coins if c in G["arch"]]
        a = _bt("arch", ac, name, params) if ac else None
        out.append({"id": bid, "label": label, "scope": scope, "strategy": name, "execution": "taker",
                    "params": params, "holdout": summ(h), "curve": curve(h),
                    "search_insample": summ(s), "archive": None if a is None else {**summ(a), "coins": [cname(c) for c in ac]},
                    "delay1": {k: v for k, v in summ(_bt("hold", coins, name, params, 1)).items() if k in ("pnl", "t", "trades")}})
    for scope, name, params, label in LIVE:
        one(f"live:{scope}:{name}", label, scope, _coins_of(scope), name, params)
    for scope, name, params, label in LIVE:          # each coin's share of the pooled live rules
        if scope != "ALL":
            continue
        short = "fair value" if name == "fair_value" else "fair value v2"
        for c in COINS:
            one(f"live:ALL:{name}|{c}", f"{cname(c)} share of all-coin {short} (live)", c, [c], name, params)
    return out


# =========================================================================== heatmaps
def heatmap(fam, scope, final_idx, agg):
    hx, hy = FAMILIES[fam]["heat"] or (None, None)
    if not hx:
        return None
    cfgs = grid_list(FAMILIES[fam]["grid"])
    base = cfgs[final_idx]
    xs, ys = FAMILIES[fam]["grid"][hx], FAMILIES[fam]["grid"][hy]
    if not all(isinstance(v, (int, float)) for v in list(xs) + list(ys)):
        return None
    index = {tuple(sorted(c.items(), key=lambda kv: kv[0])): i for i, c in enumerate(cfgs)}
    full = agg.sum(1)
    z = []
    for yv in ys:
        row = []
        for xv in xs:
            c = dict(base, **{hx: xv, hy: yv})
            i = index.get(tuple(sorted(c.items(), key=lambda kv: kv[0])))
            row.append(None if i is None or full[i, 0] < MIN_TRADES else round(tstat_agg(full[i]), 2))
        z.append(row)
    return {"family": fam, "scope": scope, "x_name": hx, "y_name": hy, "x": list(xs), "y": list(ys), "z": z,
            "metric": "search t", "fixed": {k: v for k, v in base.items() if k not in (hx, hy)}}


# =========================================================================== labels
_EXIT = {"conv0": "sell once the bid reaches fair value", "conv2": "sell within 2c of fair value",
         "conv4": "sell within 4c of fair value", "conv6": "sell within 6c of fair value",
         "tp5": "sell at a 5c gain", "tp10": "sell at a 10c gain", "tp15": "sell at a 15c gain",
         "tp20": "sell at a 20c gain", "t8": "sell at minute 8", "t10": "sell at minute 10",
         "t12": "sell at minute 12", "t14": "sell at minute 14"}
_VOL = {"60": "1-hour vol", "blend": "1h+4h vol blend", "240": "4-hour vol", "max": "larger of 1h/4h vol",
        "v15": "15-min vol", "v30": "30-min vol", "ewma30": "fast weighted vol", "ewma60": "weighted vol",
        "ewma120": "slow weighted vol", "park": "high/low range vol", "bpv": "jump-robust vol",
        "inmkt90": "vol updated each minute", "blend_ewma": "weighted+4h vol blend", "tod": "time-of-day vol",
        "tod_ewma60": "time-of-day weighted vol"}
_SESSN = {"asia": "Asia hours", "europe": "Europe hours", "us": "US hours", "late": "late US hours",
          "weekday": "weekdays", "weekend": "weekends", "not_us": "outside US hours", "asia_late": "evening+Asia"}


def describe(fam, p):
    """Plain-English summary of a config, for labels."""
    e = p.get("edge", p.get("e0"))
    parts = [f"{e * 100:.0f}c edge"] if e is not None else []
    if fam == "fv_t":
        parts.append(f"tail thickness {p['nu']}")
    elif fam == "fv_emp":
        parts.append(f"last {p['lb']} days of moves")
    elif fam == "fv_shape":
        parts.append(f"calibration slope {p['a']}")
    elif fam == "fv_tau":
        parts.append(f"time left {-p['tau_adj']:+g} min")
    elif fam == "fv_drift":
        parts.append(f"{abs(p['a']) * 100:.0f}% of last {p['L']}-min move {'carries on' if p['a'] > 0 else 'reverses'}")
    elif fam == "fv_btcdrift":
        w = "since the open" if p["L"] == "open" else f"over {p['L']} min"
        parts.append(f"BTC catch-up x{p['a']} {w}")
    elif fam == "fv_dyn":
        parts.append(f"{p['e_tau'] * 100:+.0f}c early, +{p['k_spr']}x spread" + (f", gap >= {p['rel']:.0%} of price" if p["rel"] else ""))
    elif fam == "fv_vreg":
        parts.append(f"1h/4h vol ratio {p['reg']}")
    elif fam == "fv_liq":
        q = {"any": "", "stale": ", quote unchanged", "moved": ", quote just moved"}[p["quote"]]
        parts.append(f"spread <= {p['max_spr'] * 100:.0f}c{q}" + (", traded that minute" if p["min_vol"] else ""))
    elif fam == "fv_lag":
        parts.append(f"spot moved in last {p['r']} min" + (", quote lagging" if p["qlag"] == "lag" else ""))
    elif fam == "fv_cross":
        parts.append(("BTC moved the same way" if p["mode"] == "agree" else "BTC moved the other way")
                     + (f" by {p['thr']} sd+" if p["thr"] else ""))
    elif fam == "fv_jump":
        parts.append(f"1-min move {p['jmode'][0]} {p['jmode'][1:]} sd")
    elif fam == "fv_session":
        parts.append(_SESSN[p["sess"]])
    elif fam == "fv_prev":
        parts.append(f"previous 15 min moved {'the same' if p['pmode'] == 'with' else 'the opposite'} way"
                     + (f" by {p['pz']} sd+" if p["pz"] else ""))
    elif fam == "ens_fixed":
        parts.append(p["members"].replace("all4", "4 models") + (", first signal" if p["mode"] == "first" else ", two must agree"))
    elif fam == "scalp":
        parts.append(_EXIT[p["exit"]])
    elif fam in ("maker_fv", "fv_maker"):
        parts.append(f"bid rests {p['wait']} min")
    elif fam == "sized":
        parts.append(f"stakes up to {p['cap']}x average")
    if p.get("vol") not in (None, "60"):
        parts.append(_VOL[p["vol"]])
    if p.get("vm", 1.0) != 1.0:
        parts.append(f"vol x{p['vm']}")
    if p.get("band") not in (None, "05-95"):
        lo, hi = BANDS[p["band"]]
        parts.append(f"{lo * 100:.0f}-{hi * 100:.0f}c only")
    return ", ".join(parts)


def label(fam, scope, params):
    name = FAMILIES[fam]["name"] if fam in FAMILIES else EXTRA_FAMILIES[fam][0]
    lab = f"{cname(scope)} · {name}"
    if isinstance(params, dict) and fam in FAMILIES:
        lab += f" ({describe(fam, params)})"
    return lab


# =========================================================================== main
def _bot_lag():
    try:
        with open(BOT_LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 200_000))
            lines = f.read().decode(errors="ignore").splitlines()[-200:]
        lags = [json.loads(x).get("lag_s") for x in lines if '"buy"' in x]
        lags = [x for x in lags if isinstance(x, (int, float))]
        return max(lags[-10:]) if lags else None
    except Exception:
        return None


def _workers(want):
    w = max(1, min(want, MAX_WORKERS))
    lag = _bot_lag()
    if lag is not None and lag > 2.5:
        print(f"  paper bot lag {lag}s > 2.5s -> 1 worker", flush=True)
        w = 1
    return w


def _pmap(fn, tasks, workers, label_=""):
    out = []
    t0 = time.time()
    w = _workers(workers)
    if w == 1:
        it = map(fn, tasks)
        for i, r in enumerate(it):
            out.append(r)
            if (i + 1) % 10 == 0:
                print(f"  {label_} {i + 1}/{len(tasks)} ({time.time() - t0:.0f}s)", flush=True)
        return out
    with Pool(w) as pool:
        for i, r in enumerate(pool.imap_unordered(fn, tasks, chunksize=1)):
            out.append(r)
            if (i + 1) % 10 == 0:
                print(f"  {label_} {i + 1}/{len(tasks)} ({time.time() - t0:.0f}s, bot lag {_bot_lag()}s)", flush=True)
    return out


def load(verbose=True):
    full = {}
    for s in COINS:
        p = B.Panel(B.build_panel(s))
        add_features(p, s, "main")
        full[s] = p
        if verbose:
            print(f"  {s}: {len(p)} markets", flush=True)
    start = int(max(p.open_ts.min() for p in full.values()))     # common start (SOL's older data -> archive)
    cut = int(min(p.open_ts.max() for p in full.values()) - HOLDOUT_DAYS * 86400)
    G["start"], G["cut"] = start, cut
    for s, p in full.items():
        ots = np.asarray(p.open_ts, np.int64)
        sm = (ots >= start) & (ots < cut)
        sp_ = p.subset(sm)
        fold = np.clip(((np.asarray(sp_.open_ts, np.int64) - start) * N_FOLDS) // (cut - start), 0, N_FOLDS - 1)
        G["search"][s] = Ctx(s, sp_, fold.astype(int))
        G["hold"][s] = Ctx(s, p.subset(ots >= cut))
        if s == "KXSOL15M" and (ots < start).sum() > 500:
            G["arch"][s] = Ctx(s, p.subset(ots < start - 900))
    for s in ARCH_COINS:
        if s == "KXSOL15M" or not (ARCH_DIR / f"{s}_candles.part.csv").exists():
            continue
        with lab2._source(ARCH_DIR, "candles.part"):
            p = B.Panel(B.build_panel(s))
        f = lab2.FRESH / f"{s}_markets.csv"
        if f.exists():
            p = p.subset(p.open_ts < pd.read_csv(f, usecols=["open_ts"]).open_ts.min())
        used_min = full[s].open_ts.min()
        p = p.subset(p.open_ts < used_min)            # strictly older than anything in the search window
        add_features(p, s, "archive")
        G["arch"][s] = Ctx(s, p)
        if verbose:
            print(f"  archive {s}: {len(p)} markets", flush=True)
    return full


def diagnose_file(path=None):
    """Re-run only the diagnostics on an existing results file (no search, holdout rules re-run as frozen)."""
    path = Path(path) if path else OUT
    res = json.loads(path.read_text())
    G["quick"] = 0
    load(verbose=False)
    diagnose(res)
    path.write_text(json.dumps(res, default=_jd))
    for line in res["method"]["summary"]:
        print(" -", line)
    return res


def main(workers=2, families=None, quick=0, out_path=None):
    """quick = N: only every Nth config of each grid (pipeline test). out_path: write elsewhere."""
    t0 = time.time()
    G["quick"] = quick or 0
    _GRID_CACHE.clear()
    try:
        os.nice(19)
    except OSError:
        pass
    print("lab3: loading panels + features ...", flush=True)
    full = load()
    start, cut = G["start"], G["cut"]
    fams = [f for f in FAMILIES if not families or f in families]
    print(f"search {pd.to_datetime(start, unit='s')} .. {pd.to_datetime(cut, unit='s')}, holdout from cut; "
          f"{len(fams)} families, {sum(len(grid_list(FAMILIES[f]['grid'])) for f in fams)} configs per coin "
          f"({time.time() - t0:.0f}s)", flush=True)

    # ------------------------------------------------------------------ 1. search (no holdout data touched)
    tasks = [(f, c) for f in fams for c in COINS]
    tasks.sort(key=lambda t: -len(grid_list(FAMILIES[t[0]]["grid"])))  # big ones first
    AGG = {}
    for fam, coin, agg in _pmap(_search_task, tasks, workers, "search"):
        AGG[(fam, coin)] = agg
    print(f"search done ({time.time() - t0:.0f}s)", flush=True)
    for fam in fams:
        AGG[(fam, "ALL")] = sum(AGG[(fam, c)] for c in COINS)

    # ------------------------------------------------------------------ 2. walk-forward per family x scope
    scopes = COINS + ["ALL"]
    WF, cands = {}, []
    for fam in fams:
        cfgs = grid_list(FAMILIES[fam]["grid"])
        for sc in scopes:
            w = walk(AGG[(fam, sc)])
            WF[(fam, sc)] = w
            if shortlisted(w):
                cands.append({"id": f"{fam}:{sc}", "family": fam, "scope": sc, "execution": _exec(fam),
                              "rule": {"family": fam, "params": cfgs[w["final"]]},
                              "search": {**w["oos"], "insample": w["final_search"]}})

    # per-coin tuning with shrinkage toward the pooled result (ALL scope, live-model grid)
    if "fv_ref" in fams:
        w = walk_pertune({c: AGG[("fv_ref", c)] for c in COINS})
        WF[("pertune", "ALL")] = w
        cfgs = grid_list(FAMILIES["fv_ref"]["grid"])
        if shortlisted(w):
            cands.append({"id": "pertune:ALL", "family": "pertune", "scope": "ALL", "execution": "taker",
                          "rule": {"family": "fv_ref", "per_coin": True,
                                   "params": {c: cfgs[i] for c, i in w["final"].items()}},
                          "search": {**w["oos"], "insample": None}})

    # ensembles of the best survivors (membership chosen from search-window walk-forward only)
    for sc in scopes:
        surv = sorted([c for c in cands if c["scope"] == sc and FAMILIES.get(c["family"], {}).get("single")],
                      key=lambda c: -c["search"]["t"])[:3]
        if len(surv) < 2:
            continue
        w = walk_ens(sc, [s["family"] for s in surv], WF)
        WF[("ens_best", sc)] = w
        if shortlisted(w):
            cands.append({"id": f"ens_best:{sc}", "family": "ens_best", "scope": sc, "execution": "taker",
                          "rule": {"members": [s["rule"] for s in surv]},
                          "search": {**w["oos"], "insample": None}})
    print(f"shortlist: {len(cands)} candidates reach the holdout ({time.time() - t0:.0f}s)", flush=True)
    for c in sorted(cands, key=lambda c: -c["search"]["t"]):
        s = c["search"]
        print(f"  {c['id']:28s} WF ${s['pnl']:>9} n={s['trades']:>5} t={s['t']:>5} folds+={s['fold_win']}", flush=True)

    # ------------------------------------------------------------------ 3. final exam (holdout, once)
    k = max(1, len(cands))
    t_bar = round(NormalDist().inv_cdf(1 - 0.05 / k), 2)
    res = dict(_pmap(_final_task, cands, workers, "final"))
    base = baselines()
    for c in cands:
        c.update(res[c["id"]])
    judge(cands, base, t_bar)

    # ------------------------------------------------------------------ 4. report
    fam_rows = []
    for fam in fams + ["pertune", "ens_best"]:
        mine = [c for c in cands if c["family"] == fam]
        if fam in FAMILIES:
            name, idea, ncfg = FAMILIES[fam]["name"], FAMILIES[fam]["idea"], len(grid_list(FAMILIES[fam]["grid"]))
        else:
            name, idea = EXTRA_FAMILIES[fam]
            ncfg = len(grid_list(FAMILIES["fv_ref"]["grid"])) if fam == "pertune" else None
        st = "golden" if any(c["status"] == "golden" for c in mine) else (
            "pass" if any(c["status"] == "pass" for c in mine) else "fail")
        wf = {sc: WF[(fam, sc)]["oos"] for sc in scopes if (fam, sc) in WF}
        fam_rows.append({"id": fam, "name": name, "idea": idea, "configs": ncfg,
                         "scopes_tested": len(wf), "shortlisted": len(mine),
                         "best_holdout_t": max([c["holdout"]["t"] for c in mine], default=None),
                         "best_search_t": max([v["t"] for v in wf.values()], default=None),
                         "status": st, "walk_forward": {cname(s): v for s, v in wf.items()}})
    # heatmaps: the most interesting families (best holdout t among those with a numeric heatmap)
    heats = []
    for fr in sorted(fam_rows, key=lambda r: -(r["best_holdout_t"] or -99)):
        fam = fr["id"]
        if fam not in FAMILIES or not FAMILIES[fam]["heat"]:
            continue
        best = max([c for c in cands if c["family"] == fam], key=lambda c: c["holdout"]["t"], default=None)
        if best is None:
            continue
        h = heatmap(fam, best["scope"], WF[(fam, best["scope"])]["final"], AGG[(fam, best["scope"])])
        if h:
            heats.append(h)
        if len(heats) >= 4:
            break
    cands.sort(key=lambda c: ({"golden": 0, "pass": 1, "fail": 2}[c["status"]], -c["holdout"]["t"]))
    n_grid = sum(len(grid_list(FAMILIES[f]["grid"])) for f in fams)
    out = {
        "generated": int(time.time()), "runtime_s": int(time.time() - t0),
        "method": {
            "search_window": f"{pd.to_datetime(start, unit='s'):%Y-%m-%d %H:%M} to {pd.to_datetime(cut, unit='s'):%Y-%m-%d %H:%M} UTC",
            "search_start": start, "holdout_start": cut, "holdout_days": HOLDOUT_DAYS, "n_folds": N_FOLDS,
            "n_families": len(fam_rows), "n_grid_configs": n_grid, "n_configs_tested": n_grid * len(scopes),
            "n_walk_forwards": len(WF), "n_holdout_tests": k, "t_bar_strict": t_bar, "stake": STAKE,
            "shortlist": f"walk-forward P&L > 0, t >= {T_SHORT}, >= {SHORT_TRADES} trades, >= half of test folds profitable",
            "rules": RULES(t_bar), "caveats": CAVEATS,
        },
        "coins": {s: {"markets": len(full[s]), "search_markets": len(G["search"][s]),
                      "holdout_markets": len(G["hold"][s]),
                      "archive_markets": len(G["arch"][s]) if s in G["arch"] else 0,
                      "archive_span": (f"{pd.to_datetime(G['arch'][s].open_ts.min(), unit='s'):%Y-%m-%d} to "
                                       f"{pd.to_datetime(G['arch'][s].open_ts.max(), unit='s'):%Y-%m-%d}")
                      if s in G["arch"] else None} for s in COINS},
        "families": fam_rows,
        "baselines": base,
        "candidates": [_public(c) for c in cands],
        "heatmaps": heats,
    }
    diagnose(out)
    dest = Path(out_path) if out_path else OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, default=_jd))
    print(f"\nstrict bar t >= {t_bar} over {k} holdout tests")
    for c in cands[:40]:
        h = c["holdout"]
        print(f"  {c['status']:6s} {c['id']:28s} ${h['pnl']:>8} n={h['trades']:>5} t={h['t']:>5} | "
              f"arch {(c['archive'] or {}).get('t')} | d1 t={c['delay1']['t']} | {c['why']}")
    print(f"done in {time.time() - t0:.0f}s -> {dest}")
    return out


# =========================================================================== diagnostics (do not change status)
def _tser(x):
    x = np.asarray(x, float)
    if len(x) < 3 or x.std(ddof=1) == 0:
        return 0.0
    return round(float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))), 2)


def _rule_from_public(c):
    fam, params = c["family"], c["params"]
    if fam == "ens_best":
        return {"members": params["members"]}
    if fam == "pertune":
        back = {cname(s): s for s in COINS}
        return {"family": "fv_ref", "per_coin": True, "params": {back[k]: v for k, v in params.items()}}
    return {"family": fam, "params": params}


def _base_df(b):
    coins = [b["id"].split("|")[1]] if "|" in b["id"] else _coins_of(b["scope"])
    return _bt("hold", coins, b["strategy"], b["params"])


def diagnose(res):
    """Extra skeptic's checks on the holdout, added to each candidate / baseline:
    t_by_window  t-stat of P&L summed per 15-minute window (pooled scopes trade several correlated coins in the
                 same window, which the per-trade t ignores); t_by_day  t-stat of daily P&L;
    paired_vs_live / paired_vs_control  extra P&L over the most profitable live rule (or the re-tuned live model,
                 family fv_ref) on the same markets, with the t-stat of the per-window difference."""
    o2w, wins = {}, {}
    for s, ctx in G["hold"].items():
        o2w.update(zip(ctx.panel.ticker, ctx.open_ts))
        wins[s] = np.unique(ctx.open_ts)
    scope_w = {sc: np.unique(np.concatenate([wins[c] for c in _coins_of(sc)])) for sc in COINS + ["ALL"]}

    def wsum(df):
        if df is None or len(df) == 0:
            return pd.Series(dtype=float)
        return df.groupby(df.ticker.map(o2w)).pnl.sum()

    def stats(item, df):
        ws = wsum(df)
        item["holdout"]["t_by_window"] = _tser(ws.values)
        item["holdout"]["t_by_day"] = _tser(df.groupby(df.ts // 86400).pnl.sum().values) if len(df) else 0.0
        return ws

    WS = {}
    for b in res["baselines"]:
        WS[b["id"]] = stats(b, _base_df(b))
    for c in res["candidates"]:
        WS[c["id"]] = stats(c, run_rule("hold", c["scope"], _rule_from_public(c),
                                        norms=_sized_norms(_rule_from_public(c), c["scope"])
                                        if c["family"] == "sized" else None))

    def paired(a, b, sc):
        W = scope_w[sc]
        d = WS[a].reindex(W, fill_value=0.0).to_numpy() - WS[b].reindex(W, fill_value=0.0).to_numpy()
        return {"extra_pnl": round(float(d.sum()), 2), "t": _tser(d)}
    for c in res["candidates"]:
        bl = [b for b in res["baselines"] if b["scope"] == c["scope"]]
        if bl:
            bp = max(bl, key=lambda b: b["holdout"]["pnl"])
            c["paired_vs_live"] = {"baseline_id": bp["id"], **paired(c["id"], bp["id"], c["scope"])}
        ctl = [x for x in res["candidates"] if x["family"] == "fv_ref" and x["scope"] == c["scope"] and x is not c]
        c["paired_vs_control"] = {"control_id": ctl[0]["id"], **paired(c["id"], ctl[0]["id"], c["scope"])} if ctl else None
    res["method"]["diagnostics"] = (
        "Added after the run as extra skeptic's checks; they do not change any status. 't by window' groups trades "
        "in the same 15-minute window (pooled scopes bet on several coins that move together, so the per-trade t "
        "overstates certainty); 't by day' uses daily totals. 'Paired vs live' is the extra holdout profit over the "
        "most profitable live rule on the same coin(s), with the t-stat of that difference per 15-minute window; "
        "'paired vs control' does the same against the live model simply re-tuned on the search window (fv_ref).")
    for c in res["candidates"]:
        if c["family"] in FAMILIES:
            c["label"] = label(c["family"], c["scope"], c["params"])
        c["why"] = c["why"].split(" Caution:")[0]
        pl = c.get("paired_vs_live")
        if c["status"] == "golden" and pl and pl["t"] < 2:
            c["why"] += (f" Caution: the extra ${pl['extra_pnl']:,.0f} over the live rule on the same markets is not "
                         f"statistically clear (paired t = {pl['t']}).")
    for fr in res["families"]:
        mine = [c for c in res["candidates"] if c["family"] == fr["id"]]
        if not mine:
            fr["finding"] = "Nothing reached the holdout: no scope had a good enough walk-forward record."
            continue
        b = max(mine, key=lambda c: c["holdout"]["t"])
        pc = b.get("paired_vs_control")
        fr["finding"] = (f"Best: {b['label']}: ${b['holdout']['pnl']:,.0f} at t = {b['holdout']['t']} on the holdout "
                         f"({b['status']})." + (f" Versus the re-tuned live model on the same markets: "
                                                f"{'+' if pc['extra_pnl'] >= 0 else '-'}${abs(pc['extra_pnl']):,.0f} "
                                                f"(paired t = {pc['t']})." if pc and fr["id"] != "fv_ref" else ""))
    res["method"]["summary"] = headline(res)
    return res


def headline(res):
    cs = res["candidates"]
    gold = [c for c in cs if c["status"] == "golden"]
    out = [f"{len(gold)} of {len(cs)} candidates that reached the holdout are golden, "
           f"{sum(c['status'] == 'pass' for c in cs)} pass, {sum(c['status'] == 'fail' for c in cs)} fail "
           f"(strict bar t >= {res['method']['t_bar_strict']})."]
    ctl = next((c for c in cs if c["family"] == "fv_ref" and c["scope"] == "ALL"), None)
    live = next((b for b in res["baselines"] if b["id"] == "live:ALL:fair_value"), None)
    if ctl and live:
        out.append(f"Control: simply re-tuning the live model on the search window, all 9 coins, made "
                   f"${ctl['holdout']['pnl']:,.0f} (t {ctl['holdout']['t']}) vs ${live['holdout']['pnl']:,.0f} "
                   f"(t {live['holdout']['t']}) for the live all-coin rule. Part of every all-coin gain is just this re-tuning.")
    clear = [c for c in gold if (c.get("paired_vs_live") or {}).get("t", 0) >= 2]
    if gold:
        out.append("Golden rules whose extra profit over the live rule is itself statistically clear (paired t >= 2): "
                   + (", ".join(f"{c['label']} (+${c['paired_vs_live']['extra_pnl']:,.0f}, t {c['paired_vs_live']['t']})"
                                for c in clear) or "none") + ".")
        beat_ctl = [c for c in gold if (c.get("paired_vs_control") or {}).get("t", 0) >= 2]
        out.append("Golden rules that also clearly beat the re-tuned control (paired t >= 2): "
                   + (", ".join(c["label"] for c in beat_ctl) or "none") + ".")
        under = [c for c in gold if c["holdout"].get("t_by_window", 99) < res["method"]["t_bar_strict"]]
        if under:
            out.append("Golden rules whose t-stat falls below the strict bar once trades in the same 15-minute window "
                       "are grouped: " + ", ".join(c["label"] for c in under) + ".")
        d1 = sorted(c["delay1"]["t"] for c in gold)
        out.append(f"Latency: acting one minute late, the golden rules' holdout t-stats have a median of "
                   f"{d1[len(d1) // 2]} (range {d1[0]} to {d1[-1]}); the edge depends on reacting within the minute.")
    return out


def _exec(fam):
    k = FAMILIES[fam]["kind"]
    return {"hold": "taker", "sized": "taker", "scalp": "taker+exit", "maker": "maker", "makerfv": "maker"}[k]


def _jd(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.bool_):
        return bool(o)
    return str(o)


def _public(c):
    rule = c["rule"]
    if "members" in rule:
        params = {"members": [{"family": m["family"], "params": m["params"]} for m in rule["members"]]}
        strategy = "ens_best"
    elif rule.get("per_coin"):
        params = {cname(k): v for k, v in rule["params"].items()}
        strategy = "fv_ref (per coin)"
    else:
        params, strategy = rule["params"], rule["family"]
    return {"id": f"{c['id']}:{c['execution']}", "label": c["label"], "family": c["family"], "scope": c["scope"],
            "strategy": strategy, "execution": c["execution"], "params": params, "search": c["search"],
            "holdout": c["holdout"], "archive": c["archive"], "delay1": c["delay1"], "vs_baseline": c["vs_baseline"],
            "holdout_by_coin": c.get("holdout_by_coin"), "status": c["status"], "why": c["why"],
            "checks": c["checks"], "curve": c["curve"]}


def walk_pertune(aggs, w_pool=1.0, min_coin=20):
    """Walk-forward where each coin picks its own config by (own P&L + w_pool x average-coin P&L)
    on the training folds."""
    coins = list(aggs)
    pooled = sum(aggs.values())
    oos = np.zeros(3)
    fold_pnl = []
    for k in range(1, N_FOLDS):
        tot = 0.0
        for c in coins:
            tr = aggs[c][:, :k, :].sum(1)
            score = tr[:, 1] + w_pool * pooled[:, :k, 1].sum(1) / len(coins)
            score = np.where(tr[:, 0] >= min_coin, score, -np.inf)
            if not np.isfinite(score).any():
                continue
            i = int(np.argmax(score))
            oos += aggs[c][i, k]
            tot += aggs[c][i, k, 1]
        fold_pnl.append(tot)
    final = {}
    for c in coins:
        tr = aggs[c].sum(1)
        score = np.where(tr[:, 0] >= min_coin, tr[:, 1] + w_pool * pooled.sum(1)[:, 1] / len(coins), -np.inf)
        if np.isfinite(score).any():
            final[c] = int(np.argmax(score))
    return {"oos": {"pnl": round(float(oos[1]), 2), "trades": int(oos[0]), "t": round(tstat_agg(oos), 2),
                    "fold_win": round(float(np.mean([x > 0 for x in fold_pnl])), 2)}, "final": final or None}


def walk_ens(scope, fams, WF):
    """Walk-forward of a first-to-fire ensemble: in each test fold, members use the configs their own
    walk-forward picked for that fold."""
    oos = np.zeros(3)
    fold_pnl = []
    for k in range(1, N_FOLDS):
        mem = []
        for f in fams:
            i = WF[(f, scope)]["picks"][k - 1]
            if i is not None:
                mem.append({"family": f, "params": grid_list(FAMILIES[f]["grid"])[i]})
        tot = 0.0
        if mem:
            for coin in _coins_of(scope):
                ctx = G["search"][coin]
                ctx.cache = {}
                side, minute = ens_combine(ctx, mem)
                side = np.where(ctx.fold == k, side, 0)
                a = fold_agg(ctx, execute(ctx, "_ens", {}, side, minute, None))
                oos += a[k]
                tot += a[k, 1]
                ctx.cache = {}
        fold_pnl.append(tot)
    return {"oos": {"pnl": round(float(oos[1]), 2), "trades": int(oos[0]), "t": round(tstat_agg(oos), 2),
                    "fold_win": round(float(np.mean([x > 0 for x in fold_pnl])), 2)}, "final": 0, "picks": []}


# =========================================================================== judging
def RULES(t_bar):
    return [
        "Only data from before the holdout was used to pick a family's settings; the holdout (last 15 days, same "
        "calendar cut for every coin as earlier labs) was run once per candidate with frozen settings.",
        f"Golden needs ALL of the following. (1) Made money on the holdout with a t-stat of at least {t_bar}, the "
        "strict bar that corrects for every candidate taken to the holdout (one-sided Bonferroni, 5%).",
        "(2) Beat what is live on the same coin(s) on BOTH holdout profit and holdout t-stat: more profit than the "
        "most profitable live strategy trading that coin (including that coin's share of the all-coin strategies) "
        "and a higher t-stat than the live strategy with the best t-stat.",
        "(3) Where older archive data exists for the coin (NEAR, DOGE, BNB, SOL from April-August; pooled for the "
        "all-coin scope), it also made money there with t >= 2 on at least 50 trades, with no re-tuning. If the rule "
        "cannot be run on the archive (e.g. it needs BTC prices the archive lacks), it cannot be golden.",
        "(4) No more than 40% of its holdout profit came from a single day.",
        "Pass = made money on the holdout with t >= 2 but missed at least one golden test. Fail = anything else.",
        "Every result assumes $10 per trade, Kalshi taker fees (maker fee 1.75% for maker rules), fills at the quoted "
        "price at the end of the decision minute, and one bet per market. 'One minute late' re-runs the frozen rule "
        "with a 1-minute delay as a latency check; it is reported, not graded.",
    ]


CAVEATS = [
    "The live strategies were chosen in an earlier lab using this same holdout, so their holdout numbers are "
    "flattering; beating them here is a deliberately high bar.",
    "The archive data was already used once (lab2) to check the plain live rule, so it is blind for the new "
    "families but not untouched. SOL's April-August data was used for SOL's blind test.",
    "All of the edge depends on acting within about a minute of a spot move; the one-minute-late column shows "
    "how much survives a slow bot.",
    "Backtest fills assume the quoted ask had enough size for a $10 order; real fills on thin books can be worse.",
    "BTC/ETH spot data only starts on Aug 31, so rules that need BTC cannot be checked on the archive.",
]


def judge(cands, base, t_bar):
    by_scope = {}
    for b in base:
        by_scope.setdefault(b["scope"], []).append(b)
    for c in cands:
        h, sc = c["holdout"], c["scope"]
        bl = by_scope.get(sc, [])
        best_t = max(bl, key=lambda b: b["holdout"]["t"]) if bl else None
        best_p = max(bl, key=lambda b: b["holdout"]["pnl"]) if bl else None
        c["label"] = label(c["family"], sc, c["rule"].get("params") if "params" in c["rule"] else None)
        c["vs_baseline"] = None if not bl else {
            "baseline_id": best_t["id"], "pnl_diff": round(h["pnl"] - best_t["holdout"]["pnl"], 2),
            "t_diff": round(h["t"] - best_t["holdout"]["t"], 2),
            "best_pnl_baseline_id": best_p["id"], "best_pnl_diff": round(h["pnl"] - best_p["holdout"]["pnl"], 2)}
        arch = c.get("archive")
        arch_ok = None if arch is None else bool(arch["trades"] >= MIN_ARCH_TRADES and arch["pnl"] > 0 and arch["t"] >= 2)
        top = h.get("top_day_share")
        checks = {
            "holdout_profit": h["pnl"] > 0,
            "strict_t": h["t"] >= t_bar,
            "beats_live_pnl": bool(bl) and h["pnl"] > best_p["holdout"]["pnl"],
            "beats_live_t": bool(bl) and h["t"] > best_t["holdout"]["t"],
            "archive": arch_ok,
            "not_one_day": top is not None and top <= 0.40,
        }
        c["checks"] = checks
        golden = all(v for k, v in checks.items() if k != "archive") and arch_ok is not False
        passed = h["pnl"] > 0 and h["t"] >= 2
        c["status"] = "golden" if golden else ("pass" if passed else "fail")
        c["why"] = _why(c, checks, t_bar, best_t, best_p)


def _why(c, ch, t_bar, best_t, best_p):
    h = c["holdout"]
    if h["pnl"] <= 0:
        return f"Lost ${-h['pnl']:,.0f} on the holdout ({h['trades']} trades)."
    if h["t"] < 2:
        return f"Made ${h['pnl']:,.0f} on the holdout but t = {h['t']} is too weak to rule out luck (needs 2)."
    miss = []
    if not ch["strict_t"]:
        miss.append(f"t = {h['t']} is below the strict bar of {t_bar}")
    if best_p is not None and not ch["beats_live_pnl"]:
        miss.append(f"made less than the live {best_p['label'].replace(' (live)', '')} (${h['pnl']:,.0f} vs "
                    f"${best_p['holdout']['pnl']:,.0f})")
    if best_t is not None and not ch["beats_live_t"]:
        miss.append(f"t-stat below the live {best_t['label'].replace(' (live)', '')} ({h['t']} vs {best_t['holdout']['t']})")
    if ch["archive"] is False:
        a = c["archive"]
        if a.get("note"):
            miss.append("could not be checked on the older archive data (" + a["note"] + ")")
        elif a["trades"] < MIN_ARCH_TRADES:
            miss.append(f"too few trades on the older archive data to check it ({a['trades']})")
        else:
            miss.append(f"did not hold up on the older archive data (${a['pnl']:,.0f}, t = {a['t']})")
    if not ch["not_one_day"]:
        miss.append(f"{(h.get('top_day_share') or 0) * 100:.0f}% of the profit came from one day")
    if not miss:
        a = c["archive"]
        arch = f", archive t = {a['t']}" if a else ""
        return (f"Beat every live strategy on this scope: ${h['pnl']:,.0f} at t = {h['t']} on the holdout"
                f" (strict bar {t_bar}{arch}).")
    return f"Made ${h['pnl']:,.0f} (t = {h['t']}) but " + "; ".join(miss) + "."


if __name__ == "__main__":
    main()
