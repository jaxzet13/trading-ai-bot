"""Entry signal families. Each generator yields (spec, t, direction, ref):
    spec       dict describing the entry rule (for reports)
    t[d]       minute index of the entry on day d (enter at that minute's open), -1 = no trade
    dir[d]     +1 long / -1 short
    ref[d]     reference stop distance in price units (structure- or volatility-based)
Signals only use information available before minute t. One entry per day per signal set.
"""
from __future__ import annotations

import numpy as np
from numba import njit

SESSIONS = {"ny": (570, 955), "london": (180, 655)}   # (open minute, flat-by minute), New York clock


def bars5(z: dict) -> dict:
    """5-minute bars and indicators on the dense day x minute matrices."""
    if "c5" in z:
        return z
    D, M = z["C"].shape
    n = M // 5
    z["o5"] = z["O"][:, 0::5]
    z["c5"] = z["C"][:, 4::5]
    z["h5"] = z["H"].reshape(D, n, 5).max(2)
    z["l5"] = z["L"].reshape(D, n, 5).min(2)
    flat = z["c5"].reshape(-1).astype(np.float64)
    for L in (8, 12, 20, 50, 200, 300):
        z[f"ema{L}"] = _ema(flat, L).reshape(D, n).astype(np.float32)
    hf, lf = z["h5"].reshape(-1).astype(np.float64), z["l5"].reshape(-1).astype(np.float64)
    pc = np.concatenate([[flat[0]], flat[:-1]])
    tr = np.maximum(hf - lf, np.maximum(np.abs(hf - pc), np.abs(lf - pc)))
    z["atr5"] = _ema(tr, 27).reshape(D, n).astype(np.float32)          # Wilder 14 ~ EMA 27
    z["rsi5"] = _rsi(flat, 14).reshape(D, n).astype(np.float32)
    return z


@njit(cache=True)
def _ema(x, L):
    a = 2.0 / (L + 1.0)
    out = np.empty_like(x)
    e = x[0]
    for i in range(len(x)):
        e = e + a * (x[i] - e)
        out[i] = e
    return out


@njit(cache=True)
def _rsi(x, L):
    out = np.full(len(x), 50.0)
    up = 0.0; dn = 0.0
    for i in range(1, len(x)):
        ch = x[i] - x[i - 1]
        u = ch if ch > 0 else 0.0
        d = -ch if ch < 0 else 0.0
        up += (u - up) / L
        dn += (d - dn) / L
        out[i] = 100.0 - 100.0 / (1.0 + up / dn) if dn > 1e-12 else 100.0
    return out


def session_stats(z: dict, sess: str) -> dict:
    """Previous-session close/high/low, direction and average daily range for a session."""
    key = f"ss_{sess}"
    if key in z:
        return z[key]
    s, e = SESSIONS[sess]
    seg_h = z["H"][:, s:e + 5].max(1); seg_l = z["L"][:, s:e + 5].min(1)
    o = z["O"][:, s]; c = z["C"][:, e + 4]
    rng = (seg_h - seg_l).astype(np.float64)
    adr = np.full(len(rng), np.nan)
    for i in range(1, len(rng)):
        adr[i] = np.mean(rng[max(0, i - 14):i])
    prev = lambda a: np.concatenate([[np.nan], a[:-1]])
    z[key] = {"open": o, "pc": prev(c), "ph": prev(seg_h), "pl": prev(seg_l), "pdir": prev(np.sign(c - o)), "adr": adr}
    return z[key]


def _trend_ok(z, filt, b, d):
    """Mask of days where direction d (array of +-1) agrees with the trend filter evaluated at 5-min bar index b (array)."""
    D = len(d)
    rows = np.arange(D)
    if filt == "none":
        return np.ones(D, bool)
    if filt in ("ema200", "ema300"):
        bb = np.clip(b, 0, z["c5"].shape[1] - 1)
        return np.sign(z["c5"][rows, bb] - z[filt][rows, bb]) == d
    raise ValueError(filt)


@njit(cache=True)
def _first_close_beyond(c5, hi, lo, b0, b1):
    """First bar in [b0, b1) closing above hi (+1) or below lo (-1), per day. Returns (bar, dir)."""
    D = c5.shape[0]
    bar = np.full(D, -1, np.int64); dr = np.zeros(D, np.int64)
    for d in range(D):
        if not (hi[d] > lo[d]):
            continue
        for b in range(b0, b1):
            if c5[d, b] > hi[d]:
                bar[d] = b; dr[d] = 1; break
            if c5[d, b] < lo[d]:
                bar[d] = b; dr[d] = -1; break
    return bar, dr


@njit(cache=True)
def _first_reject(h5, l5, c5, hi, lo, b0, b1):
    """First bar in [b0, b1) trading beyond a level and closing back inside: above hi -> short, below lo -> long."""
    D = c5.shape[0]
    bar = np.full(D, -1, np.int64); dr = np.zeros(D, np.int64); ext = np.zeros(D)
    for d in range(D):
        if not (hi[d] > lo[d]):
            continue
        for b in range(b0, b1):
            if h5[d, b] > hi[d] and c5[d, b] < hi[d]:
                bar[d] = b; dr[d] = -1; ext[d] = h5[d, b] - c5[d, b]; break
            if l5[d, b] < lo[d] and c5[d, b] > lo[d]:
                bar[d] = b; dr[d] = 1; ext[d] = c5[d, b] - l5[d, b]; break
    return bar, dr, ext


@njit(cache=True)
def _first_dev(c5, mean5, thr, b0, b1):
    D = c5.shape[0]
    bar = np.full(D, -1, np.int64); dr = np.zeros(D, np.int64)
    for d in range(D):
        if not (thr[d] > 0):
            continue
        for b in range(b0, b1):
            x = c5[d, b] - mean5[d, b]
            if x > thr[d]:
                bar[d] = b; dr[d] = 1; break
            if x < -thr[d]:
                bar[d] = b; dr[d] = -1; break
    return bar, dr


@njit(cache=True)
def _first_donchian(c5, h5, l5, n, b0, b1):
    D = c5.shape[0]
    bar = np.full(D, -1, np.int64); dr = np.zeros(D, np.int64)
    for d in range(D):
        for b in range(max(b0, n), b1):
            hh = h5[d, b - n:b].max(); ll = l5[d, b - n:b].min()
            if c5[d, b] > hh:
                bar[d] = b; dr[d] = 1; break
            if c5[d, b] < ll:
                bar[d] = b; dr[d] = -1; break
    return bar, dr


@njit(cache=True)
def _first_rsi(rsi5, lo, hi, b0, b1):
    D = rsi5.shape[0]
    bar = np.full(D, -1, np.int64); dr = np.zeros(D, np.int64)
    for d in range(D):
        for b in range(b0, b1):
            if rsi5[d, b] < lo:
                bar[d] = b; dr[d] = 1; break
            if rsi5[d, b] > hi:
                bar[d] = b; dr[d] = -1; break
    return bar, dr


def _pack(bar, dr, ref, e, mask=None):
    """Signal bar index -> entry minute (the minute after the bar closes)."""
    t = np.where((bar >= 0) & (dr != 0), bar * 5 + 5, -1)
    ok = (t >= 0) & (t < e - 10) & np.isfinite(ref) & (ref > 0)
    if mask is not None:
        ok &= mask
    return np.where(ok, t, -1).astype(np.int32), dr.astype(np.int8), np.where(ok, ref, 0).astype(np.float32)


def generate(z: dict, sess: str):
    """Yield every entry signal set for one instrument and session."""
    bars5(z)
    s, e = SESSIONS[sess]
    ss = session_stats(z, sess)
    D, nb = z["c5"].shape
    rows = np.arange(D)
    b0 = s // 5
    c5, h5, l5, o5, atr5 = z["c5"], z["h5"], z["l5"], z["o5"], z["atr5"]
    adr = ss["adr"]

    # ---- F1 open candle: first n-minute candle of the session vs a reference -------------------------------------
    for n in (5, 15, 30):
        k = n // 5
        last = b0 + k - 1
        co = o5[:, b0]; cc = c5[:, last]
        chi = h5[:, b0:b0 + k].max(1); clo = l5[:, b0:b0 + k].min(1)
        bar = np.full(D, last)
        for rule in ("ema8", "ema12", "ema20", "ema50", "body", "gap"):
            if rule.startswith("ema"):
                d = np.sign(cc - z[rule][:, last])
            elif rule == "body":
                d = np.sign(cc - co)
            else:
                d = np.sign(cc - ss["pc"])
            d = np.nan_to_num(d).astype(np.int64)
            ref = np.where(d > 0, cc - clo, chi - cc).astype(np.float64)
            for filt in ("none", "ema200", "ema300", "prevday"):
                m = (ss["pdir"] == d) if filt == "prevday" else _trend_ok(z, filt, bar, d)
                yield ({"family": "open_candle", "candle_min": n, "rule": rule, "trend": filt}, *_pack(bar, d, ref, e, m))

    # ---- F2 opening range breakout / failed breakout -------------------------------------------------------------
    for n in (5, 15, 30, 60):
        k = n // 5
        rh = h5[:, b0:b0 + k].max(1).astype(np.float64); rl = l5[:, b0:b0 + k].min(1).astype(np.float64)
        for win in (120, 240):
            b1 = min(b0 + win // 5, e // 5 - 2)
            bar, d = _first_close_beyond(c5, rh, rl, b0 + k, b1)
            bb = np.clip(bar, 0, nb - 1)
            px = c5[rows, bb].astype(np.float64)
            for stop in ("mid", "far"):
                lvl = (rh + rl) / 2 if stop == "mid" else np.where(d > 0, rl, rh)
                ref = np.abs(px - lvl)
                for filt in ("none", "ema200"):
                    yield ({"family": "orb", "range_min": n, "window_min": win, "stop": stop, "trend": filt}, *_pack(bar, d, ref, e, _trend_ok(z, filt, bb, d)))
            rb, rd, ext = _first_reject(h5, l5, c5, rh, rl, b0 + k, b1)
            yield ({"family": "orb_fade", "range_min": n, "window_min": win}, *_pack(rb, rd, ext + 0.25 * atr5[rows, np.clip(rb, 0, nb - 1)], e))

    # ---- F3 time-of-day momentum / reversal ----------------------------------------------------------------------
    for off in (30, 60, 90, 120, 180, 240, 300, 330):
        b = b0 + off // 5 - 1
        if b * 5 + 5 >= e - 15:
            continue
        bar = np.full(D, b)
        for anchor in ("open", "prev_close"):
            base = ss["open"] if anchor == "open" else ss["pc"]
            move = (c5[:, b] - base).astype(np.float64)
            for thr in (0.0, 0.3):
                big = np.abs(move) >= thr * adr
                for mode in ("go", "fade"):
                    d = np.nan_to_num(np.sign(move)).astype(np.int64) * (1 if mode == "go" else -1)
                    for km in (2.0, 4.0):
                        yield ({"family": "tod", "offset_min": off, "anchor": anchor, "min_move_adr": thr, "mode": mode, "stop_atr": km},
                               *_pack(bar, d, km * atr5[:, b].astype(np.float64), e, big))

    # ---- F4 opening gap ------------------------------------------------------------------------------------------
    gap = (ss["open"] - ss["pc"]).astype(np.float64)
    bar = np.full(D, b0 - 1)                       # enter at the session open
    for thr in (0.15, 0.3, 0.6):
        big = np.abs(gap) >= thr * adr
        for mode in ("go", "fade"):
            d = np.nan_to_num(np.sign(gap)).astype(np.int64) * (1 if mode == "go" else -1)
            for refm in ("half_gap", "atr"):
                ref = 0.5 * np.abs(gap) if refm == "half_gap" else 3.0 * atr5[:, b0 - 1].astype(np.float64)
                yield ({"family": "gap", "min_gap_adr": thr, "mode": mode, "stop": refm}, *_pack(bar, d, ref, e, big))

    # ---- F5 previous-session high / low: break and sweep-reject --------------------------------------------------
    ph, pl = ss["ph"].astype(np.float64), ss["pl"].astype(np.float64)
    b1 = min(b0 + 60, e // 5 - 2)
    bar, d = _first_close_beyond(c5, np.nan_to_num(ph, nan=1e18), np.nan_to_num(pl, nan=-1e18), b0, b1)
    bb = np.clip(bar, 0, nb - 1)
    for km in (2.0, 4.0):
        for filt in ("none", "ema200"):
            yield ({"family": "prev_break", "stop_atr": km, "trend": filt}, *_pack(bar, d, km * atr5[rows, bb].astype(np.float64), e, _trend_ok(z, filt, bb, d)))
    rb, rd, ext = _first_reject(h5, l5, c5, np.nan_to_num(ph, nan=1e18), np.nan_to_num(pl, nan=-1e18), b0, b1)
    for add in (0.25, 1.0):
        yield ({"family": "prev_sweep", "stop_pad_atr": add}, *_pack(rb, rd, ext + add * atr5[rows, np.clip(rb, 0, nb - 1)], e))

    # ---- F6 deviation from the session mean ----------------------------------------------------------------------
    tp = ((h5 + l5 + c5) / 3.0).astype(np.float64)
    cs = np.cumsum(tp[:, b0:], axis=1)
    mean5 = np.full((D, nb), np.nan)
    mean5[:, b0:] = cs / np.arange(1, nb - b0 + 1)
    for kdev in (0.25, 0.4, 0.6):
        bar, d0 = _first_dev(c5.astype(np.float64), mean5, kdev * np.nan_to_num(adr), b0 + 6, min(b0 + 60, e // 5 - 2))
        bb = np.clip(bar, 0, nb - 1)
        for mode in ("go", "fade"):
            d = d0 * (1 if mode == "go" else -1)
            for km in (2.0, 4.0):
                yield ({"family": "mean_dev", "dev_adr": kdev, "mode": mode, "stop_atr": km}, *_pack(bar, d, km * atr5[rows, bb].astype(np.float64), e))

    # ---- F7 intraday Donchian breakout ---------------------------------------------------------------------------
    for n in (12, 24, 48):
        bar, d0 = _first_donchian(c5, h5, l5, n, b0 + 3, min(b0 + 48, e // 5 - 2))
        bb = np.clip(bar, 0, nb - 1)
        for mode in ("go", "fade"):
            d = d0 * (1 if mode == "go" else -1)
            for km in (2.0, 4.0):
                for filt in ("none", "ema200"):
                    yield ({"family": "donchian", "lookback_bars": n, "mode": mode, "stop_atr": km, "trend": filt},
                           *_pack(bar, d, km * atr5[rows, bb].astype(np.float64), e, _trend_ok(z, filt, bb, d)))

    # ---- F8 RSI extremes -----------------------------------------------------------------------------------------
    for lo, hi in ((20.0, 80.0), (30.0, 70.0)):
        bar, d = _first_rsi(z["rsi5"], lo, hi, b0 + 2, min(b0 + 60, e // 5 - 2))
        bb = np.clip(bar, 0, nb - 1)
        for km in (2.0, 4.0):
            for filt in ("none", "ema200"):
                yield ({"family": "rsi", "low": lo, "high": hi, "stop_atr": km, "trend": filt},
                       *_pack(bar, d, km * atr5[rows, bb].astype(np.float64), e, _trend_ok(z, filt, bb, d)))

    # ---- F9 pre-session range (00:00 to the open) for the London session -----------------------------------------
    if sess == "london":
        rh = h5[:, :b0].max(1).astype(np.float64); rl = l5[:, :b0].min(1).astype(np.float64)
        bar, d = _first_close_beyond(c5, rh, rl, b0, b0 + 36)
        bb = np.clip(bar, 0, nb - 1)
        px = c5[rows, bb].astype(np.float64)
        for stop in ("mid", "far"):
            lvl = (rh + rl) / 2 if stop == "mid" else np.where(d > 0, rl, rh)
            for filt in ("none", "ema200"):
                yield ({"family": "asia_break", "stop": stop, "trend": filt}, *_pack(bar, d, np.abs(px - lvl), e, _trend_ok(z, filt, bb, d)))
        rb, rd, ext = _first_reject(h5, l5, c5, rh, rl, b0, b0 + 36)
        yield ({"family": "asia_fade"}, *_pack(rb, rd, ext + 0.25 * atr5[rows, np.clip(rb, 0, nb - 1)], e))

    # ---- NULL: coin-flip direction at fixed times (zero-edge baseline for every firm rule) -----------------------
    rng = np.random.default_rng(12345)
    for i in range(12):
        off = (5, 30, 60, 120)[i % 4]
        bar = np.full(D, b0 + off // 5 - 1)
        d = rng.choice(np.array([-1, 1]), size=D)
        km = (2.0, 4.0)[i % 2]
        yield ({"family": "null", "seed": i, "offset_min": off, "stop_atr": km}, *_pack(bar, d, km * atr5[:, bar[0]].astype(np.float64), e))


def generate_refined(z: dict, sess: str):
    """Second generation: denser grids around the families that survived the first pass
    (time-of-day momentum and the opening candle), with extra filters."""
    bars5(z)
    s, e = SESSIONS[sess]
    ss = session_stats(z, sess)
    D, nb = z["c5"].shape
    b0 = s // 5
    c5, h5, l5, o5, atr5 = z["c5"], z["h5"], z["l5"], z["o5"], z["atr5"]
    adr = ss["adr"]
    gap = np.nan_to_num((ss["open"] - ss["pc"]).astype(np.float64))

    # ---- time-of-day momentum / reversal, every 15 minutes -------------------------------------------------------
    for off in range(15, 346, 15):
        b = b0 + off // 5 - 1
        if b * 5 + 5 >= e - 15:
            continue
        bar = np.full(D, b)
        for anchor in ("open", "prev_close"):
            base = ss["open"] if anchor == "open" else ss["pc"]
            move = (c5[:, b] - base).astype(np.float64)
            sgn = np.nan_to_num(np.sign(move)).astype(np.int64)
            for thr in (0.0, 0.15, 0.3, 0.45, 0.6):
                big = np.abs(move) >= thr * adr
                for mode in ("go", "fade"):
                    d = sgn * (1 if mode == "go" else -1)
                    for filt in ("none", "ema200", "gap_agrees"):
                        m = big & ((np.sign(gap) == d) if filt == "gap_agrees" else _trend_ok(z, filt, bar, d))
                        for km in (1.5, 3.0, 6.0):
                            yield ({"family": "tod", "offset_min": off, "anchor": anchor, "min_move_adr": thr, "mode": mode, "trend": filt, "stop_atr": km},
                                   *_pack(bar, d, km * atr5[:, b].astype(np.float64), e, m))

    # ---- opening candle, more lengths and filters ----------------------------------------------------------------
    for n in (5, 10, 15, 20, 30, 45, 60):
        k = n // 5
        last = b0 + k - 1
        co = o5[:, b0].astype(np.float64); cc = c5[:, last].astype(np.float64)
        chi = h5[:, b0:b0 + k].max(1).astype(np.float64); clo = l5[:, b0:b0 + k].min(1).astype(np.float64)
        bar = np.full(D, last)
        body = np.abs(cc - co)
        a5 = atr5[:, b0 - 1].astype(np.float64)
        for rule in ("ema8", "ema12", "ema20", "ema50", "body", "gap", "body_gap"):
            if rule.startswith("ema"):
                d = np.sign(cc - z[rule][:, last])
            elif rule == "body":
                d = np.sign(cc - co)
            elif rule == "gap":
                d = np.sign(cc - ss["pc"])
            else:
                d = np.where(np.sign(cc - co) == np.sign(gap), np.sign(cc - co), 0)
            d = np.nan_to_num(d).astype(np.int64)
            for filt in ("none", "ema200", "ema300", "prevday"):
                m0 = (ss["pdir"] == d) if filt == "prevday" else _trend_ok(z, filt, bar, d)
                for minbody in (0.0, 0.5, 1.0):
                    m = m0 & (body >= minbody * a5 * np.sqrt(k))
                    for refm in ("candle", "atr"):
                        ref = np.where(d > 0, cc - clo, chi - cc) if refm == "candle" else 2.0 * a5 * np.sqrt(k)
                        yield ({"family": "open_candle", "candle_min": n, "rule": rule, "trend": filt, "min_body_atr": minbody, "stop": refm},
                               *_pack(bar, d, ref, e, m))
