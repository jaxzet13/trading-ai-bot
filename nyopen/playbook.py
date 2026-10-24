"""Build playbook/data.js from dashboard/data.json: the subset the Funded Account Playbook needs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


COMPETITIONS = [
    {"firm": "FundedNext", "cadence": "monthly", "prize": "Cash for the top 3, funded/challenge accounts deep into the leaderboard (top ~600)", "cost": "free, no card"},
    {"firm": "Alpha Capital Group", "cadence": "monthly", "prize": "Evaluation accounts down to about 70th place", "cost": "free, one entry per person"},
    {"firm": "FundingPips", "cadence": "monthly", "prize": "Funded accounts or cash", "cost": "free"},
    {"firm": "Blue Guardian", "cadence": "monthly", "prize": "Instant funded accounts or cash", "cost": "free"},
    {"firm": "The5ers", "cadence": "weekly", "prize": "100 winners a week", "cost": "free"},
    {"firm": "Pipster", "cadence": "seasonal (e.g. 25-30 Oct)", "prize": "$100k account for first", "cost": "free, no card"},
]


def fast_route(trades) -> dict:
    from fastfund.promos import promo_plan
    from fastfund.tickets import sequential, staggered
    seq = [sequential(trades, "Lucid Pro 50k (fast)", 2.0, k) for k in (1, 2, 3, 4, 6, 8)]
    stag = [staggered(trades, "Lucid Pro 50k (fast)", 2.0, k, 1, 14) for k in (1, 2, 3, 4, 6, 8)]
    return {"promos": promo_plan(100.0), "sequential": seq, "staggered": stag, "competitions": COMPETITIONS}


def export_playbook() -> Path:
    d = json.loads((ROOT / "dashboard" / "data.json").read_text())
    pf = d["prop_firm"]
    keep_rows = [r for r in pf["rows"] if r["risk_pct"] in (0.25, 0.5, 0.75, 1.0, 1.5)]
    out = {
        "generated_at": d["generated_at"], "data_range": d["data_range"], "params": d["params"], "metrics": d["metrics"], "oos": d.get("oos"),
        "best_trade": d["best_trade"], "latest_trade": d["latest_trade"], "yearly": d["yearly"],
        "rulesets": pf["rulesets"], "rows": keep_rows, "ranking": pf["ranking"], "fast_track": pf.get("fast_track", []),
        "alternatives": d.get("alternatives", []),
    }
    from .backtest import backtest
    from .strategy import Params
    out["fast_route"] = fast_route(backtest(Params())["trades"])
    fw = ROOT / "experiments" / "forward.json"
    if fw.exists():
        out["forward"] = json.loads(fw.read_text())
    dp = ROOT / "experiments" / "desk" / "portfolio.json"
    if dp.exists():
        desk = json.loads(dp.read_text())
        tested = []
        for f in sorted((ROOT / "experiments" / "desk").glob("*.json")):
            if f.name != "portfolio.json":
                j = json.loads(f.read_text())
                tested.append({"instrument": j["instrument"], "tested": j["tested"], "best": j["best"]})
        desk["tested"] = tested
        out["desk"] = desk
    (ROOT / "playbook").mkdir(exist_ok=True)
    p = ROOT / "playbook" / "data.js"
    p.write_text("window.PLAYBOOK_DATA = " + json.dumps(out, default=str) + ";\n")
    print(f"playbook data written to {p} ({p.stat().st_size / 1e3:.0f} kB)")
    return p


if __name__ == "__main__":
    export_playbook()
