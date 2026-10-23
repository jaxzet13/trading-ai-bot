"""Build playbook/data.js from dashboard/data.json: the subset the Funded Account Playbook needs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
    (ROOT / "playbook").mkdir(exist_ok=True)
    p = ROOT / "playbook" / "data.js"
    p.write_text("window.PLAYBOOK_DATA = " + json.dumps(out, default=str) + ";\n")
    print(f"playbook data written to {p} ({p.stat().st_size / 1e3:.0f} kB)")
    return p


if __name__ == "__main__":
    export_playbook()
