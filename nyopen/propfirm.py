"""Prop-firm evaluation simulator with a catalog of real firm rule sets.

Replays the strategy's historical trade stream (one trade per day, in R) against each firm's rules,
starting an evaluation on every possible day. Risk is a fixed % of the starting balance per trade
(optionally cut in drawdown). Reports pass / blow-up rates, time to pass, funded survival and the
economics of an attempt (fees paid, expected first-year payout).

Rule figures were collected from the firms' sites and third-party rule databases in October 2026.
They change often and promos vary: VERIFY on the firm's own page before paying. `verify` notes mark
the figures that were least consistent across sources.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

import numpy as np
import pandas as pd


@dataclass
class RuleSet:
    name: str
    firm: str
    market: str                      # cfd | futures | stocks
    account_size: float
    targets_pct: tuple[float, ...]   # one entry per phase
    daily_loss_pct: float            # max loss in one day, % of start balance (0 = none)
    max_loss_pct: float              # max drawdown, % of start balance
    dd_type: str = "static"          # static | eod | intraday  (trailing types follow the highest balance)
    trail_lock: bool = False         # trailing floor stops rising once it reaches the start balance
    consistency_pct: float = 0.0     # best day must be <= this % of total profit to pass (0 = none)
    funded_consistency_pct: float = 0.0
    min_days: int = 0
    time_limit_days: int = 0         # calendar days per phase (0 = unlimited)
    fee: float = 0.0                 # one-time evaluation fee (typical promo price)
    monthly_fee: float = 0.0         # subscription billed while in evaluation
    activation_fee: float = 0.0      # paid once on passing
    fee_refund: bool = False         # fee returned with the first payout
    split: float = 0.8               # trader's share of funded profit
    description: str = ""
    verify: str = ""


# ---- catalog --------------------------------------------------------------------------------------
CATALOG: list[RuleSet] = [
    RuleSet("FTMO 2-step 100k", "FTMO", "cfd", 100_000, (10, 5), 5, 10, "static", False, 0, 0, 4, 0, 540, 0, 0, True, 0.8,
            "Phase 1 +10%, phase 2 +5%. 5% daily loss, 10% static max loss, no time limit, 4 min days. 80% split rising to 90%; fee refunded with first payout.",
            "fee ~$540 at list; daily-loss reset time differs by source"),
    RuleSet("FTMO 1-step 100k", "FTMO", "cfd", 100_000, (10,), 3, 10, "eod", False, 50, 0, 0, 0, 540, 0, 0, True, 0.9,
            "Single phase +10%. 3% daily loss, 10% max loss (end-of-day trailing per most sources), 50% best-day consistency rule from Oct 2026. 90% split.",
            "max-loss type and the consistency rule scope differ across sources"),
    RuleSet("FundedNext Stellar 2-step 100k", "FundedNext", "cfd", 100_000, (8, 5), 5, 10, "static", False, 0, 0, 5, 0, 549, 0, 0, True, 0.9,
            "Phase 1 +8%, phase 2 +5%. 5% daily, 10% static, 5 min days, no time limit. Up to 95% split with add-on; fee refunded.",
            "fee and split vary by promo and add-ons"),
    RuleSet("FundingPips 2-step 100k", "FundingPips", "cfd", 100_000, (8, 5), 5, 10, "static", False, 0, 0, 3, 0, 399, 0, 0, False, 0.8,
            "Phase 1 +8%, phase 2 +5%. 5% daily, 10% static, 3 min days, no time limit. 80% split rising with add-ons.",
            "min days and refund policy vary by plan"),
    RuleSet("Topstep 50k Combine", "Topstep", "futures", 50_000, (6,), 0, 4, "eod", True, 50, 0, 2, 0, 0, 85, 149, False, 0.9,
            "Target $3k (6%). $2k end-of-day trailing drawdown that locks at the start balance. Best day must be under ~50% of the target. Monthly subscription (~$49-85 promo), $149 activation. 90% split, payout caps apply.",
            "consistency figure is 50% on the help center and 55% on the site; promo pricing changes"),
    RuleSet("Apex 50k (intraday trailing)", "Apex Trader Funding", "futures", 50_000, (6,), 0, 4, "intraday", True, 0, 50, 1, 0, 150, 0, 0, False, 1.0,
            "Target $3k. $2k intraday trailing drawdown; no daily limit; no consistency rule in evaluation. One-time fee (promo-dependent). Funded: trailing locks at start + $100, 50% consistency at each payout, 100% split on new accounts.",
            "fee is promo-dependent; funded rules changed in March 2026"),
    RuleSet("MyFundedFutures Rapid 50k", "MyFundedFutures", "futures", 50_000, (6,), 0, 4, "static", False, 50, 0, 2, 0, 105, 0, 0, False, 0.9,
            "Target $3k. $2k static max loss (end-of-day), no daily limit, 50% consistency in evaluation, 2 min days. One-time ~$209 list, often half price. Funded: no consistency, 90% split, daily payouts.",
            "consistency is 30% on the smaller Rapid EOD variants"),
    RuleSet("Tradeify Select 50k", "Tradeify", "futures", 50_000, (6,), 0, 4, "eod", False, 40, 0, 3, 0, 165, 0, 0, False, 0.9,
            "Target $3k. $2k end-of-day trailing, no daily limit, 40% consistency in evaluation, 3 min days. One-time $165. Funded Select Flex: no consistency, 90% split.",
            "Growth path has different limits"),
    RuleSet("Lucid Flex 50k", "Lucid Trading", "futures", 50_000, (6,), 0, 4, "eod", True, 50, 0, 0, 0, 100, 0, 0, False, 0.9,
            "Target $3k. $2k end-of-day trailing that locks at start + $100, optional daily limit, 50% consistency. One-time fee from ~$70-100 after discounts. Funded Flex: no consistency, 90% split.",
            "pricing after discounts varies"),
    RuleSet("Lucid Pro 50k (fast)", "Lucid Trading", "futures", 50_000, (6,), 2.4, 4, "eod", True, 0, 40, 0, 0, 120, 0, 0, False, 0.9,
            "Target $3k. $2k end-of-day trailing that locks at start + $100, $1.2k daily limit, no consistency rule, no minimum days (can pass in one day). Funded: 40% consistency per payout cycle, 90% split.",
            "pricing and the funded consistency rule vary by promo and cycle"),
    RuleSet("Take Profit Trader PRO 50k", "Take Profit Trader", "futures", 50_000, (6,), 2, 4, "static", False, 0, 0, 3, 0, 150, 0, 130, False, 0.8,
            "Target $3k. $2k static max loss, $500 daily limit, 3 min days (since Aug 2026), no consistency. One-time fee plus $130 activation (often waived). 80% split, withdrawals from day one.",
            "daily limit applies to the Test; PRO details vary"),
    RuleSet("Trade The Pool day-trade (stocks)", "Trade The Pool", "stocks", 100_000, (6,), 3, 6, "static", False, 30, 0, 0, 0, 300, 0, 0, False, 0.7,
            "US stocks/ETFs only (trade QQQ instead of NAS100). Target +6%, 6% static max loss, daily limit ~3%, best position capped at 30% of the target on the MAX plan. 70% split, payouts every 14 days.",
            "targets, daily limit and plan structure differ widely across sources; automation heavily restricted"),
]


def _daily(trades: pd.DataFrame) -> pd.DataFrame:
    g = trades.groupby("date")
    d = pd.DataFrame({"r": g.r_multiple.sum(), "mfe": g.mfe_r.max() if "mfe_r" in trades else g.r_multiple.sum()}).reset_index()
    d["date"] = pd.to_datetime(d["date"])
    return d


def scaled_risk(risk_pct: float, bal: float, peak: float, rs: RuleSet, scaling: str) -> float:
    """fixed: always risk_pct. drawdown: halve the risk once 30% of the max-loss allowance is used, quarter it at 60%."""
    if scaling == "fixed":
        return risk_pct
    used = (peak - bal) / rs.max_loss_pct if rs.dd_type != "static" else (0.0 - bal) / rs.max_loss_pct
    if used >= 0.6:
        return risk_pct * 0.25
    if used >= 0.3:
        return risk_pct * 0.5
    return risk_pct


def _floor(rs: RuleSet, peak: float) -> float:
    if rs.dd_type == "static":
        return -rs.max_loss_pct
    f = peak - rs.max_loss_pct
    return min(f, 0.0) if rs.trail_lock else f


def run_phase(r: np.ndarray, mfe: np.ndarray, dates: np.ndarray, start: int, risk_pct: float, rs: RuleSet, target_pct: float, scaling: str = "fixed") -> tuple[str, int, int]:
    """Return (outcome, trading_days_used, index after the phase). outcome: pass | fail | unfinished."""
    bal, peak, days, best_day = 0.0, 0.0, 0, 0.0
    t0 = dates[start]
    i = start
    while i < len(r):
        if rs.time_limit_days and (dates[i] - t0).astype("timedelta64[D]").astype(int) >= rs.time_limit_days:
            return "fail", days, i
        rk = scaled_risk(risk_pct, bal, peak, rs, scaling)
        day_pnl = r[i] * rk
        if rs.daily_loss_pct and day_pnl <= -rs.daily_loss_pct:
            return "fail", days + 1, i + 1
        if rs.dd_type == "intraday":
            peak = max(peak, bal + max(mfe[i], 0.0) * rk)   # the floor ratchets on the intraday high-water mark
        bal += day_pnl
        days += 1
        if bal <= _floor(rs, peak):
            return "fail", days, i + 1
        peak = max(peak, bal)
        best_day = max(best_day, day_pnl)
        consistent = (not rs.consistency_pct) or (bal > 0 and best_day <= rs.consistency_pct / 100 * bal)
        if bal >= target_pct and days >= rs.min_days and consistent:
            return "pass", days, i + 1
        i += 1
    return "unfinished", days, i


def simulate(trades: pd.DataFrame, risk_pct: float, rs: RuleSet, funded_months: int = 12, scaling: str = "fixed", funded_risk_pct: float | None = None) -> dict:
    """funded_risk_pct: risk used once funded (default: same as the evaluation). Fast-track plans pass at high risk and then cut back."""
    frisk = risk_pct if funded_risk_pct is None else funded_risk_pct
    d = _daily(trades)
    r, mfe, dates = d.r.to_numpy(), d.mfe.to_numpy(), d.date.to_numpy()
    n = len(r)
    outcomes, days_to_pass, eval_days_all, funded_survive, funded_profit = [], [], [], [], []
    for start in range(0, n - 60):
        i, total_days, ok = start, 0, True
        for target in rs.targets_pct:
            res, used, i = run_phase(r, mfe, dates, i, risk_pct, rs, target, scaling)
            total_days += used
            if res != "pass":
                outcomes.append(res)
                ok = False
                break
        if res != "unfinished":
            eval_days_all.append(int((dates[min(i, n - 1)] - dates[start]).astype("timedelta64[D]").astype(int)))
        if not ok:
            continue
        outcomes.append("pass")
        days_to_pass.append(int((dates[i - 1] - dates[start]).astype("timedelta64[D]").astype(int)))
        # funded phase: same drawdown rules, no target, for `funded_months` months after passing
        bal, peak, breached, j = 0.0, 0.0, False, i
        end = dates[i] + np.timedelta64(30 * funded_months, "D") if i < n else None
        while j < n and dates[j] < end:
            rk = scaled_risk(frisk, bal, peak, rs, scaling)
            day_pnl = r[j] * rk
            if rs.dd_type == "intraday":
                peak = max(peak, bal + max(mfe[j], 0.0) * rk)
            bal += day_pnl
            if (rs.daily_loss_pct and day_pnl <= -rs.daily_loss_pct) or bal <= _floor(rs, peak):
                breached = True
                break
            peak = max(peak, bal)
            j += 1
        if j < n or breached:
            funded_survive.append(not breached)
            funded_profit.append(bal)
    o = pd.Series(outcomes)
    counted = o[o != "unfinished"]
    pass_rate = float((counted == "pass").mean()) if len(counted) else 0.0
    months_in_eval = float(np.mean(eval_days_all)) / 30 if eval_days_all else 0.0
    pnl12 = float(np.mean(funded_profit)) if funded_profit else 0.0
    # economics of one attempt, first funded year
    fees = rs.fee + rs.monthly_fee * max(1.0, months_in_eval) + rs.activation_fee * pass_rate
    payout = pass_rate * rs.account_size * pnl12 / 100 * rs.split
    refund = rs.fee * pass_rate if rs.fee_refund else 0.0
    return {
        "ruleset": rs.name, "firm": rs.firm, "market": rs.market, "risk_pct": risk_pct, "funded_risk_pct": frisk, "scaling": scaling, "starts": int(len(o)), "resolved": int(len(counted)),
        "pass_rate_pct": pass_rate * 100 if len(counted) else None,
        "fail_rate_pct": float((counted == "fail").mean() * 100) if len(counted) else None,
        "median_days_to_pass": float(np.median(days_to_pass)) if days_to_pass else None,
        "p90_days_to_pass": float(np.percentile(days_to_pass, 90)) if days_to_pass else None,
        "funded_survival_12m_pct": float(np.mean(funded_survive) * 100) if funded_survive else None,
        "funded_pnl_12m_pct": pnl12 if funded_profit else None,
        "funded_months": funded_months,
        "expected_fees": fees, "expected_payout_y1": payout, "expected_refund": refund,
        "ev_y1": payout + refund - fees,
    }


def prop_firm_report(trades: pd.DataFrame, risks=(0.25, 0.5, 0.75, 1.0, 1.5), scalings=("fixed", "drawdown")) -> dict:
    rows = [simulate(trades, rk, rs, scaling=sc) for sc in scalings for rs in CATALOG for rk in risks]
    # ranking: for each firm, the best risk/sizing by first-year expected value among settings that pass at least 90% of the time
    ranking = []
    for rs in CATALOG:
        cand = [x for x in rows if x["ruleset"] == rs.name and (x["pass_rate_pct"] or 0) >= 90]
        if not cand:
            cand = [x for x in rows if x["ruleset"] == rs.name and x["pass_rate_pct"] is not None]
        best = max(cand, key=lambda x: x["ev_y1"]) if cand else None
        if best:
            ranking.append({**best, "description": rs.description, "verify": rs.verify, "account_size": rs.account_size, "split": rs.split, "fee": rs.fee, "monthly_fee": rs.monthly_fee, "activation_fee": rs.activation_fee})
    ranking.sort(key=lambda x: x["ev_y1"], reverse=True)
    return {"rulesets": [asdict(rs) for rs in CATALOG], "risks": list(risks), "scalings": list(scalings), "rows": rows, "ranking": ranking}


def fast_track_report(trades: pd.DataFrame, risks=(1.0, 2.0, 3.0), funded_risk_pct: float = 0.25, limits=(14, 30)) -> list[dict]:
    """For every plan and evaluation risk: share of historical starts funded within N days, blow-up rate, and what it
    costs to keep buying staggered attempts until one passes quickly. Funded phase runs at `funded_risk_pct`."""
    d = _daily(trades)
    r, mfe, dates = d.r.to_numpy(), d.mfe.to_numpy(), d.date.to_numpy()
    n = len(r)
    out = []
    for rs in CATALOG:
        for rk in risks:
            within = {L: 0 for L in limits}
            fail = tot = 0
            for s0 in range(0, n - 60):
                i, ok = s0, True
                for tg in rs.targets_pct:
                    res, used, i = run_phase(r, mfe, dates, i, rk, rs, tg, "fixed")
                    if res != "pass":
                        ok = False
                        break
                tot += 1
                if not ok:
                    fail += 1
                    continue
                days = int((dates[i - 1] - dates[s0]).astype("timedelta64[D]").astype(int))
                for L in limits:
                    if days <= L:
                        within[L] += 1
            sim = simulate(trades, rk, rs, scaling="fixed", funded_risk_pct=funded_risk_pct)
            p14 = within[limits[0]] / tot
            attempts = (1 / p14) if p14 > 0 else None
            fee_per_attempt = rs.fee + rs.monthly_fee * 1 + rs.activation_fee * p14
            out.append({"ruleset": rs.name, "firm": rs.firm, "market": rs.market, "account_size": rs.account_size, "risk_pct": rk, "funded_risk_pct": funded_risk_pct,
                        **{f"funded_within_{L}d_pct": within[L] / tot * 100 for L in limits},
                        "blow_up_pct": fail / tot * 100, "expected_attempts_14d": attempts, "expected_fees_to_funded_14d": attempts * fee_per_attempt if attempts else None,
                        "funded_survival_12m_pct": sim["funded_survival_12m_pct"], "funded_pnl_12m_pct": sim["funded_pnl_12m_pct"],
                        "expected_payout_y1_if_funded": (sim["funded_pnl_12m_pct"] or 0) / 100 * rs.account_size * rs.split, "split": rs.split})
    out.sort(key=lambda x: x[f"funded_within_{limits[0]}d_pct"], reverse=True)
    return out


# backwards-compatible alias used by propbot
RULESETS = CATALOG


if __name__ == "__main__":
    from .backtest import backtest
    from .strategy import Params
    rep = prop_firm_report(backtest(Params())["trades"])
    cols = ["ruleset", "risk_pct", "scaling", "pass_rate_pct", "median_days_to_pass", "funded_survival_12m_pct", "funded_pnl_12m_pct", "expected_fees", "expected_payout_y1", "ev_y1"]
    print(pd.DataFrame(rep["ranking"])[cols].round(1).to_string())
