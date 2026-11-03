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
_LAB = None


def _lab_holdout(series, strategy, execution):
    """Holdout result for this exact strategy from the strategy lab, if it was tested there."""
    global _LAB
    if _LAB is None:
        f = OUT.parent / "data" / "lab" / "results.json"
        _LAB = json.loads(f.read_text()) if f.exists() else {}
    for x in (_LAB.get("finals") or []) + (_LAB.get("benchmarks") or []):
        if x["scope"] == series and x["strategy"] == strategy and x["execution"] == execution:
            h = dict(x["holdout"])
            h["curve"] = x.get("curve") or []
            n = (_LAB.get("coins") or {}).get(series, {}).get("holdout_markets")
            if n:
                h["per_market"] = round(h["trades"] / n, 3)
            return h
    return None


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
    sid = lambda e: e.get("sid", e.get("series"))
    settled = {(sid(e), e["ticker"]) for e in events if e["event"] == "settle"}
    exited = {(sid(e), e["ticker"]) for e in events if e["event"] == "exit"}
    new = []
    for e in events:
        if e["event"] not in ("fill", "buy") or (sid(e), e["ticker"]) in settled or (sid(e), e["ticker"]) in exited:
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
                    "side": e["side"], "price": e["price"], "series": e["series"], "sid": sid(e), "strategy": e["strategy"],
                    "execution": e.get("execution"), "params": e.get("params"), "settled_by": "report",
                    "ts": int(datetime_close(m))})
        settled.add((sid(e), e["ticker"]))
    if new:
        with LOG.open("a") as f:
            for x in new:
                f.write(json.dumps(x) + "\n")
    return events + new


def datetime_close(m):
    from datetime import datetime
    return datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp()


_MCACHE = LOG.parent / "market_cache.json"


def enrich(events: list) -> list:
    """Attach each traded market's target price, closing time and final price (from Kalshi),
    so the dashboard can say in words what each bet was on."""
    import requests
    from datetime import datetime
    try:
        cache = json.loads(_MCACHE.read_text())
    except Exception:
        cache = {}
    tickers = {e["ticker"] for e in events if e.get("event") in ("rest", "buy", "fill", "settle", "expired")}
    changed = False
    for tk in tickers:
        c = cache.get(tk)
        if c and c.get("final") is not None:
            continue
        try:
            m = requests.get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{tk}", timeout=15).json()["market"]
        except Exception:
            continue
        fin = m.get("expiration_value")
        cache[tk] = {"strike": float(str(m.get("floor_strike")).replace(",", "")) if m.get("floor_strike") is not None else None,
                     "close_ts": int(datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp()),
                     "final": float(str(fin).replace(",", "")) if fin not in (None, "") else None,
                     "result": m.get("result") or None}
        changed = True
    if changed:
        _MCACHE.write_text(json.dumps(cache))
    for e in events:
        c = cache.get(e.get("ticker"))
        if c:
            e.setdefault("strike", c["strike"])
            e.setdefault("close_ts", c["close_ts"])
            if e.get("event") == "settle":
                e["final"] = c["final"]
    return events


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

    events = enrich(events)
    # P&L comes from each fill and Kalshi's final result (one settlement per fill), not from
    # the bot's own settle messages, which can be duplicated or missing after a restart
    try:
        cache = json.loads(_MCACHE.read_text())
    except Exception:
        cache = {}
    real = [x for x in events if x.get("event") != "settle"]
    synth = []
    # positions sold before the close (lab3 exit rule) settle at the exit, not at Kalshi's result
    exits = {(x.get("sid", x.get("series")), x["ticker"]): x for x in real if x.get("event") == "exit"}
    for x in real:
        if x.get("event") not in ("buy", "fill"):
            continue
        ex = exits.get((x.get("sid", x.get("series")), x["ticker"]))
        if ex:
            synth.append({"event": "settle", "ticker": x["ticker"], "series": x["series"],
                          "sid": x.get("sid", x["series"]), "side": x["side"], "price": x["price"], "n": x["n"],
                          "result": "sold", "exit_price": ex["exit_price"], "pnl": round(ex["pnl"], 4),
                          "ts": ex["ts"], "fill_ts": x["ts"]})
            continue
        c = cache.get(x["ticker"]) or {}
        res = c.get("result")
        if res not in ("yes", "no"):
            continue
        rate = TAKER_RATE if x["event"] == "buy" else MAKER_RATE
        pnl = x["n"] * ((res == x["side"]) - x["price"]) - kalshi_fee(x["price"], x["n"], rate=rate)
        synth.append({"event": "settle", "ticker": x["ticker"], "series": x["series"],
                      "sid": x.get("sid", x["series"]), "side": x["side"],
                      "price": x["price"], "n": x["n"], "result": res, "pnl": round(pnl, 4),
                      "strike": c.get("strike"), "final": c.get("final"), "close_ts": c.get("close_ts"),
                      "ts": c.get("close_ts") or x["ts"], "fill_ts": x["ts"]})
    events = sorted(real + synth, key=lambda x: x.get("ts", 0))
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
        pooled = isinstance(s, list)  # one rule run on several coins, reported as one strategy
        sid = e.get("id", "ALL" if pooled else s)
        members = {f"{sid}|{c}" for c in s} if pooled else {sid}
        if pooled:
            s = "ALL"
        ev = [x for x in events if x.get("sid", x.get("series")) in members]
        starts = [x["ts"] for x in ev if x["event"] == "start"]
        fills = [x for x in ev if x["event"] in ("fill", "buy")]
        settles = [x for x in ev if x["event"] == "settle"]
        settled = {x["ticker"] for x in settles}
        settled_fills = {x.get("fill_ts") for x in settles}
        pnl_curve, cum = [], 0.0
        for x in settles:
            cum += x["pnl"]
            pnl_curve.append([x["ts"], round(cum, 2)])
        sts = [status[m] for m in members if m in status]
        st = max(sts, key=lambda x: x.get("ts", 0)) if sts else None
        out["strategies"].append({
            "id": sid, "label": e.get("label"), "series": s, "strategy": e["strategy"], "name": NAMES.get(e["strategy"], e["strategy"]),
            "execution": e["execution"], "params": e["params"], "why": e.get("why", ""),
            "since": min(starts) if starts else None,
            "orders": sum(x["event"] == "rest" for x in ev) + sum(x["event"] == "buy" for x in ev),
            "fills": len(fills), "expired": sum(x["event"] == "expired" for x in ev),
            "settled": len(settles), "wins": sum(x["pnl"] > 0 for x in settles),
            # display only: how many positions were sold before the close, and what they made
            "sold": sum(x.get("result") == "sold" for x in settles),
            "sold_pnl": round(sum(x["pnl"] for x in settles if x.get("result") == "sold"), 2),
            "pnl": round(sum(x["pnl"] for x in settles), 2), "curve": pnl_curve,
            "open": [x["ticker"] for x in fills if x["ts"] not in settled_fills],
            "holding": [{k: x.get(k) for k in ("ticker", "series", "side", "n", "price", "strike", "close_ts", "model", "spot")}
                        for x in fills if x["ts"] not in settled_fills],
            "status": st, "stale": (not st) or now - st.get("ts", 0) > 180,
            "backtest": _backtest(results, s, e["strategy"], e["execution"]),
            "lab": _lab_holdout(e.get("lab_scope", s), e["strategy"], e["execution"]),
            "lags": [x.get("lag_s") for x in ev if x["event"] == "buy" and x.get("lag_s") is not None],
            "watched": sum(x["event"] == "watched" for x in ev),
            "near": sorted(([x["ticker"], x["max_gap"]] for x in ev if x["event"] == "watched"), key=lambda t: t[0])[-12:],
        })
    # the page's live log: skip bookkeeping events ("watched" is logged for every strategy x market and would crowd out bets)
    out["events"] = [x for x in events if x["event"] not in ("start", "watched")][-80:]
    return out


def _thin(curve, n=300):
    """Keep at most n points of a [[ts, value], ...] curve, always including the last one."""
    if not isinstance(curve, list) or len(curve) <= n:
        return curve
    k = -(-len(curve) // (n - 1))
    return curve[::k] + [curve[-1]]


def _lab3():
    """The golden-strategy hunt (lab3.py output), or None if it hasn't been run.
    LAB3_PATH overrides the location, e.g. to render the dashboard from a test fixture."""
    import os
    p = os.environ.get("LAB3_PATH")
    f = Path(p) if p else OUT.parent / "data" / "lab" / "lab3_results.json"
    try:
        r = json.loads(f.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(r, dict):
        return None
    allc = [c for c in (r.get("candidates") or []) if isinstance(c, dict)]
    # true totals from the full file; the page gets at most the best 150 rows
    r["counts"] = {"reached": len(allc), **{k: sum(c.get("status") == k for c in allc) for k in ("golden", "pass", "fail")}}
    cands = allc[:150]
    r["counts"]["shown"] = len(cands)
    for x in cands:
        if "curve" in x:
            x["curve"] = _thin(x["curve"], 150)
        x.pop("holdout_by_coin", None)  # not shown; keeps the page small
    for b in (r.get("baselines") or []):
        if isinstance(b, dict) and "curve" in b:
            b["curve"] = _thin(b["curve"])
    r["candidates"] = cands
    r["heatmaps"] = (r.get("heatmaps") or [])[:12]
    return r


def lab_summary():
    """Compact view of data/lab/*.json for the dashboard (drops the full search list)."""
    out = {}
    lab3 = _lab3()
    if lab3:
        out["lab3"] = lab3
    try:   # progress of a running hunt (written by scripts/lab3_progress.py), shown as a banner
        out["lab3_progress"] = json.loads((OUT.parent / "data" / "lab" / "lab3_progress.json").read_text())
    except (OSError, ValueError):
        pass
    for key, fname in (("m15", "results.json"), ("hourly", "hourly_results.json")):
        f = OUT.parent / "data" / "lab" / fname
        if not f.exists():
            continue
        r = json.loads(f.read_text())
        search = r.get("search", [])
        out[key] = {k: r.get(k) for k in ("generated", "holdout_start", "holdout_days", "t_bar_strict", "coins",
                                          "n_strategies", "n_combos", "finals", "benchmarks")}
        out[key]["n_search"] = len(search)
        out[key]["n_positive"] = sum(1 for x in search if x["oos"]["pnl"] > 0)
        out[key]["top"] = sorted(search, key=lambda x: -x["oos"]["t_stat"])[:15]
    f = OUT.parent / "data" / "lab" / "lab2_results.json"
    if f.exists():
        r = json.loads(f.read_text())
        fr = r.get("frozen_rule", {})
        params = {k: fr[k] for k in ("start", "end", "edge", "vol_mult") if k in fr}
        finals = []
        for label, part in (("Apr-Aug archive", "archive"), ("Newest data, never used", "fresh")):
            for coin, d in (r.get(part) or {}).items():
                m = d.get("frozen") or {}
                if not m.get("trades"):
                    continue
                finals.append({"scope": coin, "strategy": "fair_value", "execution": "taker",
                               "params": {"test": label, "dates": f"{str(d.get('from'))[:10]} to {str(d.get('to'))[:10]}"},
                               "holdout": {"pnl": m.get("pnl", 0), "trades": m.get("trades", 0),
                                           "win_rate": m.get("win_rate", 0), "t_stat": m.get("t_stat", 0)},
                               "passed": bool(m.get("pnl", 0) > 0 and m.get("t_stat", 0) >= 2),
                               "passed_strict": bool(m.get("pnl", 0) > 0 and m.get("t_stat", 0) >= 2.71)})
        finals.sort(key=lambda x: -x["holdout"]["t_stat"])
        out["blind"] = {"generated": r.get("generated"), "finals": finals, "benchmarks": [], "coins": {},
                        "t_bar_strict": 2.71, "n_search": len(finals), "n_positive": sum(x["holdout"]["pnl"] > 0 for x in finals),
                        "n_strategies": 1, "n_combos": 1, "holdout_start": None,
                        "intro": "The exact live rule (fair value, edge 12c, buy at the ask, $10 per trade), frozen and run on data that no test or tuning had ever touched: Kalshi's Apr-Aug archive, and markets the earlier searches never saw. Nothing was re-tuned. Pass = profit and t-stat of at least 2; strict pass = t-stat of at least 2.71."}
    return out or None


def build():
    live = summarise()
    html = (ROOT / "dashboard_template.html").read_text()
    results = (OUT / "results.json").read_text()
    html = html.replace("/*__RESULTS__*/null", results).replace("/*__LIVE__*/null", json.dumps(live))
    html = html.replace("/*__LAB__*/null", json.dumps(lab_summary()))
    (OUT / "index.html").write_text(html)
    (OUT / "live.json").write_text(json.dumps(live))
    for s in live["strategies"]:
        print(f"{s['series']} {s['strategy']}: {s['orders']} orders, {s['fills']} fills, {s['settled']} settled, "
              f"P&L ${s['pnl']}")
    return live
