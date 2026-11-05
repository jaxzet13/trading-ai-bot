"""labx: the thorough real-money research (python -m kalshi15m labx STAGE).

Stages
  calib   learn how real Kalshi orders fill, from the Kalshi trade records already downloaded (labrm's tape
          cache): for every backtest entry with a recorded tape, would an IOC buy at the live runner's limit have
          filled 1-3 s after the decision, at what price, and how did the filled bets really end (early sale
          filled or not) versus what the candle backtest assumed. Fitted per (price band, minute band, side,
          coin group) with shrinkage to broader groups. -> data/lab/labx_fill_model.json
          Run on the ORIGINAL data (the tape cache was fetched for those decisions); fills depend on Kalshi's
          book, not on which spot series produced the signal.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import labrm as R
from . import lab5 as L

ROOT = Path(__file__).resolve().parent.parent
LABDIR = ROOT / "data" / "lab"
FILL_MODEL = LABDIR / "labx_fill_model.json"
FILL_DATA = LABDIR / "labx_fill_data.csv"
THIN = {"KXNEAR15M", "KXHYPE15M", "KXDOGE15M", "KXBNB15M"}
PRICE_BINS = [0.0, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 1.0]
MIN_BINS = [0, 4, 8, 14]          # minute 1-4, 5-8, 9-13


def _limit(px, q, A=R.ACCOUNT):
    lim2 = math.floor(min(px + A["walk"], q - A["keep_edge"]) * 100 + 1e-9) / 100
    return lim2 if px < lim2 <= A["max_price"] else px


def collect(log=print):
    """Labelled entries: every backtest position (all labrm candidates, every period) whose tape is cached."""
    from . import lab3
    lab3.G["quick"] = 0
    log("loading panels (original data) ...")
    lab3.load(verbose=False)
    seen = R.load_periods(download=False)
    rows, keys = [], set()
    wheres = [w for w in ("search", "hold", "arch", "p1", "p2") if L.G.get(w)]
    for cid, label, src, cfg, ready in R.CANDS:
        if cfg is None:
            continue
        nm = R.norm_for(cid, cfg)
        for wh in wheres:
            for p in R.positions(wh, cfg, nm):
                k = (p["tk"], p["t"], p["side"])
                if k in keys or (p["tk"], p["t"]) not in R.TAPE:
                    continue
                keys.add(k)
                ctx = L.G[wh][p["coin"]]
                tks = ctx.panel.ticker
                m = int(np.nonzero(tks == p["tk"])[0][0]) if (tks == p["tk"]).any() else None
                j = p["minute"] - 1
                P = ctx.P
                vol = float(P["volume"][m, j]) if m is not None and "volume" in P else np.nan
                yb, ya = (float(P["yes_bid"][m, j]), float(P["yes_ask"][m, j])) if m is not None else (np.nan, np.nan)
                limit = _limit(p["px"], p["q"])
                f = R.entry_fill(p["tk"], p["side"], p["t"], limit)
                ex = None
                if f is not None and p["xpx"] is not None and (p["tk"], p["tx"]) in R.TAPE:
                    ex = R.exit_fill(p["tk"], p["side"], p["tx"], p["xpx"])
                fp = f[0] if f else np.nan
                # per-contract results: candle backtest vs real fill (exit only if the tape shows it filled)
                bt_c = (p["xpx"] if p["xpx"] is not None else p["res"]) - p["px"]
                if f is None:
                    real_c = np.nan
                elif p["xpx"] is not None and ex:
                    real_c = p["xpx"] - fp
                elif p["xpx"] is not None and ex is None:
                    real_c = np.nan                      # exit tape not cached: unknown
                else:
                    real_c = p["res"] - fp
                rows.append({"coin": p["coin"], "tk": p["tk"], "t": p["t"], "where": wh, "rule": cid, "side": p["side"],
                             "minute": p["minute"], "px": p["px"], "q": p["q"], "edge": p["q"] - p["px"], "limit": limit,
                             "yes_bid": yb, "yes_ask": ya, "spread": ya - yb, "kvol": vol,
                             "filled": f is not None, "fill_px": fp, "avail": f[1] if f else 0.0,
                             "has_exit": p["xpx"] is not None, "exit_filled": ex, "res": p["res"],
                             "bt_c": bt_c, "real_c": real_c})
        log(f"  {cid}: {len(rows)} labelled entries so far")
    df = pd.DataFrame(rows)
    df.to_csv(FILL_DATA, index=False)
    return df


def _bucket(df):
    pb = np.clip(np.digitize(df["px"], PRICE_BINS) - 1, 0, len(PRICE_BINS) - 2)
    mb = np.clip(np.digitize(df["minute"], MIN_BINS) - 1, 0, len(MIN_BINS) - 2)
    grp = np.where(df["coin"].isin(THIN), "thin", "liquid")
    return pb, mb, grp


def fit(df, k=25.0, log=print):
    """Shrunk cell estimates: fill rate, mean (fill price - px), exit fill rate, mean (real - backtest) per
    contract; cell = (coin group, side, price band, minute band) shrunk toward (group, side, price band) and then
    (side, price band)."""
    pb, mb, grp = _bucket(df)
    df = df.assign(pb=pb, mb=mb, grp=grp)
    df["slip"] = df["fill_px"] - df["px"]
    df["gap"] = df["real_c"] - df["bt_c"]

    def stats(g):
        f = g[g.filled]
        x = f[f.has_exit & f.exit_filled.notna()]
        r = f[f.real_c.notna()]
        return {"n": int(len(g)), "fill": float(g.filled.mean()) if len(g) else np.nan,
                "slip": float(f.slip.mean()) if len(f) else 0.0, "n_f": int(len(f)),
                "xfill": float(x.exit_filled.astype(float).mean()) if len(x) else np.nan, "n_x": int(len(x)),
                "gap": float(r.gap.mean()) if len(r) else 0.0, "n_r": int(len(r))}

    def shrink(c, parent):
        out = {}
        for key, nk in (("fill", "n"), ("slip", "n_f"), ("xfill", "n_x"), ("gap", "n_r")):
            v, n, pv = c.get(key), c.get(nk, 0), parent.get(key)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                out[key] = pv
            elif pv is None or (isinstance(pv, float) and math.isnan(pv)):
                out[key] = v
            else:
                out[key] = (n * v + k * pv) / (n + k)
        out.update({kk: c.get(kk, 0) for kk in ("n", "n_f", "n_x", "n_r")})
        return out

    top = {}
    for (side, p), g in df.groupby(["side", "pb"]):
        top[(side, int(p))] = stats(g)
    mid = {}
    for (gr, side, p), g in df.groupby(["grp", "side", "pb"]):
        mid[(gr, side, int(p))] = shrink(stats(g), top[(side, int(p))])
    cells = {}
    for (gr, side, p, m), g in df.groupby(["grp", "side", "pb", "mb"]):
        cells[f"{gr}|{side}|{int(p)}|{int(m)}"] = shrink(stats(g), mid[(gr, side, int(p))])
    model = {"price_bins": PRICE_BINS, "minute_bins": MIN_BINS, "thin": sorted(THIN), "k": k,
             "cells": cells, "mid": {f"{a}|{b}|{c}": v for (a, b, c), v in mid.items()},
             "top": {f"{a}|{b}": v for (a, b), v in top.items()},
             "overall": stats(df), "n_rows": int(len(df)), "generated": int(time.time())}
    FILL_MODEL.write_text(json.dumps(model, indent=1, default=float))
    o = model["overall"]
    log(f"fill model from {len(df)} labelled entries: fills {o['fill']:.1%}, mean fill price vs quote "
        f"{100 * o['slip']:+.2f}c, early sales filled {o['xfill']:.1%}, real - backtest per contract "
        f"{100 * o['gap']:+.2f}c")
    for gr in ("liquid", "thin"):
        for side in ("yes", "no"):
            g = df[(df.grp == gr) & (df.side == side)]
            if len(g):
                s = stats(g)
                log(f"  {gr:6s} {side:3s}: n {s['n']:5d}  fill {s['fill']:.1%}  slip {100 * s['slip']:+.2f}c  "
                    f"exit fill {s['xfill'] if not math.isnan(s['xfill']) else float('nan'):.1%}  real-bt {100 * s['gap']:+.2f}c")
    return model


def main(args=None):
    args = list(args or [])
    stage = args[0] if args else "calib"
    if stage == "calib":
        df = collect()
        fit(df)
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main(sys.argv[1:])
