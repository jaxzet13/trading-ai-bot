"""Sequential fast-lane tickets: buy one evaluation; if it blows up, buy the next the same day.
Replays the real trade history from every possible start day and reports the chance of being funded
within N calendar days for a given number of tickets, plus the fees spent."""
from __future__ import annotations

import numpy as np
import pandas as pd

from nyopen.propfirm import CATALOG, _daily, run_phase


def sequential(trades: pd.DataFrame, plan: str, risk_pct: float, max_tickets: int, horizons=(7, 14, 21, 30, 60)) -> dict:
    rs = next(r for r in CATALOG if r.name == plan)
    d = _daily(trades)
    r, mfe, dates = d.r.to_numpy(), d.mfe.to_numpy(), d.date.to_numpy()
    n = len(r)
    funded_by = {h: 0 for h in horizons}
    tickets_used, starts = [], 0
    for s0 in range(0, n - 80):
        i, used, funded_day = s0, 0, None
        while used < max_tickets and i < n:
            used += 1
            ok = True
            for tg in rs.targets_pct:
                res, _, i = run_phase(r, mfe, dates, i, risk_pct, rs, tg, "fixed")
                if res != "pass":
                    ok = False
                    break
            if ok:
                funded_day = int((dates[i - 1] - dates[s0]).astype("timedelta64[D]").astype(int))
                break
            if res == "unfinished":
                break
        starts += 1
        tickets_used.append(used)
        if funded_day is not None:
            for h in horizons:
                if funded_day <= h:
                    funded_by[h] += 1
    fee = rs.fee + rs.activation_fee
    return {"plan": plan, "risk_pct": risk_pct, "max_tickets": max_tickets, "fee_per_ticket": fee,
            **{f"funded_by_{h}d_pct": funded_by[h] / starts * 100 for h in horizons},
            "avg_tickets_used": float(np.mean(tickets_used)), "avg_fees": float(np.mean(tickets_used)) * fee}


def ticket_table(trades: pd.DataFrame, plans=("Lucid Pro 50k (fast)", "Apex 50k (intraday trailing)", "Take Profit Trader PRO 50k"),
                 risks=(1.0, 2.0), max_tickets=(1, 2, 3, 4, 6, 8, 10)) -> list[dict]:
    return [sequential(trades, p, rk, k) for p in plans for rk in risks for k in max_tickets]


if __name__ == "__main__":
    from nyopen.backtest import backtest
    from nyopen.strategy import Params
    t = backtest(Params())["trades"]
    df = pd.DataFrame(ticket_table(t))
    print(df.round(1).to_string())


def staggered(trades: pd.DataFrame, plan: str, risk_pct: float, k: int, gap_days: int = 1, horizon: int = 14) -> dict:
    """Buy k tickets, starting one every `gap_days` trading days. Chance at least one is funded within `horizon`
    calendar days of the first purchase."""
    rs = next(r for r in CATALOG if r.name == plan)
    d = _daily(trades)
    r, mfe, dates = d.r.to_numpy(), d.mfe.to_numpy(), d.date.to_numpy()
    n = len(r)
    hit = starts = 0
    for s0 in range(0, n - 80):
        got = False
        for j in range(k):
            st = s0 + j * gap_days
            i, ok = st, True
            for tg in rs.targets_pct:
                res, _, i = run_phase(r, mfe, dates, i, risk_pct, rs, tg, "fixed")
                if res != "pass":
                    ok = False
                    break
            if ok and int((dates[i - 1] - dates[s0]).astype("timedelta64[D]").astype(int)) <= horizon:
                got = True
                break
        starts += 1
        hit += got
    return {"plan": plan, "risk_pct": risk_pct, "tickets": k, "gap_days": gap_days, "horizon_days": horizon,
            "funded_pct": hit / starts * 100, "fees": k * (rs.fee + rs.activation_fee)}
