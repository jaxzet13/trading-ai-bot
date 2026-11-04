"""Forward recorder for the non-crypto 15-minute markets: every minute, the Pyth price of every feed Kalshi settles
these markets on, plus Kalshi's quotes for each open market in those series, so future tests have exact data.

    nice -n 19 python3 -u -m kalshi15m record-pyth             # runs until stopped (Ctrl-C)
    nice -n 19 python3 -u -m kalshi15m record-pyth --once      # one snapshot, then exit (smoke test)
    nice -n 19 python3 -u -m kalshi15m record-pyth --minutes 60

Output (one file per UTC day, appended, header on first write) under data/kalshi15m/lab4/live/:
  pyth_YYYY-MM-DD.csv    ts (the minute, UTC seconds), fetched_ts, then per series: <SERIES> = Pyth price,
                         <SERIES>_pt = Pyth publish time, <SERIES>_conf = confidence
  kalshi_YYYY-MM-DD.csv  ts, fetched_ts, series, ticker, open_ts, close_ts, floor_strike (= Pyth at the open),
                         yes_bid, yes_ask, yes_bid_size, yes_ask_size, last_price, volume, open_interest

Pyth: Hermes /v2/updates/price/latest, all feeds in one request. Since 2026 Hermes answers 401 without an API key:
set PYTH_API_KEY (sent as a Bearer token and x-api-key). Without a key the recorder still writes the Kalshi file
(floor_strike is the exact Pyth print at each open) and warns once per hour that Pyth is unavailable.

Kalshi: ONE GET /markets per minute (every open non-multivariate market closing within 16 minutes; one request per
series only as a fallback), exponential back-off on 429 (the bots share this IP). Nothing here trades.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from .data import KALSHI
from .data_fx import LDIR, _Lim
from .lab4p import HERMES, PYTH

LIVE = LDIR / "live"
SERIES = list(PYTH)
_k = requests.Session()
_KLIM = _Lim(1.0)


def _f(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _ts(s):
    return int(pd.Timestamp(s).timestamp()) if s else None


def kalshi_open(series=None):
    """Open markets of one series, or (series=None) every open non-multivariate market closing within 16 minutes,
    in ONE request; the caller keeps the series it records."""
    if series:
        params = {"series_ticker": series, "status": "open", "limit": 50}
    else:
        now = int(time.time())
        params = {"status": "open", "min_close_ts": now, "max_close_ts": now + 16 * 60, "limit": 1000,
                  "mve_filter": "exclude"}
    for i in range(6):
        _KLIM.wait()
        try:
            r = _k.get(f"{KALSHI}/markets", params=params, timeout=15)
        except requests.RequestException:
            time.sleep(min(20, 2 ** i))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(20, 2 ** (i + 1)))
            continue
        if r.status_code != 200:
            return []
        return r.json().get("markets", [])
    return []


def _hermes():
    s = requests.Session()
    key = os.environ.get("PYTH_API_KEY") or os.environ.get("PYTH_HERMES_KEY")
    if key:
        s.headers["Authorization"] = f"Bearer {key}"
        s.headers["x-api-key"] = key
    return s


_h = _hermes()


def pyth_latest():
    """-> ({series: (price, publish_time, conf)}, status)."""
    ids = {v[1]: k for k, v in PYTH.items()}
    try:
        r = _h.get(f"{HERMES}/v2/updates/price/latest", params=[("ids[]", x) for x in ids] + [("parsed", "true"),
                   ("ignore_invalid_price_ids", "true")], timeout=10)
    except requests.RequestException as e:
        return {}, f"error {e.__class__.__name__}"
    if r.status_code != 200:
        return {}, f"HTTP {r.status_code}"
    out = {}
    for p in r.json().get("parsed", []):
        q, e = p["price"], int(p["price"]["expo"])
        out[ids.get(p["id"], p["id"])] = (int(q["price"]) * 10 ** e, int(q["publish_time"]), int(q["conf"]) * 10 ** e)
    return out, "ok"


def _append(path: Path, rows, cols):
    if not rows:
        return
    df = pd.DataFrame(rows).reindex(columns=cols)
    df.to_csv(path, mode="a", header=not path.exists(), index=False)


PCOLS = ["ts", "fetched_ts"] + [c for s in SERIES for c in (s, f"{s}_pt", f"{s}_conf")]
KCOLS = ["ts", "fetched_ts", "series", "ticker", "open_ts", "close_ts", "floor_strike", "yes_bid", "yes_ask",
         "yes_bid_size", "yes_ask_size", "last_price", "volume", "open_interest"]


def snapshot(state):
    minute = int(time.time()) // 60 * 60
    day = pd.to_datetime(minute, unit="s").strftime("%Y-%m-%d")
    LIVE.mkdir(parents=True, exist_ok=True)
    px, status = pyth_latest()
    prow = {"ts": minute, "fetched_ts": round(time.time(), 2)}
    for s, (p, pt, cf) in px.items():
        prow.update({s: p, f"{s}_pt": pt, f"{s}_conf": cf})
    if px:
        _append(LIVE / f"pyth_{day}.csv", [prow], PCOLS)
    elif time.time() - state.get("warned", 0) > 3600:
        print(f"  Pyth unavailable ({status}); set PYTH_API_KEY. Recording Kalshi only.", flush=True)
        state["warned"] = time.time()
    krows = []
    allm = kalshi_open()
    if not allm:                                   # fall back to one request per series
        allm = [m for s in SERIES for m in kalshi_open(s)]
    for m in allm:
        s = m["ticker"].split("-")[0]
        if s in PYTH:
            if m.get("status") not in ("active", "open"):
                continue
            krows.append({"ts": minute, "fetched_ts": round(time.time(), 2), "series": s, "ticker": m["ticker"],
                          "open_ts": _ts(m.get("open_time")), "close_ts": _ts(m.get("close_time")),
                          "floor_strike": _f(m.get("floor_strike")),
                          "yes_bid": _f(m.get("yes_bid_dollars")), "yes_ask": _f(m.get("yes_ask_dollars")),
                          "yes_bid_size": _f(m.get("yes_bid_size_fp")), "yes_ask_size": _f(m.get("yes_ask_size_fp")),
                          "last_price": _f(m.get("last_price_dollars")), "volume": _f(m.get("volume_fp")),
                          "open_interest": _f(m.get("open_interest_fp"))})
    _append(LIVE / f"kalshi_{day}.csv", krows, KCOLS)
    return len(px), len(krows), status


def main(args):
    once = "--once" in args
    minutes = int(args[args.index("--minutes") + 1]) if "--minutes" in args else None
    try:
        os.nice(19)
    except OSError:
        pass
    state, n = {}, 0
    print(f"record-pyth: {len(SERIES)} series -> {LIVE}", flush=True)
    while True:
        t0 = time.time()
        try:
            npx, nk, status = snapshot(state)
            if once or n % 15 == 0:
                print(f"  {pd.Timestamp.utcnow():%Y-%m-%d %H:%M} pyth {npx} feeds ({status}), kalshi {nk} open markets",
                      flush=True)
        except Exception as e:                    # keep recording through transient errors
            print(f"  snapshot failed: {e!r}", flush=True)
        n += 1
        if once or (minutes and n >= minutes):
            return 0
        nxt = (int(time.time()) // 60 + 1) * 60 + 2      # 2 s after the next minute boundary
        time.sleep(max(1.0, nxt - time.time()))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
