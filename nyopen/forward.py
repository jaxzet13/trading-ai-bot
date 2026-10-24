"""Forward test: what the strategy should have done on each live day since FORWARD_START.

Run after the New York close:  python -m nyopen.forward
It extends the NAS100 cache to yesterday (UTC), rebuilds the 1-minute file, replays the current defaults, and writes
experiments/forward.json with every trade from FORWARD_START, the running total in R and in dollars at
0.75% of a $100k account, and the range a normal 10-day stretch falls in. Compare each row with the robot's log.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import data as data_mod
from .backtest import _BARS_CACHE, backtest
from .strategy import Params

ROOT = Path(__file__).resolve().parent.parent
FORWARD_START = "2026-10-26"
OUT = ROOT / "experiments" / "forward.json"


def run() -> dict:
    today_utc = datetime.now(timezone.utc).date()
    data_mod.download(date(2026, 10, 1), today_utc - timedelta(days=1), verbose=False)
    data_mod.build_m1(verbose=False)
    _BARS_CACHE.clear()
    p = Params()
    t = backtest(p)["trades"]
    last_data = str(data_mod.load_m1().time.max())
    f = t[t.date >= FORWARD_START].copy()
    rows = []
    cum = 0.0
    for r in f.itertuples():
        cum += r.r_multiple
        rows.append({"date": r.date, "direction": r.direction, "signal": r.entry_time[11:16], "entry": round(r.entry, 1), "stop": round(r.stop, 1),
                     "exit": round(r.exit, 1), "exit_time": r.exit_time, "exit_reason": r.exit_reason, "r": round(r.r_multiple, 2),
                     "usd_100k": round(r.r_multiple * 750, 0), "cum_r": round(cum, 2)})
    sessions = pd.bdate_range(FORWARD_START, last_data[:10])
    no_trade = [str(d.date()) for d in sessions if str(d.date()) not in set(f.date)]
    out = {"forward_start": FORWARD_START, "data_through": last_data, "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "params": p.to_dict(), "trades": rows, "no_trade_days": no_trade, "sessions": len(sessions),
           "total_r": round(cum, 2), "total_usd_100k": round(cum * 750, 0),
           "normal_10_day": {"median_r": 0.4, "p10_r": -4.1, "p90_r": 7.8, "share_positive_pct": 53, "trades_median": 6}}
    OUT.write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    o = run()
    print(f"data through {o['data_through']}; {o['sessions']} sessions since {o['forward_start']}; {len(o['trades'])} trades; total {o['total_r']:+.2f}R (${o['total_usd_100k']:+,.0f} at 0.75% of 100k)")
    for r in o["trades"]:
        print(f"  {r['date']} {r['direction']:5s} entry {r['entry']} stop {r['stop']} -> {r['exit']} at {r['exit_time']} ({r['exit_reason']}) {r['r']:+.2f}R")
    print("  no-trade days:", ", ".join(o["no_trade_days"]) or "none")
