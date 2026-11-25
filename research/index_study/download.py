"""Kalshi stock-index markets: settled markets with their 1-minute quotes, plus index bars from Yahoo.

Read-only public market data, no keys. Rerunnable: everything is appended / cached, markets already stored are
skipped.

    python3 research/index_study/download.py [days=90] [--hourly] [--minvol=10]

Series
  KXINX, KXNASDAQ100       "range" ladders: 28 brackets + 2 tails per day, settle at the 16:00 New York close.
                           Every market of every event is stored (needed for the bracket-sum test).
  KXINXU, KXNASDAQ100U     "X or above" ladders (5 / 10 point strikes). One event per hour 10:00..16:00 New York.
                           Only the 16:00 event is stored unless --hourly; only markets with volume >= minvol.

Output (data/index/, not in git)
  meta_<series>.jsonl      one line per settled market seen in the listing (no bars)
  <series>.jsonl           one line per market: ticker, event, series, close (unix s), open, type, floor, cap,
                           result, value (settlement $), exp (index value at expiry), volume,
                           bars [[minute end ts, yes bid close, yes ask close, bid low, ask high, volume], ...]
                           for the 7.5 hours before the close
  yahoo_<symbol>_<interval>.json   ^GSPC and ^NDX, 5-minute bars (60 days) and 1-minute bars (30 days)

Markets settled before Kalshi's "historical cutoff" are read from /historical/markets and
/historical/markets/{ticker}/candlesticks (same data, slightly different field names).
"""
import datetime as dt
import json
import os
import sys
import time

import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
OUT = "data/index"
RANGE = ["KXINX", "KXNASDAQ100"]
ABOVE = ["KXINXU", "KXNASDAQ100U"]
WINDOW_S = int(7.5 * 3600)
GAP = 0.40                               # seconds between requests (<= 2.5 a second; the live bot shares the network)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

S = requests.Session()
_last = [0.0]


def get(path, params=None, tries=7):
    for i in range(tries):
        w = _last[0] + GAP - time.time()
        if w > 0:
            time.sleep(w)
        _last[0] = time.time()
        try:
            r = S.get(BASE + path, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(5 * (i + 1))
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("429 too often: " + path)


def ts(s):
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()) if s else None


def fl(x):
    try:
        return round(float(x), 4)
    except (TypeError, ValueError):
        return None


def slim(m, series):
    return {"ticker": m["ticker"], "event": m["event_ticker"], "series": series, "close": ts(m["close_time"]),
            "open": ts(m.get("open_time")), "type": m.get("strike_type"), "floor": m.get("floor_strike"),
            "cap": m.get("cap_strike"), "result": m.get("result"),
            "value": fl(m.get("settlement_value_dollars", m.get("settlement_value"))),
            "exp": fl(m.get("expiration_value")), "volume": fl(m.get("volume_fp", m.get("volume")))}


def listing(series, since, cutoff, log):
    """Every settled market of the series closing after `since` (live endpoint + historical endpoint)."""
    path = f"{OUT}/meta_{series}.jsonl"
    have = {}
    if os.path.exists(path):
        for ln in open(path):
            m = json.loads(ln)
            have[m["ticker"]] = m
    newest = max((m["close"] for m in have.values()), default=0)
    oldest = min((m["close"] for m in have.values()), default=10 ** 12)
    new = []

    def page(endpoint, extra, stop_before=None):
        cursor, n = None, 0
        while True:
            p = dict({"series_ticker": series, "limit": 1000}, **extra)
            if cursor:
                p["cursor"] = cursor
            d = get(endpoint, p) or {}
            ms = d.get("markets", [])
            for m in ms:
                if m["ticker"] not in have and m.get("result") in ("yes", "no"):
                    have[m["ticker"]] = slim(m, series)
                    new.append(have[m["ticker"]])
            n += len(ms)
            cursor = d.get("cursor")
            if not cursor or not ms or (stop_before and ts(ms[-1]["close_time"]) < stop_before):
                return n

    # live endpoint: only what closed after the newest stored market (and the stretch before the oldest, once)
    page("/markets", {"status": "settled", "min_close_ts": max(since, newest - 3600)})
    if oldest > max(since, cutoff) + 86400:
        page("/markets", {"status": "settled", "min_close_ts": since, "max_close_ts": oldest + 3600})
    if since < cutoff and oldest > since + 4 * 86400:
        page("/historical/markets", {}, stop_before=since)
    with open(path, "a") as f:
        for m in new:
            f.write(json.dumps(m, separators=(",", ":")) + "\n")
    out = [m for m in have.values() if m["close"] >= since]
    log(f"  {series}: {len(out)} settled markets in {len({m['event'] for m in out})} events (+{len(new)} new)")
    return out


def bars(m, cutoff):
    q = {"start_ts": m["close"] - WINDOW_S, "end_ts": m["close"], "period_interval": 1}
    d = None
    if m["close"] >= cutoff:
        d = get(f"/series/{m['series']}/markets/{m['ticker']}/candlesticks", q)
    if d is None:
        d = get(f"/historical/markets/{m['ticker']}/candlesticks", q)
    rows = []
    for c in (d or {}).get("candlesticks", []):
        a, b = c.get("yes_ask") or {}, c.get("yes_bid") or {}
        g = lambda x, k: fl(x.get(k + "_dollars", x.get(k)))
        rows.append([int(c["end_period_ts"]), g(b, "close"), g(a, "close"), g(b, "low"), g(a, "high"),
                     fl(c.get("volume_fp", c.get("volume"))) or 0])
    return rows


def yahoo(log):
    now = int(time.time())
    for sym in ("^GSPC", "^NDX"):
        for interval, days, chunk in (("5m", 59, 59), ("1m", 29, 7)):
            path = f"{OUT}/yahoo_{sym.strip('^')}_{interval}.json"
            store = json.load(open(path)) if os.path.exists(path) else {}
            n0 = len(store)
            t0 = max(now - days * 86400, max(map(int, store), default=0) - 3600)
            while t0 < now:
                t1 = min(t0 + chunk * 86400, now)
                for i in range(4):
                    try:
                        r = requests.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}",
                                         params={"interval": interval, "period1": t0, "period2": t1},
                                         headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
                        if r.status_code == 200:
                            res = r.json()["chart"]["result"][0]
                            q = res["indicators"]["quote"][0]
                            for k, t in enumerate(res.get("timestamp") or []):
                                if q["close"][k] is not None:      # bar START time -> [open, high, low, close]
                                    store[str(t)] = [round(q[x][k], 2) for x in ("open", "high", "low", "close")]
                            break
                        log(f"  yahoo {sym} {interval}: HTTP {r.status_code}")
                    except Exception as e:
                        log(f"  yahoo {sym} {interval}: {e!r}")
                    time.sleep(10 * (i + 1))
                t0 = t1
                time.sleep(3)
            json.dump(store, open(path, "w"), separators=(",", ":"))
            log(f"  yahoo {sym} {interval}: {len(store)} bars (+{len(store) - n0})")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    days = int(args[0]) if args else 90
    hourly = "--hourly" in sys.argv
    minvol = next((float(a.split("=")[1]) for a in sys.argv if a.startswith("--minvol=")), 10.0)
    log = lambda s: print(time.strftime("%H:%M:%S"), s, flush=True)
    os.makedirs(OUT, exist_ok=True)
    if "--no-yahoo" not in sys.argv:
        yahoo(log)
    since = int(time.time()) - days * 86400
    cutoff = ts((get("/historical/cutoff") or {}).get("market_settled_ts")) or 0
    todo = []
    for s in RANGE + ABOVE:
        ms = listing(s, since, cutoff, log)
        if s in ABOVE:
            ms = [m for m in ms if (m["volume"] or 0) >= minvol and (hourly or m["event"].endswith("H1600"))]
        have = set()
        if os.path.exists(f"{OUT}/{s}.jsonl"):
            have = {json.loads(ln)["ticker"] for ln in open(f"{OUT}/{s}.jsonl")}
        todo += [m for m in ms if m["ticker"] not in have]
    # newest days first, the 16:00 events before the hourly ones
    todo.sort(key=lambda m: (not m["event"].endswith("H1600"), -m["close"], m["series"], m["ticker"]))
    log(f"{len(todo)} markets to download (~{len(todo) * (GAP + 0.1) / 60:.0f} min)")
    files = {s: open(f"{OUT}/{s}.jsonl", "a") for s in RANGE + ABOVE}
    for i, m in enumerate(todo):
        try:
            b = bars(m, cutoff)
        except Exception as e:
            log(f"  {m['ticker']}: {e!r}")
            continue
        files[m["series"]].write(json.dumps(dict(m, bars=b), separators=(",", ":")) + "\n")
        if (i + 1) % 500 == 0:
            for f in files.values():
                f.flush()
            log(f"  {i + 1} / {len(todo)}")
    log("done")


if __name__ == "__main__":
    main()
