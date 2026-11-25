"""Trade simulation on 1-minute bars (numba).

One entry set (t, dir, ref per day) is run against a grid of exit configurations:
    stop_mult   stop distance = max(ref * stop_mult, min_stop)
    target_r    take profit in R (0 = none)
    manage      0 plain | 1 move stop to entry at +1R | 2 trail 3 x ATR(5m) behind the best price after +1R
    hold_min    0 = until the session's flat-by time, else exit this many minutes after entry
Fill model: enter at the entry minute's open; inside a minute the stop is checked before the target (conservative);
a gap through the stop fills at the open; costs (spread + commission + slippage, price units) are charged on every
trade and an extra quarter of the cost on stop exits.
"""
from __future__ import annotations

import numpy as np
from numba import njit, prange

MIN_STOP_COSTS = 8.0      # a stop closer than this many round-trip costs is widened to it


def exit_grid() -> np.ndarray:
    rows = []
    for sm in (0.5, 1.0, 2.0):
        for hold in (0, 90):
            for tg in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 0.0):
                for mg in (0, 1):
                    if mg == 1 and 0 < tg <= 1.0:
                        continue            # breakeven at +1R is meaningless when the target is at or inside 1R
                    rows.append((sm, tg, mg, hold))
            for tg in (0.0, 3.0):
                rows.append((sm, tg, 2, hold))
    return np.array(rows, dtype=np.float64)


@njit(cache=True)
def _one(O, H, L, C, atr5, d, t, dr, sd, tg_r, mg, t_exit, cost):
    entry = O[d, t]
    stop = entry - dr * sd
    tgt = entry + dr * tg_r * sd
    best = entry
    mae = 0.0; mfe = 0.0
    armed = False
    px = 0.0; how = 0          # 1 stop, 2 target, 3 time
    m = t
    while m < t_exit:
        o = O[d, m]; h = H[d, m]; l = L[d, m]
        if dr > 0:
            if l <= stop:
                px = stop if (o > stop or m == t) else o
                how = 1
            elif tg_r > 0 and h >= tgt:
                px = tgt; how = 2
            adv = (entry - l) / sd; fav = (h - entry) / sd
            if h > best: best = h
        else:
            if h >= stop:
                px = stop if (o < stop or m == t) else o
                how = 1
            elif tg_r > 0 and l <= tgt:
                px = tgt; how = 2
            adv = (h - entry) / sd; fav = (entry - l) / sd
            if l < best: best = l
        if how != 0:
            if how == 1:
                a = (entry - px) * dr / sd
                if a > mae: mae = a
            else:
                if adv > mae: mae = adv
                if tg_r > mfe: mfe = tg_r
            break
        if adv > mae: mae = adv
        if fav > mfe: mfe = fav
        if mg > 0 and not armed and fav >= 1.0:
            armed = True
        if armed:
            if mg == 1:
                ns = entry
            else:
                ns = best - dr * 3.0 * atr5[d, m // 5]
            if dr > 0:
                if ns > stop: stop = ns
            else:
                if ns < stop: stop = ns
        m += 1
    if how == 0:
        px = O[d, t_exit]; how = 3
    r = (px - entry) * dr / sd - cost / sd
    if how == 1:
        r -= 0.25 * cost / sd
    return r, mae, mfe, m


@njit(parallel=True, cache=True)
def summarize(O, H, L, C, atr5, t, dr, ref, flat_by, cost, grid, period, n_periods):
    """Per exit config and period: n, sum R, sum R^2, wins, gross win, gross loss."""
    G = grid.shape[0]; D = len(t)
    out = np.zeros((G, n_periods, 6))
    for g in prange(G):
        sm = grid[g, 0]; tg = grid[g, 1]; mg = int(grid[g, 2]); hold = int(grid[g, 3])
        for d in range(D):
            if t[d] < 0 or period[d] < 0:
                continue
            sd = max(ref[d] * sm, MIN_STOP_COSTS * cost)
            te = flat_by if hold == 0 else min(flat_by, t[d] + hold)
            if te <= t[d]:
                continue
            r, mae, mfe, m = _one(O, H, L, C, atr5, d, t[d], dr[d], sd, tg, mg, te, cost)
            p = period[d]
            out[g, p, 0] += 1; out[g, p, 1] += r; out[g, p, 2] += r * r
            if r > 0:
                out[g, p, 3] += 1; out[g, p, 4] += r
            else:
                out[g, p, 5] -= r
    return out


@njit(cache=True)
def trades(O, H, L, C, atr5, t, dr, ref, flat_by, cost, cfg):
    """Per-day trade detail for one exit config: R, MAE, MFE (in R), stop distance, entry price, exit minute."""
    D = len(t)
    R = np.zeros(D); MAE = np.zeros(D); MFE = np.zeros(D); SD = np.zeros(D); PX = np.zeros(D); TX = np.full(D, -1)
    sm = cfg[0]; tg = cfg[1]; mg = int(cfg[2]); hold = int(cfg[3])
    for d in range(D):
        if t[d] < 0:
            continue
        sd = max(ref[d] * sm, MIN_STOP_COSTS * cost)
        te = flat_by if hold == 0 else min(flat_by, t[d] + hold)
        if te <= t[d]:
            continue
        r, mae, mfe, m = _one(O, H, L, C, atr5, d, t[d], dr[d], sd, tg, mg, te, cost)
        R[d] = r; MAE[d] = mae; MFE[d] = mfe; SD[d] = sd; PX[d] = O[d, t[d]]; TX[d] = m
    return R, MAE, MFE, SD, PX, TX
