"""Kalshi stock-index markets: settled markets with their 1-minute quotes, plus index bars from Yahoo.

Read-only public market data, no keys. Rerunnable: everything is appended / cached, markets already stored are
skipped.

    python3 research/index_study/download.py [days=90] [--hourly] [--minvol=10] [--hourly-minvol=100]
                                             [--live-only] [--no-yahoo]

Series
  KXINX, KXNASDAQ100       "range" ladders: 28 brackets + 2 tails per day, settle at the 16:00 New York close.
                           Every market of every event is stored (needed for the bracket-sum test); for days
                           older than Kalshi's historical cutoff only the brackets that traded.
  KXINXU, KXNASDAQ100U     "X or above" ladders (5 / 10 point strikes). One event per hour 10:00..16:00 New York.
                           Only the 16:00 event is stored unless --hourly; only markets with volume >= minvol
                           (hourly events: >= hourly-minvol). --live-only skips days older than Kalshi's
                           historical cutoff (those cost one request per market).

Output (data/index/, not in git)
  meta_<series>.jsonl      one line per settled market seen in the listing (no bars)
  <series>.jsonl           one line per market: ticker, event, series, close (unix s), open, type, floor, cap,
                           result, value (settlement $), exp (index value at expiry), volume,
                           bars [[minute end ts, yes bid close, yes ask close, bid low, ask high, volume], ...]
                           from 18 / 9 / 4 hours before the close (range / 16:00 above / hourly above);
                           only minutes in which something changed
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
# Kalshi returns a bar only for minutes in which the book or the tape changed (quotes persist in between), and at
# most 10,000 bars per batch request. Window before the close and tickers per request, by kind of market:
PLAN = {"range": (18 * 3600, 8),         # quiet far brackets: reach back to the previous evening for a first quote
        "above": (9 * 3600, 18),         # 16:00 "or above" strikes
        "hourly": (4 * 3600, 40)}        # 10:00..15:00 "or above" strikes
OLD_MINVOL = 50                          # 'or above' markets older than the historical cutoff: volume >= 50
GAP = 0.7                                # seconds between candlestick requests, see polite()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

S = requests.Session()
STATS = {"429": 0}
GAP_NOW = [GAP]
_last = [0.0]


def polite():
    """Candlestick requests draw on a token bucket (600 tokens, 50 a request, 200 a second back) that the live
    bot's own quote reads share. So: never in the seconds around a minute boundary (when the bot reads), at most
    one a second, and a pause to refill whenever the bucket runs low (the tennis learner
    and the other collectors draw on it too)."""
    while True:
        now = time.time()
        sec = now % 60
        if sec < 6:
            time.sleep(6 - sec)
        elif sec > 54:
            time.sleep(66 - sec)
        elif now < _last[0] + GAP_NOW[0]:
            time.sleep(_last[0] + GAP_NOW[0] - now)
        else:
            return


def get(path, params=None, tries=8):
    candle = "candlesticks" in path
    for i in range(tries):
        if candle:
            polite()
        else:
            time.sleep(max(0.0, _last[0] + 0.5 - time.time()))
        _last[0] = time.time()
        try:
            r = S.get(BASE + path, params=params, timeout=60)
            left, reset = r.headers.get("x-ratelimit-remaining"), r.headers.get("x-ratelimit-reset")
            if candle and left is not None and float(left) < 150:
                time.sleep(float(reset or 2) + 0.2)            # let the bucket refill before the next one
            if r.status_code == 429:
                STATS["429"] += 1
                time.sleep(float(reset or 3) + 1)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except requests.HTTPError:
            raise
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


def _rows(cands):
    rows = []
    for c in cands or []:
        a, b = c.get("yes_ask") or {}, c.get("yes_bid") or {}
        g = lambda x, k: fl(x.get(k + "_dollars", x.get(k)))
        rows.append([int(c["end_period_ts"]), g(b, "close"), g(a, "close"), g(b, "low"), g(a, "high"),
                     fl(c.get("volume_fp", c.get("volume"))) or 0])
    return rows


def kind(m):
    return "range" if m["series"] in RANGE else "above" if m["event"].endswith("H1600") else "hourly"


def bars_batch(ms):
    """Live markets of one event in one request (GET /markets/candlesticks)."""
    close = ms[0]["close"]
    WINDOW_S = PLAN[kind(ms[0])][0]
    d = get("/markets/candlesticks", {"market_tickers": ",".join(m["ticker"] for m in ms),
                                      "start_ts": close - WINDOW_S, "end_ts": close, "period_interval": 1})
    got = {x["market_ticker"]: _rows(x.get("candlesticks")) for x in (d or {}).get("markets", [])}
    return [got.get(m["ticker"], []) for m in ms]


def bars_one(m):
    """A market older than the historical cutoff (one request each; the batch endpoint does not serve them)."""
    q = {"start_ts": m["close"] - PLAN[kind(m)][0], "end_ts": m["close"], "period_interval": 1}
    d = get(f"/historical/markets/{m['ticker']}/candlesticks", q)
    if d is None:
        d = get(f"/series/{m['series']}/markets/{m['ticker']}/candlesticks", q)
    return _rows((d or {}).get("candlesticks"))


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
    hourly_minvol = next((float(a.split("=")[1]) for a in sys.argv if a.startswith("--hourly-minvol=")), 100.0)
    live_only = "--live-only" in sys.argv
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
            ms = [m for m in ms if (m["volume"] or 0) >= (minvol if m["event"].endswith("H1600") else hourly_minvol)
                  and (hourly or m["event"].endswith("H1600"))]
        if live_only:
            ms = [m for m in ms if m["close"] >= cutoff]
        # older than the cutoff = one request per market: only the traded ones (no bracket sums for those days)
        ms = [m for m in ms if m["close"] >= cutoff or (m["volume"] or 0) >= (OLD_MINVOL if s in ABOVE else 1)]
        have = set()
        if os.path.exists(f"{OUT}/{s}.jsonl"):
            have = {json.loads(ln)["ticker"] for ln in open(f"{OUT}/{s}.jsonl")}
        todo += [m for m in ms if m["ticker"] not in have]
    # newest days first, the 16:00 events before the hourly ones
    todo.sort(key=lambda m: (not m["event"].endswith("H1600"), -m["close"], m["series"], m["ticker"]))
    files = {s: open(f"{OUT}/{s}.jsonl", "a") for s in RANGE + ABOVE}
    groups, cur = [], []
    for m in todo:                              # live markets: batches within one event; old ones: singly
        live = m["close"] >= cutoff
        if cur and (not live or len(cur) >= PLAN[kind(cur[0])][1] or cur[0]["event"] != m["event"] or cur[0]["close"] < cutoff):
            groups.append(cur)
            cur = []
        cur.append(m)
        if not live:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    log(f"{len(todo)} markets to download in {len(groups)} requests (~{len(groups) * 1.5 / 60:.0f} min)")
    done = 0
    for n, g in enumerate(groups):
        try:
            if g[0]["close"] < cutoff:
                bs = [bars_one(g[0])]
            else:
                try:
                    bs = bars_batch(g)
                except requests.HTTPError:                  # more than 10,000 candles: ask in halves
                    h = len(g) // 2
                    bs = bars_batch(g[:h]) + bars_batch(g[h:]) if h else [[]]
        except Exception as e:
            log(f"  {g[0]['ticker']}: {e!r}"[:300])
            continue
        for m, b in zip(g, bs):
            files[m["series"]].write(json.dumps(dict(m, bars=b), separators=(",", ":")) + "\n")
            files[m["series"]].flush()
        done += len(g)
        if (n + 1) % 100 == 0:
            log(f"  {done} / {len(todo)} markets  (429 answers so far: {STATS['429']}, gap {GAP_NOW[0]:.1f}s)")
    log("done")


if __name__ == "__main__":
    main()
