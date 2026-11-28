"""Forward test of the pre-registered sports candidates (frozen Nov 28 2026): no hindsight possible.

frozen.json holds the 40 series-level strategies that looked best IN-SAMPLE on the 34 days before the freeze (scored by a
conservative edge: the 90% lower bound of the win rate minus the cost). This looks only at markets that SETTLED AFTER the
freeze, rebuilds each candidate's bets exactly as analyze.py does (hourly quote 3.5/5/8 h before expected expiration,
+1c slip, Kalshi fee, >= 10 contracts traded before, spread <= 8c) and reports how they did on games they never saw.

Correlated bets (several strikes of one game, a 3.5h and a 5h entry on the same market) are not independent: the pooled
number also counts each (market) once and clusters by day, so a handful of games cannot look like a hundred.

    python3 research/sports_universe/forward.py          -> research/sports_universe/forward_results.json
"""
import collections
import datetime as dt
import json
import math
import time
from pathlib import Path

import numpy as np
import requests

API = "https://api.elections.kalshi.com/trade-api/v2"
HERE = Path("research/sports_universe")
HS = {3.5: 0, 5.0: 1, 8.0: 2}


def fee(p):
    return 0.07 * p * (1 - p)


def get(path, params):
    for i in range(6):
        try:
            r = requests.get(API + path, params=params, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2 + 3 * i)
                continue
        except Exception:
            pass
        time.sleep(1 + i)
    return {}


def ts(x):
    return int(dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp())


def settled(series, since):
    out, cur = [], None
    while True:
        p = {"series_ticker": series, "status": "settled", "limit": 1000, "min_close_ts": since}
        if cur:
            p["cursor"] = cur
        d = get("/markets", p)
        out += [m for m in d.get("markets", []) if m.get("result") in ("yes", "no") and m.get("expected_expiration_time") and float(m.get("volume_fp") or 0) > 0]
        cur = d.get("cursor")
        if not cur:
            return out
        time.sleep(0.2)


def snapshots(ms):
    """market -> list of [end_ts, bid, ask, volume] hourly bars before expected expiration - 2.5 h."""
    by = collections.defaultdict(list)
    for m in ms:
        m["xs"] = ts(m["expected_expiration_time"])
        by[(m["xs"] // 3600 + 1) * 3600].append(m)
    bars = {}
    for end, grp in by.items():
        for i in range(0, len(grp), 100):
            part = grp[i:i + 100]
            d = get("/markets/candlesticks", {"market_tickers": ",".join(m["ticker"] for m in part), "start_ts": end - 14 * 3600 - 3600,
                                              "end_ts": end, "period_interval": 60})
            time.sleep(0.3)
            x = {m["ticker"]: m["xs"] for m in part}
            for r in d.get("markets", []):
                xs = x.get(r.get("market_ticker"))
                bl = []
                for c in r.get("candlesticks") or []:
                    e = int(c["end_period_ts"])
                    if xs - 14 * 3600 <= e <= xs - int(2.5 * 3600):
                        try:
                            bl.append([e, float(c["yes_bid"]["close_dollars"]), float(c["yes_ask"]["close_dollars"]), float(c.get("volume_fp") or 0)])
                        except (KeyError, TypeError, ValueError):
                            pass
                bars[r["market_ticker"]] = bl
    return bars


def main():
    fz = json.load(open(HERE / "frozen.json"))
    since = fz["frozen_at"]
    cands = []
    for c in fz["candidates"]:
        _, series, side, band, h = c.split("|")
        lo = int(band.split("-")[0]) / 100
        cands.append((c, series, 1 if side == "YES" else -1, lo, float(h[:-1])))
    series = sorted({c[1] for c in cands})
    ms = []
    for s in series:
        ms += [dict(m, series=s) for m in settled(s, since)]
    bars = snapshots(ms)
    res = {c[0]: [] for c in cands}
    for m in ms:
        b = bars.get(m["ticker"]) or []
        y = float(m["result"] == "yes")
        for name, s, side, lo, h in cands:
            if s != m["series"]:
                continue
            tref = m["xs"] - h * 3600
            k = -1
            for j, bar in enumerate(b):
                if bar[0] <= tref:
                    k = j
            if k < 0 or m["xs"] - b[k][0] > (h + 3) * 3600:
                continue
            bid, ask = b[k][1], b[k][2]
            if ask - bid > 0.08 or sum(bar[3] for bar in b[:k + 1]) < 10:
                continue
            price = min((ask if side == 1 else 1 - bid) + 0.01, 0.99)
            if not (0.05 <= price <= 0.95 and lo <= price < lo + 0.10):
                continue
            win = y if side == 1 else 1 - y
            res[name].append((m["ticker"], m["xs"] // 86400, win - price - fee(price), win))
    out = {"frozen_at": since, "evaluated_at": int(time.time()), "markets_settled_after": len(ms), "per_candidate": {}}
    allb = []
    for name, rows in res.items():
        if rows:
            p = np.array([r[2] for r in rows])
            out["per_candidate"][name] = {"bets": len(rows), "cents_per_bet": round(100 * float(p.mean()), 2), "win_rate": round(float(np.mean([r[3] for r in rows])), 3)}
            allb += rows
    first = {}
    for t, d, p, w in allb:                                  # one bet per market: the first candidate that bought it
        first.setdefault(t, (d, p))
    pooled = {"bets_all": len(allb), "markets": len(first)}
    if first:
        pp = np.array([v[1] for v in first.values()])
        dd = collections.defaultdict(float)
        for d, p in first.values():
            dd[d] += p
        v = np.array(list(dd.values()))
        pooled.update({"cents_per_market": round(100 * float(pp.mean()), 2), "pnl_per_contract_sum": round(float(pp.sum()), 2), "days": len(v),
                       "t_by_day": round(float(v.mean() / v.std(ddof=1) * math.sqrt(len(v))), 2) if len(v) > 2 and v.std(ddof=1) > 0 else None})
    out["pooled_one_bet_per_market"] = pooled
    json.dump(out, open(HERE / "forward_results.json", "w"), indent=1)
    print(json.dumps(pooled))
    for n, v in sorted(out["per_candidate"].items(), key=lambda kv: -kv[1]["bets"])[:12]:
        print(n, v)


if __name__ == "__main__":
    main()
