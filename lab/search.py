"""Mass strategy search.

Three time periods, never mixed:
    TRAIN  2016-2021   strategies are filtered on their trade statistics here
    VALID  2022-2023   the edge must persist here; firm, sizing and ranking are chosen here
    TEST   2024-2026   reported only, never used to choose anything

    python -m lab.search                 # everything -> experiments/lab/
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from . import data as D
from .firms import FIRM_MATRIX, FIRM_NAMES, FIRMS, evaluate
from .kernel import exit_grid, summarize, trades
from .signals import SESSIONS, bars5, generate, generate_refined

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments" / "lab"
VALID_START, TEST_START = np.datetime64("2022-01-01"), np.datetime64("2024-01-01")
FE = np.array([0.15, 0.25, 0.4, 0.6, 1.0])      # evaluation risk per trade, as a share of the drawdown
FF = np.array([0.05, 0.1, 0.2])                 # funded risk per trade, as a share of the drawdown
NULL_SHAPES = {(2.0, 0.5, 0.0, 0.0), (1.0, 0.75, 0.0, 0.0), (1.0, 1.0, 0.0, 0.0), (1.0, 2.0, 0.0, 0.0), (0.5, 3.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0),
               (2.0, 0.75, 0.0, 0.0), (0.5, 1.0, 0.0, 0.0)}   # zero-edge baselines: (stop mult, target R, manage, hold)
HORIZON = 126                                   # funded trading days simulated after passing (about 6 months)
UNIT = {  # usd per price unit per unit, notional per unit (as a function of price), units per micro, CFD leverage
    "NAS100": (lambda p: 1.0, lambda p: p, 2.0, 20.0), "SPX500": (lambda p: 1.0, lambda p: p, 5.0, 20.0),
    "XAUUSD": (lambda p: 1.0, lambda p: p, 10.0, 20.0), "WTI": (lambda p: 1.0, lambda p: p, 100.0, 10.0),
    "DAX": (lambda p: 1.1, lambda p: p * 1.1, 1.0, 20.0), "EU50": (lambda p: 1.1, lambda p: p * 1.1, 10.0, 20.0),
    "UK100": (lambda p: 1.25, lambda p: p * 1.25, 1.0, 20.0), "EURUSD": (lambda p: 1.0, lambda p: p, 12500.0, 50.0),
    "GBPUSD": (lambda p: 1.0, lambda p: p, 6250.0, 50.0), "USDJPY": (lambda p: 1.0 / p, lambda p: 1.0 + 0 * p, 10000.0, 50.0),
}


def periods(days: np.ndarray) -> np.ndarray:
    return np.where(days < VALID_START, 0, np.where(days < TEST_START, 1, 2)).astype(np.int64)


def stats(s: np.ndarray) -> dict:
    """s = [n, sumR, sumR2, wins, gross win, gross loss]"""
    n = s[0]
    if n < 2:
        return {"n": int(n), "mean": 0.0, "t": 0.0, "pf": 0.0, "win": 0.0}
    mean = s[1] / n
    var = max(s[2] / n - mean * mean, 1e-12)
    return {"n": int(n), "mean": float(mean), "t": float(mean / np.sqrt(var) * np.sqrt(n)), "pf": float(s[4] / s[5]) if s[5] > 0 else 9.99,
            "win": float(s[3] / n)}


def stream(name: str, z: dict, R, MAE, MFE, SD, PX, TX, mask: np.ndarray) -> tuple:
    """Trade arrays for the firm simulator, restricted to days in `mask`."""
    qf, nf, upm, lev = UNIT[name]
    m = mask & (SD > 0)
    px = PX[m]
    day = z["days"][m].astype("datetime64[D]").astype(np.int64)
    return (day, R[m], MAE[m], MFE[m], SD[m] * qf(px), nf(px) * np.ones(m.sum()), np.full(m.sum(), upm), np.full(m.sum(), lev))


def starts_for(day: np.ndarray, frac: float = 0.65, step: int = 3) -> np.ndarray:
    """Indices of the first trade of every `step`-th trading day in the first `frac` of the stream."""
    if len(day) == 0:
        return np.zeros(0, np.int64)
    first = np.flatnonzero(np.r_[True, day[1:] != day[:-1]])
    first = first[: max(1, int(len(first) * frac))]
    return first[::step].astype(np.int64)


def firm_scores(st: tuple) -> np.ndarray:
    s = starts_for(st[0])
    if len(s) < 5:
        return np.zeros((len(FIRM_NAMES), len(FE), len(FF), 8))
    return evaluate(FIRM_MATRIX, FE, FF, s, *st, HORIZON)


def describe(spec: dict, cfg: np.ndarray, name: str, sess: str) -> str:
    sm, tg, mg, hold = cfg
    core = ", ".join(f"{k}={v}" for k, v in spec.items() if k != "family")
    ex = f"stop x{sm:g}, " + (f"target {tg:g}R" if tg > 0 else "no target") + ("", ", breakeven at 1R", ", ATR trail")[int(mg)] + (f", max {int(hold)} min" if hold else ", hold to session end")
    return f"{name} {sess} · {spec['family']} ({core}) · {ex}"


def run(names: list[str] | None = None, max_per_set: int = 2) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    grid = exit_grid()
    G = len(grid)
    t0 = time.time()
    funnel = {"tested": 0, "train_pass": 0, "valid_pass": 0}
    fam_counts: dict = {}
    cands, nulls = [], []
    tstats_train, tstats_valid_given_train = [], []
    for name in names or list(D.INSTRUMENTS):
        ins = D.INSTRUMENTS[name]
        try:
            z = D.load(name)
        except FileNotFoundError:
            continue
        bars5(z)
        per = periods(z["days"])
        if (per == 2).sum() < 200:
            print(f"{name}: no test-period data, skipped", flush=True)
            continue
        atr5 = z["atr5"]
        for sess in ins.sessions:
            flat_by = SESSIONS[sess][1]
            nset = 0
            import itertools
            for spec, t, dr, ref in itertools.chain(generate(z, sess), generate_refined(z, sess)):
                nset += 1
                S = summarize(z["O"], z["H"], z["L"], z["C"], atr5, t, dr, ref, flat_by, ins.cost, grid, per, 3)
                fam = spec["family"]
                is_null = fam == "null"
                if not is_null:
                    funnel["tested"] += G
                    fam_counts.setdefault(fam, [0, 0, 0])[0] += G
                picked = []
                for g in range(G):
                    a, b = stats(S[g, 0]), stats(S[g, 1])
                    if not is_null and a["n"] >= 200:
                        tstats_train.append(a["t"])
                    if is_null:
                        if a["n"] >= 200:
                            picked.append((0.0, g, a, b))
                        continue
                    if a["n"] >= 200 and a["t"] >= 2.0 and a["pf"] >= 1.05:
                        funnel["train_pass"] += 1; fam_counts[fam][1] += 1
                        tstats_valid_given_train.append(b["t"])
                        if b["n"] >= 60 and b["mean"] > 0:
                            funnel["valid_pass"] += 1; fam_counts[fam][2] += 1
                            picked.append((a["t"] + b["t"], g, a, b))
                picked.sort(key=lambda x: -x[0])
                if is_null:
                    picked = [x for x in picked if tuple(grid[x[1]]) in NULL_SHAPES]
                for score, g, a, b in picked[:max_per_set] if not is_null else picked:
                    tr = trades(z["O"], z["H"], z["L"], z["C"], atr5, t, dr, ref, flat_by, ins.cost, grid[g])
                    c = stats(S[g, 2])
                    sv = firm_scores(stream(name, z, *tr, per == 1))
                    st = firm_scores(stream(name, z, *tr, per == 2))
                    rec = {"inst": name, "sess": sess, "spec": spec, "cfg": grid[g].tolist(), "desc": describe(spec, grid[g], name, sess),
                           "train": a, "valid": b, "test": c, "sv": sv, "st": st}
                    (nulls if is_null else cands).append(rec)
            print(f"{name} {sess}: {nset} entry sets x {G} exits, {len(cands)} candidates so far, {time.time() - t0:.0f}s", flush=True)
    res = {"funnel": funnel, "families": fam_counts, "cands": cands, "nulls": nulls,
           "t_train": np.array(tstats_train, np.float32), "t_valid_given_train": np.array(tstats_valid_given_train, np.float32)}
    np.save(OUT / "raw.npy", np.array([res], dtype=object), allow_pickle=True)
    print(f"done: {funnel} in {time.time() - t0:.0f}s", flush=True)
    return res


if __name__ == "__main__":
    run(sys.argv[1:] or None)
