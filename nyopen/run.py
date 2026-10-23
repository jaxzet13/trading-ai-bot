"""Command line entry point.

  python -m nyopen.run download                      # fetch / refresh NAS100 1-minute history
  python -m nyopen.run backtest [--name N] [--set k=v ...]   # run one backtest, log it, export dashboard data
  python -m nyopen.run sweep                         # run the default parameter sweep (logged)
  python -m nyopen.run improve --name v3            # staged search, IS selection with an OOS guard
  python -m nyopen.run export                        # rebuild dashboard/data.js from the latest best run
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from . import data as data_mod
from .backtest import backtest, log_experiment
from .export import export_dashboard
from .optimize import sweep
from .improve import improve
from .strategy import Params


def parse_set(items: list[str]) -> dict:
    out = {}
    for it in items or []:
        k, v = it.split("=", 1)
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            pass
        out[k] = v
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download"); d.add_argument("--start", default="2019-01-01"); d.add_argument("--end", default=str(date.today() - timedelta(days=1)))
    b = sub.add_parser("backtest"); b.add_argument("--name", default="manual"); b.add_argument("--note", default=""); b.add_argument("--set", nargs="*"); b.add_argument("--no-export", action="store_true")
    s = sub.add_parser("sweep"); s.add_argument("--name", default="sweep")
    i = sub.add_parser("improve"); i.add_argument("--name", default="improve"); i.add_argument("--from-video-rule", action="store_true")
    sub.add_parser("export")
    a = ap.parse_args()

    if a.cmd == "download":
        data_mod.download(date.fromisoformat(a.start), date.fromisoformat(a.end))
        data_mod.build_m1()
    elif a.cmd == "backtest":
        p = Params.from_dict({**Params().to_dict(), **parse_set(a.set)})
        res = backtest(p)
        rec = log_experiment(a.name, res, a.note)
        m = res["metrics"]
        print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}, indent=2))
        if not a.no_export:
            export_dashboard(res, rec["id"])
    elif a.cmd == "sweep":
        space = {"ema_len": [8, 12, 20], "trail_mode": ["ema", "atr", "chandelier"], "exit_time": ["12:00", "15:55"]}
        df = sweep(Params(), space, name=a.name)
        print(df.sort_values("oos_score", ascending=False).to_string())
    elif a.cmd == "improve":
        from .strategy import VIDEO_RULE
        start = Params.from_dict({**Params().to_dict(), **VIDEO_RULE, "min_risk_points": 5.0}) if a.from_video_rule else None
        improve(a.name, start)
    elif a.cmd == "export":
        res = backtest(Params())
        export_dashboard(res, "latest")


if __name__ == "__main__":
    main()
