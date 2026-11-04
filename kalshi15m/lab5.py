"""Lab 5: execution-level variants of the two best lab3 rules (Kalshi 15-minute crypto up/down).

    nice -n 19 python -m kalshi15m lab5 download          # fresh markets after the on-disk data (once, gently)
    nice -n 19 python -m kalshi15m lab5 run [WORKERS]     # search + walk-forward + holdout + archive + fresh
                                                          #   -> data/lab/lab5_results.json

lab3 found that the best all-coin rules are the live fair-value signal with (a) Kelly-sized stakes
("sized:ALL") and (b) an early exit once the bid reaches fair value ("scalp:ALL"); the combination
("sized_exit:ALL", golden_live.EXTRA) made $8,034 at t 6.95 on lab3's locked 15-day holdout. lab5 asks
whether HOW a signal is traded (sizing, exits, re-entry, maker legs, timing, portfolio caps) or WHICH
lab3 entry it is applied to can do clearly better.

Protocol (same spirit as lab3, everything fixed before any holdout number is computed):
 1. Same data, same calendar cut, same search window / 5 folds / holdout / archive as lab3 (lab3.load).
 2. Each idea is a FAMILY = an entry rule (a lab3 family with that family's lab3-tuned ALL-coin params,
    or a small grid) x an execution grid. Only the all-coin (ALL) scope is searched: nothing per coin
    can reach the $8,000 bar.
 3. Walk-forward on the 5 search folds exactly like lab3.walk (best P&L on earlier folds traded on the
    next). Shortlist = lab3's (WF P&L > 0, t >= 1.5, >= 50 trades, >= half the folds positive) AND
    walk-forward t >= the walk-forward t of sized_exit:ALL's own family run through the same machinery
    (a candidate has to look at least as good as the bar out of sample before it may touch the holdout).
    At most MAX_HOLDOUT candidates (best WF t first) go to the holdout.
 4. Final exam: tune on the whole search window, freeze, run ONCE on the holdout, one minute late, on the
    archive and on fresh data downloaded after the holdout (data/kalshi15m/lab5/).
 5. Strict bar = one-sided Bonferroni at 5% over EVERY holdout test ever run on lab3's holdout:
    lab3's 112 + the combo test (1) + lab5's own holdout tests.
"""
from __future__ import annotations

import json
import math
import os
import time
from multiprocessing import Pool
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import backtest as B
from . import data as D
from . import lab3
from .lab3 import G, MIN, STAKE, N_FOLDS

OUT = D.DATA_DIR.parent / "lab" / "lab5_results.json"
FRESH = D.DATA_DIR / "lab5"
COINS = list(D.SERIES)
PRIOR_HOLDOUT_TESTS = 112 + 1          # lab3's candidates + the combo test (scratchpad combo.py, Nov 3)
MAX_HOLDOUT = 12
MAKER = B.MAKER_RATE
TAKER = B.TAKER_RATE
np.seterr(all="ignore")


# =========================================================================== fresh data (download once)
def _kalshi_get(url, params, gap=0.6):
    """<= ~1.7 requests/s (the bots share the IP); D._get backs off on 429/5xx."""
    time.sleep(gap)
    return D._get(url, params)


def download(series_list=None, days=4):
    """Settled markets opening after each coin's last market in data/kalshi15m (= after lab3's holdout),
    their 1-minute candles, and Coinbase spot (on-disk spot + new bars, so features have full history)."""
    FRESH.mkdir(parents=True, exist_ok=True)
    for series in series_list or COINS:
        if (FRESH / f"{series}_markets.csv").exists():
            print(f"{series}: cached")
            continue
        last = int(pd.read_csv(D.DATA_DIR / f"{series}_markets.csv", usecols=["open_ts"]).open_ts.max())
        now = int(time.time())
        rows, cursor = [], None
        params = {"series_ticker": series, "status": "settled", "limit": 1000, "min_close_ts": now - days * 86400}
        while True:
            if cursor:
                params["cursor"] = cursor
            d = _kalshi_get(f"{D.KALSHI}/markets", params)
            rows += [r for r in map(D._market_row, d.get("markets", [])) if r]
            cursor = d.get("cursor")
            if not cursor or not d.get("markets"):
                break
        mk = pd.DataFrame(rows).drop_duplicates("ticker").sort_values("open_ts")
        mk = mk[mk.open_ts > last].reset_index(drop=True)
        if mk.empty:
            print(f"{series}: no new markets")
            continue
        crow = []
        for chunk in D._chunks(mk):
            d = _kalshi_get(f"{D.KALSHI}/markets/candlesticks",
                            {"market_tickers": ",".join(m.ticker for m in chunk),
                             "start_ts": min(m.open_ts for m in chunk) - 60,
                             "end_ts": max(m.close_ts for m in chunk) + 60, "period_interval": 1})
            for m in d.get("markets", []):
                tk = m.get("market_ticker") or m.get("ticker")
                crow += [D._candle_row(tk, c) for c in m.get("candlesticks", [])]
        cd = pd.DataFrame(crow)
        old = pd.read_csv(D.DATA_DIR / f"{series}_spot.csv")
        s0 = int(old.ts.max()) + 60
        new = D.fetch_spot(D.SERIES[series], s0, int(mk.close_ts.max()) + 120)
        sp = pd.concat([old, new], ignore_index=True).drop_duplicates("ts").sort_values("ts")
        mk.to_csv(FRESH / f"{series}_markets.csv", index=False)
        cd.to_csv(FRESH / f"{series}_candles.csv", index=False)
        sp.to_csv(FRESH / f"{series}_spot.csv", index=False)
        print(f"{series}: {len(mk)} fresh markets {pd.to_datetime(mk.open_ts.min(), unit='s')} .. "
              f"{pd.to_datetime(mk.open_ts.max(), unit='s')}, {len(cd)} candles, {len(new)} new spot bars", flush=True)


def load_fresh(verbose=True):
    """G['fresh']: panels of the downloaded markets, features built from the full spot history."""
    from . import lab2
    G["fresh"] = {}
    for s in COINS:
        if not (FRESH / f"{s}_markets.csv").exists():
            continue
        lab3._SPOT[(s, "fresh")] = lab3.Spot(FRESH / f"{s}_spot.csv")
        with lab2._source(FRESH):
            p = B.Panel(B.build_panel(s))
        lab3.add_features(p, s, "fresh")
        G["fresh"][s] = lab3.Ctx(s, p)
        if verbose:
            print(f"  fresh {s}: {len(p)} markets", flush=True)


# =========================================================================== entries
# The lab3 entry rules (ALL-coin params exactly as lab3 tuned them on the search window, golden_live.GOLDEN).
ENTRY = {
    "fv13": ("sized", {"start": 2, "end": 13, "edge": 0.13, "band": "05-95", "vm": 1.0, "cap": 5}),   # sized:ALL
    "fv12v8": ("scalp", {"vm": 0.8, "edge": 0.12, "start": 2, "end": 13, "band": "05-95", "exit": "conv0"}),  # scalp:ALL
    "lag": ("fv_lag", {"start": 2, "end": 13, "edge": 0.12, "band": "05-95", "r": 1, "k": 0.25, "qlag": "lag", "vm": 0.8}),
    "shape": ("fv_shape", {"start": 2, "end": 13, "edge": 0.14, "band": "05-95", "a": 1.1, "vm": 1.0}),
    "drift": ("fv_drift", {"start": 2, "end": 13, "edge": 0.18, "band": "05-95", "L": 1, "a": 0.25, "vm": 1.0}),
    "emp": ("fv_emp", {"start": 2, "end": 13, "edge": 0.14, "band": "05-95", "lb": 21, "vm": 1.0}),
    "vol": ("fv_vol", {"start": 2, "end": 13, "edge": 0.13, "band": "05-95", "vol": "ewma30", "vm": 0.9}),
    "ref": ("fv_ref", {"start": 2, "end": 13, "edge": 0.14, "band": "05-95", "vol": "max", "vm": 0.8}),
    "t4": ("fv_t", {"start": 2, "end": 13, "edge": 0.13, "band": "05-95", "nu": 4, "vol": "60", "vm": 1.25}),
}
ENS = {"ens_or4": ("fv13", "lag", "shape", "drift"), "ens_or3": ("fv13", "shape", "emp"),
       "ens_vote2": ("fv13", "lag", "shape", "drift", "emp")}


def entry_masks(ctx, ekey, dedge=0.0, timing="none"):
    """-> (y, n, p): entry masks (markets x 14) and the entry model's P(YES)."""
    ck = ("entry", ekey, dedge, timing)
    if ck in ctx.cache:
        return ctx.cache[ck]
    if ekey in ENS:
        ms = [entry_masks(ctx, m, dedge) for m in ENS[ekey]]
        if ekey.startswith("ens_vote"):
            y = np.sum([m[0] for m in ms], 0) >= 2
            n = np.sum([m[1] for m in ms], 0) >= 2
        else:
            y = np.logical_or.reduce([m[0] for m in ms])
            n = np.logical_or.reduce([m[1] for m in ms])
        p = ms[0][2]
    else:
        fam, cfg = ENTRY[ekey]
        cfg = dict(cfg, edge=round(cfg["edge"] + dedge, 4))
        y, n, p = lab3.FAMILIES[fam]["fn"](ctx, cfg)
    if timing != "none":
        P = ctx.P
        gy, gn = p - P["yes_ask"], (1 - p) - P["no_ask"]
        if timing == "grow":       # the gap is wider than a minute ago (or there was no quote a minute ago)
            py = np.c_[np.full(len(p), np.nan), gy[:, :-1]]
            pn = np.c_[np.full(len(p), np.nan), gn[:, :-1]]
            y = y & ~(py >= gy)
            n = n & ~(pn >= gn)
        elif timing == "confirm":  # the signal was already there a minute ago
            y = y & np.c_[np.zeros(len(p), bool), y[:, :-1]]
            n = n & np.c_[np.zeros(len(p), bool), n[:, :-1]]
        elif timing == "shrink":   # contrarian control: the gap is narrowing
            py = np.c_[np.full(len(p), np.nan), gy[:, :-1]]
            pn = np.c_[np.full(len(p), np.nan), gn[:, :-1]]
            y = y & (py > gy)
            n = n & (pn > gn)
    both = y & n
    y, n = y & ~both, n & ~both
    ctx.cache[ck] = (y, n, p)
    return ctx.cache[ck]


# =========================================================================== position simulator
def _fee(price, n, rate):
    return np.ceil(rate * n * price * (1 - price) * 100 - 1e-9) / 100


def _ok(x):
    return np.isfinite(x) & (x > 0) & (x < 1)


def simulate(ctx, y, n, p, ex, delay=0):
    """Minute-by-minute state machine over all markets of a panel at once.

    Entry (taker unless ex['entry'] == 'maker'): at the end of a minute where the entry mask fires
    (YES and NO the same minute -> nothing), buy that side at its ask (fill `delay` minutes later). Each
    signal consumes one of ex['reentry'] (default 1) entry attempts, so reentry=1 is exactly lab3 (one
    bet per market; a signal with no valid ask is not retried). One position at a time.
    Exit, checked at the end of every later minute on the bid of the held side (YES: yes_bid,
    NO: 1 - yes_ask) against q = the entry model's value of that side:
      conv=k     sell when bid >= q - k cents (lab3 "convK"; k < 0 waits for the bid to overshoot)
      minp=x     ... and only if bid - entry price >= x cents
      tmax=m     ... and only up to minute m (after that: hold to settlement)
      trail=(a,d) sell when the best bid since entry was >= entry + a cents and the bid is now <= best - d
      stop=x     sell when q has fallen below entry price - x cents (model says the bet went bad)
      tstop=m    sell at the bid of minute m whatever happens (time stop)
      maker=m    rest a SELL at q + m cents (re-priced every minute, never at/below the bid); fills during
                 the next minute if the held side's best bid or a trade reaches it (lab3 maker rule:
                 strictly through it when we are not alone at that price); maker fee
      frac=f     only sell a fraction f of the contracts at the exit, hold the rest
    Positions still open settle at the market result. Returns one row per position (episode)."""
    P = ctx.P
    M = len(ctx)
    YA, YB = P["yes_ask"], P["yes_bid"]
    NA = P["no_ask"]
    reach_y = np.fmax(P["bid_high"], P["trade_high"])
    reach_n = 1 - np.fmin(P["ask_low"], P["trade_low"])
    buy_y = np.fmin(P["ask_low"], P["trade_low"])                 # lowest price a resting YES bid could get
    buy_n = 1 - np.fmax(P["bid_high"], P["trade_high"])           # ... a resting NO bid
    max_ent = ex.get("reentry", 1)
    conv, minp, tmax = ex.get("conv"), ex.get("minp"), ex.get("tmax", 14)
    trail, stop, tstop = ex.get("trail"), ex.get("stop"), ex.get("tstop")
    mk, wait = ex.get("maker"), ex.get("wait", 2)
    maker_entry = ex.get("entry") == "maker"
    cap = M * max_ent
    E = {k: np.zeros(cap) for k in ("m", "dec", "fc", "side", "px", "erate", "q", "xc", "xpx", "xrate")}
    ne = 0
    pos = np.zeros(M, np.int8)          # +1 YES, -1 NO
    ep = np.full(M, -1)
    ent_c = np.full(M, -1)
    ent_px = np.full(M, np.nan)
    nent = np.zeros(M, int)
    last_x = np.full(M, -1)
    L = np.full(M, np.nan)
    alone = np.zeros(M, bool)
    best = np.full(M, np.nan)
    pend_side = np.zeros(M, np.int8)
    pend_c = np.full(M, -1)             # taker: fill column; maker: decision column
    pend_px = np.full(M, np.nan)
    pend_alone = np.zeros(M, bool)
    pend_q = np.full(M, np.nan)
    pend_dec = np.full(M, -1)
    rows_all = np.arange(M)

    def open_(idx, side, c, px, rate, q, dec):
        nonlocal ne
        k = len(idx)
        if not k:
            return
        sl = slice(ne, ne + k)
        E["m"][sl], E["dec"][sl], E["fc"][sl], E["side"][sl] = idx, dec, c, side
        E["px"][sl], E["erate"][sl], E["q"][sl] = px, rate, q
        E["xc"][sl], E["xpx"][sl], E["xrate"][sl] = 14, np.nan, 0.0
        ep[idx] = np.arange(ne, ne + k)
        ne += k
        pos[idx], ent_c[idx], ent_px[idx] = side, c, px
        best[idx] = np.nan
        L[idx] = np.nan

    def close_(idx, c, px, rate):
        if not len(idx):
            return
        e = ep[idx]
        E["xc"][e], E["xpx"][e], E["xrate"][e] = c, px, rate
        pos[idx] = 0
        ep[idx] = -1
        last_x[idx] = c
        L[idx] = np.nan

    for c in range(14):
        yes_bid_c = YB[:, c]
        sb = np.where(pos == 1, yes_bid_c, 1 - YA[:, c])          # bid of the held side
        pe = p[:, c]
        q = np.where(pos == 1, pe, 1 - pe)
        # 1. resting maker sell placed at the end of c-1 fills during c
        if mk is not None:
            held = (pos != 0) & np.isfinite(L) & (ent_c < c)
            reach = np.where(pos == 1, reach_y[:, c], reach_n[:, c])
            hit = held & np.isfinite(reach) & np.where(alone, reach >= L - 1e-9, reach > L + 1e-9)
            idx = np.nonzero(hit)[0]
            close_(idx, c, L[idx], MAKER)
        # 2. pending entries
        if delay or maker_entry:
            if maker_entry:
                live = (pend_side != 0) & (pend_c < c) & (c <= pend_c + wait)
                reachb = np.where(pend_side == 1, buy_y[:, c], buy_n[:, c])
                hit = live & np.isfinite(reachb) & np.where(pend_alone, reachb <= pend_px + 1e-9, reachb < pend_px - 1e-9)
                idx = np.nonzero(hit)[0]
                open_(idx, pend_side[idx], c, pend_px[idx], MAKER, pend_q[idx], pend_dec[idx])
                pend_side[idx] = 0
                pend_side[(pend_side != 0) & (c >= pend_c + wait)] = 0
            else:
                due = (pend_side != 0) & (pend_c == c)
                idx = np.nonzero(due)[0]
                px = np.where(pend_side[idx] == 1, YA[idx, c], NA[idx, c])
                g = _ok(px)
                open_(idx[g], pend_side[idx[g]], c, px[g], TAKER, pend_q[idx[g]], pend_dec[idx[g]])
                pend_side[idx] = 0
        # 3. taker exit at the end of c
        held = (pos != 0) & (ent_c < c)
        if held.any():
            sb = np.where(pos == 1, yes_bid_c, 1 - YA[:, c])
            q = np.where(pos == 1, pe, 1 - pe)
            v = held & _ok(sb)
            best = np.where(v, np.fmax(best, sb), best)
            cond = np.zeros(M, bool)
            if conv is not None:
                cc = sb >= q - conv / 100
                if minp is not None:
                    cc &= sb - ent_px >= minp / 100 - 1e-9
                cond |= cc & (c <= tmax - 1)
            if trail is not None:
                a, d = trail
                cond |= (best - ent_px >= a / 100 - 1e-9) & (sb <= best - d / 100 + 1e-9)
            if stop is not None:
                cond |= q < ent_px - stop / 100
            if tstop is not None and c == tstop - 1:
                cond |= True
            idx = np.nonzero(v & cond)[0]
            close_(idx, c, sb[idx], TAKER)
        # 4. new entries decided at the end of c
        sig = (y[:, c] | n[:, c]) & (pos == 0) & (pend_side == 0) & (nent < max_ent) & (last_x < c)
        if sig.any():
            idx = np.nonzero(sig)[0]
            side = np.where(y[idx, c], 1, -1).astype(np.int8)
            nent[idx] += 1
            qs = np.where(side == 1, p[idx, c], 1 - p[idx, c])
            if maker_entry:
                bid = np.where(side == 1, YB[idx, c], 1 - YA[idx, c])
                ask = np.where(side == 1, YA[idx, c], NA[idx, c])
                better = np.round(bid + 0.01, 4)
                al = better < ask - 1e-9
                px = np.where(al, better, bid)
                g = _ok(px) & (c < 13)
                i2 = idx[g]
                pend_side[i2], pend_c[i2], pend_px[i2], pend_alone[i2] = side[g], c, px[g], al[g]
                pend_q[i2], pend_dec[i2] = qs[g], c
            elif delay:
                g = c + delay <= 13
                i2 = idx[g]
                pend_side[i2], pend_c[i2], pend_q[i2], pend_dec[i2] = side[g], c + delay, qs[g], c
            else:
                px = np.where(side == 1, YA[idx, c], NA[idx, c])
                g = _ok(px)
                open_(idx[g], side[g], c, px[g], TAKER, qs[g], c)
        # 5. (re)place the resting maker sell for every open position
        if mk is not None:
            held = pos != 0
            if held.any():
                sb = np.where(pos == 1, yes_bid_c, 1 - YA[:, c])
                ask = np.where(pos == 1, YA[:, c], NA[:, c])
                q = np.where(pos == 1, pe, 1 - pe)
                lim = np.round(np.clip(q + mk / 100, 0.01, 0.99), 2)
                lim = np.where(_ok(sb), np.fmax(lim, np.round(sb + 0.01, 2)), lim)
                lim = np.where(held & np.isfinite(q) & (c < 13), lim, np.nan)
                L = np.where(held, lim, L)
                alone = ~(ask <= lim + 1e-9)
    out = {k: v[:ne] for k, v in E.items()}
    out["m"] = out["m"].astype(int)
    res = ctx.result[out["m"]]
    out["res"] = ((res == 1) == (out["side"] == 1)).astype(float)
    out["vr"] = (P["vol240"] / P["vol1m"])[out["m"], out["dec"].astype(int)]
    return out


SIZES = {
    "flat": None,
    "k3": ("kelly", 1.0, 3), "k5": ("kelly", 1.0, 5), "k8": ("kelly", 1.0, 8),
    "k5p05": ("kelly", 0.5, 5), "k5p15": ("kelly", 1.5, 5),
    "gap5": ("gap", 1.0, 5), "ret5": ("ret", 1.0, 5),
    "k5vr+": ("kelly_vr", 1.0, 5), "k5vr-": ("kelly_vr", -1.0, 5),
}


def weight(E, size):
    s = SIZES[size]
    if s is None:
        return np.ones(len(E["px"]))
    kind, pw, _ = s
    q, px = E["q"], E["px"]
    if kind == "gap":
        w = np.clip(q - px, 1e-4, None) ** pw
    elif kind == "ret":
        w = np.clip((q - px) / px, 1e-4, None) ** pw
    else:
        w = np.clip((q - px) / (1 - px), 1e-4, None)
        if kind == "kelly_vr":
            w = w * np.clip(np.nan_to_num(E["vr"], nan=1.0), 0.5, 2.0) ** pw
        else:
            w = w ** pw
    return w


def pnl_of(E, size, norm, frac=1.0):
    """Per-position P&L at an average stake of ~$10 (stake = 10 x min(w / norm, cap))."""
    s = SIZES[size]
    if s is None:
        stake = np.full(len(E["px"]), STAKE)
    else:
        stake = STAKE * np.minimum(weight(E, size) / norm, s[2])
    px = E["px"]
    n = np.maximum(1, np.floor(stake / px + 1e-9))
    fe = _fee(px, n, E["erate"])
    ex = np.isfinite(E["xpx"])
    ns = np.where(ex, n if frac >= 1 else np.floor(n * frac + 1e-9), 0)
    nh = n - ns
    xp = np.where(ex, E["xpx"], 0.0)
    pnl = ns * (xp - px) - np.where(ex, _fee(xp, ns, E["xrate"]), 0.0) + nh * (E["res"] - px) - fe
    return pnl, stake, n, fe


# =========================================================================== families (all-coin scope)
EX = {
    "hold": {}, "c-6": {"conv": -6}, "c-4": {"conv": -4}, "c-2": {"conv": -2}, "c0": {"conv": 0},
    "c2": {"conv": 2}, "c4": {"conv": 4},
    "c0p0": {"conv": 0, "minp": 0}, "c0p4": {"conv": 0, "minp": 4},
    "c0m11": {"conv": 0, "tmax": 11}, "c0m13": {"conv": 0, "tmax": 13},
    "c0t13": {"conv": 0, "tstop": 13}, "c0t14": {"conv": 0, "tstop": 14},
    "tr5_3": {"trail": (5, 3)}, "c0tr5_3": {"conv": 0, "trail": (5, 3)}, "c0tr10_5": {"conv": 0, "trail": (10, 5)},
    "c0h": {"conv": 0, "frac": 0.5}, "c-4h": {"conv": -4, "frac": 0.5},
    "c0s15": {"conv": 0, "stop": 15}, "s15": {"stop": 15},
}
for _m in (-2, 0, 2, 4, 6):
    EX[f"mk{_m}"] = {"maker": _m}
    EX[f"mk{_m}c0"] = {"maker": _m, "conv": 0}
    EX[f"mk{_m}c2"] = {"maker": _m, "conv": 2}
X_EXITS = ["hold", "c-6", "c-4", "c-2", "c0", "c2", "c4", "c0p0", "c0p4", "c0m11", "c0m13", "c0t13", "c0t14",
           "tr5_3", "c0tr5_3", "c0tr10_5", "c0h", "c-4h", "c0s15", "s15"]
TWO = ["fv13", "fv12v8"]
DEDGE = [-0.02, -0.01, 0.0, 0.01, 0.02]
S4 = ["flat", "k3", "k5", "k8"]

FAM5 = {
    "x_exit": dict(name="Exit variants (+ sizing)",
                   idea="The two best lab3 entries (Kelly-sized and scalp signals) with 20 exit rules: sell at fair "
                        "value -/+ k cents, only in profit, only until minute 11/13, time stop, trailing stop, "
                        "model stop-loss, half exits; and 10 stake rules (flat, Kelly capped 3-8x, Kelly^0.5/1.5, "
                        "edge-, return- and volatility-regime-scaled).",
                   grid=dict(entry=TWO, dedge=DEDGE, timing=["none"], exit=X_EXITS, size=list(SIZES))),
    "x_maker_exit": dict(name="Maker exit at fair value",
                         idea="Taker entry, then rest a sell at fair value + m cents (re-priced every minute) instead "
                              "of hitting the bid; optionally still hit the bid once it reaches fair value - k.",
                         grid=dict(entry=TWO, dedge=DEDGE, timing=["none"],
                                   exit=[f"mk{m}{s}" for m in (-2, 0, 2, 4, 6) for s in ("", "c0", "c2")], size=S4)),
    "x_reentry": dict(name="Re-entry after an early exit",
                      idea="After selling early, the same market may be bought again (either side) if the mispricing "
                           "re-appears; one position at a time, up to 2-8 round trips per market.",
                      grid=dict(entry=TWO, dedge=DEDGE, timing=["none"], exit=["c-2", "c0", "c2", "c4"],
                                reentry=[2, 3, 4, 8], size=S4 + ["k5p05"])),
    "x_maker_entry": dict(name="Maker entry + taker exit",
                          idea="On the signal rest a buy one cent above the best bid for 1-3 minutes (maker fee) "
                               "instead of paying the ask; exit as before.",
                          grid=dict(entry=TWO, dedge=DEDGE, timing=["none"], exit=["hold", "c0", "c2"],
                                    wait=[1, 2, 3], size=S4)),
    "x_timing": dict(name="Entry timing",
                     idea="Only enter when the gap is wider than a minute ago (edge growing), when the signal has "
                          "held for two minutes (confirmation), or when it is narrowing (control).",
                     grid=dict(entry=TWO, dedge=DEDGE, timing=["grow", "confirm", "shrink"], exit=["hold", "c0", "c2"],
                               size=S4)),
    "x_cap": dict(name="Portfolio cap on same-direction bets",
                  idea="All 9 coins tend to move together inside a 15-minute window. Allow at most K same-direction "
                       "positions per window (first come, or biggest edge first).",
                  grid=dict(entry=TWO, dedge=[0.0], timing=["none"], exit=["hold", "c0", "c2"], capk=[1, 2, 3, 4, 6],
                            prio=["first", "edge"], size=S4)),
    "x_entries": dict(name="Other lab3 entries with sizing + exits",
                      idea="The other golden all-coin lab3 entries (fresh-move/lagging quote, recalibrated, momentum, "
                           "bootstrap, EWMA vol, re-tuned, fat-tail) and three ensembles of them, each with Kelly "
                           "stakes and the early exit.",
                      grid=dict(entry=["lag", "shape", "drift", "emp", "vol", "ref", "t4", "ens_or4", "ens_or3",
                                       "ens_vote2"], dedge=[-0.01, 0.0, 0.01], timing=["none"],
                                exit=["hold", "c-2", "c0", "c2", "c4"], size=S4)),
    "x_combo": dict(name="Best pieces combined",
                    idea="Designed after the search-window results of the families above (holdout untouched): the "
                         "strongest entries (scalp, fresh-move/lagging quote, EWMA vol, recalibrated, 4-model "
                         "ensemble) with edge offsets, edge-growing timing, exit at fair value or within 2c, one "
                         "re-entry, Kelly stakes, and an optional 6-coin same-direction cap.",
                    grid=dict(entry=["fv12v8", "lag", "vol", "shape", "ens_or4"], dedge=[0.0, 0.01, 0.02],
                              timing=["none", "grow"], exit=["c0", "c2"], reentry=[1, 2], capk=[0, 6], prio=["first"],
                              size=["flat", "k5", "k5p15"])),
}
REF_CFG = {"entry": "fv13", "dedge": 0.0, "timing": "none", "exit": "c0", "size": "k5"}  # = sized_exit:ALL


def configs(fam):
    g = FAM5[fam]["grid"]
    keys = list(g)
    import itertools
    return [dict(zip(keys, v)) for v in itertools.product(*(g[k] for k in keys))]


def _exd(cfg):
    ex = dict(EX[cfg["exit"]])
    if cfg.get("reentry"):
        ex["reentry"] = cfg["reentry"]
    if cfg.get("wait"):
        ex["entry"], ex["wait"] = "maker", cfg["wait"]
    return ex


def episodes(where, cfg, delay=0, coins=None):
    """Simulate one config on every coin of G[where] -> dict of concatenated episode arrays (+ coin, window)."""
    ex = _exd(cfg)
    parts = []
    for coin in coins or list(G[where]):
        ctx = G[where][coin]
        y, n, p = entry_masks(ctx, cfg["entry"], cfg.get("dedge", 0.0), cfg.get("timing", "none"))
        E = simulate(ctx, y, n, p, ex, delay)
        E["coin"] = np.full(len(E["m"]), COINS.index(coin))
        E["win_ts"] = ctx.open_ts[E["m"]]
        E["fold"] = ctx.fold[E["m"]] if ctx.fold is not None else np.zeros(len(E["m"]), int)
        parts.append(E)
    return {k: np.concatenate([e[k] for e in parts]) for k in parts[0]}


def cap_mask(E, k, prio, w):
    """Keep at most k same-direction positions per 15-minute window across coins: earliest entry minute
    first (ties: bigger edge), or biggest edge first."""
    df = pd.DataFrame({"w": E["win_ts"], "s": E["side"], "c": E["fc"], "e": -w, "i": np.arange(len(w))})
    df = df.sort_values(["w", "s", "e"] if prio == "edge" else ["w", "s", "c", "e"], kind="stable")
    r = df.groupby(["w", "s"], sort=False).cumcount().to_numpy()
    keep = np.zeros(len(w), bool)
    keep[df.i.to_numpy()[r < k]] = True
    return keep


def evaluate(E, cfg, norm):
    """-> per-position pnl, stake, n, fee, keep-mask."""
    keep = np.ones(len(E["px"]), bool)
    if cfg.get("capk"):
        keep = cap_mask(E, cfg["capk"], cfg["prio"], weight(E, cfg["size"]))
    pnl, stake, n, fe = pnl_of(E, cfg["size"], norm, EX[cfg["exit"]].get("frac", 1.0))
    return pnl, stake, n, fe, keep


def norm_of(E, cfg):
    if SIZES[cfg["size"]] is None:
        return 1.0
    w = weight(E, cfg["size"])
    if cfg.get("capk"):
        w = w[cap_mask(E, cfg["capk"], cfg["prio"], w)]
    return float(w.mean()) if len(w) else 1.0


def per_market(E, pnl, keep):
    """Sum positions per market (re-entry -> several positions in one market count as ONE observation)."""
    key = E["coin"].astype(np.int64) * 10_000_000 + E["m"].astype(np.int64)
    k, inv = np.unique(key[keep], return_inverse=True)
    s = np.bincount(inv, weights=pnl[keep])
    fold = np.zeros(len(k), int)
    fold[inv] = E["fold"][keep]
    return s, fold


def _search_task(args):
    fam, sub = args
    out = []
    for coin in G["search"]:
        G["search"][coin].cache = {}
    sims = {}
    for i, cfg in sub:
        sk = (cfg["exit"], cfg.get("reentry"), cfg.get("wait"))
        if sk not in sims:
            sims[sk] = episodes("search", cfg)
        E = sims[sk]
        nrm = norm_of(E, cfg)
        pnl, _, _, _, keep = evaluate(E, cfg, nrm)
        s, fold = per_market(E, pnl, keep)
        a = np.zeros((N_FOLDS, 3))
        a[:, 0] = np.bincount(fold, minlength=N_FOLDS)
        a[:, 1] = np.bincount(fold, weights=s, minlength=N_FOLDS)
        a[:, 2] = np.bincount(fold, weights=s ** 2, minlength=N_FOLDS)
        out.append((i, a, nrm))
    for coin in G["search"]:
        G["search"][coin].cache = {}
    return fam, out


def _tasks(fam):
    """Group a family's configs so that one task shares the entry masks / simulations."""
    cf = configs(fam)
    groups = {}
    for i, c in enumerate(cf):
        groups.setdefault((c["entry"], c["dedge"], c["timing"]), []).append((i, c))
    return [(fam, g) for g in groups.values()]


def _lag():
    try:
        with open(D.DATA_DIR / "real_all9_console.log", "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 20000))
            txt = f.read().decode(errors="ignore")
        import re
        v = [float(x) for x in re.findall(r"lag=([0-9.]+)s", txt)][-30:]
        return sorted(v)[len(v) // 2] if v else None
    except Exception:
        return None


def pmap(fn, tasks, workers, label=""):
    out, t0 = [], time.time()
    lag = _lag()
    w = 1 if (lag or 0) > 2.5 else max(1, min(workers, 2))
    print(f"  {label}: {len(tasks)} tasks on {w} worker(s) (demo bot median lag {lag}s)", flush=True)
    if w == 1:
        for i, t in enumerate(tasks):
            out.append(fn(t))
            if (i + 1) % 5 == 0:
                print(f"  {label} {i + 1}/{len(tasks)} ({time.time() - t0:.0f}s, lag {_lag()}s)", flush=True)
        return out
    with Pool(w) as pool:
        for i, r in enumerate(pool.imap_unordered(fn, tasks, chunksize=1)):
            out.append(r)
            if (i + 1) % 5 == 0:
                print(f"  {label} {i + 1}/{len(tasks)} ({time.time() - t0:.0f}s, lag {_lag()}s)", flush=True)
    return out


# =========================================================================== final exam
def trades_df(where, cfg, norm, delay=0, coins=None):
    """One row per market traded (positions summed), in lab3.summ's format."""
    if not G.get(where):
        return pd.DataFrame(columns=["ts", "pnl"])
    for ctx in G[where].values():
        ctx.cache = {}
    E = episodes(where, cfg, delay, coins)
    if not len(E["m"]):
        return pd.DataFrame(columns=["ts", "pnl"])
    pnl, stake, n, fe, keep = evaluate(E, cfg, norm)
    df = pd.DataFrame({"coin": E["coin"], "m": E["m"], "ts": E["win_ts"] + 60 * (E["fc"].astype(int) + 1),
                       "win_ts": E["win_ts"], "pnl": pnl, "stake": stake, "price": E["px"],
                       "cost": n * E["px"] + fe, "fee": fe, "exited": np.isfinite(E["xpx"])})[keep]
    g = df.groupby(["coin", "m"], sort=False)
    out = g.agg(ts=("ts", "min"), win_ts=("win_ts", "first"), pnl=("pnl", "sum"), stake=("stake", "sum"),
                price=("price", "first"), cost=("cost", "sum"), fee=("fee", "sum"), exited=("exited", "mean"),
                positions=("pnl", "size")).reset_index()
    out["win"] = out.pnl > 0
    out["series"] = [COINS[i] for i in out.coin]
    for ctx in G[where].values():
        ctx.cache = {}
    return out


def _tser(x):
    x = np.asarray(x, float)
    if len(x) < 3 or x.std(ddof=1) == 0:
        return 0.0
    return round(float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))), 2)


def summ(df):
    s = lab3.summ(df if len(df) else None)
    if len(df):
        s["t_by_window"] = _tser(df.groupby("win_ts").pnl.sum().values)
        s["t_by_day"] = _tser(df.groupby(df.ts // 86400).pnl.sum().values)
        s["positions"] = int(df.positions.sum())
        s["exit_share"] = round(float(df.exited.mean()), 3)
    return s


def exam(cfg, norm):
    hold = trades_df("hold", cfg, norm)
    arch = trades_df("arch", cfg, norm)
    fresh = trades_df("fresh", cfg, norm)
    d1 = trades_df("hold", cfg, norm, delay=1)
    srch = trades_df("search", cfg, norm)
    out = {"holdout": summ(hold), "curve": lab3.curve(hold), "archive": {**summ(arch), "coins": [lab3.cname(c) for c in G["arch"]]},
           "fresh": {**summ(fresh), "span": _span(fresh)}, "search_insample": summ(srch),
           "delay1": ({k: v for k, v in summ(d1).items() if k in ("pnl", "t", "trades")} if not cfg.get("wait") else
                      {"pnl": None, "t": None, "trades": None, "note": "latency check not modelled for maker entries"}),
           "holdout_by_coin": {lab3.cname(c): round(float(g.pnl.sum()), 2) for c, g in hold.groupby("series")}}
    if len(arch):
        mo = pd.to_datetime(arch.ts, unit="s").dt.strftime("%Y-%m")
        out["archive"]["monthly_pnl"] = {k: round(float(v), 2) for k, v in arch.groupby(mo).pnl.sum().items()}
    return out, {"hold": hold, "arch": arch, "fresh": fresh}


def _span(df):
    if not len(df):
        return None
    return f"{pd.to_datetime(df.win_ts.min(), unit='s'):%Y-%m-%d %H:%M} to {pd.to_datetime(df.win_ts.max(), unit='s'):%Y-%m-%d %H:%M} UTC"


def paired(a, b, by="win_ts"):
    """Extra P&L of a over b on the same 15-minute windows + t-stat of the per-window difference."""
    wa, wb = a.groupby(by).pnl.sum(), b.groupby(by).pnl.sum()
    W = wa.index.union(wb.index)
    d = wa.reindex(W, fill_value=0).to_numpy() - wb.reindex(W, fill_value=0).to_numpy()
    return {"extra_pnl": round(float(d.sum()), 2), "t": _tser(d)}


# =========================================================================== search
SEARCH_CACHE = D.DATA_DIR.parent / "lab" / "lab5_search.pkl"


def search(fams, workers=2):
    """Score every config of every family on the 5 search folds (all coins pooled). Cached on disk."""
    import pickle
    cache = pickle.loads(SEARCH_CACHE.read_bytes()) if SEARCH_CACHE.exists() else {}
    todo = [f for f in fams if f not in cache or cache[f]["n"] != len(configs(f))]
    if todo:
        tasks = [t for f in todo for t in _tasks(f)]
        tasks.sort(key=lambda t: -len(t[1]))
        res = pmap(_search_task, tasks, workers, "search")
        for f in todo:
            n = len(configs(f))
            cache[f] = {"n": n, "agg": np.zeros((n, N_FOLDS, 3)), "norm": np.ones(n)}
        for f, out in res:
            for i, a, nrm in out:
                cache[f]["agg"][i] = a
                cache[f]["norm"][i] = nrm
        SEARCH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SEARCH_CACHE.write_bytes(pickle.dumps(cache))
    return cache


def _tv(a):
    n, s, ss = a[..., 0], a[..., 1], a[..., 2]
    nn = np.maximum(n, 2)
    var = (ss - s * s / nn) / (nn - 1)
    with np.errstate(all="ignore"):
        t = s / nn / np.sqrt(var / nn)
    return np.where((n >= lab3.MIN_TRADES) & (var > 0), t, -np.inf)


def walk_t(agg):
    """lab3.walk, but each fold's config is the one with the best t-stat (not P&L) on the earlier folds: the bar
    is a t-stat, and stake-scaling variants can buy P&L with variance."""
    oos = np.zeros(3)
    picks, fold_pnl = [], []
    for k in range(1, N_FOLDS):
        sc = _tv(agg[:, :k, :].sum(1))
        if not np.isfinite(sc).any():
            picks.append(None)
            fold_pnl.append(0.0)
            continue
        c = int(np.argmax(sc))
        picks.append(c)
        oos += agg[c, k]
        fold_pnl.append(float(agg[c, k, 1]))
    full = agg.sum(1)
    sc = _tv(full)
    final = int(np.argmax(sc)) if np.isfinite(sc).any() else None
    return {"oos": {"pnl": round(float(oos[1]), 2), "trades": int(oos[0]), "t": round(lab3.tstat_agg(oos), 2),
                    "fold_win": round(float(np.mean([x > 0 for x in fold_pnl])), 2)},
            "picks": picks, "final": final,
            "final_search": None if final is None else {"pnl": round(float(full[final, 1]), 2),
                                                        "trades": int(full[final, 0]),
                                                        "t": round(lab3.tstat_agg(full[final]), 2)},
            "oos_by_pnl_selection": lab3.walk(agg)["oos"]}


def ref_search(cache):
    """The bar's own search record: sized_exit:ALL is config REF_CFG of x_exit (fixed, so in-sample)."""
    cf = configs("x_exit")
    i = next(i for i, c in enumerate(cf) if all(c.get(k) == v for k, v in REF_CFG.items()))
    a = cache["x_exit"]["agg"][i]
    tf = a[1:].sum(0)
    return {"pnl_folds2_5": round(float(tf[1]), 2), "t_folds2_5": round(lab3.tstat_agg(tf), 2),
            "pnl": round(float(a.sum(0)[1]), 2), "t": round(lab3.tstat_agg(a.sum(0)), 2),
            "trades": int(a.sum(0)[0]), "norm": float(cache["x_exit"]["norm"][i])}


def is_ref(cfg):
    return all(cfg.get(k) == v for k, v in REF_CFG.items()) and not cfg.get("capk") and cfg.get("reentry", 1) <= 1 \
        and not cfg.get("wait")


def describe(cfg):
    e = ENTRY.get(cfg["entry"])
    ent = {"fv13": "Kelly-sized entry (fair value, 13c edge)", "fv12v8": "scalp entry (vol x0.8, 12c edge)"}.get(
        cfg["entry"], f"{cfg['entry']} entry")
    parts = [ent + (f" {cfg['dedge'] * 100:+.0f}c" if cfg.get("dedge") else "")]
    if cfg.get("timing", "none") != "none":
        parts.append({"grow": "edge growing", "confirm": "2-minute confirmation", "shrink": "edge shrinking"}[cfg["timing"]])
    if cfg.get("wait"):
        parts.append(f"maker buy at bid+1c for {cfg['wait']} min")
    x = EX[cfg["exit"]]
    xs = []
    if "maker" in x:
        xs.append(f"rest a sell at fair value {x['maker']:+d}c")
    if "conv" in x:
        xs.append(f"sell at the bid once it is within {x['conv']}c of fair value" if x["conv"] >= 0 else
                  f"sell at the bid once it is {-x['conv']}c above fair value")
    if "minp" in x:
        xs.append(f"only if >= {x['minp']}c profit")
    if "tmax" in x:
        xs.append(f"only until minute {x['tmax']}")
    if "tstop" in x:
        xs.append(f"time stop minute {x['tstop']}")
    if "trail" in x:
        xs.append(f"trailing stop (arm {x['trail'][0]}c, give back {x['trail'][1]}c)")
    if "stop" in x:
        xs.append(f"stop when fair value < entry - {x['stop']}c")
    if "frac" in x:
        xs.append("sell half")
    parts.append(", ".join(xs) if xs else "hold to settlement")
    if cfg.get("reentry", 1) > 1:
        parts.append(f"re-enter up to {cfg['reentry']}x per market")
    if cfg.get("capk"):
        parts.append(f"max {cfg['capk']} same-direction coins per window ({cfg['prio']})")
    sz = SIZES[cfg["size"]]
    parts.append("flat $10" if sz is None else f"{sz[0]} stakes^{sz[1]} capped {sz[2]}x")
    return "; ".join(parts)


# =========================================================================== judging + report
PEEKED = 3   # holdout runs made while validating the simulator (maker0, maker0+conv0, re-entry x3 conv0)


def judge(c, t_bar, live_best, ref):
    h, a, f = c["holdout"], c["archive"], c["fresh"]
    league = h["t"] >= 6 or (h["pnl"] >= 8000 and h["t"] >= 5.5)
    ch = {
        "holdout_profit": h["pnl"] > 0,
        "strict_t": h["t"] >= t_bar,
        "same_league": bool(league),
        "archive": bool(a["trades"] >= 50 and a["pnl"] > 0 and a["t"] >= 4),
        "fresh_positive": bool(f["trades"] > 0 and f["pnl"] > 0),
        "not_one_day": h.get("top_day_share") is not None and h["top_day_share"] <= 0.40,
        "beats_live_pnl": h["pnl"] > live_best["pnl"],
        "beats_live_t": h["t"] > live_best["t"],
        "live_data_ok": True,
    }
    c["checks"] = ch
    c["beats_sized_exit"] = bool(h["pnl"] > ref["holdout"]["pnl"] and h["t"] > ref["holdout"]["t"])
    golden = all(ch.values())
    c["status"] = "golden" if golden else ("pass" if h["pnl"] > 0 and h["t"] >= 2 else "fail")
    miss = [k for k, v in ch.items() if not v]
    c["why"] = (f"Holdout ${h['pnl']:,.0f} (t {h['t']}), archive ${a['pnl']:,.0f} (t {a['t']}), fresh "
                f"${f['pnl']:,.0f} (t {f['t']}, {f['trades']} mkts); vs sized_exit:ALL ${c['vs_sized_exit']['extra_pnl']:+,.0f} "
                f"on the holdout (paired t {c['vs_sized_exit']['t']}). "
                + ("All golden tests met." if golden else "Missed: " + ", ".join(miss) + "."))


def main(args=None):
    args = list(args or [])
    cmd = args[0] if args else "run"
    if cmd == "download":
        return download(args[1:] or None)
    workers = int(args[1]) if len(args) > 1 else 2
    try:
        os.nice(19)
    except OSError:
        pass
    t0 = time.time()
    lab3.G["quick"] = 0
    print("lab5: loading lab3 panels + features ...", flush=True)
    full = lab3.load(verbose=False)
    fams = list(FAM5)
    cache = search(fams, workers)
    print(f"search done ({time.time() - t0:.0f}s)", flush=True)
    ref_s = ref_search(cache)
    print(f"sized_exit:ALL on the search window (in-sample, fixed): {ref_s}", flush=True)
    WF, cands = {}, []
    for f in fams:
        cf = configs(f)
        w = walk_t(cache[f]["agg"])
        WF[f] = w
        fin = cf[w["final"]] if w["final"] is not None else None
        print(f"  {f:14s} WF ${w['oos']['pnl']:>9} n={w['oos']['trades']:>6} t={w['oos']['t']:>5} "
              f"folds+={w['oos']['fold_win']} | final {w['final_search']} {fin and describe(fin)}", flush=True)
        if cmd == "search":
            continue
        if lab3.shortlisted(w) and fin is not None and not is_ref(fin):
            cands.append({"id": f"{f}:ALL", "family": f, "cfg": fin, "norm": float(cache[f]["norm"][w["final"]]),
                          "search": {**w["oos"], "insample": w["final_search"]}})
    if cmd == "search":
        return
    cands = sorted(cands, key=lambda c: -c["search"]["t"])[:MAX_HOLDOUT]
    k_total = PRIOR_HOLDOUT_TESTS + PEEKED + len(cands)
    t_bar = round(NormalDist().inv_cdf(1 - 0.05 / k_total), 2)
    print(f"{len(cands)} candidates go to the holdout; cumulative holdout tests {k_total} -> strict bar t >= {t_bar}",
          flush=True)
    load_fresh()
    # ---- baselines (re-runs of rules already counted; fresh data is new)
    BASE = [("sized_exit:ALL", "Kelly-sized entries + exit at fair value (golden_live EXTRA)", REF_CFG, ref_s["norm"]),
            ("sized:ALL", "Kelly-sized entries, hold (lab3 golden #2)", {**REF_CFG, "exit": "hold"}, ref_s["norm"]),
            ("scalp:ALL", "Flat $10 scalp: exit at fair value (lab3 golden #1)",
             {"entry": "fv12v8", "dedge": 0.0, "timing": "none", "exit": "c0", "size": "flat"}, 1.0)]
    base, DF = [], {}
    for bid, lab, cfg, nrm in BASE:
        r, dfs = exam(cfg, nrm)
        DF[bid] = dfs
        base.append({"id": bid, "label": lab, "scope": "ALL", "strategy": "lab5", "execution": "taker", "params": cfg,
                     "norm": nrm, **r})
        print(f"  baseline {bid:16s} hold ${r['holdout']['pnl']} t {r['holdout']['t']} | arch ${r['archive']['pnl']} "
              f"t {r['archive']['t']} | fresh ${r['fresh']['pnl']} t {r['fresh']['t']} n {r['fresh']['trades']}", flush=True)
    lab3_res = json.loads(lab3.OUT.read_text())
    live = next(b for b in lab3_res["baselines"] if b["id"] == "live:ALL:fair_value")
    base.append({k: live.get(k) for k in ("id", "label", "scope", "strategy", "execution", "params", "holdout", "curve",
                                          "archive", "delay1")})
    live_best = {"pnl": max(b["holdout"]["pnl"] for b in lab3_res["baselines"] if b["scope"] == "ALL"),
                 "t": max(b["holdout"]["t"] for b in lab3_res["baselines"] if b["scope"] == "ALL")}
    ref = base[0]
    # ---- final exam, once per candidate
    for c in cands:
        r, dfs = exam(c["cfg"], c["norm"])
        c.update(r)
        c["vs_sized_exit"] = paired(dfs["hold"], DF["sized_exit:ALL"]["hold"])
        c["vs_sized_exit_archive"] = paired(dfs["arch"], DF["sized_exit:ALL"]["arch"])
        c["vs_sized_exit_fresh"] = paired(dfs["fresh"], DF["sized_exit:ALL"]["fresh"]) if len(dfs["fresh"]) else None
        judge(c, t_bar, live_best, ref)
        print(f"  {c['status']:6s} {c['id']:16s} {c['why']}", flush=True)
    cands.sort(key=lambda c: ({"golden": 0, "pass": 1, "fail": 2}[c["status"]], -c["holdout"]["t"]))
    for c in cands:
        c["label"] = "All 9 coins · " + FAM5[c["family"]]["name"] + " (" + describe(c["cfg"]) + ")"
    fam_rows = []
    for f in fams:
        mine = [c for c in cands if c["family"] == f]
        w = WF[f]
        fam_rows.append({"id": f, "name": FAM5[f]["name"], "idea": FAM5[f]["idea"], "configs": len(configs(f)),
                         "scopes_tested": 1, "shortlisted": len(mine),
                         "best_holdout_t": max([c["holdout"]["t"] for c in mine], default=None),
                         "best_search_t": (w["final_search"] or {}).get("t"),
                         "status": "golden" if any(c["status"] == "golden" for c in mine) else
                         ("pass" if any(c["status"] == "pass" for c in mine) else "fail"),
                         "walk_forward": {"All 9 coins": w["oos"]},
                         "finding": (f"Walk-forward t {w['oos']['t']} (sized_exit:ALL fixed, in-sample folds 2-5: "
                                     f"t {ref_s['t_folds2_5']}); " + (
                             f"best: {mine[0]['label']}: ${mine[0]['holdout']['pnl']:,.0f} at t {mine[0]['holdout']['t']} "
                             f"({mine[0]['status']})." if mine else "nothing new reached the holdout "
                             "(not shortlisted, or the walk-forward picked sized_exit:ALL itself)."))})
    pub = []
    for c in cands:
        cfg = c["cfg"]
        pub.append({"id": f"{c['id']}:{_exec(cfg)}", "label": c["label"], "family": c["family"], "scope": "ALL", "strategy": c["family"],
                    "execution": _exec(cfg), "params": {**cfg, "norm": c["norm"], "exit_rule": EX[cfg["exit"]]},
                    "search": c["search"], "holdout": c["holdout"], "archive": c["archive"], "fresh": c["fresh"],
                    "search_insample": c["search_insample"], "delay1": c["delay1"],
                    "vs_baseline": {"baseline_id": "sized_exit:ALL", "pnl_diff": round(c["holdout"]["pnl"] - ref["holdout"]["pnl"], 2),
                                    "t_diff": round(c["holdout"]["t"] - ref["holdout"]["t"], 2)},
                    "paired_vs_live": {"baseline_id": "sized_exit:ALL", **c["vs_sized_exit"]},
                    "paired_vs_sized_exit_archive": c["vs_sized_exit_archive"],
                    "paired_vs_sized_exit_fresh": c["vs_sized_exit_fresh"],
                    "beats_sized_exit": c["beats_sized_exit"],
                    "holdout_by_coin": c["holdout_by_coin"], "status": c["status"], "why": c["why"],
                    "checks": c["checks"], "live_implementation": live_notes(cfg, c["norm"]), "curve": c["curve"]})
    out = {
        "generated": int(time.time()), "runtime_s": int(time.time() - t0),
        "method": {
            "search_window": f"{pd.to_datetime(G['start'], unit='s'):%Y-%m-%d %H:%M} to {pd.to_datetime(G['cut'], unit='s'):%Y-%m-%d %H:%M} UTC",
            "search_start": G["start"], "holdout_start": G["cut"], "holdout_days": lab3.HOLDOUT_DAYS,
            "n_folds": N_FOLDS, "n_families": len(fams), "n_grid_configs": sum(len(configs(f)) for f in fams),
            "n_configs_tested": sum(len(configs(f)) for f in fams), "n_walk_forwards": len(fams),
            "n_holdout_tests": len(cands), "n_holdout_tests_cumulative": k_total,
            "holdout_tests_breakdown": {"lab3": 112, "combo_sized_exit": 1, "lab5_validation_peeks": PEEKED,
                                        "lab5_candidates": len(cands)},
            "t_bar_strict": t_bar, "stake": STAKE, "scope": "ALL (all 9 coins pooled, one parameter set)",
            "selection": "walk-forward and final tuning pick the config with the best search t-stat (lab3 used P&L)",
            "shortlist": "lab3's: walk-forward P&L > 0, t >= 1.5, >= 50 trades, >= half of test folds profitable; and "
                         "the family's final config is not sized_exit:ALL itself; one candidate per family",
            "sized_exit_search": ref_s,
            "fresh_data": {s: {"markets": len(G["fresh"][s]), "span": f"{pd.to_datetime(G['fresh'][s].open_ts.min(), unit='s'):%Y-%m-%d %H:%M} to "
                                                                      f"{pd.to_datetime(G['fresh'][s].open_ts.max(), unit='s'):%Y-%m-%d %H:%M}"}
                           for s in G["fresh"]},
            "rules": RULES5(t_bar, live_best), "caveats": CAVEATS5,
        },
        "coins": {s: {"markets": len(full[s]), "search_markets": len(G["search"][s]), "holdout_markets": len(G["hold"][s]),
                      "archive_markets": len(G["arch"][s]) if s in G["arch"] else 0,
                      "fresh_markets": len(G["fresh"][s]) if s in G["fresh"] else 0} for s in COINS},
        "families": fam_rows, "baselines": base, "candidates": pub, "heatmaps": [],
    }
    out["method"]["decomposition"] = decomposition()
    gold = [c for c in pub if c["status"] == "golden"]
    out["method"]["summary"] = [
        f"{len(gold)} of {len(pub)} lab5 candidates that reached the holdout are golden (cumulative strict bar t >= {t_bar} "
        f"over {k_total} holdout tests).",
        f"Bar: sized_exit:ALL holdout ${ref['holdout']['pnl']:,.0f} (t {ref['holdout']['t']}), archive "
        f"${ref['archive']['pnl']:,.0f} (t {ref['archive']['t']}), fresh ${ref['fresh']['pnl']:,.0f} (t {ref['fresh']['t']}).",
    ] + [f"{c['label']}: {c['why']}" for c in pub]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, default=lab3._jd))
    print(f"done in {time.time() - t0:.0f}s -> {OUT}")
    return out


DECOMP = [
    ("scalp:ALL (scalp entry, flat $10, exit at fair value)", {"entry": "fv12v8", "dedge": 0.0, "exit": "c0", "size": "flat"}),
    ("+ Kelly stakes", {"entry": "fv12v8", "dedge": 0.0, "exit": "c0", "size": "k5"}),
    ("+ exit within 2c of fair value", {"entry": "fv12v8", "dedge": 0.0, "exit": "c2", "size": "k5"}),
    ("+ 14c entry edge", {"entry": "fv12v8", "dedge": 0.02, "exit": "c2", "size": "k5"}),
    ("+ one re-entry (= x_reentry:ALL)", {"entry": "fv12v8", "dedge": 0.02, "exit": "c2", "size": "k3", "reentry": 2}),
    ("scalp entry, Kelly, hold to settlement", {"entry": "fv12v8", "dedge": 0.0, "exit": "hold", "size": "k5"}),
    ("sized_exit:ALL", REF_CFG),
    ("sized_exit:ALL with flat $10", {**REF_CFG, "size": "flat"}),
    ("sized_exit:ALL, exit within 2c", {**REF_CFG, "exit": "c2"}),
]


def decomposition():
    """Where the gain comes from, step by step. Search window, archive and fresh data only: these
    intermediate rules were NOT run on the holdout (they would be extra holdout tests)."""
    out = []
    for name, c in DECOMP:
        c = {"timing": "none", **c}
        for ctx in G["search"].values():
            ctx.cache = {}
        nrm = norm_of(episodes("search", c), c)
        row = {"step": name, "params": c}
        for w in ("search", "arch", "fresh"):
            s = summ(trades_df(w, c, nrm))
            row[w] = {k: s.get(k) for k in ("pnl", "trades", "t", "t_by_window", "max_dd")}
        out.append(row)
    return out


def live_notes(cfg, norm):
    """How golden_live / real.py would run this rule live (golden_live already has the lab3 families, the
    per-minute features, sized_stake and the convK exit_check)."""
    fam, ecfg = ENTRY[cfg["entry"]] if cfg["entry"] in ENTRY else ("ensemble", {})
    ecfg = {k: v for k, v in ecfg.items() if k not in ("cap", "exit")}
    if "edge" in ecfg:
        ecfg["edge"] = round(ecfg["edge"] + cfg.get("dedge", 0.0), 4)
    sz = SIZES[cfg["size"]]
    x = EX[cfg["exit"]]
    steps = [f"Entry: lab3 family '{fam}' with params {ecfg} (golden_live._signal / lab3.FAMILIES[fam]['fn'] on the "
             f"live 1-row panel); taker buy of the signalled side at its ask (YES: yes_ask, NO: 1 - yes_bid)."]
    if sz is not None:
        steps.append(f"Stake: base x min(w / {norm:.6f}, {sz[2]}), w = kelly" + (f"**{sz[1]}" if sz[1] != 1 else "")
                     + ", kelly = max((q - price) / (1 - price), 1e-4), q = the rule's model value of the side at the "
                     "decision minute (golden_live.sized_stake" + (" + a new power parameter" if sz[1] != 1 else "") + ").")
    if "conv" in x:
        steps.append(f"Exit: every later minute, sell all contracts at the held side's bid (YES: yes_bid, NO: 1 - yes_ask, "
                     f"taker/IOC) once bid >= q - {x['conv'] / 100:.2f}, q = the entry family's model value of the held "
                     f"side that minute (golden_live.exit_check with params exit='conv{x['conv']}', kind 'sized_exit').")
    if cfg.get("timing") == "grow":
        steps.append("NEW: entry filter 'edge growing': gap(minute) = q - ask of that side must exceed the same gap one "
                     "minute earlier (previous column of the live panel; no quote a minute ago = allowed).")
    if cfg.get("reentry", 1) > 1:
        steps.append(f"NEW: re-entry. Per-market state (entries used, open position, exit minute). After an exit fills, "
                     f"from the NEXT minute up to the rule's end minute, a fresh signal at the CURRENT minute (mask at "
                     f"column minute-1, not lab3.signal's first-minute logic) opens a new position (either side), Kelly "
                     f"stake again; at most {cfg['reentry']} entry signals per market (a signal with no valid ask still "
                     f"uses one), one position at a time.")
    if cfg.get("capk"):
        steps.append(f"NEW: portfolio cap shared by the 9 coin threads: per 15-minute window at most {cfg['capk']} "
                     f"positions on the same side (YES or NO), first come first served (lock-protected counter keyed "
                     f"by window open time and side).")
    if cfg.get("wait"):
        steps.append(f"NEW: maker entry: rest a buy at best bid + 1c (or at the bid if that would cross) for "
                     f"{cfg['wait']} minute(s), cancel if unfilled.")
    if "maker" in x:
        steps.append(f"NEW: resting sell at q + {x['maker']}c re-priced every minute (never at/below the bid).")
    return steps


def _exec(cfg):
    e = "maker" if cfg.get("wait") else "taker"
    x = EX[cfg["exit"]]
    if "maker" in x:
        return e + "+maker-exit"
    if x:
        return e + "+exit"
    return e


def RULES5(t_bar, live_best):
    return [
        "Only data from before lab3's locked holdout was used to pick settings: each family's grid was scored on the "
        "lab3 search window (5 folds, all 9 coins pooled), walk-forward exactly as lab3, and the config tuned on the "
        "whole search window was frozen and run once on the holdout, the archive and the fresh data.",
        f"(1) Holdout profit with t >= {t_bar}: one-sided Bonferroni at 5% over EVERY test ever run on this holdout "
        "(lab3's 112 + the sized_exit combo + lab5's validation peeks + lab5's candidates).",
        "(2) Same league as the best rules: holdout t >= 6, or holdout P&L >= $8,000 with t >= 5.5.",
        "(3) Archive (NEAR, DOGE, BNB, SOL Apr-Aug, never used for tuning) profitable with t >= 4 on >= 50 markets.",
        "(4) Profitable on fresh markets downloaded after the holdout ended (Nov 1-4).",
        f"(5) Beats the live all-coin rules on the holdout (P&L > ${live_best['pnl']:,.0f}, t > {live_best['t']}), as in lab3.",
        "(6) No more than 40% of its holdout profit from one day; (7) runnable live with data the bot already has "
        "(golden_live features; new execution features are listed per candidate).",
        "Rules with several positions per market (re-entry) are scored per MARKET (positions summed), never per trade. "
        "Stakes average ~$10 on the search window (Kelly normaliser fixed from the search window).",
    ]


CAVEATS5 = [
    "lab3's holdout has now been looked at by 110+ rules; even a rule clearing the cumulative bar here is partly "
    "selected on noise. The archive and the fresh days are the cleaner checks.",
    "Fresh data are only ~1.5-2.5 days (about 1,800 markets), so a fresh t-stat near 1-2 is all that can be expected.",
    "Maker fills (entry or exit) assume our resting order would have traded whenever the bid/ask high-low or a trade "
    "reached its price within the minute; real queues can be worse.",
    "Everything depends on reacting within the minute (see delay1).",
]
