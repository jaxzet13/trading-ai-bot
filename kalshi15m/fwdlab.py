"""Forward lab: thousands of strategies, frozen now, scored on days none of them has seen, with Kalshi's own
trade records deciding every fill (python -m kalshi15m fwdlab pick | score).

pick   (run once, Nov 5) For every live-runnable strategy family (taker entries: hold / sized / scalp; no BTC-reference
       families, no maker families) and every scope (each coin alone, and all 9 coins together), score every
       setting of the family's grid on ALL the data before the forward start (search window Sep 1 - Oct 17 plus the
       exam days Oct 17 - Nov 1) at real-money scoring (LAB3_REAL=1: ~$0.50 bets, the fill model). Keep the TOP_K
       settings per family x scope by the combined t-stat (profitable in both, enough trades) and write them to
       data/lab/fwd_candidates.json. That file is committed before any forward day is scored, so the choice
       cannot have been shaped by the forward results.
score  (daily) Download every market of every coin since FWD_START (after all data used anywhere), with each
       market's full Kalshi trade list, run every frozen candidate on those markets and settle each bet the way the
       real-money test does: the order goes in at the live runner's limit (walk 5c, keep 8c below fair value),
       ~$0.50 a bet (1-10 contracts), and it FILLS only if Kalshi's trade records show someone buying that side at
       our limit or better 1-3 s after the decision (fill price = that trade, size capped by what traded); early
       sales only if someone bought the other side at our price within 1-3 s, else the bet is held to the end.
       -> data/lab/fwd_results.json, shown on the app.

Grading (fixed with the candidates): a candidate passes the forward test when, over at least 7 forward days and 30
filled bets, its forward t-stat clears the Bonferroni bar for the number of candidates (one-sided 5%), i.e. it is
unlikely that the best of thousands looks this good by luck. Anything weaker is reported, not traded.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LABDIR = ROOT / "data" / "lab"
CANDS = LABDIR / "fwd_candidates.json"
TOP_K = 20
MIN_SEARCH_N, MIN_HOLD_N = 100, 30
FWD_START = 1793823300          # 2026-11-04 20:15 UTC, as kalshi15m/zecfwd.py: after all data used anywhere


def _families():
    from . import lab3
    return [f for f, v in lab3.FAMILIES.items() if v["kind"] in ("hold", "sized", "scalp") and not v["needs_ref"]]


def _agg(pnl):
    pnl = np.asarray(pnl, float)
    return np.array([len(pnl), pnl.sum(), (pnl ** 2).sum()])


def _pick_task(args):
    from . import lab3
    fam, coin = args
    cs, ch = lab3.G["search"][coin], lab3.G["hold"][coin]
    cs.cache, ch.cache = {}, {}
    cfgs = lab3.grid_list(lab3.FAMILIES[fam]["grid"])
    sized = lab3.FAMILIES[fam]["kind"] == "sized"
    out = np.zeros((len(cfgs), 2, 3))
    kel = np.zeros((len(cfgs), 2))             # sized: (sum, count) of the search window's Kelly fractions
    for i, c in enumerate(cfgs):
        side, minute, p = lab3.signal(cs, fam, c)
        tr = lab3.execute(cs, fam, c, side, minute, p)
        out[i, 0] = _agg(tr["pnl"])
        nrm = None
        if sized and len(tr["m"]):
            k = np.clip((tr["q"] - tr["price"]) / (1 - tr["price"]), 1e-4, None)
            kel[i] = k.sum(), len(k)
            nrm = float(k.mean())
        side, minute, p = lab3.signal(ch, fam, c)
        out[i, 1] = _agg(lab3.execute(ch, fam, c, side, minute, p, norm=nrm)["pnl"])
    cs.cache, ch.cache = {}, {}
    return fam, coin, out, kel


def pick(workers=4, log=print):
    from . import lab3
    lab3.REAL = True                         # real-money scoring (~$0.50 bets, fill model), as the clean rebuild
    t0 = time.time()
    lab3.G["quick"] = int(os.environ.get("FWD_QUICK", "0"))
    lab3._GRID_CACHE.clear()
    log("fwdlab pick: loading panels (clean prices) ...")
    lab3.load(verbose=False)
    fams = _families()
    tasks = sorted([(f, c) for f in fams for c in lab3.COINS], key=lambda t: -len(lab3.grid_list(lab3.FAMILIES[t[0]]["grid"])))
    log(f"  {len(fams)} families x {len(lab3.COINS)} coins, "
        f"{sum(len(lab3.grid_list(lab3.FAMILIES[f]['grid'])) for f in fams):,} settings per coin ({time.time() - t0:.0f}s)")
    R, K = {}, {}
    with Pool(workers) as pool:
        for k, (fam, coin, out, kel) in enumerate(pool.imap_unordered(_pick_task, tasks, chunksize=1)):
            R[(fam, coin)], K[(fam, coin)] = out, kel
            if (k + 1) % 10 == 0 or k + 1 == len(tasks):
                log(f"  {k + 1}/{len(tasks)} tasks ({time.time() - t0:.0f}s)")
    rows = []
    for fam in fams:
        cfgs = lab3.grid_list(lab3.FAMILIES[fam]["grid"])
        sized = lab3.FAMILIES[fam]["kind"] == "sized"
        for sc in lab3.COINS + ["ALL"]:
            coins = lab3.COINS if sc == "ALL" else [sc]
            a = sum(R[(fam, c)] for c in coins)
            comb = a.sum(1)
            ok = (a[:, 0, 0] >= MIN_SEARCH_N) & (a[:, 1, 0] >= MIN_HOLD_N) & (a[:, 0, 1] > 0) & (a[:, 1, 1] > 0)
            if not ok.any():
                continue
            t = np.array([lab3.tstat_agg(x) if o else -np.inf for x, o in zip(comb, ok)])
            for rank, i in enumerate(np.argsort(-t)[:TOP_K]):
                if not np.isfinite(t[i]):
                    break
                c = {"id": f"{fam}:{sc}:{rank + 1}", "family": fam, "scope": sc, "rank": rank + 1,
                     "kind": lab3.FAMILIES[fam]["kind"], "params": cfgs[i],
                     "search": {"pnl": round(float(a[i, 0, 1]), 2), "trades": int(a[i, 0, 0]), "t": round(lab3.tstat_agg(a[i, 0]), 2)},
                     "hold": {"pnl": round(float(a[i, 1, 1]), 2), "trades": int(a[i, 1, 0]), "t": round(lab3.tstat_agg(a[i, 1]), 2)},
                     "t_before": round(float(t[i]), 2)}
                if sized:
                    ks = sum(K[(fam, cc)][i] for cc in coins)
                    v = float(ks[0] / ks[1]) if ks[1] else 1.0
                    c["norms"] = {cc: v for cc in coins}
                rows.append(c)
    out = {"frozen_at": int(time.time()), "fwd_start": FWD_START, "top_k": TOP_K, "families": fams,
           "coins": lab3.COINS, "n_candidates": len(rows), "runtime_s": int(time.time() - t0),
           "selection": (f"Top {TOP_K} settings per family x scope by the t-stat of search window + exam days "
                         f"combined, at real-money scoring; profitable in both, >= {MIN_SEARCH_N} search and "
                         f">= {MIN_HOLD_N} exam trades. Nothing from after the forward start was loaded."),
           "candidates": rows}
    CANDS.write_text(json.dumps(out, default=float))
    log(f"fwdlab pick: {len(rows)} candidates frozen -> {CANDS} ({time.time() - t0:.0f}s)")
    return out


def main(args=None):
    args = list(args or [])
    if not args or args[0] == "pick":
        pick(int(args[1]) if len(args) > 1 else 4)
    elif args[0] == "score":
        from . import fwdscore
        fwdscore.score(download="--no-download" not in args)
    else:
        sys.exit("usage: python -m kalshi15m fwdlab pick [WORKERS] | score [--no-download]")
