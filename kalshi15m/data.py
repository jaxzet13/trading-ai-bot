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
                "strike": float(str(m["floor_strike"]).replace(",", "")),
                "settle_value": float(str(m["expiration_value"]).replace(",", "")) if m.get("expiration_value") else None,
                "result": 1 if m["result"] == "yes" else 0,
                "volume": float(m.get("volume_fp") or 0),
            })
        cursor = d.get("cursor")
        if not cursor or not d.get("markets"):
            break
        time.sleep(0.2)
    return pd.DataFrame(rows).drop_duplicates("ticker").sort_values("open_ts").reset_index(drop=True)


def _num(d, *keys):
    for k in keys:
        v = (d or {}).get(k)
        if v is not None:
            return float(v)
    return None


def _candle_row(tk: str, c: dict) -> dict:
    """Normalise a candle from either the live (`close_dollars`) or historical (`close`) API."""
    ya, yb = c.get("yes_ask") or {}, c.get("yes_bid") or {}
    return {
        "ticker": tk, "ts": int(c["end_period_ts"]),
        "yes_bid": _num(yb, "close_dollars", "close"), "yes_ask": _num(ya, "close_dollars", "close"),
        "bid_high": _num(yb, "high_dollars", "high"), "ask_low": _num(ya, "low_dollars", "low"),
        "last": _num(c.get("price"), "close_dollars", "close"),
        "volume": _num(c, "volume_fp", "volume") or 0.0,
    }


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
            rows += [_candle_row(tk, c) for c in m.get("candlesticks", [])]
        done += len(chunk)
        print(f"  {series} candles {done}/{len(markets)}", end="\r", flush=True)
        time.sleep(0.25)
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- historical archive
def _market_row(m: dict):
    if m.get("result") not in ("yes", "no") or m.get("floor_strike") is None:
        return None
    return {"ticker": m["ticker"], "open_ts": _ts(m["open_time"]), "close_ts": _ts(m["close_time"]),
            "strike": float(str(m["floor_strike"]).replace(",", "")),
            "settle_value": float(str(m["expiration_value"]).replace(",", "")) if m.get("expiration_value") else None,
            "result": 1 if m["result"] == "yes" else 0,
            "volume": float(m.get("volume_fp") or m.get("volume") or 0)}


def fetch_markets_hist(series: str, since_ts: int = 0) -> pd.DataFrame:
    """Markets settled before Kalshi's historical cutoff (served from /historical)."""
    rows, cursor = [], None
    while True:
        params = {"series_ticker": series, "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        d = _get(f"{KALSHI}/historical/markets", params)
        ms = d.get("markets", [])
        rows += [r for r in map(_market_row, ms) if r]
        cursor = d.get("cursor")
        if not cursor or not ms or (rows and rows[-1]["open_ts"] < since_ts):
            break
        time.sleep(0.2)
    df = pd.DataFrame(rows)
    return df[df.open_ts >= since_ts].drop_duplicates("ticker").sort_values("open_ts").reset_index(drop=True)


class _Rate:
    def __init__(self, per_sec: float):
        import threading
        self.gap, self.next, self.lock = 1 / per_sec, 0.0, threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            t = max(now, self.next)
            self.next = t + self.gap
        time.sleep(max(0, t - now))


def fetch_candles_hist(series: str, markets: pd.DataFrame, part: Path, workers: int = 4, rate: float = 4.0):
    """One request per market (no batch endpoint for the archive). Resumable via `part` file."""
    from concurrent.futures import ThreadPoolExecutor
    done = set(pd.read_csv(part, usecols=["ticker"]).ticker) if part.exists() else set()
    todo = markets[~markets.ticker.isin(done)]
    lim = _Rate(rate)
    print(f"  {series}: {len(done)} archive markets cached, {len(todo)} to fetch")

    def one(m):
        for i in range(8):
            lim.wait()
            r = _session.get(f"{KALSHI}/historical/markets/{m.ticker}/candlesticks",
                             params={"start_ts": m.open_ts - 60, "end_ts": m.close_ts + 60,
                                     "period_interval": 1}, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1 + i)
                continue
            if r.status_code == 404:
                return []
            r.raise_for_status()
            return [_candle_row(m.ticker, c) for c in r.json().get("candlesticks", [])]
        return []

    t0, n = time.time(), 0
    with ThreadPoolExecutor(workers) as ex:
        for i in range(0, len(todo), 300):
            chunk = list(todo.iloc[i:i + 300].itertuples())
            rows = [r for rs in ex.map(one, chunk) for r in rs]
            pd.DataFrame(rows).to_csv(part, mode="a", header=not part.exists(), index=False)
            n += len(chunk)
            el = time.time() - t0
            print(f"  {series} archive candles {n}/{len(todo)}  ({n / el:.1f}/s, "
                  f"~{(len(todo) - n) / max(n / el, 1e-9) / 60:.0f} min left)", flush=True)


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
def download(series_list=("KXBTC15M",), days: int = 45, force: bool = False, history: bool = True,
             since: str = "2026-04-01", every: int = 2) -> None:
    """days = recent window from the live API; history=True also pulls the archive from `since`,
    keeping every `every`-th market (the archive only serves one market per request)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for series in series_list:
        mpath, cpath, spath = (DATA_DIR / f"{series}_{k}.csv" for k in ("markets", "candles", "spot"))
        if mpath.exists() and not force:
            print(f"{series}: cached (use --force to refetch)")
            continue
        rm, rc = DATA_DIR / f"{series}_recent_markets.part.csv", DATA_DIR / f"{series}_recent_candles.part.csv"
        if rm.exists() and rc.exists() and time.time() - rm.stat().st_mtime < 6 * 3600:
            mk, cd = pd.read_csv(rm), pd.read_csv(rc)
            print(f"{series}: using recent data fetched {int((time.time() - rm.stat().st_mtime) / 60)} min ago")
        else:
            print(f"{series}: fetching recent settled markets ...")
            mk = fetch_markets(series, days)
            cd = fetch_candles(series, mk)
            mk.to_csv(rm, index=False)
            cd.to_csv(rc, index=False)
        if history:
            print(f"{series}: fetching archive market list ...")
            since_ts = int(datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp())
            mh = fetch_markets_hist(series, since_ts)
            mh = mh[~mh.ticker.isin(mk.ticker)].iloc[::every]
            part = DATA_DIR / f"{series}_candles_hist.part.csv"
            fetch_candles_hist(series, mh, part)
            hist = pd.read_csv(part)
            cd = pd.concat([hist[hist.ticker.isin(mh.ticker)], cd], ignore_index=True)
            mk = pd.concat([mh, mk], ignore_index=True)
        mk = mk.drop_duplicates("ticker").sort_values("open_ts").reset_index(drop=True)
        cd = cd.drop_duplicates(["ticker", "ts"])
        print(f"  {len(mk)} markets; fetching spot ...")
        sp = fetch_spot(SERIES[series], int(mk.open_ts.min()) - 4 * 3600, int(mk.close_ts.max()) + 120)
        mk.to_csv(mpath, index=False)
        cd.to_csv(cpath, index=False)
        sp.to_csv(spath, index=False)
        (DATA_DIR / f"{series}_meta.json").write_text(json.dumps(
            {"fetched": int(time.time()), "days": days, "history": history, "markets": len(mk)}))
        print(f"  saved {len(mk)} markets, {len(cd)} candles, {len(sp)} spot bars")


def load(series: str):
    return tuple(pd.read_csv(DATA_DIR / f"{series}_{k}.csv") for k in ("markets", "candles", "spot"))
