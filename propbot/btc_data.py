"""Download BTCUSDT 5-minute candles from Binance's public data mirror (data-api.binance.vision) and cache them."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "btc" / "btcusdt_5m.csv.gz"
URL = "https://data-api.binance.vision/api/v3/klines"


def download(start: str = "2019-01-01", end: str | None = None, symbol: str = "BTCUSDT") -> pd.DataFrame:
    t0 = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    t_end = int((pd.Timestamp(end, tz="UTC") if end else pd.Timestamp.now(tz="UTC")).timestamp() * 1000)
    rows = []
    s = requests.Session()
    n = 0
    while t0 < t_end:
        for attempt in range(5):
            try:
                r = s.get(URL, params={"symbol": symbol, "interval": "5m", "startTime": t0, "limit": 1000}, timeout=30)
                if r.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(2 * (attempt + 1))
        data = r.json()
        if not data:
            break
        rows.extend(data)
        t0 = data[-1][0] + 300_000
        n += 1
        if n % 100 == 0:
            print(f"  {len(rows):,} bars, up to {pd.Timestamp(t0, unit='ms', tz='UTC')}", flush=True)
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume", "close_time", "qv", "trades", "tbb", "tbq", "ignore"])
    df = df[["open_time", "open", "high", "low", "close", "volume"]].astype({"open": float, "high": float, "low": float, "close": float, "volume": float})
    df["time"] = pd.to_datetime(df.open_time, unit="ms", utc=True)
    df = df.drop(columns="open_time").drop_duplicates("time").sort_values("time")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, compression="gzip")
    print(f"wrote {len(df):,} bars to {OUT}")
    return df


def load() -> pd.DataFrame:
    df = pd.read_csv(OUT)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


if __name__ == "__main__":
    download(sys.argv[1] if len(sys.argv) > 1 else "2019-01-01")
