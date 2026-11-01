"""Summarise the live paper-trading log and inject it into the dashboard.

    python -m kalshi15m live-report      # rewrites dashboard/index.html with the latest live numbers
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .backtest import MAKER_RATE, TAKER_RATE, kalshi_fee
from .bot import LOG, STATUS
from .report import OUT, ROOT

CONFIG = ROOT / "live.json"
NAMES = {"reversal_z": "Reversal after big move", "fair_value": "Fair value model"}


def _backtest(results: dict, series: str, strategy: str, execution: str):
    scope = (results.get("scopes") or {}).get(series.replace("KX", "").replace("15M", "") + " only")
    if not scope:
        return None
    run = scope["strategies"].get(strategy, {}).get("runs", {}).get(execution)
    if not run:
        return None
    return {"oos": run["oos"], "curve": run["curve"], "fold_win": run["fold_win"],
            "folds": len(run["folds"]), "diag": run.get("diag", {})}


def settle_open(events: list) -> list:
    """Settle paper fills the bot never got to settle (e.g. it stopped mid-market), using
    Kalshi's real result. Appends the settle events to the log so it only happens once."""
    import requests
    settled = {e["ticker"] for e in events if e["event"] == "settle"}
    new = []
    for e in events:
        if e["event"] not in ("fill", "buy") or e["ticker"] in settled:
            continue
        try:
            m = requests.get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{e['ticker']}",
                             timeout=15).json()["market"]
        except Exception:
            continue
        res = m.get("result")
        if res not in ("yes", "no"):
            continue
        rate = MAKER_RATE if e["event"] == "fill" else TAKER_RATE
        fee = kalshi_fee(e["price"], e["n"], rate=rate)
        pnl = e["n"] * ((res == e["side"]) - e["price"]) - fee
        new.append({"event": "settle", "ticker": e["ticker"], "result": res, "pnl": round(pnl, 4),
                    "side": e["side"], "price": e["price"], "series": e["series"], "strategy": e["strategy"],
                    "execution": e.get("execution"), "params": e.get("params"), "settled_by": "report",
                    "ts": int(datetime_close(m))})
        settled.add(e["ticker"])
    if new:
        with LOG.open("a") as f:
            for x in new:
                f.write(json.dumps(x) + "\n")
    return events + new


def datetime_close(m):
    from datetime import datetime
    return datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp()


def summarise() -> dict:
    cfg = json.loads(CONFIG.read_text())
    events = []
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    events = settle_open(events)
    events.sort(key=lambda x: x.get("ts", 0))
    try:
        status = json.loads(STATUS.read_text())
    except Exception:
        status = {}
    try:
        results = json.loads((OUT / "results.json").read_text())
    except Exception:
        results = {}
    now = int(time.time())
    out = {"generated": now, "stake": cfg.get("stake"), "strategies": []}
    for e in cfg["strategies"]:
        s = e["series"]
        ev = [x for x in events if x.get("series") == s]
        starts = [x["ts"] for x in ev if x["event"] == "start"]
        fills = [x for x in ev if x["event"] in ("fill", "buy")]
        settles = [x for x in ev if x["event"] == "settle"]
        settled = {x["ticker"] for x in settles}
        pnl_curve, cum = [], 0.0
        for x in settles:
            cum += x["pnl"]
            pnl_curve.append([x["ts"], round(cum, 2)])
        st = status.get(s)
        out["strategies"].append({
            "series": s, "strategy": e["strategy"], "name": NAMES.get(e["strategy"], e["strategy"]),
            "execution": e["execution"], "params": e["params"], "why": e.get("why", ""),
            "since": min(starts) if starts else None,
            "orders": sum(x["event"] == "rest" for x in ev) + sum(x["event"] == "buy" for x in ev),
            "fills": len(fills), "expired": sum(x["event"] == "expired" for x in ev),
            "settled": len(settles), "wins": sum(x["pnl"] > 0 for x in settles),
            "pnl": round(sum(x["pnl"] for x in settles), 2), "curve": pnl_curve,
            "open": [x["ticker"] for x in fills if x["ticker"] not in settled],
            "status": st, "stale": (not st) or now - st.get("ts", 0) > 180,
            "backtest": _backtest(results, s, e["strategy"], e["execution"]),
        })
    out["events"] = [x for x in events if x["event"] != "start"][-40:]
    return out


def build():
    live = summarise()
    html = (ROOT / "dashboard_template.html").read_text()
    results = (OUT / "results.json").read_text()
    html = html.replace("/*__RESULTS__*/null", results).replace("/*__LIVE__*/null", json.dumps(live))
    (OUT / "index.html").write_text(html)
    (OUT / "live.json").write_text(json.dumps(live))
    for s in live["strategies"]:
        print(f"{s['series']} {s['strategy']}: {s['orders']} orders, {s['fills']} fills, {s['settled']} settled, "
              f"P&L ${s['pnl']}")
    return live
