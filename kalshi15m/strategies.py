"""Strategies (vectorised over many markets at once).

Every strategy receives `P`, a dict of 2-D numpy arrays shaped (markets, 14):
column j = state at the END of minute j+1 after the market opened. Keys:
    yes_ask, no_ask, yes_bid, p_model, spot, strike, vol1m, prev_ret, ret_from_open
Values a bot would not have known yet are NaN (the live bot fills columns as
time passes), so a strategy can only use information available at that minute.

A strategy returns (side, minute):
    side   int array, +1 = buy YES, -1 = buy NO, 0 = no trade
    minute int array, the minute (1..14) at which to buy at the ask
"""
from __future__ import annotations

import numpy as np
import math

_erf = np.vectorize(math.erf, otypes=[float])


def ndtr(z):
    """Standard normal CDF (NaN-safe, no scipy needed)."""
    z = np.asarray(z, float)
    out = np.full(z.shape, np.nan)
    ok = np.isfinite(z)
    out[ok] = 0.5 * (1 + _erf(z[ok] / math.sqrt(2)))
    return out

M = 14
MIN = np.arange(1, M + 1)


def _valid(px):
    return np.isfinite(px) & (px > 0) & (px < 1)


def _at(P, minute, side_mask_yes, side_mask_no):
    """Trade at a fixed minute with yes/no masks evaluated at that column."""
    n = P["yes_ask"].shape[0]
    side = np.where(side_mask_yes, 1, np.where(side_mask_no, -1, 0))
    return side.astype(int), np.full(n, minute)


def _first(mask_yes, mask_no):
    """First minute where either mask is true."""
    any_ = mask_yes | mask_no
    has = any_.any(axis=1)
    j = np.argmax(any_, axis=1)
    rows = np.arange(len(j))
    side = np.where(mask_yes[rows, j], 1, -1) * has
    return side.astype(int), j + 1


def baseline_yes(P, minute=1):
    """Always buy YES at the open. Shows the cost of spread + fees."""
    j = minute - 1
    return _at(P, minute, _valid(P["yes_ask"][:, j]), np.zeros(len(P["yes_ask"]), bool))


def momentum(P, minute=1, min_move=0.0005, max_price=0.6):
    """Previous 15m window went up -> buy YES this window (and vice versa)."""
    j = minute - 1
    r, ya, na = P["prev_ret"][:, j], P["yes_ask"][:, j], P["no_ask"][:, j]
    big = np.isfinite(r) & (np.abs(r) >= max(min_move, 1e-12))
    return _at(P, minute, big & (r > 0) & _valid(ya) & (ya <= max_price),
               big & (r < 0) & _valid(na) & (na <= max_price))


def reversal(P, minute=1, min_move=0.0005, max_price=0.6):
    """Fade the previous window's move."""
    j = minute - 1
    r, ya, na = P["prev_ret"][:, j], P["yes_ask"][:, j], P["no_ask"][:, j]
    big = np.isfinite(r) & (np.abs(r) >= max(min_move, 1e-12))
    return _at(P, minute, big & (r < 0) & _valid(ya) & (ya <= max_price),
               big & (r > 0) & _valid(na) & (na <= max_price))


def late_favorite(P, minute=12, lo=0.80, hi=0.95):
    """Near expiry, buy whichever side is priced as a strong (not certain) favourite."""
    j = minute - 1
    ya, na = P["yes_ask"][:, j], P["no_ask"][:, j]
    y = _valid(ya) & (ya >= lo) & (ya <= hi)
    return _at(P, minute, y, ~y & _valid(na) & (na >= lo) & (na <= hi))


def longshot(P, minute=10, max_price=0.15):
    """Buy the cheap side (lottery ticket). Tests the favourite-longshot bias."""
    j = minute - 1
    ya, na = P["yes_ask"][:, j], P["no_ask"][:, j]
    y = _valid(ya) & (ya <= max_price)
    return _at(P, minute, y, ~y & _valid(na) & (na <= max_price))


def model_prob(P, vol_mult=1.0):
    tau = 15 - MIN[None, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.log(P["spot"] / P["strike"]) / (P["vol1m"] * vol_mult * np.sqrt(tau))
    return ndtr(z)


def fair_value(P, start=3, end=13, edge=0.08, vol_mult=1.0, min_price=0.05, max_price=0.95):
    """Price the contract with a driftless lognormal model of spot vs strike
    (vol = trailing 60-min realised vol) and take the first quote that is
    cheaper than fair value by at least `edge`."""
    p = model_prob(P, vol_mult)
    ya, na = P["yes_ask"], P["no_ask"]
    win = (MIN >= start) & (MIN <= end)
    ok = np.isfinite(p) & win[None, :]
    with np.errstate(invalid="ignore"):
        y = ok & _valid(ya) & (ya >= min_price) & (ya <= max_price) & (p - ya >= edge)
        n = ok & _valid(na) & (na >= min_price) & (na <= max_price) & ((1 - p) - na >= edge)
    return _first(y, n)


def spot_lag(P, start=2, end=12, move_sd=1.5, max_price=0.75):
    """Spot has already moved `move_sd` standard deviations away from the strike
    but the book still prices the leader below `max_price` -> buy the leader."""
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.log(P["spot"] / P["strike"]) / (P["vol1m"] * np.sqrt(MIN[None, :]))
        win = ((MIN >= start) & (MIN <= end))[None, :]
        y = win & (z >= move_sd) & _valid(P["yes_ask"]) & (P["yes_ask"] <= max_price)
        n = win & (z <= -move_sd) & _valid(P["no_ask"]) & (P["no_ask"] <= max_price)
    return _first(y, n)


def _prev_z(P):
    """Previous window's return in standard deviations of a 15-minute move."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return P["prev_ret"] / (P["vol1m"] * np.sqrt(15))


def reversal_z(P, minute=1, min_z=1.5, max_z=99.0, max_price=0.6):
    """Fade the previous window only after an unusually large move (in vol units)."""
    j = minute - 1
    z, ya, na = _prev_z(P)[:, j], P["yes_ask"][:, j], P["no_ask"][:, j]
    with np.errstate(invalid="ignore"):
        big = np.isfinite(z) & (np.abs(z) >= min_z) & (np.abs(z) <= max_z)
        return _at(P, minute, big & (z < 0) & _valid(ya) & (ya <= max_price),
                   big & (z > 0) & _valid(na) & (na <= max_price))


def momentum_z(P, minute=1, min_z=1.5, max_z=99.0, max_price=0.6):
    """Follow the previous window only after an unusually large move (in vol units)."""
    j = minute - 1
    z, ya, na = _prev_z(P)[:, j], P["yes_ask"][:, j], P["no_ask"][:, j]
    with np.errstate(invalid="ignore"):
        big = np.isfinite(z) & (np.abs(z) >= min_z) & (np.abs(z) <= max_z)
        return _at(P, minute, big & (z > 0) & _valid(ya) & (ya <= max_price),
                   big & (z < 0) & _valid(na) & (na <= max_price))


def fair_value_v2(P, start=3, end=13, edge=0.06, vol="blend", min_price=0.25, max_price=0.75):
    """Fair-value model restricted to mid-priced contracts (where the earlier version's
    cheap longshot buys did the damage), with a choice of volatility estimate."""
    v = {"60": P["vol1m"], "240": P["vol240"],
         "blend": np.sqrt((P["vol1m"] ** 2 + P["vol240"] ** 2) / 2),
         "max": np.fmax(P["vol1m"], P["vol240"])}[vol]
    tau = 15 - MIN[None, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        p = ndtr(np.log(P["spot"] / P["strike"]) / (v * np.sqrt(tau)))
    ya, na = P["yes_ask"], P["no_ask"]
    ok = np.isfinite(p) & ((MIN >= start) & (MIN <= end))[None, :]
    with np.errstate(invalid="ignore"):
        y = ok & _valid(ya) & (ya >= min_price) & (ya <= max_price) & (p - ya >= edge)
        n = ok & _valid(na) & (na >= min_price) & (na <= max_price) & ((1 - p) - na >= edge)
    return _first(y, n)


def closing_value(P, minute=13, edge=0.10, vol_mult=1.0, min_price=0.10, max_price=0.90):
    """In the last minutes, compare spot vs strike with the little time left; when the
    quote still lags what spot implies, buy the underpriced side at that single minute."""
    j = minute - 1
    tau = 15 - minute
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.log(P["spot"][:, j] / P["strike"][:, j]) / (P["vol1m"][:, j] * vol_mult * np.sqrt(tau))
    p = ndtr(z)
    ya, na = P["yes_ask"][:, j], P["no_ask"][:, j]
    with np.errstate(invalid="ignore"):
        y = np.isfinite(p) & _valid(ya) & (ya >= min_price) & (ya <= max_price) & (p - ya >= edge)
        n = ~y & np.isfinite(p) & _valid(na) & (na >= min_price) & (na <= max_price) & ((1 - p) - na >= edge)
    return _at(P, minute, y, n)


def fair_value_bid(P, start=2, end=12, edge=0.05, vol_mult=1.0, min_price=0.10, max_price=0.90):
    """Built for limit orders: rest a bid on whichever side the fair-value model says is
    worth at least `edge` more than the current BID (not the ask)."""
    p = model_prob(P, vol_mult)
    yb, nb = P["yes_bid"], 1 - P["yes_ask"]
    ok = np.isfinite(p) & ((MIN >= start) & (MIN <= end))[None, :]
    with np.errstate(invalid="ignore"):
        y = ok & _valid(yb) & (yb >= min_price) & (yb <= max_price) & (p - yb >= edge)
        n = ok & _valid(nb) & (nb >= min_price) & (nb <= max_price) & ((1 - p) - nb >= edge)
    return _first(y, n)


# name -> (function, description, parameter grid for the sweep)
def _own_z(P):
    """This coin's move since the open, in standard deviations for the time elapsed."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.log(P["spot"] / P["strike"]) / (P["vol1m"] * np.sqrt(MIN[None, :]))


def cross_lead(P, start=2, end=10, min_z=1.5, lag=0.5, max_price=0.7):
    """BTC tends to move first. When BTC has moved `min_z` sd since the open but this
    coin has moved less than `lag` x that, buy this coin in BTC's direction."""
    if "btc_z" not in P:
        n = P["yes_ask"].shape[0]
        return np.zeros(n, int), np.ones(n, int)
    bz, oz = P["btc_z"], _own_z(P)
    win = ((MIN >= start) & (MIN <= end))[None, :]
    with np.errstate(invalid="ignore"):
        y = win & (bz >= min_z) & (oz < lag * bz) & _valid(P["yes_ask"]) & (P["yes_ask"] <= max_price)
        n = win & (bz <= -min_z) & (oz > lag * bz) & _valid(P["no_ask"]) & (P["no_ask"] <= max_price)
    return _first(y, n)


def quote_move(P, lookback=2, min_move=0.15, follow=False, start=3, end=12, min_price=0.15, max_price=0.85):
    """Kalshi's own price jumped by `min_move` over `lookback` minutes without a matching
    spot move. Fade it (or follow it if follow=True)."""
    mid = (P["yes_bid"] + P["yes_ask"]) / 2
    d = np.full_like(mid, np.nan)
    d[:, lookback:] = mid[:, lookback:] - mid[:, :-lookback]
    win = ((MIN >= start) & (MIN <= end))[None, :]
    up, dn = d >= min_move, d <= -min_move
    if not follow:
        up, dn = dn, up  # fade: price fell -> buy YES
    with np.errstate(invalid="ignore"):
        y = win & up & _valid(P["yes_ask"]) & (P["yes_ask"] >= min_price) & (P["yes_ask"] <= max_price)
        n = win & dn & _valid(P["no_ask"]) & (P["no_ask"] >= min_price) & (P["no_ask"] <= max_price)
    return _first(y, n)


def fair_value_regime(P, start=2, end=13, edge=0.10, regime="rising", min_price=0.05, max_price=0.95):
    """Fair-value model, only when short-term vol is rising (vol60 > vol240) or falling."""
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = P["vol1m"] / P["vol240"]
    keep = (ratio > 1.1) if regime == "rising" else (ratio < 0.9)
    side, minute = fair_value(P, start=start, end=end, edge=edge, min_price=min_price, max_price=max_price)
    rows = np.arange(len(side))
    side = np.where(keep[rows, minute - 1], side, 0)
    return side, minute


def opening_value(P, minute=1, edge=0.06, vol_mult=1.0):
    """The strike is set at the open, so the first minutes should price near 50% plus
    whatever spot did since. Buy whichever side the model says is cheap at `minute`."""
    j = minute - 1
    p = model_prob(P, vol_mult)[:, j]
    ya, na = P["yes_ask"][:, j], P["no_ask"][:, j]
    with np.errstate(invalid="ignore"):
        y = np.isfinite(p) & _valid(ya) & (p - ya >= edge)
        n = ~y & np.isfinite(p) & _valid(na) & ((1 - p) - na >= edge)
    return _at(P, minute, y, n)


STRATEGIES = {
    "baseline_yes": (baseline_yes, "Always buy YES at minute 1. The control group: shows what spread and fees cost.",
                     {"minute": [1]}),
    "momentum": (momentum, "Bet that the previous 15 minutes' direction continues.",
                 {"minute": [1, 2], "min_move": [0.0, 0.0005, 0.001, 0.002], "max_price": [0.55, 0.65]}),
    "reversal": (reversal, "Bet that the previous 15 minutes' direction reverses.",
                 {"minute": [1, 2], "min_move": [0.0, 0.0005, 0.001, 0.002], "max_price": [0.55, 0.65]}),
    "late_favorite": (late_favorite, "Buy the side priced as a strong favourite in the last few minutes.",
                      {"minute": [10, 11, 12, 13, 14], "lo": [0.7, 0.8, 0.9], "hi": [0.95, 0.98]}),
    "longshot": (longshot, "Buy the cheap side (under 25c) and hope for a late reversal.",
                 {"minute": [5, 8, 10, 12], "max_price": [0.05, 0.1, 0.15, 0.25]}),
    "spot_lag": (spot_lag, "Spot has run away from the strike but the order book hasn't caught up: buy the leader.",
                 {"start": [2, 4], "end": [8, 12], "move_sd": [1.0, 1.5, 2.0, 3.0], "max_price": [0.6, 0.75, 0.85]}),
    "reversal_z": (reversal_z, "Fade the previous 15 minutes only after an unusually big move, measured in volatility units.",
                   {"minute": [1, 2, 3], "min_z": [1.0, 1.5, 2.0, 2.5], "max_price": [0.55, 0.65, 0.75]}),
    "momentum_z": (momentum_z, "Follow the previous 15 minutes only after an unusually big move, measured in volatility units.",
                   {"minute": [1, 2, 3], "min_z": [1.0, 1.5, 2.0, 2.5], "max_price": [0.55, 0.65, 0.75]}),
    "fair_value_v2": (fair_value_v2, "Fair-value model limited to 25-75c contracts, with a choice of volatility window.",
                      {"start": [2, 5, 8], "end": [10, 13], "edge": [0.03, 0.05, 0.08, 0.12],
                       "vol": ["60", "blend", "max"], "min_price": [0.2, 0.35], "max_price": [0.65, 0.8]}),
    "closing_value": (closing_value, "Final 1-4 minutes: buy the side the spot price says is underpriced.",
                      {"minute": [11, 12, 13, 14], "edge": [0.05, 0.10, 0.15, 0.20, 0.30],
                       "vol_mult": [0.8, 1.0, 1.25], "min_price": [0.05, 0.15], "max_price": [0.85, 0.95]}),
    "fair_value_bid": (fair_value_bid, "Made for limit orders: bid on the side the fair-value model rates above the current bid.",
                       {"start": [2, 5], "end": [10, 13], "edge": [0.02, 0.04, 0.06, 0.10],
                        "vol_mult": [0.8, 1.0, 1.25], "min_price": [0.1, 0.25], "max_price": [0.75, 0.9]}),
    "cross_lead": (cross_lead, "BTC moved first; buy this coin in BTC's direction before its own price catches up.",
                   {"start": [1, 2, 4], "end": [6, 10, 13], "min_z": [1.0, 1.5, 2.0, 3.0], "lag": [0.3, 0.6],
                    "max_price": [0.6, 0.75]}),
    "quote_move": (quote_move, "Kalshi's price jumped on its own: fade it (or follow it).",
                   {"lookback": [1, 2, 3], "min_move": [0.1, 0.15, 0.25], "follow": [False, True],
                    "start": [3, 6], "end": [10, 13], "min_price": [0.15], "max_price": [0.85]}),
    "fair_value_regime": (fair_value_regime, "Fair-value model only when short-term volatility is rising, or only when it is falling.",
                          {"start": [2, 5], "end": [10, 13], "edge": [0.06, 0.10, 0.14], "regime": ["rising", "falling"],
                           "min_price": [0.05, 0.2], "max_price": [0.8, 0.95]}),
    "opening_value": (opening_value, "First minutes: buy whichever side the model says the opening price gets wrong.",
                      {"minute": [1, 2, 3], "edge": [0.03, 0.05, 0.08, 0.12], "vol_mult": [0.8, 1.0, 1.25]}),
    "fair_value": (fair_value, "Lognormal fair-value model vs. the order book; buy whichever side is underpriced.",
                   {"start": [2, 5, 8], "end": [10, 13], "edge": [0.04, 0.08, 0.12, 0.16],
                    "vol_mult": [0.8, 1.0, 1.25]}),
}


# ---- golden-hunt additions (lab3). Appended only; nothing above changed. ----
def fair_value_shape(P, start=2, end=13, edge=0.14, vol_mult=1.0, shape=1.1, min_price=0.05, max_price=0.95):
    """fair_value with the model's probabilities recalibrated by a logistic slope `shape`
    (>1 = more confident). lab3 family fv_shape."""
    q = np.clip(model_prob(P, vol_mult), 1e-9, 1 - 1e-9)
    p = 1 / (1 + np.exp(-shape * np.log(q / (1 - q))))
    ya, na = P["yes_ask"], P["no_ask"]
    win = (MIN >= start) & (MIN <= end)
    ok = np.isfinite(p) & win[None, :]
    with np.errstate(invalid="ignore"):
        y = ok & _valid(ya) & (ya >= min_price) & (ya <= max_price) & (p - ya >= edge)
        n = ok & _valid(na) & (na >= min_price) & (na <= max_price) & ((1 - p) - na >= edge)
    return _first(y, n)


STRATEGIES["fair_value_shape"] = (fair_value_shape, "Fair value with recalibrated (sharper) probabilities.",
                                  {"edge": [0.12, 0.14], "shape": [1.1, 1.25]})


def _fv_pick(P, p, start, end, edge, min_price=0.05, max_price=0.95, extra_y=None, extra_n=None):
    ya, na = P["yes_ask"], P["no_ask"]
    win = (MIN >= start) & (MIN <= end)
    ok = np.isfinite(p) & win[None, :]
    with np.errstate(invalid="ignore"):
        y = ok & _valid(ya) & (ya >= min_price) & (ya <= max_price) & (p - ya >= edge)
        n = ok & _valid(na) & (na >= min_price) & (na <= max_price) & ((1 - p) - na >= edge)
    if extra_y is not None:
        y &= extra_y
        n &= extra_n
    both = y & n                      # lab3 drops cells where both sides qualify
    return _first(y & ~both, n & ~both)


def _vol(P, vol):
    if vol == "max":
        return np.fmax(P["vol1m"], P["vol240"])
    if vol == "blend":
        return np.sqrt((P["vol1m"] ** 2 + P["vol240"] ** 2) / 2)
    if vol == "ewma30":
        return P["vol_ewma30"]
    return P["vol1m"]


def _prob(P, vol="60", vol_mult=1.0, drift=0.0):
    tau = 15 - MIN[None, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (np.log(P["spot"] / P["strike"]) + drift) / (_vol(P, vol) * vol_mult * np.sqrt(tau))
    return ndtr(z)


def fair_value_vol(P, start=2, end=13, edge=0.13, vol="max", vol_mult=0.8, min_price=0.05, max_price=0.95):
    """lab3 fv_ref / fv_vol: fair value with a different volatility measure ("max" of 1h/4h, "ewma30")."""
    return _fv_pick(P, _prob(P, vol, vol_mult), start, end, edge, min_price, max_price)


def fair_value_drift(P, start=2, end=13, edge=0.18, vol_mult=1.0, a=0.25, min_price=0.05, max_price=0.95):
    """lab3 fv_drift (L=1): assume a share `a` of the last 1-minute spot move carries on."""
    with np.errstate(invalid="ignore", divide="ignore"):
        lc = np.log(P["spot"])
    r1 = np.full_like(lc, np.nan)
    r1[:, 1:] = lc[:, 1:] - lc[:, :-1]
    return _fv_pick(P, _prob(P, "60", vol_mult, a * r1), start, end, edge, min_price, max_price)


def fair_value_lag(P, start=2, end=13, edge=0.12, vol_mult=0.8, r=1, k=0.25, qlag="lag", min_price=0.05, max_price=0.95):
    """lab3 fv_lag: only when the model just jumped (spot moved in the last r minutes) and,
    with qlag="lag", the Kalshi quote has not followed."""
    p = _prob(P, "60", vol_mult)
    dp = np.full_like(p, np.nan)
    dp[:, r:] = p[:, r:] - p[:, :-r]
    with np.errstate(invalid="ignore"):
        ey, en = dp >= k * edge, -dp >= k * edge
        if qlag == "lag":
            mid = (P["yes_ask"] + P["yes_bid"]) / 2
            dm = np.full_like(mid, np.nan)
            dm[:, r:] = mid[:, r:] - mid[:, :-r]
            ey &= dm < 0.5 * dp
            en &= dm > 0.5 * dp
    return _fv_pick(P, p, start, end, edge, min_price, max_price, ey, en)


STRATEGIES["fair_value_vol"] = (fair_value_vol, "Fair value with another volatility measure.", {"vol": ["max", "ewma30"]})
STRATEGIES["fair_value_drift"] = (fair_value_drift, "Fair value that assumes part of the last 1-min move carries on.", {"a": [0.25]})
STRATEGIES["fair_value_lag"] = (fair_value_lag, "Fair value only right after a fresh spot move the quote hasn't followed.", {"k": [0.25]})
