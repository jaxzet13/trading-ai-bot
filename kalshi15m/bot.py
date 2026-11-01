"""Live / paper trading loop for Kalshi 15-minute up/down markets.

PAPER MODE IS THE DEFAULT. Nothing is sent to Kalshi unless you pass --live
AND set KALSHI_KEY_ID + KALSHI_PRIVATE_KEY_PATH. Try --demo (Kalshi's demo
exchange with fake money) before risking real funds.

    python -m kalshi15m bot --series KXBTC15M --strategy fair_value
"""
from __future__ import annotations

import base64
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

from .backtest import kalshi_fee
from .data import COINBASE, SERIES
from .backtest import FIELDS
from .strategies import STRATEGIES, model_prob

PROD = "https://api.elections.kalshi.com"
DEMO = "https://demo-api.kalshi.co"
LOG = Path(__file__).resolve().parent.parent / "data" / "kalshi15m" / "bot_log.jsonl"


class Kalshi:
    def __init__(self, base: str, key_id: str | None = None, key_path: str | None = None):
        self.base, self.key_id, self.key = base, key_id, None
        if key_id and key_path:
            from cryptography.hazmat.primitives import serialization
            self.key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)

    def _headers(self, method: str, path: str) -> dict:
        if not self.key:
            return {}
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        ts = str(int(time.time() * 1000))
        sig = self.key.sign((ts + method + path.split("?")[0]).encode(),
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                        salt_length=padding.PSS.DIGEST_LENGTH),
                            hashes.SHA256())
        return {"KALSHI-ACCESS-KEY": self.key_id, "KALSHI-ACCESS-TIMESTAMP": ts,
                "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode()}

    def req(self, method: str, path: str, **kw):
        path = "/trade-api/v2" + path
        r = requests.request(method, self.base + path, headers=self._headers(method, path), timeout=15, **kw)
        r.raise_for_status()
        return r.json()

    def open_market(self, series: str):
        ms = self.req("GET", "/markets", params={"series_ticker": series, "status": "open"}).get("markets", [])
        return min(ms, key=lambda m: m["close_time"]) if ms else None

    def balance(self) -> float:
        return self.req("GET", "/portfolio/balance")["balance"] / 100

    def buy(self, ticker: str, side: str, count: int, price: float):
        cents = int(round(price * 100))
        body = {"ticker": ticker, "action": "buy", "side": side, "count": count, "type": "limit",
                "client_order_id": str(uuid.uuid4()), f"{side}_price": cents,
                "time_in_force": "immediate_or_cancel"}
        return self.req("POST", "/portfolio/orders", json=body)


def _spot_and_vol(product: str):
    d = requests.get(f"{COINBASE}/products/{product}/candles", params={"granularity": 60}, timeout=10).json()
    closes = np.array([c[4] for c in sorted(d)[-61:]])
    vol = float(np.std(np.diff(np.log(closes)), ddof=1))
    t = requests.get(f"{COINBASE}/products/{product}/ticker", timeout=10).json()
    return float(t["price"]), vol, {int(c[0]): c[4] for c in d}


def _ts(s): return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def run(series="KXBTC15M", strategy="fair_value", params=None, stake=5.0, live=False, demo=False,
        max_daily_loss=50.0, max_trades_per_day=40, poll=5):
    fn = STRATEGIES[strategy][0]
    params = params or {}
    base = DEMO if demo else PROD
    api = Kalshi(base, os.getenv("KALSHI_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH")) if live else Kalshi(base)
    if live and not api.key:
        raise SystemExit("--live needs KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH env vars")
    mode = ("LIVE-DEMO" if demo else "LIVE") if live else "PAPER"
    print(f"[{mode}] {strategy} {params} on {series}, stake ${stake}/trade, "
          f"daily loss cap ${max_daily_loss}")
    LOG.parent.mkdir(parents=True, exist_ok=True)

    P, seen, traded, cur, day, day_pnl, day_trades, open_pos = None, set(), set(), None, None, 0.0, 0, {}
    while True:
        try:
            today = datetime.now(timezone.utc).date()
            if today != day:
                day, day_pnl, day_trades = today, 0.0, 0
            m = api.open_market(series)
            if not m:
                time.sleep(poll); continue
            # settle paper positions from previous markets
            for tk in list(open_pos):
                if tk != m["ticker"]:
                    res = api.req("GET", f"/markets/{tk}")["market"].get("result")
                    if res in ("yes", "no"):
                        p = open_pos.pop(tk)
                        pnl = p["n"] * ((res == p["side"]) - p["price"]) - p["fee"]
                        day_pnl += pnl
                        print(f"  settled {tk}: {res} -> pnl ${pnl:+.2f} (today ${day_pnl:+.2f})")
                        _log({"event": "settle", "ticker": tk, "result": res, "pnl": pnl})
            if m["ticker"] != cur:
                cur, seen = m["ticker"], set()
                P = {f: np.full((1, 14), np.nan) for f in FIELDS}
            open_ts = _ts(m["open_time"])
            minute = int((time.time() - open_ts) // 60)
            if minute < 1 or minute > 14 or minute in seen:
                time.sleep(poll); continue
            spot, vol, bars = _spot_and_vol(SERIES[series])
            yb = float(m.get("yes_bid_dollars") or 0)
            ya = float(m.get("yes_ask_dollars") or 1)
            p0, p1 = bars.get(open_ts - 960), bars.get(open_ts - 60)
            strike = float(m.get("floor_strike") or 0)
            j = minute - 1
            vals = {"yes_bid": yb if yb > 0 else np.nan, "yes_ask": ya if ya < 1 else np.nan,
                    "no_ask": 1 - yb if yb > 0 else np.nan, "spot": spot, "strike": strike or np.nan,
                    "vol1m": vol, "prev_ret": (p1 / p0 - 1) if p0 and p1 else np.nan,
                    "ret_from_open": (spot / p1 - 1) if p1 else np.nan}
            for f in FIELDS:
                P[f][0, j] = vals[f]
            P["p_model"] = model_prob(P)
            seen.add(minute)
            print(f"{datetime.now():%H:%M:%S} {cur} m{minute:02d} spot={spot:.2f} K={strike:.2f} "
                  f"bid/ask={yb:.3f}/{ya:.3f} model={P['p_model'][0, j]:.3f}")
            if cur in traded or day_pnl <= -max_daily_loss or day_trades >= max_trades_per_day:
                continue
            sides, mins = fn(P, **params)
            if sides[0] != 0 and mins[0] == minute:
                side = "yes" if sides[0] == 1 else "no"
                price = P["yes_ask"][0, j] if side == "yes" else P["no_ask"][0, j]
                n = max(1, int(stake // price))
                fee = kalshi_fee(price, n)
                print(f"  >>> BUY {n} {side.upper()} @ {price:.3f} (fee ${fee:.2f})")
                if live:
                    print("  order:", api.buy(cur, side, n, price))
                open_pos[cur] = {"side": side, "n": n, "price": price, "fee": fee}
                traded.add(cur); day_trades += 1
                _log({"event": "buy", "mode": mode, "ticker": cur, "side": side, "n": n, "price": price})
        except requests.RequestException as e:
            print("  network error:", e)
        except KeyboardInterrupt:
            print("stopped"); return
        time.sleep(poll)


def _log(d):
    d["ts"] = int(time.time())
    with LOG.open("a") as f:
        f.write(json.dumps(d) + "\n")
