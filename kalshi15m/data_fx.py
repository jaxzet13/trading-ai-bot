"""Data for lab4: Kalshi 15-minute markets beyond the 9 crypto coins (FX, commodities, indices,
rates, extra crypto) plus their underlying 1-minute prices.

    python -m kalshi15m lab4 survey      -> data/lab/lab4_survey.json
    python -m kalshi15m lab4 download    -> data/kalshi15m/lab4/{SERIES}_{markets,candles,spot}.csv

Kalshi: public trade API, ONE request at a time, <= 2 requests/second, exponential back-off on 429
(the paper and demo bots share this IP).

Underlying prices:
  * Kalshi's FX / metals / energy / rates contracts settle on Pyth. Pyth's own history API now needs
    an API key (the free Benchmarks TradingView shim was sunset in Aug 2026), and Yahoo's chart API
    answered 429 from this IP, so we use Dukascopy's free 1-minute BID candles instead
    (datafeed.dukascopy.com, one LZMA file per symbol per day, month index 0-based). Dukascopy is a
    different venue than Pyth: we measure how often its sign agrees with Kalshi's settlement.
  * Extra crypto (BCH, ADA, TON) settle on CF Benchmarks; Coinbase 1-minute candles as for the 9 coins.
Nothing here is used by the live bots.
"""
from __future__ import annotations

import json
import lzma
import struct
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .data import KALSHI, _candle_row, _chunks, _ts, fetch_spot

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "kalshi15m"
LDIR = DATA_DIR / "lab4"
DUKA_DIR = LDIR / "duka"
SURVEY_OUT = DATA_DIR.parent / "lab" / "lab4_survey.json"

# Kalshi series -> (underlying source, symbol, price scale for Dukascopy integers)
UNDERLYING = {
    "KXEURUSD15M": ("duka", "EURUSD", 1e-5), "KXGBPUSD15M": ("duka", "GBPUSD", 1e-5),
    "KXAUDUSD15M": ("duka", "AUDUSD", 1e-5), "KXUSDCAD15M": ("duka", "USDCAD", 1e-5),
    "KXUSDJPY15M": ("duka", "USDJPY", 1e-3), "KXUSDMXN15M": ("duka", "USDMXN", 1e-5),
    "KXGOLD15M": ("duka", "XAUUSD", 1e-3), "KXSILVER15M": ("duka", "XAGUSD", 1e-5),
    "KXWTI15M": ("duka", "LIGHTCMDUSD", 1e-3), "KXBRENT15M": ("duka", "BRENTCMDUSD", 1e-3),
    "KXCOPPER15M": ("duka", "COPPERCMDUSD", 1e-5), "KXNATGAS15M": ("duka", "GASCMDUSD", 1e-5),
    "KXINX15M": ("duka", "USA500IDXUSD", 1e-3), "KXNDQ15M": ("duka", "USATECHIDXUSD", 1e-3),
    "KXDJIA15M": ("duka", "USA30IDXUSD", 1e-3),
    "KXBCH15M": ("coinbase", "BCH-USD", None), "KXADA15M": ("coinbase", "ADA-USD", None),
    "KXTON15M": ("coinbase", "TON-USD", None),
}

_s = requests.Session()
_s.headers["User-Agent"] = "Mozilla/5.0 (research script)"


class _Lim:
    """Global <= `per_sec` requests/second, single-threaded."""

    def __init__(self, per_sec):
        self.gap, self.last = 1.0 / per_sec, 0.0

    def wait(self):
        dt = time.time() - self.last
        if dt < self.gap:
            time.sleep(self.gap - dt)
        self.last = time.time()


_KLIM = _Lim(2.0)


def kget(path, params=None, tries=10):
    for i in range(tries):
        _KLIM.wait()
        try:
            r = _s.get(f"{KALSHI}{path}", params=params, timeout=30)
        except requests.RequestException:
            time.sleep(min(60, 2 ** i))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(60, 2 ** (i + 1)))
            continue
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Kalshi {path} failed after {tries} tries")


def _mrow(m):
    if m.get("result") not in ("yes", "no"):
        return None
    fs = m.get("floor_strike")
    return {"ticker": m["ticker"], "event": m.get("event_ticker"), "open_ts": _ts(m["open_time"]),
            "close_ts": _ts(m["close_time"]),
            "strike": float(str(fs).replace(",", "")) if fs is not None else np.nan,
            "cap_strike": float(str(m["cap_strike"]).replace(",", "")) if m.get("cap_strike") is not None else np.nan,
            "strike_type": m.get("strike_type"),
            "settle_value": float(str(m["expiration_value"]).replace(",", "")) if m.get("expiration_value") else np.nan,
            "result": 1 if m["result"] == "yes" else 0,
            "volume": float(m.get("volume_fp") or m.get("volume") or 0)}


def fetch_settled(series, max_pages=60, hist=True):
    """All settled markets: live API (after Kalshi's historical cutoff) + /historical (before)."""
    rows = []
    for path in (["/markets", "/historical/markets"] if hist else ["/markets"]):
        cursor, pages = None, 0
        while pages < max_pages:
            p = {"series_ticker": series, "limit": 1000}
            if path == "/markets":
                p["status"] = "settled"
            if cursor:
                p["cursor"] = cursor
            d = kget(path, p)
            ms = d.get("markets", [])
            rows += [r for r in map(_mrow, ms) if r]
            cursor, pages = d.get("cursor"), pages + 1
            if not cursor or not ms:
                break
    if not rows:
        return pd.DataFrame(columns=["ticker", "open_ts", "close_ts", "strike", "result", "volume"])
    return pd.DataFrame(rows).drop_duplicates("ticker").sort_values("open_ts").reset_index(drop=True)


def fetch_candles(series, markets, part: Path, every_log=50):
    """1-minute candles via the batch endpoint (live API markets only); resumable via `part`."""
    done = set(pd.read_csv(part, usecols=["ticker"]).ticker) if part.exists() else set()
    todo = markets[~markets.ticker.isin(done)]
    n = 0
    for chunk in _chunks(todo):
        params = {"market_tickers": ",".join(m.ticker for m in chunk),
                  "start_ts": min(m.open_ts for m in chunk) - 60, "end_ts": max(m.close_ts for m in chunk) + 60,
                  "period_interval": 1}
        d = kget("/markets/candlesticks", params)
        rows = []
        for m in d.get("markets", []):
            tk = m.get("market_ticker") or m.get("ticker")
            rows += [_candle_row(tk, c) for c in m.get("candlesticks", [])]
        got = {r["ticker"] for r in rows}
        rows += [{"ticker": m.ticker, "ts": -1} for m in chunk if m.ticker not in got]   # mark as done
        pd.DataFrame(rows).to_csv(part, mode="a", header=not part.exists(), index=False)
        n += 1
        if n % every_log == 0:
            print(f"    {series} candle batches {n}", flush=True)


def fetch_candles_hist(series, markets, part: Path):
    """Archive markets (before the cutoff): one request per market."""
    done = set(pd.read_csv(part, usecols=["ticker"]).ticker) if part.exists() else set()
    todo = markets[~markets.ticker.isin(done)]
    buf = []
    for i, m in enumerate(todo.itertuples()):
        d = kget(f"/historical/markets/{m.ticker}/candlesticks",
                 {"start_ts": m.open_ts - 60, "end_ts": m.close_ts + 60, "period_interval": 1})
        rows = [_candle_row(m.ticker, c) for c in d.get("candlesticks", [])] or [{"ticker": m.ticker, "ts": -1}]
        buf += rows
        if (i + 1) % 200 == 0 or i == len(todo) - 1:
            pd.DataFrame(buf).to_csv(part, mode="a", header=not part.exists(), index=False)
            buf = []
            print(f"    {series} archive candles {i + 1}/{len(todo)}", flush=True)


# =========================================================================== Dukascopy
def duka_day(sym, day: datetime, scale):
    """1-minute BID candles for one UTC day (bar start ts). Cached as .bi5 files."""
    DUKA_DIR.mkdir(parents=True, exist_ok=True)
    f = DUKA_DIR / f"{sym}_{day:%Y%m%d}.bi5"
    if not f.exists():
        url = (f"https://datafeed.dukascopy.com/datafeed/{sym}/{day.year}/{day.month - 1:02d}/{day.day:02d}/"
               "BID_candles_min_1.bi5")
        for i in range(6):
            try:
                r = _s.get(url, timeout=30)
            except requests.RequestException:
                time.sleep(2 ** i)
                continue
            if r.status_code == 200:
                f.write_bytes(r.content)
                break
            if r.status_code == 404:
                f.write_bytes(b"")
                break
            time.sleep(2 ** i)
        time.sleep(0.3)
    raw = f.read_bytes() if f.exists() else b""
    if not raw:
        return None
    raw = lzma.decompress(raw)
    n = len(raw) // 24
    a = np.array(struct.unpack(">" + "5if" * n, raw[:24 * n]), dtype=float).reshape(n, 6)
    t0 = int(day.replace(tzinfo=timezone.utc).timestamp())
    df = pd.DataFrame({"ts": t0 + a[:, 0].astype(np.int64), "open": a[:, 1] * scale, "close": a[:, 2] * scale,
                       "low": a[:, 3] * scale, "high": a[:, 4] * scale, "volume": a[:, 5]})
    return df


def duka_range(sym, scale, start_ts, end_ts):
    d0 = datetime.fromtimestamp(start_ts, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    d1 = datetime.fromtimestamp(end_ts, timezone.utc).replace(tzinfo=None)
    out, d = [], d0
    while d <= d1:
        x = duka_day(sym, d, scale)
        if x is not None and len(x):
            out.append(x)
        d += timedelta(days=1)
    df = pd.concat(out, ignore_index=True)
    # Dukascopy pads closed-market minutes with flat zero-volume bars; keep them (ffill semantics)
    return df[(df.ts >= start_ts) & (df.ts <= end_ts)].drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


# =========================================================================== survey
def survey(series_list, out=SURVEY_OUT):
    rows = {}
    if out.exists():
        rows = json.loads(out.read_text())
    for s in series_list:
        if s in rows:
            continue
        t0 = time.time()
        mk = fetch_settled(s, max_pages=40)
        if len(mk) == 0:
            rows[s] = {"markets": 0}
        else:
            days = (mk.open_ts.max() - mk.open_ts.min()) / 86400
            rec = mk[mk.open_ts >= mk.open_ts.max() - 14 * 86400]
            rows[s] = {"markets": int(len(mk)), "first": f"{pd.to_datetime(mk.open_ts.min(), unit='s'):%Y-%m-%d}",
                       "last": f"{pd.to_datetime(mk.open_ts.max(), unit='s'):%Y-%m-%d}", "span_days": round(days, 1),
                       "markets_per_day_recent": round(len(rec) / 14, 1),
                       "median_volume": float(mk.volume.median()), "mean_volume_recent": round(float(rec.volume.mean()), 1),
                       "zero_volume_frac": round(float((mk.volume == 0).mean()), 3),
                       "yes_rate": round(float(mk.result.mean()), 3),
                       "strike_types": sorted(map(str, mk.strike_type.dropna().unique()))[:4]}
            LDIR.mkdir(parents=True, exist_ok=True)
            mk.to_csv(LDIR / f"{s}_markets_all.csv", index=False)
        print(f"  {s}: {rows[s]} ({time.time() - t0:.0f}s)", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, indent=1))
    return rows


# =========================================================================== download for lab4
def download(series, since_ts=None, hist_every=1):
    """Markets (cached by survey), 1-minute candles, underlying spot -> data/kalshi15m/lab4/."""
    LDIR.mkdir(parents=True, exist_ok=True)
    mpath = LDIR / f"{series}_markets_all.csv"
    mk = pd.read_csv(mpath) if mpath.exists() else fetch_settled(series)
    if since_ts:
        mk = mk[mk.open_ts >= since_ts]
    mk = mk[np.isfinite(mk.strike)]
    cutoff = _ts(kget("/historical/cutoff")["market_settled_ts"])
    live, old = mk[mk.close_ts >= cutoff], mk[mk.close_ts < cutoff].iloc[::hist_every]
    part = LDIR / f"{series}_candles.part.csv"
    print(f"  {series}: {len(live)} live + {len(old)} archive markets", flush=True)
    fetch_candles(series, live, part)
    if len(old):
        fetch_candles_hist(series, old, LDIR / f"{series}_candles_hist.part.csv")
    src, sym, scale = UNDERLYING[series]
    lo, hi = int(mk.open_ts.min()) - 6 * 3600, int(mk.close_ts.max()) + 120
    spath = LDIR / f"{series}_spot.csv"
    if not spath.exists():
        sp = duka_range(sym, scale, lo, hi) if src == "duka" else fetch_spot(sym, lo, hi)
        sp.to_csv(spath, index=False)
    mk.to_csv(LDIR / f"{series}_markets.csv", index=False)


def load(series):
    mk = pd.read_csv(LDIR / f"{series}_markets.csv")
    parts = [p for p in (LDIR / f"{series}_candles.part.csv", LDIR / f"{series}_candles_hist.part.csv") if p.exists()]
    cd = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
    cd = cd[cd.ts > 0].drop_duplicates(["ticker", "ts"])
    sp = pd.read_csv(LDIR / f"{series}_spot.csv")
    return mk, cd, sp
