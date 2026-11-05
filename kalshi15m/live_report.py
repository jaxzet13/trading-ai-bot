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


def _lab3_holdout(cid):
    """Holdout result of a golden-hunt candidate (data/lab/lab3_results.json), in the same shape as
    _lab_holdout, for paper strategies that came from the hunt (live.json "lab3_id")."""
    try:
        r = json.loads((OUT.parent / "data" / "lab" / "lab3_results.json").read_text())
    except (OSError, ValueError):
        return None
    for x in r.get("candidates") or []:
        if x.get("id") == cid:
            h = x.get("holdout") or {}
            out = {"pnl": h.get("pnl"), "trades": h.get("trades"), "t_stat": h.get("t"), "win_rate": h.get("win_rate"),
                   "curve": x.get("curve") or []}
            n = sum((v.get("holdout_markets") or 0) for k, v in (r.get("coins") or {}).items()
                    if x.get("scope") in ("ALL", k))
            if n and h.get("trades"):
                out["per_market"] = round(h["trades"] / n, 3)
            return out
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
            "staked": round(sum(x["n"] * x["price"] for x in fills), 2),  # display only: profit per $1 staked
            "pnl": round(sum(x["pnl"] for x in settles), 2), "curve": pnl_curve,
            "open": [x["ticker"] for x in fills if x["ts"] not in settled_fills],
            "holding": [{k: x.get(k) for k in ("ticker", "series", "side", "n", "price", "strike", "close_ts", "model", "spot")}
                        for x in fills if x["ts"] not in settled_fills],
            "status": st, "stale": (not st) or now - st.get("ts", 0) > 180,
            "backtest": _backtest(results, s, e["strategy"], e["execution"]),
            "lab": (_lab3_holdout(e["lab3_id"]) if e.get("lab3_id") else None)
                   or _lab_holdout(e.get("lab_scope", s), e["strategy"], e["execution"]),
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
    return _hunt_results("LAB3_PATH", "lab3_results.json")


def _lab4():
    """The same hunt run on Kalshi's other 15-minute markets (currencies, Treasury yields, stock indices;
    lab4 output, with an extra "markets_surveyed" list), or None. LAB4_PATH overrides the location."""
    return _hunt_results("LAB4_PATH", "lab4_results.json")


def _hunt_results(env, fname):
    import os
    p = os.environ.get(env)
    f = Path(p) if p else OUT.parent / "data" / "lab" / fname
    try:
        r = json.loads(f.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(r, dict):
        return None
    allc = [c for c in (r.get("candidates") or []) if isinstance(c, dict)]
    for c in allc:   # labrm never re-enters a market (one bet per market), so name x_reentry for what was tested
        if c.get("id") == "x_reentry:ALL":
            c["label"] = "Early sale, 14c gap, bets up to 3x (x_reentry, one bet per market)"
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
    lab4 = _lab4()
    if lab4:
        out["lab4"] = lab4
    out["how"] = {"combo": COMBO, "combo_days": COMBO_DAYS}  # the "How it works" tab's evidence
    try:  # the demo runner's real safety limits and rule list, quoted on the page's Plan A / Plan C cards
        cfg = json.loads((ROOT / "real_best_demo.json").read_text())
        out["how"]["runner"] = {"limits": cfg.get("limits"), "rules": [r.get("id") for r in cfg.get("golden_rules") or []],
                                "series": cfg.get("series"), "note": cfg.get("_note")}
    except (OSError, ValueError):
        pass
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


# Kalshi's other 15-minute up/down markets, shown on the dashboard's "Currencies & more" tab.
# Research only: nothing trades on them. (series, plain-English name, short name, group)
OTHER_SERIES = [
    ("KXEURUSD15M", "Euro vs US dollar", "EUR/USD", "fx"), ("KXUSDJPY15M", "US dollar vs Japanese yen", "USD/JPY", "fx"),
    ("KXGBPUSD15M", "British pound vs US dollar", "GBP/USD", "fx"), ("KXAUDUSD15M", "Australian dollar vs US dollar", "AUD/USD", "fx"),
    ("KXUSDCAD15M", "US dollar vs Canadian dollar", "USD/CAD", "fx"), ("KXUSDMXN15M", "US dollar vs Mexican peso", "USD/MXN", "fx"),
    ("KX2YRRATE15M", "2-year Treasury yield", "2Y yield", "rates"), ("KX5YRRATE15M", "5-year Treasury yield", "5Y yield", "rates"),
    ("KX10YRRATE15M", "10-year Treasury yield", "10Y yield", "rates"), ("KX30YRRATE15M", "30-year Treasury yield", "30Y yield", "rates"),
    ("KXINX15M", "S&P 500", "S&P 500", "index"), ("KXNDQ15M", "Nasdaq-100", "Nasdaq-100", "index"),
    ("KXDJIA15M", "Dow Jones Industrial Average", "Dow", "index"),
]
_OCACHE = OUT.parent / "data" / "kalshi15m" / "other_markets_cache.json"


def other_markets(budget_s: float = 6.0) -> dict:
    """The open market for each OTHER_SERIES from Kalshi's public API, plus how much a typical market trades
    (median volume of the last ~50 settled ones, cached and refreshed at most hourly). Best effort and bounded:
    sequential requests, short timeouts, a hard time budget; anything that fails shows as missing on the page."""
    import requests
    from datetime import datetime
    api = "https://api.elections.kalshi.com/trade-api/v2/markets"
    stop, now = time.monotonic() + budget_s, time.time()
    try:
        cache = json.loads(_OCACHE.read_text())
    except (OSError, ValueError):
        cache = {}
    sess, last = requests.Session(), [0.0]

    def get(params, retry=True):
        wait = last[0] + 0.35 - time.monotonic()  # Kalshi rate-limits bursts (shared with the bots): space requests out
        if wait > 0:
            time.sleep(wait)
        left = stop - time.monotonic()
        if left < 0.4:
            return None
        try:
            last[0] = time.monotonic()
            r = sess.get(api, params=params, timeout=min(2.5, left))
            if r.status_code == 429 and retry and stop - time.monotonic() > 2.0:
                time.sleep(1.0)
                return get(params, retry=False)
            return r.json().get("markets") if r.ok else None
        except Exception:
            return None

    def ts(v):
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None

    def num(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    rows, seen = [], cache.setdefault("open", {})
    for series, name, short, group in OTHER_SERIES:
        row = {"series": series, "name": name, "short": short, "group": group, "market": None}
        ms = get({"series_ticker": series, "status": "open", "limit": 20})
        if ms is None:  # no answer: keep showing the last market we saw while it is still open
            old = seen.get(series)
            if old and (old.get("close_ts") or 0) > now:
                row["market"], row["stale_since"] = old, old.get("fetched")
            else:
                row["error"] = True
        else:
            live = [m for m in ms if (ts(m.get("close_time")) or 0) > now]
            if live:
                m = min(live, key=lambda m: ts(m.get("close_time")))
                row["market"] = seen[series] = {
                    "ticker": m.get("ticker"), "title": m.get("title"), "strike": num(m.get("floor_strike")),
                    "open_ts": ts(m.get("open_time")), "close_ts": ts(m.get("close_time")),
                    "yes_bid": num(m.get("yes_bid_dollars")), "yes_ask": num(m.get("yes_ask_dollars")),
                    "last": num(m.get("last_price_dollars")), "volume": num(m.get("volume_fp")),
                    "open_interest": num(m.get("open_interest_fp")), "fetched": int(now)}
            else:
                seen.pop(series, None)
        rows.append(row)
    # typical volume: refresh the 3 stalest figures per run (each at most hourly), with whatever time is left
    vol = cache.setdefault("volume", {})
    for series, *_ in sorted(OTHER_SERIES, key=lambda x: (vol.get(x[0]) or {}).get("ts", 0))[:3]:
        if now - (vol.get(series) or {}).get("ts", 0) < 3600:
            continue
        ms = get({"series_ticker": series, "status": "settled", "limit": 50})
        if ms is None:
            break
        vols = sorted(v for v in (num(m.get("volume_fp")) for m in ms) if v is not None)
        vol[series] = {"ts": now, "median_volume": vols[len(vols) // 2] if vols else None, "n": len(vols)}
    try:
        _OCACHE.write_text(json.dumps(cache))
    except OSError:
        pass
    for row in rows:
        c = vol.get(row["series"]) or {}
        row["typical_volume"], row["typical_n"] = c.get("median_volume"), c.get("n")
    return {"generated": int(now), "series": rows}


# Best fixed combination from the golden hunt ("sized" Kelly entries + "scalp" early exit, no tuning).
# Copied from the one-off run scratchpad/combo.py (combo.json, 2026-11-03), which re-ran lab3's engine on the
# search window, the locked 15-day holdout and the Apr-Aug archive. $10 base stake. Update by re-running it.
COMBO = {"search": {"pnl": 21896, "trades": 13453, "t": 11.3, "days": 47, "per_day": 465.9, "worst_day": -352.6, "pos_days": 0.94},
         "hold": {"pnl": 8034, "trades": 5537, "t": 6.95, "days": 17, "per_day": 472.6, "worst_day": -367.4, "pos_days": 0.82},
         "arch": {"pnl": 6607, "trades": 4797, "t": 5.81, "days": 154, "per_day": 42.9, "worst_day": -194.6, "pos_days": 0.66}}
# Day-by-day profit of that combination (UTC days, $; day0 = days since 1970-01-01), from the same re-run
# (scratchpad/combo_days.py = combo.py with the per-day totals kept). Its sums match COMBO above.
COMBO_DAYS = {
    "arch": {"day0": 20544, "pnl": [5, -15, 85, 74, 10, 42, 146, 32, -24, -53, 142, 117, -148, 48, 83, 13, -57, 33, 27, -32, 27, 79, -111, 30, 281, 333, 1, 74, -49, 29, -40, -68, 19, -10, 65, 66, -47, 86, 50, -2, 135, -15, 34, 23, -37, -101, -28, -24, -67, -97, 18, 45, 222, 45, 86, -61, -54, -7, -25, -102, -72, 177, 56, 29, 28, 50, 39, -67, 91, 5, 73, 43, 5, 9, 100, 55, -23, 71, -42, -24, -27, 9, -50, -60, 98, -62, -88, 31, -33, 77, 151, 197, 31, -144, -156, 227, 96, 326, -53, -106, 43, 71, -20, 184, 80, -195, 63, -115, 201, 146, -50, 98, 185, 132, 95, -10, 67, 293, 7, 220, 175, 47, -64, 126, 375, 197, 370, 49, 83, 251, -28, 7, -88, 34, 42, 112, 39, 70, 92, 184, -72, 52, 25, 32, 29, -59, 284, 132, 109, 24, -24, -49, 93, 69]},
    "search": {"day0": 20697, "pnl": [141, 217, 442, 365, 596, 342, 869, 305, 603, 693, 406, 1400, 1237, 312, 749, 656, 454, 437, 911, 1087, 190, 331, 496, 404, 279, 61, -324, 928, -353, 78, 232, 374, 433, -104, 261, 1048, 565, 504, 188, 294, 453, 1097, 179, 871, 169, 325, 695]},
    "hold": {"day0": 20743, "pnl": [-192, 396, 414, 730, 1085, 490, 266, 358, 1424, 767, 749, 372, 926, -367, -135, 482, 268]},
}
DEMO_LOG = OUT.parent / "data" / "kalshi15m" / "real_all9_log.jsonl"


def demo_summary(start_balance: float = 10.0) -> dict | None:
    """The Kalshi demo account (fake money, real order book) from the real runner's log: realised P&L from
    every settlement and early sale, as a balance curve from the $10 it started with. Display only."""
    try:
        lines = DEMO_LOG.read_text().splitlines()
    except OSError:
        return None
    ev = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("mode") == "DEMO":
            ev.append(e)
    if not ev:
        return None
    ev.sort(key=lambda e: e.get("ts", 0))
    closes = [e for e in ev if e.get("event") in ("settle", "exit") and isinstance(e.get("pnl"), (int, float))]
    fills = [e for e in ev if e.get("event") == "fill"]
    bal, curve = start_balance, [[int(ev[0]["ts"]), start_balance]]
    for e in closes:
        bal += e["pnl"]
        curve.append([int(e["ts"]), round(bal, 4)])
    staked = sum(e.get("cost") or 0 for e in fills)
    pnl = sum(e["pnl"] for e in closes)
    # the clearest recent early sale (biggest move from buy price to sale price), for the "how it works" example
    intents = {(e.get("ticker"), e.get("side")): e for e in ev if e.get("event") == "order_intent"}
    exits = {(e.get("ticker"), e.get("side")): e for e in ev if e.get("event") == "exit_intent"}  # last one = the filled sale
    example = None
    for e in ev:
        if e.get("event") != "exit" or not (e.get("pnl") or 0) > 0 or not e.get("n"):
            continue
        k = (e.get("ticker"), e.get("side"))
        oi, xi = intents.get(k), exits.get(k)
        if not oi or oi.get("model") is None or not xi:
            continue
        buy = (e.get("entry_cost") or 0) / e["n"]
        held = (lambda q: q if e.get("side") == "yes" else 1 - q)
        cand = {"ts": int(e["ts"]), "series": e.get("series"), "ticker": e.get("ticker"), "side": e.get("side"), "n": e["n"],
                "minute_in": oi.get("minute"), "buy": round(buy, 4), "fair_in": round(held(oi["model"]), 4),
                "spot": oi.get("spot"), "strike": oi.get("strike"), "lag_s": oi.get("lag_s"),
                "minute_out": e.get("minute"), "sell": e.get("sell_avg"),
                "fair_out": round(xi["model_value"], 4) if isinstance(xi.get("model_value"), (int, float)) else None,
                "pnl": e.get("pnl"), "close_ts": e.get("close_ts")}
        if example is None or (cand["sell"] or 0) - cand["buy"] > (example["sell"] or 0) - example["buy"]:
            example = cand
    return {"start_balance": start_balance, "balance": round(bal, 2), "pnl": round(pnl, 2), "fills": len(fills),
            "closed": len(closes), "wins": sum(e["pnl"] > 0 for e in closes), "exits": sum(e["event"] == "exit" for e in closes),
            "staked": round(staked, 2), "since": int(ev[0]["ts"]), "last": int(ev[-1]["ts"]), "curve": curve[-400:],
            "example": example,
            "reported_balance": next((e["balance_crypto"] for e in reversed(ev) if isinstance(e.get("balance_crypto"), (int, float))), None)}


REAL_LOG = OUT.parent / "data" / "kalshi15m" / "real_live_log.jsonl"
# When the real-money runner's price bugs were fixed (2026-11-04 15:39:53 UTC). Real bets placed before this
# used wrong prices, so the "Real money" tab counts the account from here, with all-time totals alongside.
# Same moment as "daily_loss_ignore_before_ts" in kalshi15m/real_best_live.json.
FIX_TS = 1793806793


def realmoney_results(max_rows: int = 60) -> dict | None:
    """The real-money test (labrm.py: each strategy replayed at the account's real bet size and limits, a bet
    counting only if Kalshi's real trade records show it would have filled), or None if it hasn't started.
    REALMONEY_RESULTS overrides the location, e.g. to render the dashboard from a test fixture."""
    import os
    p = os.environ.get("REALMONEY_RESULTS")
    f = Path(p) if p else OUT.parent / "data" / "lab" / "realmoney_results.json"
    try:
        r = json.loads(f.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(r, dict):
        return None
    allc = [c for c in (r.get("candidates") or []) if isinstance(c, dict)]
    for c in allc:   # labrm never re-enters a market (one bet per market), so name x_reentry for what was tested
        if c.get("id") == "x_reentry:ALL":
            c["label"] = "Early sale, 14c gap, bets up to 3x (x_reentry, one bet per market)"
    # true totals from the full file; the page (and the live db document) gets at most the best max_rows
    r["counts"] = {"tested": len(allc), "golden": sum(c.get("status") == "real-money golden" for c in allc),
                   **{k: sum(c.get("status") == k for c in allc) for k in ("pass", "fail")}}

    def pnl(c):
        t = c.get("total")
        v = t.get("pnl") if isinstance(t, dict) else None
        return v if isinstance(v, (int, float)) else float("-inf")
    keep = sorted(allc, key=pnl, reverse=True)[:max_rows]
    if not isinstance(r.get("chosen"), dict):
        # what the real account actually runs (kalshi15m/real_best_live.json), so the tab shows it
        try:
            cfg = json.loads((ROOT / "real_best_live.json").read_text())
            ids = [g.get("id") for g in cfg.get("golden_rules") or []]
            labels = {c.get("id"): c.get("label") for c in allc}
            if ids:
                r["chosen"] = {"id": ids[0], "ids": ids, "applied_at": int((ROOT / "real_best_live.json").stat().st_mtime),
                               "note": "Live on the real account now: " + ", ".join(labels.get(i) or i for i in ids)
                                       + (" (first one has priority)" if len(ids) > 1 else "")}
        except (OSError, ValueError):
            pass
    chosen = r.get("chosen").get("id") if isinstance(r.get("chosen"), dict) else None
    if chosen is not None and all(c.get("id") != chosen for c in keep):
        keep += [c for c in allc if c.get("id") == chosen][:1]
    for c in keep:
        if "curve" in c:
            c["curve"] = _thin(c["curve"], 200)
    r["candidates"] = keep
    r["counts"]["shown"] = len(keep)
    return r


RULE_LABELS = {"x_reentry:ALL": "Early sale, 14c gap, bets up to 3x (x_reentry)",
               "x_exit:ALL": "Early sale near fair value (x_exit)",
               "sized_exit:ALL": "Bigger bets on bigger gaps + early sale (sized_exit)",
               "sized:ALL": "Bigger bets on bigger gaps, hold to the end (sized)",
               "fv_t:ALL": "Fair value, fat-tailed model (fv_t)",
               "scalp:ALL": "Early sale at fair value (scalp)", "x_cap:ALL": "Scalp with a window cap (x_cap)"}


def real_by_rule(ev, num):
    """Live real-money stats per strategy since FIX_TS: which rule placed each bet (order_intent.rule), and how
    each bet ended (exit / settle P&L, grouped per market). Rules in kalshi15m/real_best_live.json are 'live';
    ones that traded earlier but are no longer configured are 'retired'. Each carries its real-money-test
    average per bet (data/lab/realmoney_results.json, out-of-sample) for comparison."""
    try:
        live_ids = [g.get("id") for g in json.loads((ROOT / "real_best_live.json").read_text()).get("golden_rules") or []]
    except (OSError, ValueError):
        live_ids = []
    test = {}
    try:
        rr = json.loads((OUT.parent / "data" / "lab" / "realmoney_results.json").read_text())
        for c in rr.get("candidates") or []:
            t = c.get("total") or {}
            if num(t.get("pnl")) and t.get("filled"):
                test[c.get("id")] = {"per_bet": round(t["pnl"] / t["filled"], 4), "status": c.get("status"),
                                     "pnl": t["pnl"], "filled": t["filled"], "t": t.get("t")}
    except (OSError, ValueError):
        pass
    rule_of, intent, bets = {}, {}, {}
    for e in ev:
        if e["ts"] < FIX_TS:
            continue
        tk, k = e.get("ticker"), e.get("event")
        if k == "order_intent" and tk:
            rule_of[tk] = e.get("rule")
            intent[tk] = e
        elif k == "fill" and tk in rule_of and num(e.get("n")) and e["n"] > 0:
            b = bets.setdefault(tk, {"rule": rule_of[tk], "ts": e["ts"], "cost": 0.0, "pnl": 0.0, "closed_n": 0.0,
                                     "n": 0.0, "side": e.get("side"), "price": e.get("avg_price"), "done": False})
            b["cost"] += (e.get("cost") or 0) + (e.get("fees") or 0)
            b["n"] += e["n"]
        elif k in ("exit", "settle") and tk in bets and num(e.get("pnl")):
            b = bets[tk]
            b["pnl"] += e["pnl"]
            b["closed_n"] += e.get("n") or 0
            b["end"] = e["ts"]
            if k == "settle" or (k == "exit" and (e.get("remaining") or 0) <= 1e-9):
                b["done"] = True
    rows = {}
    for tk, b in sorted(bets.items(), key=lambda kv: kv[1]["ts"]):
        rid = b["rule"] or "unknown"
        r = rows.setdefault(rid, {"id": rid, "label": RULE_LABELS.get(rid, rid), "live": rid in live_ids,
                                  "bets": 0, "closed": 0, "wins": 0, "pnl": 0.0, "open": 0, "at_risk": 0.0,
                                  "first": int(b["ts"]), "curve": [], "test": test.get(rid)})
        r["bets"] += 1
        if b["done"]:
            r["closed"] += 1
            r["wins"] += b["pnl"] > 0
            r["pnl"] += b["pnl"]
            r["curve"].append([int(b.get("end", b["ts"])), round(r["pnl"], 4)])
        else:
            r["open"] += 1
            r["at_risk"] += max(b["cost"] - 0, 0) if not b["closed_n"] else max(b["cost"] * (1 - b["closed_n"] / b["n"]), 0)
        r["last"] = {"ticker": tk, "coin": tk.split("-")[0][2:-3], "side": b["side"], "price": b["price"], "ts": int(b["ts"]),
                     "pnl": round(b["pnl"], 4) if b["done"] else None, "open": not b["done"]}
    for rid in live_ids:
        rows.setdefault(rid, {"id": rid, "label": RULE_LABELS.get(rid, rid), "live": True, "bets": 0, "closed": 0,
                              "wins": 0, "pnl": 0.0, "open": 0, "at_risk": 0.0, "first": None, "curve": [],
                              "test": test.get(rid), "last": None})
    out = []
    for r in rows.values():
        r["pnl"], r["at_risk"] = round(r["pnl"], 2), round(r["at_risk"], 2)
        r["per_bet"] = round(r["pnl"] / r["closed"], 4) if r["closed"] else None
        r["priority"] = live_ids.index(r["id"]) if r["id"] in live_ids else None
        r["curve"] = _thin(r["curve"], 200)
        out.append(r)
    return sorted(out, key=lambda r: (not r["live"], r["priority"] if r["priority"] is not None else 99, -r["bets"]))


def real_account() -> dict | None:
    """The REAL Kalshi account, from the real runner's log ("mode": "LIVE" rows only): closed bets, wins, profit
    and a running-profit curve since FIX_TS and for all time, plus the last cash balance Kalshi reported.
    A bet is one market (ticker): one partly sold early and then settled counts once, with both parts' profit."""
    try:
        lines = REAL_LOG.read_text().splitlines()
    except OSError:
        return None
    ev = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("mode") == "LIVE" and isinstance(e.get("ts"), (int, float)):
            ev.append(e)
    if not ev:
        return None
    ev.sort(key=lambda e: e["ts"])
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)

    def part(since):
        bets = {}
        for e in ev:
            if e["ts"] >= since and e.get("event") in ("exit", "settle") and num(e.get("pnl")) and e.get("ticker"):
                b = bets.setdefault(e["ticker"], {"pnl": 0.0, "ts": e["ts"]})
                b["pnl"] += e["pnl"]
                b["ts"] = max(b["ts"], e["ts"])
        closed = sorted(bets.values(), key=lambda b: b["ts"])
        cum, curve = 0.0, []
        for b in closed:
            cum += b["pnl"]
            curve.append([int(b["ts"]), round(cum, 4)])
        return {"since": int(since or ev[0]["ts"]), "closed": len(closed), "wins": sum(b["pnl"] > 0 for b in closed),
                "pnl": round(cum, 2), "curve": _thin(curve, 400)}

    out = {"fix_ts": FIX_TS, "since_fix": part(FIX_TS), "all_time": part(0), "last": int(ev[-1]["ts"])}
    try:
        out["by_rule"] = real_by_rule(ev, num)
    except Exception as e:   # never allowed to break the report
        print(f"real account by rule: skipped ({e})")
    bal = next((e for e in reversed(ev) if num(e.get("balance_crypto"))), None)
    if bal:
        out["balance"], out["balance_ts"] = round(bal["balance_crypto"], 2), int(bal["ts"])
    return out


def rebuild_summary() -> dict | None:
    """The clean real-money rebuild, coin by coin (lab3 LAB3_REAL search on trade-built prices, plus labx's
    replay of any finalist against Kalshi's trade records), or None if it hasn't run."""
    lab = OUT.parent / "data" / "lab"
    try:
        r = json.loads((lab / "lab3_real_results.json").read_text())
    except (OSError, ValueError):
        return None
    try:
        val = {x["id"]: x for x in json.loads((lab / "labx_results.json").read_text()).get("results", [])}
    except (OSError, ValueError, KeyError, TypeError):
        val = {}
    m, cands = r.get("method") or {}, [c for c in (r.get("candidates") or []) if isinstance(c, dict)]
    wf = {}   # best walk-forward (search) result per coin over every family, for coins where nothing got through
    for f in r.get("families") or []:
        for k, w in (f.get("walk_forward") or {}).items():
            if isinstance(w, dict) and isinstance(w.get("t"), (int, float)) and (k not in wf or w["t"] > wf[k]["t"]):
                wf[k] = {"family": f.get("name") or f.get("id"), "t": w["t"], "pnl": w.get("pnl"), "trades": w.get("trades")}
    rows = []
    for coin in [*(r.get("coins") or {}), "ALL"]:
        cs = [c for c in cands if c.get("scope") == coin]
        best = max(cs, key=lambda c: (c.get("holdout") or {}).get("t") or -9) if cs else None
        row = {"coin": coin, "reached": len(cs), "status": best.get("status") if best else "none",
               "search_best": wf.get("All 9 coins" if coin == "ALL" else coin.replace("KX", "").replace("15M", ""))}
        if best:
            h = best.get("holdout") or {}
            row.update(id=best.get("id"), label=best.get("label"), pnl=h.get("pnl"), trades=h.get("trades"),
                       t=h.get("t"), win_rate=h.get("win_rate"), late_t=(best.get("delay1") or {}).get("t"),
                       why=best.get("why"))
            v = val.get(best.get("id"))
            if v:
                row["tape"] = {pid: {k: x.get(k) for k in ("pnl", "bets", "filled", "t", "days", "winning_days")}
                               for pid, x in (v.get("periods") or {}).items()}
                row["stress"] = {pid: {k: x for k, x in st.items() if "classic" not in k}
                                 for pid, st in (v.get("stress") or {}).items()}
                row["bankroll_1day"] = v.get("bankroll_1day")
        rows.append(row)
    return {"generated": r.get("generated"), "configs": m.get("n_configs_tested"), "families": m.get("n_families"),
            "t_bar": m.get("t_bar_strict"), "holdout_days": m.get("holdout_days"),
            "search_window": m.get("search_window"), "shortlist": m.get("shortlist"),
            "counts": {"exam": len(cands), "golden": sum(c.get("status") == "golden" for c in cands),
                       "pass": sum(c.get("status") == "pass" for c in cands)},
            "coins": rows}


def build():
    live = summarise()
    try:  # Kalshi demo account, for the "How it works" tab
        live["demo"] = demo_summary()
    except Exception as e:
        print(f"demo summary: skipped ({e})")
    try:  # the real-money test, for the "Real money" tab (live, so the page updates as the test runs)
        rm = realmoney_results()
        if rm:
            live["realmoney"] = rm
    except Exception as e:
        print(f"real-money results: skipped ({e})")
    try:  # the clean coin-by-coin rebuild, for the "Real money" tab
        rb = rebuild_summary()
        if rb:
            live["rebuild"] = rb
    except Exception as e:
        print(f"rebuild summary: skipped ({e})")
    try:  # the real Kalshi account, for the "Real money" tab
        ra = real_account()
        if ra:
            live["real_account"] = ra
    except Exception as e:
        print(f"real account: skipped ({e})")
    try:  # research-only markets for the "Currencies & more" tab; never allowed to break the report
        live["other_markets"] = other_markets()
    except Exception as e:
        print(f"other markets: skipped ({e})")
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
