"""Combine accepted day-trading strategies into one desk and run it through the prop-firm simulator.

Every strategy trades at the same risk per trade; a day's result in R is the sum over strategies. One strategy per
instrument and session family (the open-candle rule and its video variant are the same family: keep the better).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from nyopen.metrics import compute_metrics
from nyopen.optimize import OOS_START
from nyopen.propfirm import CATALOG, simulate
from fastfund.tickets import sequential

ROOT = Path(__file__).resolve().parent.parent
DESK = ROOT / "experiments" / "desk"


def accepted() -> list[dict]:
    rows = []
    for p in sorted(DESK.glob("*.json")):
        if p.name == "portfolio.json":
            continue
        rows += json.loads(p.read_text()).get("accepted", [])
    fam = {}
    for r in rows:
        k = (r["instrument"], r["session"], "open" if r["setup"].startswith("open_candle") else r["setup"])
        if k not in fam or r["is_pf"] > fam[k]["is_pf"]:
            fam[k] = r
    return list(fam.values())


def daily_matrix(strats: list[dict]) -> pd.DataFrame:
    cols = {}
    mfe = {}
    for s in strats:
        t = pd.read_csv(DESK / f"{s['id']}.csv")
        cols[s["id"]] = t.groupby("date").r_multiple.sum()
        mfe[s["id"]] = t.groupby("date").mfe_r.max()
    R = pd.DataFrame(cols).fillna(0.0).sort_index()
    F = pd.DataFrame(mfe).reindex(R.index).fillna(0.0)
    return R, F


def desk_trades(R: pd.DataFrame, F: pd.DataFrame) -> pd.DataFrame:
    """One row per day with the summed R, shaped like a trade list so the prop simulator can replay it."""
    tot = R.sum(axis=1)
    df = pd.DataFrame({"date": R.index, "r_multiple": tot.values, "mfe_r": np.maximum(F.clip(lower=0).sum(axis=1).values, tot.values)})
    eq, rows = 10_000.0, []
    for r in df.r_multiple:
        eq += eq * 0.01 * r
        rows.append(eq)
    df["pnl"] = df.r_multiple * 100
    df["equity_after"] = rows
    df["direction"] = "desk"
    df["bars_held"] = 0
    return df


def build(risk_list=(0.25, 0.5, 0.75, 1.0)) -> dict:
    strats = accepted()
    R, F = daily_matrix(strats)
    corr = R.corr().round(2)
    t = desk_trades(R, F)
    m = compute_metrics(t, 10_000)
    mi = compute_metrics(t[t.date < OOS_START], 10_000)
    mo = compute_metrics(t[t.date >= OOS_START], 10_000)
    singles = {}
    for c in R.columns:
        s = R[c][R[c] != 0]
        singles[c] = {"trades_days": int(len(s)), "sum_r": float(s.sum()), "avg_r_day": float(s.mean())}
    prop = []
    for rs in CATALOG:
        for rk in risk_list:
            for sc in ("fixed", "drawdown"):
                prop.append(simulate(t, rk, rs, scaling=sc))
    fast = [sequential(t, p, rk, k) for p in ("Lucid Pro 50k (fast)", "Apex 50k (intraday trailing)") for rk in (0.5, 1.0) for k in (1, 3, 6)]
    yearly = t.groupby(pd.to_datetime(t.date).dt.year).r_multiple.sum().round(1).to_dict()
    out = {"strategies": strats, "corr": {"cols": list(corr.columns), "values": corr.values.tolist()}, "metrics": m, "is": mi, "oos": mo,
           "singles": singles, "yearly_r": {int(k): v for k, v in yearly.items()}, "prop": prop, "fast": fast,
           "equity": {"dates": list(t.date), "cum_r": [round(x, 2) for x in t.r_multiple.cumsum()],
                      "per_strategy": {c: [round(x, 2) for x in R[c].cumsum()] for c in R.columns}}}
    (DESK / "portfolio.json").write_text(json.dumps(out, default=float))
    return out


if __name__ == "__main__":
    o = build()
    print("strategies:", [s["id"] for s in o["strategies"]])
    print("corr:", o["corr"])
    for k in ("metrics", "is", "oos"):
        m = o[k]; print(k, {x: round(m[x], 3) for x in ("trades", "win_rate_pct", "profit_factor", "avg_r", "max_drawdown_pct", "sharpe", "longest_loss_streak")})
    print("yearly R:", o["yearly_r"])
    df = pd.DataFrame(o["prop"])
    print(df[df.ruleset.str.contains("FundedNext|Lucid Pro|Apex|FTMO 2")][["ruleset", "risk_pct", "scaling", "pass_rate_pct", "median_days_to_pass", "funded_survival_12m_pct", "funded_pnl_12m_pct"]].round(1).to_string())
    print(pd.DataFrame(o["fast"]).round(1).to_string())
