"""Prop-firm evaluation simulator.

Replays the strategy's historical trade stream (R-multiples, one trade per day) against typical
funded-account rules, starting an evaluation on every possible day. Risk is a fixed % of the starting
balance per trade (no compounding inside a challenge). This answers: with this edge, this variance and
this risk size, how often does a challenge pass, how often does it blow up, and how long does it take?
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass
class RuleSet:
    name: str
    description: str
    targets_pct: tuple[float, ...]   # one entry per phase, e.g. (10, 5) for a two-step challenge
    daily_loss_pct: float            # max loss in one day, % of starting balance (0 = none)
    max_loss_pct: float              # max total loss, % of starting balance
    trailing: bool = False           # True: measured from the highest closed balance (futures style)
    min_days: int = 0                # minimum trading days per phase
    time_limit_days: int = 0         # calendar days allowed per phase (0 = unlimited)


RULESETS = [
    RuleSet("Two-step 10 / 5", "Phase 1 +10%, phase 2 +5%. 5% daily loss, 10% max loss from the start balance, no time limit, 4 min days.", (10, 5), 5, 10, False, 4, 0),
    RuleSet("One-step 10 / 6", "Single phase +10%. 3% daily loss, 6% max loss from the start balance, no time limit.", (10,), 3, 6, False, 3, 0),
    RuleSet("Two-step, 30-day phases", "Same as the two-step but each phase must be finished within 30 calendar days.", (10, 5), 5, 10, False, 4, 30),
    RuleSet("Futures-style trailing 6 / 4", "Target +6%, 4% trailing drawdown measured from the highest closed balance (e.g. $3k target and $2k trail on $50k).", (6,), 0, 4, True, 0, 0),
]


def _daily(trades: pd.DataFrame) -> pd.DataFrame:
    d = trades.groupby("date").r_multiple.sum().reset_index()
    d["date"] = pd.to_datetime(d["date"])
    return d


def scaled_risk(risk_pct: float, bal: float, peak: float, rs: "RuleSet", scaling: str) -> float:
    """Risk for the next trade under a sizing policy.
    fixed:      always risk_pct.
    drawdown:   halve the risk once the balance is 30% of the way to the max-loss line, quarter it at 60%.
    """
    if scaling == "fixed":
        return risk_pct
    floor = (peak - rs.max_loss_pct) if rs.trailing else -rs.max_loss_pct
    used = (0.0 - bal) / rs.max_loss_pct if not rs.trailing else (peak - bal) / rs.max_loss_pct
    if used >= 0.6:
        return risk_pct * 0.25
    if used >= 0.3:
        return risk_pct * 0.5
    return risk_pct


def run_phase(r: np.ndarray, dates: np.ndarray, start: int, risk_pct: float, rs: RuleSet, target_pct: float, scaling: str = "fixed") -> tuple[str, int, int]:
    """Return (outcome, trading_days_used, index after the phase). outcome: pass | fail | unfinished."""
    bal, peak, days = 0.0, 0.0, 0
    t0 = dates[start]
    i = start
    while i < len(r):
        if rs.time_limit_days and (dates[i] - t0).astype("timedelta64[D]").astype(int) >= rs.time_limit_days:
            return "fail", days, i
        day_pnl = r[i] * scaled_risk(risk_pct, bal, peak, rs, scaling)
        if rs.daily_loss_pct and day_pnl <= -rs.daily_loss_pct:
            return "fail", days + 1, i + 1
        bal += day_pnl
        days += 1
        floor = (peak - rs.max_loss_pct) if rs.trailing else -rs.max_loss_pct
        if bal <= floor:
            return "fail", days, i + 1
        peak = max(peak, bal)
        if bal >= target_pct and days >= rs.min_days:
            return "pass", days, i + 1
        i += 1
    return "unfinished", days, i


def simulate(trades: pd.DataFrame, risk_pct: float, rs: RuleSet, funded_months: int = 12, scaling: str = "fixed") -> dict:
    d = _daily(trades)
    r, dates = d.r_multiple.to_numpy(), d.date.to_numpy()
    n = len(r)
    outcomes, days_to_pass, funded_survive, funded_profit = [], [], [], []
    for start in range(0, n - 60):
        i, total_days, ok = start, 0, True
        for target in rs.targets_pct:
            res, used, i = run_phase(r, dates, i, risk_pct, rs, target, scaling)
            total_days += used
            if res != "pass":
                outcomes.append(res)
                ok = False
                break
        if not ok:
            continue
        outcomes.append("pass")
        days_to_pass.append(int((dates[i - 1] - dates[start]).astype("timedelta64[D]").astype(int)))
        # funded phase: same rules without a target, for `funded_months` months after passing
        bal, peak, breached, j = 0.0, 0.0, False, i
        end = dates[i] + np.timedelta64(30 * funded_months, "D") if i < n else None
        while j < n and dates[j] < end:
            day_pnl = r[j] * scaled_risk(risk_pct, bal, peak, rs, scaling)
            bal += day_pnl
            floor = (peak - rs.max_loss_pct) if rs.trailing else -rs.max_loss_pct
            if (rs.daily_loss_pct and day_pnl <= -rs.daily_loss_pct) or bal <= floor:
                breached = True
                break
            peak = max(peak, bal)
            j += 1
        if j < n or breached:
            funded_survive.append(not breached)
            funded_profit.append(bal)   # closed P&L after `funded_months` months, or at the breach (account gone)
    o = pd.Series(outcomes)
    counted = o[o != "unfinished"]
    return {
        "ruleset": rs.name, "risk_pct": risk_pct, "scaling": scaling, "starts": int(len(o)), "resolved": int(len(counted)),
        "pass_rate_pct": float((counted == "pass").mean() * 100) if len(counted) else None,
        "fail_rate_pct": float((counted == "fail").mean() * 100) if len(counted) else None,
        "median_days_to_pass": float(np.median(days_to_pass)) if days_to_pass else None,
        "p90_days_to_pass": float(np.percentile(days_to_pass, 90)) if days_to_pass else None,
        "funded_survival_12m_pct": float(np.mean(funded_survive) * 100) if funded_survive else None,
        "funded_pnl_12m_pct": float(np.mean(funded_profit)) if funded_profit else None,
        "funded_months": funded_months,
    }


def prop_firm_report(trades: pd.DataFrame, risks=(0.25, 0.5, 0.75, 1.0, 1.5), scalings=("fixed", "drawdown")) -> dict:
    rows = [simulate(trades, rk, rs, scaling=sc) for sc in scalings for rs in RULESETS for rk in risks]
    return {"rulesets": [asdict(rs) for rs in RULESETS], "risks": list(risks), "scalings": list(scalings), "rows": rows}


if __name__ == "__main__":
    from .backtest import backtest
    from .strategy import Params
    rep = prop_firm_report(backtest(Params())["trades"])
    print(pd.DataFrame(rep["rows"]).round(1).to_string())
