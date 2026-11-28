"""First look at Kalshi's 15-minute GOLD market (KXGOLD15M) using Coinbase's PAXG (gold token) as a stand-in price (Nov 28 2026).

The market asks whether gold is higher 15 minutes after the window starts. Settles on Pyth's gold feed, which needs an API key
from this container, so PAXG 1-minute candles stand in. PAXG trades at a small premium to spot gold, so the strike used here is
PAXG's own price at the window start (the "up" question is then answered on one clean series). Same logic as the live crypto
model's raw input: p = Phi(ln(S/K) / (sigma_1m * sqrt(minutes left))), sigma from the last 60 minutes of PAXG.
Bets: decide on minute j's quotes, buy the next minute's ask (YES) or 1-bid (NO), Kalshi fee, first qualifying minute per
window, price 5-95c. Only ~2 weeks of history exist, so this is a feasibility look, not a verdict.

    python3 research/other_markets/gold_probe.py
"""
import datetime as dt
import json
import math
import sys
import time

import numpy as np
import requests
from scipy.special import ndtr

API = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = sys.argv[1] if len(sys.argv) > 1 else "KXGOLD15M"
PRODUCT = sys.argv[2] if len(sys.argv) > 2 else "PAXG-USD"


def get(url, params, tries=6):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2 + 3 * i)
                continue
        except Exception:
            pass
        time.sleep(1 + i)
    return {}


def fee(p):
    return 0.07 * p * (1 - p)


def ts(x):
    return int(dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp())


def main():
    ms, cur = [], None
    while True:
        p = {"series_ticker": SERIES, "status": "settled", "limit": 1000, "min_close_ts": int(time.time()) - 120 * 86400}
        if cur:
            p["cursor"] = cur
        d = get(API + "/markets", p)
        ms += [m for m in d.get("markets", []) if m.get("result") in ("yes", "no")]
        cur = d.get("cursor")
        if not cur:
            break
    ms.sort(key=lambda m: m["close_time"])
    print(len(ms), "settled markets,", ms[0]["close_time"], "to", ms[-1]["close_time"], flush=True)
    t0, t1 = ts(ms[0]["close_time"]) - 4 * 3600, ts(ms[-1]["close_time"]) + 600
    spot = {}
    s = t0
    while s < t1:
        e = min(s + 299 * 60, t1)
        d = get(f"https://api.exchange.coinbase.com/products/{PRODUCT}/candles",
                {"granularity": 60, "start": dt.datetime.fromtimestamp(s, dt.timezone.utc).isoformat(), "end": dt.datetime.fromtimestamp(e, dt.timezone.utc).isoformat()})
        for c in d if isinstance(d, list) else []:
            spot[int(c[0])] = float(c[4])                      # minute start -> close
        s = e
        time.sleep(0.25)
    print(len(spot), "spot minutes", flush=True)
    book = {}
    chunks, cur_c = [], []
    for m in ms:                                                  # consecutive windows only: a few hours per call
        if cur_c and (ts(m["close_time"]) - ts(cur_c[-1]["close_time"]) > 1800 or len(cur_c) >= 12):
            chunks.append(cur_c); cur_c = []
        cur_c.append(m)
    chunks.append(cur_c)
    for n_, part in enumerate(chunks):
        end = max(ts(m["close_time"]) for m in part)
        start = min(ts(m["close_time"]) for m in part) - 16 * 60
        d = get(API + "/markets/candlesticks", {"market_tickers": ",".join(m["ticker"] for m in part), "start_ts": start, "end_ts": end, "period_interval": 1})
        for r in d.get("markets", []):
            bars = {}
            for c in r.get("candlesticks") or []:
                try:
                    bars[int(c["end_period_ts"])] = (float(c["yes_bid"]["close_dollars"]), float(c["yes_ask"]["close_dollars"]))
                except (KeyError, TypeError, ValueError):
                    pass
            book[r["market_ticker"]] = bars
        time.sleep(0.25)
        if n_ % 50 == 0:
            print("  quotes", n_, "/", len(chunks), flush=True)
    rows = []
    for m in ms:
        close = ts(m["close_time"])
        start = close - 900
        bars = book.get(m["ticker"]) or {}
        y = float(m["result"] == "yes")
        K = spot.get(start - 60)                              # PAXG minute that ENDS at the window start
        if K is None:
            continue
        for j in range(2, 14):                                # minutes into the window
            now = start + 60 * j
            q0, q1 = bars.get(now), bars.get(now + 60)
            S = spot.get(now - 60)
            sig = [math.log(spot[k + 60] / spot[k]) for k in range(now - 3660, now - 60, 60) if k in spot and k + 60 in spot]
            if q0 is None or q1 is None or S is None or len(sig) < 30:
                continue
            sd = float(np.std(sig, ddof=1))
            if sd <= 0:
                continue
            tau = 15 - j
            p = float(ndtr(math.log(S / K) / (sd * math.sqrt(tau))))
            rows.append({"t": m["ticker"], "j": j, "y": y, "p": p, "bid": q0[0], "ask": q0[1], "fa": q1[1], "fb": q1[0], "day": close // 86400})
    print(len(rows), "rows from", len({r["t"] for r in rows}), "windows", flush=True)
    y = np.array([r["y"] for r in rows]); p = np.array([r["p"] for r in rows])
    mid = np.array([(r["bid"] + r["ask"]) / 2 for r in rows])
    ll = lambda q: float(-np.mean(y * np.log(np.clip(q, 1e-3, 1)) + (1 - y) * np.log(np.clip(1 - q, 1e-3, 1))))
    ok = (mid > 0.03) & (mid < 0.97)
    print("log loss (rows with mid 3-97c): market mid %.4f | PAXG model %.4f | n %d" % (ll(mid[ok]) if False else float(-np.mean((y*np.log(mid)+(1-y)*np.log(1-mid))[ok])), float(-np.mean((y*np.log(np.clip(p,1e-3,1))+(1-y)*np.log(np.clip(1-p,1e-3,1)))[ok])), int(ok.sum())), flush=True)
    res = {}
    for thr in (0.04, 0.06, 0.08, 0.12, 0.16):
        seen, pn, dd = set(), [], {}
        for r in sorted(rows, key=lambda r: (r["t"], r["j"])):
            if r["t"] in seen:
                continue
            ya, na = r["ask"], 1 - r["bid"]
            ey, en = r["p"] - ya - fee(ya), (1 - r["p"]) - na - fee(na)
            if ey >= thr and 0.05 <= ya <= 0.95:
                fa = r["fa"]; pnl = r["y"] - fa - fee(fa)
            elif en >= thr and 0.05 <= na <= 0.95:
                fn = 1 - r["fb"]; pnl = (1 - r["y"]) - fn - fee(fn)
            else:
                continue
            seen.add(r["t"]); pn.append(pnl); dd[r["day"]] = dd.get(r["day"], 0) + pnl
        if pn:
            v = np.array(list(dd.values())); n = len(pn)
            tt = float(v.mean() / v.std(ddof=1) * math.sqrt(len(v))) if len(v) > 2 and v.std(ddof=1) > 0 else 0.0
            res[thr] = {"bets": n, "cents_per_bet": round(100 * float(np.mean(pn)), 2), "days": len(v), "t_by_day": round(tt, 2)}
            print(f"  bar {thr:.2f}: {n} bets, {100 * float(np.mean(pn)):+.2f}c a bet over {len(v)} days (t {tt:+.2f})", flush=True)
    json.dump(res, open(f"research/other_markets/{SERIES}_probe.json", "w"), indent=1)


main()
