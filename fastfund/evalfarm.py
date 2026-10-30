"""Eval farming: the all-in evaluation method from "How I Made $50,000 in a Week as a Prop Firm Trader" (Andy Trades).

On a cheap futures evaluation, every trade risks the whole remaining drawdown with a target SMALLER than the risk
(negative R:R, e.g. 0.5 or 0.75), no breakeven moves. Each win covers a slice of the profit target; one loss ends the
account and a new evaluation is bought. Passing takes 2 to 3 winning trades, which the consistency rules require anyway.

Here the entries come from the NAS100 New York open signal (09:30 candle vs the EMAs). For every signal day we walk the
5-minute bars after entry: the stop sits `stop_mult` x the candle risk away, the target `rr` x the stop distance. Stop and
target touched in the same bar count as a loss. A trade still open at the exit time closes at market.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nyopen.backtest import get_bars
from nyopen.strategy import Params, VIDEO_RULE, add_indicators, run_day


def trade_paths(p: Params) -> list[dict]:
    """Per signal day: direction, entry, candle risk, and the bars after entry until the exit time."""
    bars = add_indicators(get_bars(5), p)
    out = []
    exit_hhmm = int(p.exit_time.replace(":", ""))
    for date, day in bars.groupby("date", sort=True):
        t = run_day(day, p, 10_000.0)
        if t is None:
            continue
        day = day.reset_index(drop=True)
        i0 = int(np.flatnonzero(day.hhmm.to_numpy() == int(p.signal_time.replace(":", "")))[0])
        after = day.iloc[i0 + 1:]
        after = after[after.hhmm <= exit_hhmm]
        out.append({"date": str(date), "dir": 1 if t.direction == "long" else -1, "entry": t.entry, "risk": t.risk_points,
                    "h": after.high.to_numpy(), "l": after.low.to_numpy(), "o": after.open.to_numpy(), "c": after.close.to_numpy(), "hhmm": after.hhmm.to_numpy()})
    return out


def outcome(path: dict, stop_mult: float, rr: float, cost_points: float = 1.0) -> float:
    """Result as a multiple of the amount risked (stake): +rr on target, -1 on stop, fractional at the time exit."""
    d, e = path["dir"], path["entry"]
    sd = stop_mult * path["risk"]
    stop, tgt = e - d * sd, e + d * rr * sd
    h, l, o, c, hh = path["h"], path["l"], path["o"], path["c"], path["hhmm"]
    for j in range(len(h)):
        if j == len(h) - 1 or hh[j] >= hh[-1]:
            return ((o[j] - e) * d - cost_points) / sd
        hit_stop = l[j] <= stop if d > 0 else h[j] >= stop
        hit_tgt = h[j] >= tgt if d > 0 else l[j] <= tgt
        if hit_stop:
            return -1.0 - cost_points / sd
        if hit_tgt:
            return rr - cost_points / sd
    return ((c[-1] - e) * d - cost_points) / sd if len(c) else 0.0


def farm(paths: list[dict], stop_mult: float, rr: float, target_in_dd: float = 1.5, consistency: float = 0.4,
         horizon_days: int = 14) -> dict:
    """Replay an evaluation from every signal day: each trade stakes the whole remaining drawdown room.
    target_in_dd: profit target / drawdown (50k: $3k / $2k = 1.5). EOD trailing drawdown: after a win the floor rises,
    so the room stays at the full drawdown. Pass needs target and best day <= consistency x total."""
    res = np.array([outcome(p, stop_mult, rr) for p in paths])
    dates = pd.to_datetime([p["date"] for p in paths])
    n = len(res)
    passed = failed = 0
    days_to_pass, trades_used = [], []
    within = 0
    for s in range(n - 10):
        bal, best, room = 0.0, 0.0, 1.0
        for k in range(s, n):
            stake = room
            r = res[k] * stake
            bal += r
            best = max(best, r)
            room = 1.0 if bal >= 0 else max(0.0, 1.0 + bal)   # EOD trailing: floor follows the high-water mark up to the start
            if bal <= -1.0 + 1e-9 or room <= 1e-6:
                failed += 1
                break
            if bal >= target_in_dd and best <= consistency * bal + 1e-9:
                passed += 1
                dd = (dates[k] - dates[s]).days
                days_to_pass.append(dd)
                trades_used.append(k - s + 1)
                within += dd <= horizon_days
                break
    tot = passed + failed
    return {"stop_mult": stop_mult, "rr": rr, "single_trade_win_pct": float((res > 0).mean() * 100), "pass_pct": passed / tot * 100,
            "pass_within_14d_pct": within / tot * 100, "median_days": float(np.median(days_to_pass)) if days_to_pass else None,
            "median_trades": float(np.median(trades_used)) if trades_used else None, "evals_per_pass": tot / passed if passed else None}


def points_outcome(path: dict, stop_mult: float, rr: float) -> tuple[float, float]:
    """(points made before costs, stop distance in points) for one signal day."""
    d, e = path["dir"], path["entry"]
    sd = stop_mult * path["risk"]
    stop, tgt = e - d * sd, e + d * rr * sd
    h, l, o, c, hh = path["h"], path["l"], path["o"], path["c"], path["hhmm"]
    for j in range(len(h)):
        if j == len(h) - 1 or hh[j] >= hh[-1]:
            return (o[j] - e) * d, sd
        if (l[j] <= stop) if d > 0 else (h[j] >= stop):
            return -sd, sd
        if (h[j] >= tgt) if d > 0 else (l[j] <= tgt):
            return rr * sd, sd
    return ((c[-1] - e) * d if len(c) else 0.0), sd


def farm_usd(paths: list[dict], stop_mult: float = 2.0, rr: float = 0.75, dd: float = 2000.0, target: float = 3000.0,
             consistency: float = 0.5, cost_pts: float = 1.0, min_room: float = 500.0, horizon_days: int = 14) -> dict:
    """Same rules as the live engine: each trade risks the distance to the end-of-day trailing floor (stop plus costs
    lands on the floor), sized in whole MNQ ($2/pt); an evaluation with under min_room of room is reset (counted as
    blown); pass at the target with the best day under the consistency share."""
    pts = [points_outcome(p, stop_mult, rr) for p in paths]
    dates = pd.to_datetime([p["date"] for p in paths])
    n = len(pts)
    passed = failed = within = 0
    days_to_pass, trades_used, wins = [], [], 0
    for s in range(n - 10):
        bal = peak = best = 0.0
        k = s
        while k < n:
            floor = min(peak - dd, 0.0)
            room = bal - floor
            if room < min_room:
                failed += 1
                break
            made, sd = pts[k]
            per_pt = np.floor(room / (sd + cost_pts) / 2.0) * 2.0
            if per_pt > 0:
                pnl = (made - cost_pts) * per_pt
                bal += pnl
                best = max(best, pnl)
                peak = max(peak, bal)
            if bal <= floor + 1e-9:
                failed += 1
                break
            if bal >= target and best <= consistency * bal + 1e-9:
                passed += 1
                dd_days = (dates[k] - dates[s]).days
                days_to_pass.append(dd_days)
                trades_used.append(k - s + 1)
                within += dd_days <= horizon_days
                break
            k += 1
    tot = passed + failed
    single = np.array([m - cost_pts for m, _ in pts]) > 0
    return {"stop_mult": stop_mult, "rr": rr, "single_trade_win_pct": float(single.mean() * 100), "pass_pct": passed / tot * 100,
            "pass_within_14d_pct": within / tot * 100, "median_days": float(np.median(days_to_pass)) if days_to_pass else None,
            "median_trades": float(np.median(trades_used)) if trades_used else None, "evals_per_pass": tot / passed if passed else None}


def export() -> dict:
    import json
    from pathlib import Path
    vr = Params.from_dict({**Params().to_dict(), **VIDEO_RULE, "exit_time": "15:30"})
    paths = trade_paths(vr)
    grid = [farm_usd(paths, sm, rr) for sm in (1.0, 1.5, 2.0) for rr in (0.5, 0.75, 1.0)]
    sizes = []
    for label, size, dd_usd, tgt_usd, cons, fee, yearly in (("Tradeify Select 50k", 50_000, 2000, 3000, 0.4, 165, 2800), ("Tradeify Select 100k", 100_000, 3000, 6000, 0.4, 265, 5600),
                                                            ("Tradeify Select 150k", 150_000, 4500, 9000, 0.4, 369, 8400), ("Lucid Flex 50k", 50_000, 2000, 3000, 0.5, 100, 2800)):
        r = farm_usd(paths, 2.0, 0.75, dd_usd, tgt_usd, cons)
        cost = r["evals_per_pass"] * fee if r["evals_per_pass"] else None
        sizes.append({**r, "plan": label, "size": size, "fee": fee, "cost_per_funded": cost, "funded_year_payout": yearly, "monthly": yearly / 12})
    out = {"signal_days": len(paths), "grid": grid, "sizes": sizes,
           "source": "How I Made $50,000 in a Week as a Prop Firm Trader (Andy Trades), transcript 05:43: on evals he risks the whole account with a negative R:R target and no breakeven."}
    (Path(__file__).resolve().parent.parent / "experiments" / "evalfarm.json").write_text(json.dumps(out, indent=1, default=float))
    return out


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--export"]:
        o = export()
        print(pd.DataFrame(o["sizes"])[["plan", "pass_pct", "median_days", "evals_per_pass", "cost_per_funded", "monthly"]].round(1).to_string())
        raise SystemExit
    for label, params in (("current defaults", Params()), ("video rule (trades more days)", Params.from_dict({**Params().to_dict(), **VIDEO_RULE, "exit_time": "15:30"}))):
        paths = trade_paths(params)
        print(f"== {label}: {len(paths)} signal days")
        rows = []
        for sm in (0.5, 1.0, 1.5, 2.0):
            for rr in (0.5, 0.75, 1.0):
                rows.append(farm(paths, sm, rr))
        print(pd.DataFrame(rows).round(1).to_string())
