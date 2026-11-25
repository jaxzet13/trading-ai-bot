"""Turn the raw search output into rankings, zero-edge baselines, portfolios and the app's data file.

    python -m lab.report            # reads experiments/lab/raw.npy, writes experiments/lab/results.json and lab_app/data.js
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

from . import data as D
from .firms import FIRM_MATRIX, FIRM_NAMES, FIRMS, F_FEE, F_FEEMO, F_ACT, F_KIND, F_SIZE
from .kernel import exit_grid, trades
from .search import FE, FF, HORIZON, OUT, UNIT, evaluate, periods, starts_for
from .signals import SESSIONS, bars5, generate, generate_refined

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "lab_app"
COLS = ["resolved", "pass", "mean_days", "median_days", "paid_if_funded", "p_payout", "alive", "ev"]


def pick(sv: np.ndarray, st: np.ndarray, min_res: int = 10) -> dict | None:
    """Sizing chosen on VALID expected value; both periods' numbers for that sizing."""
    ev = sv[:, :, 7].copy()
    ev[sv[:, :, 0] < min_res] = -1e12
    b, c = np.unravel_index(np.argmax(ev), ev.shape)
    if ev[b, c] <= -1e11:
        return None
    return {"fe": float(FE[b]), "ff": float(FF[c]), "valid": dict(zip(COLS, map(float, sv[b, c]))), "test": dict(zip(COLS, map(float, st[b, c])))}


def dedupe(cands: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in sorted(cands, key=lambda c: -(c["train"]["t"] + c["valid"]["t"])):
        k = (c["inst"], c["sess"], c["train"]["n"], round(c["train"]["mean"], 4), round(c["valid"]["mean"], 4))
        if k not in seen:
            seen.add(k); out.append(c)
    return out


def null_baseline(nulls: list[dict]) -> dict:
    """Zero-edge value of each firm: coin-flip entries, averaged over seeds and markets, for each trade shape.
    Sizing chosen on the VALID average; reported on the TEST average."""
    out = {}
    shapes = sorted({tuple(n["cfg"]) for n in nulls})
    for a, fn in enumerate(FIRM_NAMES):
        best = None
        for sh in shapes:
            grp = [n for n in nulls if tuple(n["cfg"]) == sh]
            sv = np.mean([n["sv"][a] for n in grp], axis=0); st = np.mean([n["st"][a] for n in grp], axis=0)
            b, c = np.unravel_index(np.argmax(sv[:, :, 7]), sv[:, :, 7].shape)
            row = {"shape": list(sh), "n": len(grp), "fe": float(FE[b]), "ff": float(FF[c]), "valid": dict(zip(COLS, map(float, sv[b, c]))),
                   "test": dict(zip(COLS, map(float, st[b, c]))), "mean_r_test": float(np.mean([n["test"]["mean"] for n in grp]))}
            if best is None or row["valid"]["ev"] > best["valid"]["ev"]:
                best = row
        out[fn] = best
    return out


_SIG: dict = {}


def signal(name: str, sess: str, spec: dict):
    key = (name, sess)
    if key not in _SIG:
        z = D.load(name); bars5(z)
        _SIG[key] = {json.dumps(sp, sort_keys=True): (t, dr, ref) for sp, t, dr, ref in itertools.chain(generate(z, sess), generate_refined(z, sess))}
    return _SIG[key][json.dumps(spec, sort_keys=True)]


def trade_table(c: dict) -> dict:
    """Per-trade arrays for a candidate over all days (with period labels)."""
    z = D.load(c["inst"]); bars5(z)
    t, dr, ref = signal(c["inst"], c["sess"], c["spec"])
    R, MAE, MFE, SD, PX, TX = trades(z["O"], z["H"], z["L"], z["C"], z["atr5"], t, dr, ref, SESSIONS[c["sess"]][1], D.INSTRUMENTS[c["inst"]].cost, np.array(c["cfg"]))
    qf, nf, upm, lev = UNIT[c["inst"]]
    m = SD > 0
    return {"day": z["days"][m].astype("datetime64[D]").astype(np.int64), "t": t[m].astype(np.int64), "R": R[m], "MAE": MAE[m], "MFE": MFE[m],
            "RPU": SD[m] * qf(PX[m]), "NPU": nf(PX[m]) * np.ones(m.sum()), "UPM": np.full(m.sum(), upm), "LEV": np.full(m.sum(), lev),
            "per": periods(z["days"][m])}


def merged_stream(tabs: list[dict], period: int) -> tuple:
    keys = ["day", "t", "R", "MAE", "MFE", "RPU", "NPU", "UPM", "LEV"]
    parts = {k: np.concatenate([tb[k][tb["per"] == period] for tb in tabs]) for k in keys}
    o = np.lexsort((parts["t"], parts["day"]))
    return tuple(parts[k][o] for k in ["day", "R", "MAE", "MFE", "RPU", "NPU", "UPM", "LEV"])


def score_stream(tabs: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    res = []
    for period in (1, 2):
        st = merged_stream(tabs, period)
        s = starts_for(st[0])
        res.append(evaluate(FIRM_MATRIX, FE, FF, s, *st, HORIZON) if len(s) >= 5 else np.zeros((len(FIRM_NAMES), len(FE), len(FF), 8)))
    return res[0], res[1]


def daily_r(tb: dict) -> dict:
    out: dict = {}
    for d, r in zip(tb["day"], tb["R"]):
        out[d] = out.get(d, 0.0) + r
    return out


def build_portfolio(firm: str, ranked: list[dict], tabs: dict, max_n: int = 5) -> dict | None:
    """Greedy: start from the best single strategy for this firm on VALID, add the strategy that raises VALID EV most."""
    a = FIRM_NAMES.index(firm)
    pool = ranked[:25]
    if not pool:
        return None
    chosen = [pool[0]]
    sv, st = score_stream([tabs[id(pool[0])]])
    best = pick(sv[a], st[a])
    path = [{"n": 1, "valid_ev": best["valid"]["ev"], "test_ev": best["test"]["ev"]}]
    while len(chosen) < max_n:
        top = None
        for c in pool:
            if any(c is x for x in chosen):
                continue
            # skip near-duplicates of something already chosen (same market + session + family)
            if any(c["inst"] == x["inst"] and c["sess"] == x["sess"] and c["spec"]["family"] == x["spec"]["family"] for x in chosen):
                continue
            sv2, st2 = score_stream([tabs[id(x)] for x in chosen] + [tabs[id(c)]])
            p = pick(sv2[a], st2[a])
            if p and (top is None or p["valid"]["ev"] > top[1]["valid"]["ev"]):
                top = (c, p)
        if top is None or top[1]["valid"]["ev"] <= best["valid"]["ev"] * 1.03 + 1:
            break
        chosen.append(top[0]); best = top[1]
        path.append({"n": len(chosen), "valid_ev": best["valid"]["ev"], "test_ev": best["test"]["ev"]})
    return {"firm": firm, "members": [c["desc"] for c in chosen], "pick": best, "path": path}


def run() -> dict:
    raw = np.load(OUT / "raw.npy", allow_pickle=True)[0]
    cands = dedupe(raw["cands"])
    nulls = raw["nulls"]
    base = null_baseline(nulls)
    for c in cands:
        c["firms"] = {fn: pick(c["sv"][a], c["st"][a]) for a, fn in enumerate(FIRM_NAMES)}
        pos = [p for p in c["firms"].values() if p and p["valid"]["ev"] > 0]
        c["score_valid"] = float(sum(p["valid"]["ev"] / max(FIRMS[fn]["p"][F_FEE] + FIRMS[fn]["p"][F_FEEMO] * 2 + FIRMS[fn]["p"][F_ACT], 1.0)
                                     for fn, p in c["firms"].items() if p and p["valid"]["ev"] > 0))
        c["firms_ok_valid"] = len(pos)
        c["firms_ok_test"] = sum(1 for p in c["firms"].values() if p and p["test"]["ev"] > 0)
    ranked = sorted(cands, key=lambda c: -c["score_valid"])

    # per firm: top strategies chosen on VALID EV, reported with TEST
    per_firm = {}
    for fn in FIRM_NAMES:
        rows = sorted([c for c in cands if c["firms"][fn]], key=lambda c: -c["firms"][fn]["valid"]["ev"])[:8]
        per_firm[fn] = [{"desc": c["desc"], "inst": c["inst"], "train": c["train"], "valid_r": c["valid"], "test_r": c["test"], **c["firms"][fn]} for c in rows]

    # portfolios: one or two representatives from each strategy family that produced several survivors.
    # Families are ordered by how many survivors they have (a lone survivor is more likely luck); representatives are the
    # ones with the strongest combined train + valid evidence. How many families to use is chosen per firm on VALID.
    clusters: dict = {}
    for c in cands:  # cands is sorted by train t + valid t
        clusters.setdefault((c["inst"], c["sess"], c["spec"]["family"]), []).append(c)
    fams = sorted([v for v in clusters.values() if len(v) >= 3], key=lambda v: -len(v))
    cluster_rows = [{"inst": v[0]["inst"], "sess": v[0]["sess"], "family": v[0]["spec"]["family"], "survivors": len(v), "rep": v[0]["desc"],
                     "mean_r_train": float(np.mean([y["train"]["mean"] for y in v])), "mean_r_valid": float(np.mean([y["valid"]["mean"] for y in v])),
                     "mean_r_test": float(np.mean([y["test"]["mean"] for y in v])), "share_pos_test": float(np.mean([y["test"]["mean"] > 0 for y in v]))} for v in fams]
    ladder = []
    for k in range(1, len(fams) + 1):
        for top in (1, 2):
            mem = [y for v in fams[:k] for y in v[:top]]
            sv, st = score_stream([trade_table(y) for y in mem])
            ladder.append((k, top, mem, sv, st))
    ports = []
    for a, fn in enumerate(FIRM_NAMES):
        rows = [(k, top, mem, pick(sv[a], st[a])) for k, top, mem, sv, st in ladder]
        rows = [r for r in rows if r[3]]
        if not rows:
            continue
        k, top, mem, best = max(rows, key=lambda r: r[3]["valid"]["ev"])
        ports.append({"firm": fn, "members": [c["desc"] for c in mem], "families": k, "per_family": top, "pick": best,
                      "path": [{"families": r[0], "per_family": r[1], "n": len(r[2]), "valid_ev": r[3]["valid"]["ev"], "test_ev": r[3]["test"]["ev"],
                                "test_pass": r[3]["test"]["pass"], "test_days": r[3]["test"]["median_days"]} for r in rows]})

    tt = raw["t_train"]
    tv = raw["t_valid_given_train"]
    hist, edges = np.histogram(np.clip(tt, -8, 6), bins=28)
    summary = {
        "funnel": raw["funnel"], "families": raw["families"], "n_candidates": len(cands), "n_nulls": len(nulls),
        "t_hist": {"counts": hist.tolist(), "edges": [round(float(x), 2) for x in edges], "median": float(np.median(tt)),
                   "share_gt2": float((tt > 2).mean()), "share_gt3": float((tt > 3).mean())},
        "valid_given_train": {"n": int(len(tv)), "share_positive": float((tv > 0).mean()) if len(tv) else 0.0, "mean_t": float(tv.mean()) if len(tv) else 0.0},
        "test_of_candidates": {"n": len(cands), "share_positive": float(np.mean([c["test"]["mean"] > 0 for c in cands])) if cands else 0.0,
                               "mean_r": float(np.mean([c["test"]["mean"] for c in cands])) if cands else 0.0,
                               "mean_r_valid": float(np.mean([c["valid"]["mean"] for c in cands])) if cands else 0.0,
                               "mean_r_train": float(np.mean([c["train"]["mean"] for c in cands])) if cands else 0.0},
        "periods": {"train": "2016-2021", "valid": "2022-2023", "test": "2024-Nov 2026"},
        "sizing": {"eval": FE.tolist(), "funded": FF.tolist(), "horizon_days": HORIZON},
        "firms": {fn: {"note": FIRMS[fn]["note"], "kind": "futures" if FIRMS[fn]["p"][F_KIND] == 0 else "cfd", "size": float(FIRMS[fn]["p"][F_SIZE]),
                       "fee": float(FIRMS[fn]["p"][F_FEE]), "fee_monthly": float(FIRMS[fn]["p"][F_FEEMO]), "activation": float(FIRMS[fn]["p"][F_ACT]),
                       "null": base[fn]} for fn in FIRM_NAMES},
        "leaderboard": [{"desc": c["desc"], "inst": c["inst"], "sess": c["sess"], "family": c["spec"]["family"], "train": c["train"], "valid": c["valid"],
                         "test": c["test"], "score_valid": c["score_valid"], "firms_ok_valid": c["firms_ok_valid"], "firms_ok_test": c["firms_ok_test"],
                         "firms": c["firms"]} for c in ranked[:60]],
        "per_firm": per_firm, "portfolios": ports, "clusters": cluster_rows,
        "instruments": {n: {"cost": i.cost, "micro": i.micro} for n, i in D.INSTRUMENTS.items()},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(summary, default=float))
    APP.mkdir(exist_ok=True)
    (APP / "data.js").write_text("window.LAB_DATA = " + json.dumps(summary, default=float) + ";\n")
    return summary


if __name__ == "__main__":
    s = run()
    print("funnel", s["funnel"], "candidates", s["n_candidates"])
    print("test of candidates", {k: round(v, 3) if isinstance(v, float) else v for k, v in s["test_of_candidates"].items()})
    print("\nZERO-EDGE value per firm (TEST): pass, median days, EV")
    for fn, f in s["firms"].items():
        n = f["null"]
        print(f"  {fn:26s} shape stop x{n['shape'][0]:g} target {n['shape'][1]:g}R eval x{n['fe']} funded x{n['ff']}: pass {n['test']['pass']*100:4.0f}% days {n['test']['median_days']:4.0f} EV ${n['test']['ev']:7.0f} (valid ${n['valid']['ev']:7.0f})")
    print("\nBEST STRATEGY per firm (picked on VALID, shown on TEST)")
    for fn, rows in s["per_firm"].items():
        if rows:
            r = rows[0]
            print(f"  {fn:26s} VALID EV ${r['valid']['ev']:7.0f} | TEST pass {r['test']['pass']*100:4.0f}% days {r['test']['median_days']:4.0f} EV ${r['test']['ev']:7.0f} | {r['desc'][:90]}")
    print("\nPORTFOLIOS")
    for p in s["portfolios"]:
        print(f"  {p['firm']:26s} {p['families']} families x{p['per_family']}: VALID EV ${p['pick']['valid']['ev']:7.0f} | TEST pass {p['pick']['test']['pass']*100:4.0f}% days {p['pick']['test']['median_days']:4.0f} EV ${p['pick']['test']['ev']:7.0f}")
