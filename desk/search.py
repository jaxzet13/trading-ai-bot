"""Search day-trading setups per instrument and session. Selection uses in-sample only (before OOS_START);
a candidate is accepted only if it also holds out of sample and in most in-sample years.

    python -m desk.search XAUUSD EURUSD ...      # writes experiments/desk/<instrument>.json and trade lists
"""
from __future__ import annotations

import itertools
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from nyopen.metrics import compute_metrics
from nyopen.optimize import OOS_START, evaluate, year_consistency
from nyopen.strategy import Params, VIDEO_RULE
from propbot.engine import EngineParams, simulate_day

from .features import bars, build_days
from .instruments import INSTRUMENTS
from .strategies import DP, SETUPS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments" / "desk"
ACCEPT = dict(is_pf=1.10, oos_pf=1.10, min_trades=150, consistency=0.6)


def _fmt(h: int) -> str:
    return f"{h // 100:02d}:{h % 100:02d}"


def _add(h: int, minutes: int) -> int:
    m = h // 100 * 60 + h % 100 + minutes
    return m // 60 * 100 + m % 60


def split(t: pd.DataFrame) -> tuple[dict, dict, float]:
    if t.empty:
        return {"trades": 0}, {"trades": 0}, 0.0
    a, b = t[t.date < OOS_START], t[t.date >= OOS_START]
    ma = compute_metrics(a, 10_000) if len(a) else {"trades": 0}
    mb = compute_metrics(b, 10_000) if len(b) else {"trades": 0}
    return ma, mb, year_consistency(a)


def run_setup(name: str, setup: str, session: tuple, dp: DP, max_trades: int = 1) -> pd.DataFrame:
    ins = INSTRUMENTS[name]
    days = build_days(name, session)
    ep = EngineParams(max_trades_per_day=max_trades, daily_loss_cap_r=2.0, cost_points=ins.cost, risk_pct=1.0, min_risk_points=ins.min_risk,
                      session_start=session[0] if setup != "asia_break" else 300, session_end=session[1])
    strat = SETUPS[setup](dp)
    rows, eq = [], 10_000.0
    for date, ctx in days:
        for tr in simulate_day(ctx, strat, ep, eq, date):
            rows.append(tr)
            eq = tr["equity_after"]
    return pd.DataFrame(rows)


def candidates_for(name: str):
    ins = INSTRUMENTS[name]
    for label, s0, s1 in ins.sessions:
        exit_t = _add(s1, -5) if s1 < 1600 else 1555
        win = (_add(s0, 15), _add(s0, 120))
        grid = dict(target_r=[1.0, 1.5, 2.0, 3.0], trend=["slow_ema", "none"], be_at_r=[0.0, 1.0])
        for setup in ("or_break", "vwap_pullback") + (("asia_break",) if label == "london" else ()):
            start = s0 if setup == "asia_break" else win[0]
            for combo in itertools.product(*grid.values()):
                kw = dict(zip(grid, combo))
                yield ("setup", label, setup, (s0, s1), DP(start=start, end=win[1], time_exit=exit_t, **kw))
        # the open-candle rule from the NAS100 study, at this session's open
        for rule, extra in (("open_candle", {}), ("open_candle_video", VIDEO_RULE)):
            yield ("open", label, rule, (s0, s1), {**Params().to_dict(), **extra, "signal_time": _fmt(s0), "exit_time": _fmt(exit_t),
                                                    "cost_points": ins.cost, "min_risk_points": ins.min_risk})


def search(name: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    b = bars(name)
    results = []
    best: dict = {}
    for kind, label, setup, sess, cfg in candidates_for(name):
        if kind == "setup":
            t = run_setup(name, setup, sess, cfg)
            conf = asdict(cfg)
        else:
            r = evaluate(Params.from_dict(cfg), b)
            t = r["trades"]
            conf = {k: cfg[k] for k in ("signal_time", "exit_time", "ema_len", "trail_mode", "trend_filter")}
        if t.empty or len(t) < 50:
            continue
        mi, mo, cons = split(t)
        row = {"instrument": name, "session": label, "setup": setup, "config": conf, "trades": len(t),
               "win_rate_pct": float((t.r_multiple > 0).mean() * 100), "avg_r": float(t.r_multiple.mean()),
               "is_pf": mi.get("profit_factor", 0), "oos_pf": mo.get("profit_factor", 0), "is_avg_r": mi.get("avg_r", 0), "oos_avg_r": mo.get("avg_r", 0),
               "is_trades": mi.get("trades", 0), "oos_trades": mo.get("trades", 0), "consistency": cons}
        results.append(row)
        k = (label, setup)
        if k not in best or row["is_pf"] > best[k][0]["is_pf"]:
            best[k] = (row, t)
    accepted = []
    for (label, setup), (row, t) in best.items():
        ok = (row["is_pf"] >= ACCEPT["is_pf"] and row["oos_pf"] >= ACCEPT["oos_pf"] and row["trades"] >= ACCEPT["min_trades"]
              and row["consistency"] >= ACCEPT["consistency"])
        row["accepted"] = bool(ok)
        if ok:
            sid = f"{name}_{label}_{setup}"
            t[["date", "direction", "entry_time", "exit_time", "r_multiple", "mfe_r", "exit_reason"]].to_csv(OUT / f"{sid}.csv", index=False)
            row["id"] = sid
            accepted.append(row)
    summary = {"instrument": name, "tested": len(results), "best": [v[0] for v in best.values()], "accepted": accepted}
    (OUT / f"{name}.json").write_text(json.dumps(summary, indent=1, default=float))
    print(f"== {name}: {len(results)} configs tested")
    for r in sorted(summary["best"], key=lambda r: -r["is_pf"]):
        print(f"  {r['session']:6s} {r['setup']:18s} n={r['trades']:5d} win {r['win_rate_pct']:4.1f}% IS PF {r['is_pf']:.2f} OOS PF {r['oos_pf']:.2f} yrs {r['consistency']:.2f} {'ACCEPT' if r['accepted'] else ''}", flush=True)
    return summary


if __name__ == "__main__":
    for n in sys.argv[1:] or list(INSTRUMENTS):
        search(n)
