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
    R.OUT = LABDIR / "labx_progress.json"   # labrm writes its progress to R.OUT: keep the real-money tab's file intact
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
    elif stage == "validate":
        validate()
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main(sys.argv[1:])


# =========================================================================== validate (after the real-money search)
REAL_RESULTS = LABDIR / "lab3_real_results.json"
VALID_OUT = LABDIR / "labx_results.json"
ACCOUNT_X = {"start_balance": 11.90, "min_balance": 6.0}


def _positions_from_lab3(df):
    """lab3 trade rows (candle backtest, $10 stakes) -> labrm position dicts."""
    out = []
    for r in df.itertuples(index=False):
        em = int(r.exit_minute) if pd.notna(r.exit_minute) else 0
        yes = r.side == "yes"
        out.append({"coin": r.series, "tk": r.ticker, "win": int(r.open_ts), "t": int(r.ts), "minute": int(r.minute),
                    "side": r.side, "px": float(r.price), "q": float(r.q) if pd.notna(r.q) else float(r.price) + 0.1,
                    "tx": int(r.open_ts) + 60 * em if em > 0 and pd.notna(r.sell) else None,
                    "xpx": float(r.sell) if em > 0 and pd.notna(r.sell) else None,
                    "res": float((int(r.result) == 1) == yes), "stake10": float(r.stake),
                    "pnl10": float(r.pnl)})
    return sorted(out, key=lambda p: (p["t"], p["coin"]))


def _daily(trades):
    d = {}
    for x in trades:
        if x["filled"]:
            d.setdefault(int(x["t"] // 86400), 0.0)
            d[int(x["t"] // 86400)] += x["pnl"]
    return d


def _tstat(v):
    v = np.asarray(v, float)
    return float(v.mean() / v.std(ddof=1) * math.sqrt(len(v))) if len(v) > 2 and v.std(ddof=1) > 0 else None


def _sim(pos, label, stress=None):
    R.STRESS.update({"window": (1.0, 3.0), "worse": 0.0, "fee_mult": 1.0, **(stress or {})})
    try:
        trades, curve = R.simulate(pos, label)
    finally:
        R.STRESS.update({"window": (1.0, 3.0), "worse": 0.0, "fee_mult": 1.0})
    f = [x for x in trades if x["filled"]]
    pn = [x["pnl"] for x in f]
    days = _daily(trades)
    return {"pnl": round(float(sum(pn)), 2), "bets": len(trades), "filled": len(f),
            "wins": int(sum(1 for v in pn if v > 0)), "t": _tstat(pn), "days": len(days),
            "winning_days": int(sum(1 for v in days.values() if v > 0)),
            "worst_day": round(min(days.values()), 2) if days else None, "max_dd": R.max_dd(curve),
            "end": round(curve[-1][1], 2)}, trades, curve


def _regimes(pos, trades, where):
    """P&L of the filled bets split by side, by the coin's direction that day, and by the day's volatility."""
    from . import lab3
    by_t = {(x["t"]): x for x in trades if x["filled"]}
    rows = []
    for p in pos:
        x = by_t.get(p["t"])
        if x is None:
            continue
        rows.append({"coin": p["coin"], "side": p["side"], "day": int(p["t"] // 86400), "pnl": x["pnl"]})
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    out = {"side": {s: round(float(g.pnl.sum()), 2) for s, g in df.groupby("side")}}
    # coin direction + realised volatility per day from the (clean) spot series
    lab = []
    for coin, g in df.groupby("coin"):
        sp = lab3.spot(coin, "archive" if where == "arch" and coin != "KXSOL15M" else "main")
        for day in g.day.unique():
            t0, t1 = day * 86400, day * 86400 + 86340
            a = sp.at(sp.c, np.array([t0, t1]))
            r = sp.at(sp.c, np.arange(t0, t1, 60))
            ret = float(a[1] / a[0] - 1) if np.all(np.isfinite(a)) and a[0] > 0 else np.nan
            vol = float(np.nanstd(np.diff(np.log(r)))) if np.isfinite(r).sum() > 100 else np.nan
            lab.append({"coin": coin, "day": int(day), "ret": ret, "vol": vol})
    L_ = pd.DataFrame(lab)
    df = df.merge(L_, on=["coin", "day"], how="left")
    df["dir"] = np.where(df.ret > 0.01, "up day", np.where(df.ret < -0.01, "down day", "flat day"))
    q = df.vol.quantile([1 / 3, 2 / 3]).to_list() if df.vol.notna().sum() > 10 else [np.nan, np.nan]
    df["volb"] = np.where(df.vol <= q[0], "calm", np.where(df.vol <= q[1], "normal", "wild"))
    out["direction"] = {k: round(float(g.pnl.sum()), 2) for k, g in df.groupby("dir")}
    out["volatility"] = {k: round(float(g.pnl.sum()), 2) for k, g in df.groupby("volb")}
    return out


def _bankroll(daily_all, days=1, start=11.90, stop=6.0, target=25.0, n=20000, seed=7):
    """Bootstrap of real daily P&L: chance of hitting the target / the stop within `days` days."""
    v = np.array(list(daily_all), float)
    if len(v) < 5:
        return None
    rng = np.random.default_rng(seed)
    hit_t = hit_s = 0
    ends = []
    for _ in range(n):
        b = start
        for _d in range(days):
            b += rng.choice(v)
            if b >= target:
                hit_t += 1
                break
            if b <= stop:
                hit_s += 1
                break
        ends.append(b)
    ends = np.array(ends)
    return {"days": days, "p_target": round(hit_t / n, 4), "p_stop": round(hit_s / n, 4),
            "median_end": round(float(np.median(ends)), 2), "p10_end": round(float(np.percentile(ends, 10)), 2),
            "p90_end": round(float(np.percentile(ends, 90)), 2)}


def validate(top_per_scope=2, log=print):
    from . import lab3
    res = json.loads(REAL_RESULTS.read_text())
    cands = [c for c in res.get("candidates", []) if c.get("status") in ("golden", "pass")]
    by_scope = {}
    for c in sorted(cands, key=lambda c: -((c.get("holdout") or {}).get("t") or -9)):
        by_scope.setdefault(c["scope"], [])
        if len(by_scope[c["scope"]]) < top_per_scope:
            by_scope[c["scope"]].append(c)
    picks = [c for v in by_scope.values() for c in v]
    log(f"validating {len(picks)} finalists from {REAL_RESULTS.name}: " + ", ".join(c["id"] for c in picks))
    lab3.REAL = False                                    # candle positions; reality comes from the tape
    lab3.G["quick"] = 0
    lab3.load(verbose=False)
    R.OUT = LABDIR / "labx_progress.json"   # labrm writes its progress to R.OUT: keep the real-money tab's file intact
    seen = R.load_periods(download=False)
    R.ACCOUNT.update(ACCOUNT_X)
    p2_start = R.STATE["periods"][1]["start"]
    rows = []
    for k, c in enumerate(picks):
        rule = {"family": c["family"], "params": c["params"]}
        if c.get("members"):
            rule = {"members": c["members"]}
        norms = lab3._sized_norms(rule, c["scope"]) if c.get("family") and lab3.FAMILIES.get(c["family"], {}).get("kind") == "sized" else None
        per = {}
        per["hold"] = _positions_from_lab3(lab3.run_rule("hold", c["scope"], rule, norms=norms))
        if any(x in L.G.get("arch", {}) for x in lab3._coins_of(c["scope"])):
            arch_ok = [x for x in lab3._coins_of(c["scope"]) if x in L.G["arch"]]
            per["arch"] = _positions_from_lab3(lab3.run_rule("arch", c["scope"], rule, norms=norms)) if arch_ok else []
        rec = []
        for wh in ("p1", "p2"):
            if L.G.get(wh):
                lab3.G[wh] = L.G[wh]
                df = lab3.run_rule(wh, c["scope"], rule, norms=norms)
                ps = _positions_from_lab3(df)
                rec += [p for p in ps if wh == "p1" or (p["tk"] not in seen and p["t"] >= p2_start)]
        per["recent"] = sorted(rec, key=lambda p: (p["t"], p["coin"]))
        out = {"id": c["id"], "scope": c["scope"], "family": c.get("family"), "params": c.get("params"),
               "search_t": (c.get("search") or {}).get("t"), "holdout_classic": c.get("holdout"), "periods": {},
               "stress": {}, "regimes": {}}
        daily_all = []
        for pid, pos in per.items():
            if not pos:
                continue
            s, trades, curve = _sim(pos, f"{c['id']} {pid}")
            out["periods"][pid] = s
            daily_all += list(_daily(trades).values())
            out["regimes"][pid] = _regimes(pos, trades, pid)
            st = {}
            for name, kw in (("orders 3 s late", {"window": (3.0, 6.0)}), ("fills 1c worse", {"worse": 0.01}),
                             ("fees +25%", {"fee_mult": 1.25})):
                st[name] = _sim(pos, f"{c['id']} {pid} {name}", kw)[0]["pnl"]
            d1 = lab3.run_rule("hold" if pid == "hold" else ("arch" if pid == "arch" else "p1"), c["scope"], rule, delay=1, norms=norms)
            st["1 minute late (classic)"] = round(float(d1.pnl.sum()), 2) if len(d1) else 0.0
            out["stress"][pid] = st
            log(f"  {c['id']} {pid}: real ${s['pnl']:+.2f} ({s['filled']}/{s['bets']} filled, t {s['t']}) | " +
                ", ".join(f"{k} ${v:+.2f}" for k, v in st.items()))
        out["bankroll_1day"] = _bankroll(daily_all, 1)
        out["bankroll_3days"] = _bankroll(daily_all, 3)
        oos = [v for v in out["periods"].values()]
        allpos = all(v["pnl"] > 0 for v in oos) and len(oos) >= 2
        nf = sum(v["filled"] for v in oos)
        stress_ok = all(all(v >= 0 for kk, v in st.items() if kk != "1 minute late (classic)") for st in out["stress"].values())
        if allpos and nf >= 50 and stress_ok:
            out["status"] = "real-money golden"
        elif sum(v["pnl"] for v in oos) > 0:
            out["status"] = "pass"
        else:
            out["status"] = "fail"
        rows.append(out)
        VALID_OUT.write_text(json.dumps({"generated": int(time.time()), "done": k + 1, "total": len(picks),
                                         "account": ACCOUNT_X, "results": rows}, indent=1, default=float))
        pickle_tape()
    log("validation done")
    return rows


def pickle_tape():
    import pickle
    pickle.dump(R.TAPE, open(R.TAPE_CACHE, "wb"))
