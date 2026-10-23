"""Staged improvement search: the loop an agent runs to make the strategy better without fooling itself.

Each stage varies one group of levers, scores every candidate in-sample only, and keeps the best one
if it beats the incumbent in-sample AND does not collapse out of sample (a guard against promoting
something that only worked before 2024). Every candidate is logged to experiments.jsonl, and the
stage-by-stage path is saved to experiments/improve_<name>.json for the dashboard.

    python -m nyopen.run improve --name v3
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .backtest import get_bars, log_experiment
from .optimize import evaluate, KEEP
from .strategy import Params

ROOT = Path(__file__).resolve().parent.parent

STAGES: list[tuple[str, list[dict]]] = [
    ("signal candle", [dict(signal_time="09:30"), dict(signal_time="09:35"), dict(signal_time="09:40")]),
    ("direction bias", [dict(trend_filter="none"), dict(trend_filter="slow_ema", slow_ema_len=30), dict(trend_filter="slow_ema", slow_ema_len=50),
                        dict(trend_filter="slow_ema", slow_ema_len=100), dict(trend_filter="slow_ema", slow_ema_len=200), dict(trend_filter="prev_day")]),
    ("trailing stop", [dict(trail_mode="ema"), dict(trail_mode="atr", atr_mult=1.5), dict(trail_mode="atr", atr_mult=2.0), dict(trail_mode="atr", atr_mult=3.0),
                       dict(trail_mode="chandelier", atr_mult=2.0), dict(trail_mode="chandelier", atr_mult=3.0), dict(trail_mode="swing", swing_len=2), dict(trail_mode="swing", swing_len=3)]),
    ("signal EMA", [dict(ema_len=v) for v in (8, 10, 12, 16, 20)]),
    ("time exit", [dict(exit_time=v) for v in ("11:00", "12:00", "13:00", "14:00", "15:55")]),
    ("trail timing", [dict(trail_after_r=a, breakeven_at_r=b) for a in (0.0, 0.5, 1.0) for b in (0.0, 1.0, 1.5)]),
    ("signal quality", [dict(min_body_r=v) for v in (0.0, 0.1, 0.25, 0.5)]),
    ("candle size", [dict(min_risk_atr=a, max_risk_atr=b) for a in (0.0, 0.5, 0.75) for b in (0.0, 2.0, 3.0)]),
    ("weekday", [dict(skip_weekdays="")] + [dict(skip_weekdays=d) for d in ("Mon", "Tue", "Wed", "Thu", "Fri")]),
    ("side", [dict(allow_long=True, allow_short=True), dict(allow_long=True, allow_short=False), dict(allow_long=False, allow_short=True)]),
    # second pass over the levers that matter most, with finer grids around the incumbent
    ("trend length", [dict(slow_ema_len=v) for v in (100, 150, 200, 300, 400)]),
    ("trail width", [dict(atr_mult=v) for v in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0)]),
    ("profit taking", [dict(tp_r=0.0, partial_tp_r=0.0), dict(tp_r=3.0), dict(tp_r=5.0), dict(tp_r=8.0), dict(partial_tp_r=2.0, partial_frac=0.3), dict(partial_tp_r=3.0, partial_frac=0.5)]),
    ("signal quality 2", [dict(min_body_r=v) for v in (0.05, 0.1, 0.15, 0.2, 0.3)]),
    ("time exit 2", [dict(exit_time=v) for v in ("13:00", "14:00", "15:00", "15:30", "15:55")]),
]


def summarize(res: dict) -> dict:
    return {"is": {k: res["is"].get(k) for k in KEEP}, "oos": {k: res["oos"].get(k) for k in KEEP},
            "full": {k: res["metrics"].get(k) for k in KEEP}, "is_score": res["is_score"], "oos_score": res["oos_score"], "consistency": res["consistency"]}


def improve(name: str, start: Params | None = None, oos_guard: float = 1.0) -> tuple[Params, dict]:
    bars = get_bars((start or Params()).bar_minutes)
    current = start or Params()
    best = evaluate(current, bars)
    path = [{"stage": "start", "change": "defaults", "params": current.to_dict(), **summarize(best)}]
    log_experiment(f"{name}:start", best, extra={"is": best["is"], "oos": best["oos"], "is_score": best["is_score"], "oos_score": best["oos_score"], "consistency": best["consistency"], "improve": name})
    print(f"start  IS score {best['is_score']:.3f}  OOS PF {best['oos'].get('profit_factor', 0):.3f}", flush=True)

    for stage, candidates in STAGES:
        stage_best, stage_res, stage_change = None, None, None
        for kw in candidates:
            p = Params.from_dict({**current.to_dict(), **kw})
            if p.to_dict() == current.to_dict():
                res = best
            else:
                res = evaluate(p, bars)
                log_experiment(f"{name}:{stage}:" + ",".join(f"{k}={v}" for k, v in kw.items()), res,
                               extra={"is": res["is"], "oos": res["oos"], "is_score": res["is_score"], "oos_score": res["oos_score"], "consistency": res["consistency"], "improve": name, "stage": stage})
            print(f"  [{stage}] {kw} -> IS {res['is_score']:.3f} (PF {res['is'].get('profit_factor', 0):.3f}, n={res['is'].get('trades', 0)})  OOS PF {res['oos'].get('profit_factor', 0):.3f}", flush=True)
            if stage_res is None or res["is_score"] > stage_res["is_score"]:
                stage_best, stage_res, stage_change = p, res, kw
        improved = stage_res["is_score"] > best["is_score"] + 1e-9
        # OOS guard: refuse a change whose out-of-sample profit factor falls below `oos_guard` x the incumbent's.
        # Selection is still in-sample only; the guard just stops a change that only worked before 2024 from being promoted.
        guard_ok = stage_res["oos"].get("profit_factor", 0) >= oos_guard * best["oos"].get("profit_factor", 0)
        accepted = improved and guard_ok and stage_best.to_dict() != current.to_dict()
        if accepted:
            current, best = stage_best, stage_res
        path.append({"stage": stage, "change": ", ".join(f"{k}={v}" for k, v in stage_change.items()), "accepted": accepted, "params": current.to_dict(), **summarize(best)})
        print(f"stage '{stage}': best {stage_change} accepted={accepted}  IS {best['is_score']:.3f}  OOS PF {best['oos'].get('profit_factor', 0):.3f}", flush=True)

    out = {"name": name, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "final_params": current.to_dict(), "path": path}
    (ROOT / "experiments").mkdir(exist_ok=True)
    (ROOT / "experiments" / f"improve_{name}.json").write_text(json.dumps(out, indent=1, default=float))
    print("final params:", json.dumps(current.to_dict()))
    return current, out
