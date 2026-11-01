"""Historical data download + caching for Kalshi 15-minute crypto up/down markets.

Sources (all public, no API key needed):
  * Kalshi trade API  -> settled markets (strike, result) + 1-minute bid/ask candles
  * Coinbase Exchange -> 1-minute spot candles (proxy for CF Benchmarks BRTI)
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
COINBASE = "https://api.exchange.coinbase.com"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "kalshi15m"

SERIES = {  # Kalshi series ticker -> Coinbase product
    "KXBTC15M": "BTC-USD",
    "KXETH15M": "ETH-USD",
    "KXSOL15M": "SOL-USD",
}

_session = requests.Session()


def _get(url: str, params: dict | None = None, tries: int = 6):
    for i in range(tries):
        r = _session.get(url, params=params, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(1.5 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def _ts(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


# --------------------------------------------------------------------------- markets
def fetch_markets(series: str, days: int) -> pd.DataFrame:
    now = int(time.time())
    params = {"series_ticker": series, "status": "settled", "limit": 1000,
              "min_close_ts": now - days * 86400}
    rows, cursor = [], None
    while True:
        if cursor:
            params["cursor"] = cursor
        d = _get(f"{KALSHI}/markets", params)
        for m in d.get("markets", []):
            if m.get("result") not in ("yes", "no") or m.get("floor_strike") is None:
                continue
            rows.append({
                "ticker": m["ticker"],
                "open_ts": _ts(m["open_time"]),
                "close_ts": _ts(m["close_time"]),
                "strike": float(m["floor_strike"]),
                "settle_value": float(m["expiration_value"]) if m.get("expiration_value") else None,
                "result": 1 if m["result"] == "yes" else 0,
                "volume": float(m.get("volume_fp") or 0),
            })
        cursor = d.get("cursor")
        if not cursor or not d.get("markets"):
            break
        time.sleep(0.2)
    return pd.DataFrame(rows).drop_duplicates("ticker").sort_values("open_ts").reset_index(drop=True)


def _px(c: dict, side: str, field: str = "close_dollars"):
    v = (c.get(side) or {}).get(field)
    return float(v) if v is not None else None


def _chunks(markets: pd.DataFrame, max_tickers: int = 25, max_candles: int = 8000):
    """Group markets so tickers x minutes-in-range stays under the API cap."""
    cur = []
    for m in markets.itertuples():
        trial = cur + [m]
        span = (max(x.close_ts for x in trial) - min(x.open_ts for x in trial)) / 60 + 4
        if cur and (len(trial) > max_tickers or len(trial) * span > max_candles):
            yield cur
            trial = [m]
        cur = trial
    if cur:
        yield cur


def fetch_candles(series: str, markets: pd.DataFrame) -> pd.DataFrame:
    """1-minute yes_bid / yes_ask / last for every market (batched endpoint)."""
    rows, done = [], 0
    for chunk in _chunks(markets):
        params = {"market_tickers": ",".join(m.ticker for m in chunk),
                  "start_ts": min(m.open_ts for m in chunk) - 60,
                  "end_ts": max(m.close_ts for m in chunk) + 60,
                  "period_interval": 1}
        d = _get(f"{KALSHI}/markets/candlesticks", params)
        for m in d.get("markets", []):
            tk = m.get("market_ticker") or m.get("ticker")
            for c in m.get("candlesticks", []):
                rows.append({
                    "ticker": tk,
                    "ts": int(c["end_period_ts"]),
                    "yes_bid": _px(c, "yes_bid"),
                    "yes_ask": _px(c, "yes_ask"),
                    "last": _px(c, "price"),
                    "volume": float(c.get("volume_fp") or 0),
                })
        done += len(chunk)
        print(f"  {series} candles {done}/{len(markets)}", end="\r", flush=True)
        time.sleep(0.25)
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- spot
def fetch_spot(product: str, start: int, end: int) -> pd.DataFrame:
    rows, t = [], start
    step = 300 * 60
    while t < end:
        t2 = min(t + step, end)
        d = _get(f"{COINBASE}/products/{product}/candles",
                 {"granularity": 60,
                  "start": datetime.fromtimestamp(t, timezone.utc).isoformat(),
                  "end": datetime.fromtimestamp(t2, timezone.utc).isoformat()})
        rows += d
        t = t2
        time.sleep(0.12)
    df = pd.DataFrame(rows, columns=["ts", "low", "high", "open", "close", "volume"])
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


# --------------------------------------------------------------------------- orchestration
def download(series_list=("KXBTC15M",), days: int = 30, force: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for series in series_list:
        mpath, cpath, spath = (DATA_DIR / f"{series}_{k}.csv" for k in ("markets", "candles", "spot"))
        if mpath.exists() and not force:
            print(f"{series}: cached (use --force to refetch)")
            continue
        print(f"{series}: fetching settled markets for last {days}d ...")
        mk = fetch_markets(series, days)
        print(f"  {len(mk)} markets")
        cd = fetch_candles(series, mk)
        sp = fetch_spot(SERIES[series], int(mk.open_ts.min()) - 4 * 3600, int(mk.close_ts.max()) + 120)
        mk.to_csv(mpath, index=False)
        cd.to_csv(cpath, index=False)
        sp.to_csv(spath, index=False)
        (DATA_DIR / f"{series}_meta.json").write_text(json.dumps(
            {"fetched": int(time.time()), "days": days, "markets": len(mk)}))
        print(f"  saved {len(mk)} markets, {len(cd)} candles, {len(sp)} spot bars")


def load(series: str):
    return tuple(pd.read_csv(DATA_DIR / f"{series}_{k}.csv") for k in ("markets", "candles", "spot"))
