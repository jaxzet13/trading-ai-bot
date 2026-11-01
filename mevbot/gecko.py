"""Throttled GeckoTerminal client with on-disk caching.

The free API allows only a handful of calls per minute, so every request goes
through a global throttle and 429s are retried with backoff.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests

BASE = "https://api.geckoterminal.com/api/v2"
CACHE_DIR = Path(os.environ.get("MEV_CACHE_DIR", Path(__file__).resolve().parent.parent / "data" / "mev" / "cache"))
MIN_INTERVAL = float(os.environ.get("GECKO_MIN_INTERVAL", "6.5"))

_last_call = 0.0


def _throttle() -> None:
    global _last_call
    wait = MIN_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def get(path: str, params: dict | None = None, cache: bool = True, retries: int = 6) -> dict:
    params = params or {}
    key = hashlib.sha1((path + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    cfile = CACHE_DIR / f"{key}.json"
    if cache and cfile.exists():
        return json.loads(cfile.read_text())
    delay = 15.0
    for _ in range(retries):
        _throttle()
        try:
            r = requests.get(f"{BASE}{path}", params=params, timeout=20,
                             headers={"accept": "application/json"})
        except requests.RequestException:
            time.sleep(delay)
            delay *= 1.6
            continue
        if r.status_code == 429:
            time.sleep(delay)
            delay *= 1.6
            continue
        if r.status_code == 404:
            return {"data": []}
        r.raise_for_status()
        data = r.json()
        if cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cfile.write_text(json.dumps(data))
        return data
    raise RuntimeError(f"GeckoTerminal request failed after retries: {path} {params}")


def new_pools(page: int = 1) -> list[dict]:
    return get("/networks/solana/new_pools", {"page": page, "include": "base_token"}, cache=False).get("data", [])


def trending_pools(page: int = 1) -> list[dict]:
    return get("/networks/solana/trending_pools", {"page": page}, cache=False).get("data", [])


def token_pools(token: str, page: int = 1) -> list[dict]:
    return get(f"/networks/solana/tokens/{token}/pools", {"page": page}, cache=False).get("data", [])


def pool_trades(pool: str, cache: bool = True) -> list[dict]:
    return get(f"/networks/solana/pools/{pool}/trades", {}, cache=cache).get("data", [])


def ohlcv_minute(pool: str, limit: int = 1000, before: int | None = None, cache: bool = True) -> list[list[float]]:
    params = {"aggregate": 1, "limit": limit, "currency": "token"}
    if before:
        params["before_timestamp"] = before
    d = get(f"/networks/solana/pools/{pool}/ohlcv/minute", params, cache=cache)
    rows = d.get("data", {}).get("attributes", {}).get("ohlcv_list", []) if isinstance(d.get("data"), dict) else []
    return sorted(rows, key=lambda r: r[0])
