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


# name -> (function, description, parameter grid for the sweep)
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
    "fair_value": (fair_value, "Lognormal fair-value model vs. the order book; buy whichever side is underpriced.",
                   {"start": [2, 5, 8], "end": [10, 13], "edge": [0.04, 0.08, 0.12, 0.16],
                    "vol_mult": [0.8, 1.0, 1.25]}),
}
