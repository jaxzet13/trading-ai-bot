"""End-to-end simulation of the eval-farming plan with real money flows.

Day by day over the historical calendar:
  * cash buys a Lucid Flex 50k evaluation ($100) whenever there is no evaluation running, cash allows, and fewer than
    MAX_FUNDED accounts are funded;
  * the evaluation trades the all-in method on the New York open signal (stop 2x candle, target 0.75x stop, whole
    $2,000 drawdown at risk, 50% consistency, $3,000 target);
  * a passed evaluation becomes a funded account trading the tuned NY open rule at 0.25% of $50k ($125 per R), with an
    end-of-day trailing $2,000 drawdown that locks at start + $100;
  * every 20 trading days a funded account pays out min(profit - $1,100 cushion, $1,000) if that is at least $500,
    at a 90% split, into cash;
  * a funded account that hits its floor is gone.
Started from every 5th trading day in the history, run for 252 trading days (one year).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from nyopen.backtest import backtest
from nyopen.strategy import Params, VIDEO_RULE
from .evalfarm import outcome, trade_paths

ROOT = Path(__file__).resolve().parent.parent
FEE, DD, TARGET, CONS, FUNDED_R_USD, MAX_FUNDED = 100.0, 2000.0, 3000.0, 0.5, 125.0, 5
PAYOUT_EVERY, CUSHION, CAP, MIN_PAY, SPLIT = 20, 1100.0, 1000.0, 500.0, 0.9


def calendars():
    vr = Params.from_dict({**Params().to_dict(), **VIDEO_RULE, "exit_time": "15:30"})
    paths = trade_paths(vr)
    ev = {p["date"]: outcome(p, 2.0, 0.75) for p in paths}
    t = backtest(Params())["trades"]
    fr = t.groupby("date").r_multiple.sum().to_dict()
    days = sorted(set(ev) | set(fr) | {str(d.date()) for d in pd.bdate_range(min(ev), max(ev))})
    return days, ev, fr


def run(days, ev, fr, start: int, bankroll: float, horizon: int = 252) -> dict:
    cash, fees, payouts = bankroll, 0.0, 0.0
    evals_bought = evals_passed = 0
    active = None            # running evaluation: dict(bal, best)
    funded = []              # dict(bal, peak, age)
    funded_ever = 0
    for k in range(start, min(start + horizon, len(days))):
        d = days[k]
        if active is None and cash >= FEE and len(funded) < MAX_FUNDED:
            cash -= FEE; fees += FEE; evals_bought += 1
            active = {"bal": 0.0, "best": 0.0}
        if active is not None and d in ev:
            room = DD if active["bal"] >= 0 else DD + active["bal"]
            pnl = ev[d] * room
            active["bal"] += pnl
            active["best"] = max(active["best"], pnl)
            if active["bal"] <= -DD + 1e-6:
                active = None
            elif active["bal"] >= TARGET and active["best"] <= CONS * active["bal"]:
                evals_passed += 1; funded_ever += 1
                funded.append({"bal": 0.0, "peak": 0.0, "age": 0})
                active = None
        alive = []
        for f in funded:
            f["bal"] += fr.get(d, 0.0) * FUNDED_R_USD
            f["peak"] = max(f["peak"], f["bal"])
            floor = min(f["peak"] - DD, 100.0)
            f["age"] += 1
            if f["bal"] <= floor:
                continue
            if f["age"] % PAYOUT_EVERY == 0:
                amt = min(f["bal"] - CUSHION, CAP)
                if amt >= MIN_PAY:
                    f["bal"] -= amt; f["peak"] = max(f["peak"] - amt, f["bal"])
                    cash += amt * SPLIT; payouts += amt * SPLIT
            alive.append(f)
        funded = alive
    return {"start": days[start], "net": cash - bankroll, "cash_end": cash, "fees": fees, "payouts": payouts,
            "evals_bought": evals_bought, "evals_passed": evals_passed, "funded_ever": funded_ever, "funded_end": len(funded)}


def study(bankroll: float = 300.0, horizon: int = 252) -> dict:
    days, ev, fr = calendars()
    runs = [run(days, ev, fr, s, bankroll, horizon) for s in range(0, len(days) - horizon, 5)]
    df = pd.DataFrame(runs)
    q = lambda p: float(df.net.quantile(p))
    return {"bankroll": bankroll, "horizon_days": horizon, "runs": len(df),
            "share_ahead_pct": float((df.net > 0).mean() * 100), "share_lost_all_pct": float((df.payouts == 0).mean() * 100),
            "median_net": q(.5), "p10_net": q(.1), "p25_net": q(.25), "p75_net": q(.75), "p90_net": q(.9), "mean_net": float(df.net.mean()),
            "avg_evals_bought": float(df.evals_bought.mean()), "avg_funded": float(df.funded_ever.mean()), "avg_fees": float(df.fees.mean()),
            "avg_payouts": float(df.payouts.mean()), "hist": np.histogram(df.net.clip(-bankroll, 30000), bins=24)[0].tolist(),
            "hist_edges": np.histogram(df.net.clip(-bankroll, 30000), bins=24)[1].round(0).tolist(),
            "by_year": df.assign(y=df.start.str[:4]).groupby("y").net.median().round(0).to_dict()}


if __name__ == "__main__":
    out = {}
    for b in (100.0, 300.0, 500.0):
        s = study(b)
        out[str(int(b))] = s
        print(f"start ${b:.0f}: ahead after 1 year {s['share_ahead_pct']:.0f}% | lost the whole bankroll {s['share_lost_all_pct']:.0f}% | median net ${s['median_net']:,.0f} | bad case (10th) ${s['p10_net']:,.0f} | good case (90th) ${s['p90_net']:,.0f} | avg evals {s['avg_evals_bought']:.1f}, funded {s['avg_funded']:.1f}, payouts ${s['avg_payouts']:,.0f}")
        print("   median by start year:", s["by_year"])
    (ROOT / "experiments" / "campaign.json").write_text(json.dumps(out, indent=1))
