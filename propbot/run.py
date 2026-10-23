"""Evaluate prop-bot candidates: IS/OOS metrics plus challenge pass odds."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict

import pandas as pd

from nyopen.metrics import compute_metrics
from nyopen.optimize import OOS_START, split_metrics, year_consistency
from nyopen.propfirm import RULESETS, simulate

from .engine import EngineParams, simulate_day
from .features import build_days
from .strategies import CANDIDATES, SP


def run(strategy_name: str, sp: SP, ep: EngineParams, days=None) -> dict:
    days = days or build_days()
    strat = CANDIDATES[strategy_name](sp)
    equity = ep.start_equity
    trades = []
    for date, ctx in days:
        for t in simulate_day(ctx, strat, ep, equity, date):
            trades.append(t)
            equity = t["equity_after"]
    tdf = pd.DataFrame(trades)
    res = {"strategy": strategy_name, "sp": asdict(sp), "ep": asdict(ep), "trades": tdf, "metrics": compute_metrics(tdf, ep.start_equity) if len(tdf) else {"trades": 0}}
    if len(tdf):
        res["is"], res["oos"] = split_metrics(res, ep.start_equity)
        res["consistency"] = year_consistency(tdf[tdf.date < OOS_START])
    return res


def brief(res: dict) -> str:
    f = lambda m: (f"n={m.get('trades', 0):4d} win {m.get('win_rate_pct', 0):4.1f}% PF {m.get('profit_factor', 0):.3f} avgR {m.get('avg_r', 0):+.3f} "
                   f"DD {m.get('max_drawdown_pct', 0):4.1f}% streak {m.get('longest_loss_streak', 0):2d} sharpe {m.get('sharpe', 0):.2f}") if m.get("trades") else "no trades"
    return f"FULL {f(res['metrics'])}\n  IS   {f(res.get('is', {}))}\n  OOS  {f(res.get('oos', {}))}  years+ {res.get('consistency', 0):.2f}"


def pass_odds(trades: pd.DataFrame, risk: float = 0.5) -> str:
    rs = RULESETS[0]
    s = simulate(trades, risk, rs)
    g = lambda k: "–" if s.get(k) is None else f"{s[k]:.0f}"
    return f"two-step @ {risk}%: pass {g('pass_rate_pct')}%  blowup {g('fail_rate_pct')}%  median days {g('median_days_to_pass')}  funded12m {g('funded_survival_12m_pct')}%"


def export_alternatives() -> None:
    """Write experiments/alternatives.json: the best in-sample configuration of every candidate plus the
    open-candle rule at other session opens, so the dashboard can show what was tried and why it was rejected."""
    import itertools
    from pathlib import Path
    from nyopen.optimize import evaluate
    from nyopen.strategy import Params

    days = build_days()
    ep = EngineParams()
    out = []
    space = dict(target_r=[1.0, 1.5, 2.0, 3.0], trend=["slow_ema", "both", "none"], end=[1130, 1430], be_at_r=[0.0, 1.0])
    descr = {"orb": "15-minute opening-range breakout, stop at the range midpoint, fixed R target",
             "vwap_pullback": "trend pullback to session VWAP, bullish/bearish close, fixed R target",
             "ema_pullback": "trend pullback to the 20 EMA, fixed R target",
             "or_fade": "fade a stretch beyond the opening range once price closes back inside",
             "prev_day_break": "break of the previous session high/low in the trend direction"}
    for name in CANDIDATES:
        best = None
        for combo in itertools.product(*space.values()):
            kw = dict(zip(space.keys(), combo))
            if name == "or_fade" and kw["trend"] != "none":
                continue
            r = run(name, SP(**kw), ep, days)
            if r["metrics"].get("trades", 0) < 200:
                continue
            if best is None or r["is"]["profit_factor"] > best["is"]["profit_factor"]:
                best = r
                best["kw"] = kw
        if best:
            out.append({"family": "intraday candidates", "name": name, "description": descr[name], "config": best["kw"],
                        "trades": best["metrics"]["trades"], "win_rate_pct": best["metrics"]["win_rate_pct"], "profit_factor": best["metrics"]["profit_factor"],
                        "is_pf": best["is"]["profit_factor"], "oos_pf": best["oos"]["profit_factor"], "max_drawdown_pct": best["metrics"]["max_drawdown_pct"],
                        "verdict": "no edge after costs" if best["is"]["profit_factor"] < 1.08 or best["oos"]["profit_factor"] < 1.08 else "candidate"})
    base = Params().to_dict()
    for name, kw in {"London open 03:00": dict(signal_time="03:00", exit_time="09:25"), "Frankfurt open 02:00": dict(signal_time="02:00", exit_time="08:25"),
                     "US data 08:30": dict(signal_time="08:30", exit_time="09:25"), "10:00 candle": dict(signal_time="10:00", exit_time="15:30")}.items():
        r = evaluate(Params.from_dict({**base, **kw}))
        out.append({"family": "open-candle rule at other opens", "name": name, "description": f"same rule and exits as the NY open strategy, signal candle at {kw['signal_time']}", "config": kw,
                    "trades": r["metrics"]["trades"], "win_rate_pct": r["metrics"]["win_rate_pct"], "profit_factor": r["metrics"]["profit_factor"],
                    "is_pf": r["is"]["profit_factor"], "oos_pf": r["oos"]["profit_factor"], "max_drawdown_pct": r["metrics"]["max_drawdown_pct"],
                    "verdict": "no edge" if r["is"]["profit_factor"] < 1.08 or r["oos"]["profit_factor"] < 1.08 else "candidate"})
    p = Path(__file__).resolve().parent.parent / "experiments" / "alternatives.json"
    p.write_text(json.dumps(out, indent=1, default=float))
    print(pd.DataFrame(out)[["family", "name", "trades", "win_rate_pct", "profit_factor", "is_pf", "oos_pf", "verdict"]].round(3).to_string())


if __name__ == "__main__":
    if sys.argv[1:] == ["--export"]:
        export_alternatives()
        sys.exit(0)
    days = build_days()
    ep = EngineParams()
    which = sys.argv[1:] or list(CANDIDATES)
    for name in which:
        res = run(name, SP(), ep, days)
        print(f"== {name}\n  {brief(res)}")
        if res["metrics"].get("trades", 0) > 100:
            print("  " + pass_odds(res["trades"]))

