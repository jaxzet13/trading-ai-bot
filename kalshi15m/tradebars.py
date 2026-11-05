"""1-minute bars built from Coinbase's public trade list (python -m kalshi15m tradebars [PRODUCT ...]).

Why: for thinly traded coins (NEAR, HYPE, DOGE, BNB) Coinbase's 1-minute *candles* include trades that never
appear in the public trade feed / trade list (checked live 2026-11-05: the websocket matched /trades exactly in
every minute, the candle did not), so a backtest on candles sees prices the live bot cannot. Bars built here from
/products/{p}/trades are exactly what the live trade stream (kalshi15m.streams.CoinbaseBars) builds.

Pages backwards through the trade list (cursor = trade id, 1000 per request) from now to --since, aggregating
open/high/low/close/volume per minute of the trade time. Resumable: progress is kept in
data/kalshi15m/tradebars/{PRODUCT}.state.json and the bars in {PRODUCT}_bars.csv (same columns as the spot csvs:
ts, low, high, open, close, volume; minutes without trades are absent, as with candles).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "kalshi15m" / "tradebars"
API = "https://api.exchange.coinbase.com"
DEFAULT_SINCE = {"NEAR-USD": "2026-06-25", "HYPE-USD": "2026-08-05", "DOGE-USD": "2026-03-25", "BNB-USD": "2026-03-25"}


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def fetch(product: str, since: str, pace: float = 0.25, log=print):
    DIR.mkdir(parents=True, exist_ok=True)
    st_path, out = DIR / f"{product}.state.json", DIR / f"{product}_bars.csv"
    since_ts = pd.Timestamp(since, tz="UTC").timestamp()
    st = json.loads(st_path.read_text()) if st_path.exists() else {"after": None, "oldest_ts": None, "done": False}
    bars = {}
    if out.exists():
        for r in pd.read_csv(out).itertuples(index=False):
            bars[int(r.ts)] = [r.open, r.high, r.low, r.close, r.volume, None, None]   # first/last trade id unknown
    if st.get("done"):
        log(f"{product}: already complete ({len(bars)} bars)")
        return out
    s = requests.Session()
    n_req, t0 = 0, time.time()
    newest_seen = {}            # minute -> highest trade id applied (to keep close = last trade, open = first)

    def flush():
        rows = [(ts, b[2], b[1], b[0], b[3], b[4]) for ts, b in sorted(bars.items())]
        df = pd.DataFrame(rows, columns=["ts", "low", "high", "open", "close", "volume"])
        tmp = out.with_suffix(".tmp")
        df.to_csv(tmp, index=False)
        os.replace(tmp, out)
        st_path.write_text(json.dumps(st))

    while True:
        params = {"limit": 1000}
        if st["after"]:
            params["after"] = st["after"]
        for a in range(30):
            try:
                r = s.get(f"{API}/products/{product}/trades", params=params, timeout=20)
            except requests.RequestException:
                time.sleep(3)
                continue
            if r.status_code == 429:
                time.sleep(min(2 + 2 * a, 20))
                continue
            r.raise_for_status()
            break
        else:
            raise RuntimeError(f"{product}: Coinbase trades unavailable")
        tr = r.json()
        n_req += 1
        if not tr:
            st["done"] = True
            break
        # trades come newest first; we walk backwards in time, so within a minute later pages hold EARLIER trades
        for x in tr:
            t, px, sz, tid = _ts(x["time"]), float(x["price"]), float(x["size"]), int(x["trade_id"])
            m = int(t // 60 * 60)
            b = bars.get(m)
            if b is None:
                bars[m] = [px, px, px, px, sz, tid, tid]      # open, high, low, close, vol, first id, last id
            else:
                if b[5] is None or tid < b[5]:
                    b[0], b[5] = px, tid                      # earlier trade -> new open
                if b[6] is None or tid > b[6]:
                    b[3], b[6] = px, tid                      # later trade -> new close
                b[1], b[2], b[4] = max(b[1], px), min(b[2], px), b[4] + sz
        oldest = min(_ts(x["time"]) for x in tr)
        st["oldest_ts"] = oldest
        st["after"] = r.headers.get("cb-after") or str(min(int(x["trade_id"]) for x in tr))
        if n_req % 50 == 0:
            flush()
            log(f"{product}: {n_req} requests, back to {datetime.utcfromtimestamp(oldest):%Y-%m-%d %H:%M} UTC, "
                f"{len(bars)} minutes, {time.time() - t0:.0f}s")
        if oldest < since_ts:
            st["done"] = True
            break
        time.sleep(pace)
    flush()
    log(f"{product}: done, {len(bars)} minutes from {datetime.utcfromtimestamp(min(bars)):%Y-%m-%d} "
        f"({n_req} requests, {time.time() - t0:.0f}s)")
    return out


def main(args=None):
    prods = [a for a in (args or []) if "-" in a] or list(DEFAULT_SINCE)
    for p in prods:
        fetch(p, DEFAULT_SINCE.get(p, "2026-06-25"))


if __name__ == "__main__":
    main(sys.argv[1:])
