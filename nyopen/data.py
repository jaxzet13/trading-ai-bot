"""Download NAS100 (USATECHIDXUSD) 1-minute candles from Dukascopy and cache them.

Dukascopy publishes one LZMA-compressed file per instrument per UTC day:
    https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM-1}/{DD}/BID_candles_min_1.bi5
Each record is 24 bytes big-endian: seconds-since-midnight, open, close, low, high (int, x1000), volume (float).
"""
from __future__ import annotations

import concurrent.futures as cf
import io
import lzma
import os
import struct
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

SYMBOL = "USATECHIDXUSD"
PRICE_SCALE = 1000.0
BASE = "https://datafeed.dukascopy.com/datafeed"
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
M1_PATH = ROOT / "data" / "nas100_m1.csv.gz"
HEADERS = {"User-Agent": "Mozilla/5.0 (research backtester)"}
REC = struct.Struct(">IIIIIf")


SCALES = {"USATECHIDXUSD": 1000.0, "USA30IDXUSD": 1000.0, "USA500IDXUSD": 1000.0, "XAUUSD": 1000.0, "USDJPY": 1000.0,
          "EURUSD": 100000.0, "GBPUSD": 100000.0}


def paths(symbol: str = SYMBOL) -> tuple[Path, Path]:
    """(cache dir, 1-minute csv) for a symbol. NAS100 keeps its original paths."""
    if symbol == SYMBOL:
        return CACHE_DIR, M1_PATH
    return ROOT / "data" / f"cache_{symbol}", ROOT / "data" / f"{symbol.lower()}_m1.csv.gz"


def day_url(d: date, symbol: str = SYMBOL) -> str:
    return f"{BASE}/{symbol}/{d.year}/{d.month - 1:02d}/{d.day:02d}/BID_candles_min_1.bi5"


def fetch_day(d: date, session: requests.Session, retries: int = 5, symbol: str = SYMBOL) -> bytes | None:
    """Return raw bi5 bytes for a day, b"" if the day has no file (weekend/holiday), None on failure."""
    url = day_url(d, symbol)
    for attempt in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return b""
            if r.status_code == 200:
                if r.content[:5] == b"<!DOC":
                    return b""
                return r.content
            time.sleep(1.5 * (attempt + 1))
        except requests.RequestException:
            time.sleep(1.5 * (attempt + 1))
    return None


def decode_day(d: date, raw: bytes, scale: float = PRICE_SCALE) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    data = lzma.decompress(raw)
    n = len(data) // REC.size
    arr = np.frombuffer(data[: n * REC.size], dtype=np.dtype(">u4, >u4, >u4, >u4, >u4, >f4"))
    df = pd.DataFrame({
        "time": pd.Timestamp(d, tz="UTC") + pd.to_timedelta(arr["f0"].astype("int64"), unit="s"),
        "open": arr["f1"] / scale,
        "close": arr["f2"] / scale,
        "low": arr["f3"] / scale,
        "high": arr["f4"] / scale,
        "volume": arr["f5"].astype("float64"),
    })
    # Dukascopy pads closed-market minutes with flat zero-volume candles; drop them.
    flat = (df.open == df.close) & (df.high == df.low) & (df.volume == 0)
    return df[~flat].reset_index(drop=True)


def download(start: date, end: date, workers: int = 6, verbose: bool = True, symbol: str = SYMBOL) -> None:
    """Fetch any missing day files into the symbol's cache dir (idempotent, resumable)."""
    cache, _ = paths(symbol)
    cache.mkdir(parents=True, exist_ok=True)
    days = [start + timedelta(i) for i in range((end - start).days + 1)]
    todo = [d for d in days if d.weekday() != 5 and not (cache / f"{d:%Y-%m-%d}.bi5").exists()]
    if verbose:
        print(f"{len(todo)} day files to fetch ({start} .. {end})", flush=True)
    session = requests.Session()
    failed: list[date] = []

    def job(d: date):
        raw = fetch_day(d, session, symbol=symbol)
        if raw is None:
            return d, None
        (cache / f"{d:%Y-%m-%d}.bi5").write_bytes(raw)
        return d, len(raw)

    done = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for d, n in ex.map(job, todo):
            done += 1
            if n is None:
                failed.append(d)
            if verbose and done % 100 == 0:
                print(f"  {done}/{len(todo)} fetched, {len(failed)} failed", flush=True)
    if failed:
        print(f"WARNING: {len(failed)} days failed: {failed[:10]}...", file=sys.stderr)


def build_m1(verbose: bool = True, symbol: str = SYMBOL) -> pd.DataFrame:
    """Decode every cached day into one 1-minute frame and write the symbol's csv.gz."""
    cache, m1 = paths(symbol)
    scale = SCALES.get(symbol, PRICE_SCALE)
    frames = []
    for p in sorted(cache.glob("*.bi5")):
        raw = p.read_bytes()
        if raw:
            frames.append(decode_day(date.fromisoformat(p.stem), raw, scale))
    df = pd.concat(frames, ignore_index=True).sort_values("time").drop_duplicates("time")
    df.to_csv(m1, index=False, compression="gzip")
    if verbose:
        print(f"wrote {len(df):,} 1-minute bars to {m1} ({df.time.min()} .. {df.time.max()})")
    return df


def load_m1(symbol: str = SYMBOL) -> pd.DataFrame:
    _, m1 = paths(symbol)
    df = pd.read_csv(m1, parse_dates=["time"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def resample(df: pd.DataFrame, minutes: int = 5) -> pd.DataFrame:
    """Resample 1-minute bars to N-minute bars in New York time (bars labelled by open time)."""
    s = df.set_index("time").tz_convert("America/New_York")
    out = s.resample(f"{minutes}min", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum")
    ).dropna(subset=["open"])
    return out.reset_index()


if __name__ == "__main__":
    # python -m nyopen.data [start] [end] [SYMBOL ...]
    start = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2019, 1, 1)
    end = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today() - timedelta(days=1)
    for sym in (sys.argv[3:] or [SYMBOL]):
        print(f"== {sym}", flush=True)
        download(start, end, symbol=sym)
        build_m1(symbol=sym)
