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
    if st.get("done") and st.get("oldest_ts") is not None and st["oldest_ts"] <= since_ts:
        log(f"{product}: already complete back to {since} ({len(bars)} bars)")
        return out
    st["done"] = False                        # (an earlier, shorter run can be extended further back)
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
    args = list(args or [])
    since = next((a.split("=", 1)[1] for a in args if a.startswith(("--since=", "since="))), None)
    prods = [a for a in args if a.endswith("-USD")] or list(DEFAULT_SINCE)
    for p in prods:
        fetch(p, since or DEFAULT_SINCE.get(p, "2026-06-25"))


if __name__ == "__main__":
    main(sys.argv[1:])


# --------------------------------------------------------------------------- parallel segments (by trade id)
def trade_at(product, tid, s=None):
    """(trade id, time) of the trade just below `tid` (Coinbase's `after` cursor)."""
    s = s or requests.Session()
    for a in range(20):
        r = s.get(f"{API}/products/{product}/trades", params={"limit": 1, "after": str(tid)}, timeout=20)
        if r.status_code == 429:
            time.sleep(2 + a)
            continue
        r.raise_for_status()
        x = r.json()[0]
        return int(x["trade_id"]), _ts(x["time"])
    raise RuntimeError("rate limited")


def id_for_time(product, t_target, hi_id, s=None):
    """Smallest trade id whose time is >= t_target (binary search on ids below hi_id)."""
    s = s or requests.Session()
    lo, hi = 1, hi_id
    while hi - lo > 500:
        mid = (lo + hi) // 2
        _, t = trade_at(product, mid, s)
        if t < t_target:
            lo = mid
        else:
            hi = mid
        time.sleep(0.2)
    return lo


def fetch_segment(product, id_hi, id_lo, out, pace=0.25, log=print):
    """Every trade with id in (id_lo, id_hi] -> per-minute bars with first/last trade ids (for merging)."""
    s = requests.Session()
    bars, after, n = {}, id_hi + 1, 0
    part = Path(str(out) + ".partial.json")
    if part.exists():                                   # resume after a container restart
        st = json.loads(part.read_text())
        bars = {int(k): v for k, v in st["bars"].items()}
        after = st["after"]
        log(f"{product} segment {id_lo}-{id_hi}: resuming at trade id {after} ({len(bars)} minutes)")
    while True:
        for a in range(30):
            try:
                r = s.get(f"{API}/products/{product}/trades", params={"limit": 1000, "after": str(after)}, timeout=20)
            except requests.RequestException:
                time.sleep(3)
                continue
            if r.status_code == 429:
                time.sleep(min(2 + 2 * a, 20))
                continue
            r.raise_for_status()
            break
        tr = [x for x in r.json() if int(x["trade_id"]) > id_lo]
        n += 1
        for x in tr:
            t, px, sz, tid = _ts(x["time"]), float(x["price"]), float(x["size"]), int(x["trade_id"])
            m = int(t // 60 * 60)
            b = bars.get(m)
            if b is None:
                bars[m] = [px, px, px, px, sz, tid, tid]
            else:
                if tid < b[5]:
                    b[0], b[5] = px, tid
                if tid > b[6]:
                    b[3], b[6] = px, tid
                b[1], b[2], b[4] = max(b[1], px), min(b[2], px), b[4] + sz
        if not tr or min(int(x["trade_id"]) for x in r.json()) <= id_lo + 1:
            break
        after = min(int(x["trade_id"]) for x in tr)
        if n % 100 == 0:
            part.write_text(json.dumps({"after": after, "bars": bars}))
            log(f"{product} segment {id_lo}-{id_hi}: {n} requests, back to "
                f"{datetime.utcfromtimestamp(min(bars)):%Y-%m-%d %H:%M}")
        time.sleep(pace)
    pd.DataFrame([(ts, *b) for ts, b in sorted(bars.items())],
                 columns=["ts", "open", "high", "low", "close", "volume", "first_tid", "last_tid"]).to_csv(out, index=False)
    part.unlink(missing_ok=True)
    log(f"{product} segment {id_lo}-{id_hi}: done, {len(bars)} minutes ({n} requests)")


def merge_segments(product, log=print):
    """Merge segment files into {product}_bars.csv (a minute split across segments: open from the lower ids,
    close from the higher ids, high/low/volume combined)."""
    main = DIR / f"{product}_bars.csv"
    parts = [pd.read_csv(main).assign(first_tid=None, last_tid=None)] if main.exists() else []
    segs = sorted(DIR.glob(f"{product}_seg_*.csv"))
    parts += [pd.read_csv(f) for f in segs]
    df = pd.concat(parts, ignore_index=True)
    rows = []
    for ts, g in df.groupby("ts"):
        if len(g) == 1:
            r = g.iloc[0]
            rows.append((ts, r.low, r.high, r.open, r.close, r.volume))
            continue
        g = g.assign(f_id=pd.to_numeric(g.first_tid, errors="coerce"), l_id=pd.to_numeric(g.last_tid, errors="coerce"))
        o = g.loc[g.f_id.idxmin()].open if g.f_id.notna().any() else g.iloc[0].open
        c = g.loc[g.l_id.idxmax()].close if g.l_id.notna().any() else g.iloc[-1].close
        rows.append((ts, g.low.min(), g.high.max(), o, c, g.volume.sum()))
    out = pd.DataFrame(rows, columns=["ts", "low", "high", "open", "close", "volume"]).sort_values("ts")
    out.to_csv(main, index=False)
    log(f"{product}: merged {len(segs)} segments -> {len(out)} minutes from "
        f"{datetime.utcfromtimestamp(out.ts.min()):%Y-%m-%d}")
