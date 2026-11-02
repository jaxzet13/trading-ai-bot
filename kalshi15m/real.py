"""REAL-MONEY runner for one frozen strategy: fair_value on KXNEAR15M (taker).

    python -m kalshi15m real --demo --dry-run     # signals only, public data, no key, no orders
    python -m kalshi15m real check --demo         # auth + balance + positions, NO orders
    python -m kalshi15m real --demo               # demo exchange (fake money)   <- default
    python -m kalshi15m real --live               # REAL MONEY (asks you to type a phrase)
    python -m kalshi15m real-report               # P&L from the log (+ Kalshi settlements)

Read REAL_MONEY.md first. Credentials come ONLY from the env vars KALSHI_KEY_ID and
KALSHI_PRIVATE_KEY_PATH (path to the PEM private key). They are never printed or logged.

Signals are computed exactly as the paper bot (bot.run) computes them: the same Coinbase
spot/vol helper (bot._spot_and_vol), the same per-minute input panel, model_prob and the
strategy function from strategies.py, evaluated ~0.5 s after each minute boundary, one bet
per market. Only the execution differs: a real immediate-or-cancel limit order at the ask.

Kalshi Trade API v2 as documented on 2026-11-02 (written to these docs, not to bot.py's
older Kalshi class, whose POST /portfolio/orders now returns `deprecated_v1_order_endpoint`):
  Environments  https://docs.kalshi.com/getting_started/api_environments
                prod https://external-api.kalshi.com (api.elections.kalshi.com also supported)
                demo https://external-api.demo.kalshi.co (demo-api.kalshi.co also supported)
  Auth          https://docs.kalshi.com/getting_started/quick_start_authenticated_requests
                https://docs.kalshi.com/getting_started/api_keys
                headers KALSHI-ACCESS-KEY / -TIMESTAMP (ms) / -SIGNATURE = base64(sign(ts+METHOD+path)),
                path = full path from root WITHOUT query; RSA keys: RSA-PSS SHA-256 (MGF1 SHA-256,
                salt = digest length); Ed25519 keys: plain Ed25519 signature.
  Create order  https://docs.kalshi.com/api-reference/orders/create-order-v2
                POST /trade-api/v2/portfolio/events/orders, body: ticker, client_order_id,
                side "bid" (= buy YES) | "ask" (= sell YES = buy NO at 1-price), count (string
                contracts), price (string fixed-point YES price in dollars), time_in_force
                fill_or_kill | good_till_canceled | immediate_or_cancel, self_trade_prevention_type
                (required). No buy_max_cost in V2 (that was a legacy-endpoint field): the cost cap is
                enforced here (count x limit price <= stake, IOC never rests).
                Response 201: order_id, client_order_id, fill_count, remaining_count,
                average_fill_price, average_fee_paid, ts_ms. 409 = duplicate client_order_id.
  Get order(s)  https://docs.kalshi.com/api-reference/orders/get-order
                https://docs.kalshi.com/api-reference/orders/get-orders
                GET /portfolio/orders/{id} -> {"order": {status resting|canceled|executed,
                fill_count_fp, remaining_count_fp, taker_fill_cost_dollars, taker_fees_dollars,
                outcome_side, book_side, client_order_id, ...}}; GET /portfolio/orders?ticker=&min_ts=
                (no client_order_id filter: we scan the list for it).
  Cancel        https://docs.kalshi.com/api-reference/orders/cancel-order-v2
                DELETE /portfolio/events/orders/{order_id}
  Fills         https://docs.kalshi.com/api-reference/portfolio/get-fills
                GET /portfolio/fills?order_id=|ticker= -> fills[]: count_fp, yes/no_price_dollars,
                outcome_side, fee_cost (dollars), is_taker
  Balance       https://docs.kalshi.com/api-reference/portfolio/get-balance
                GET /portfolio/balance -> balance (cents), balance_dollars (string)
  Positions     https://docs.kalshi.com/api-reference/portfolio/get-positions
                GET /portfolio/positions -> market_positions[]: ticker, position_fp (+YES / -NO),
                market_exposure_dollars, fees_paid_dollars
  Settlements   https://docs.kalshi.com/api-reference/portfolio/get-settlements
                GET /portfolio/settlements?ticker= -> settlements[]: market_result, yes/no_count_fp,
                yes/no_total_cost_dollars, revenue (CENTS), fee_cost (dollars), settled_time
  Rate limits   https://docs.kalshi.com/getting_started/rate_limits
                token buckets (most calls 10 tokens), 429 body {"error": "too many requests"},
                no Retry-After header, no penalty; balance has its own 1/s bucket on Basic.
  Changelog     https://docs.kalshi.com/changelog (legacy /portfolio/orders mutations deprecated
                Jun 2026; integer cents/count fields removed from most responses Mar 2026)
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import signal
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

from . import bot
from .backtest import FIELDS, kalshi_fee
from .data import SERIES
from .strategies import STRATEGIES, model_prob

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path(__file__).resolve().parent / "real.json"
LOG = ROOT / "data" / "kalshi15m" / "real_log.jsonl"
STOP_FILE = ROOT / "STOP"
PROD = "https://external-api.kalshi.com"
DEMO = "https://external-api.demo.kalshi.co"
API = "/trade-api/v2"
CONFIRM_PHRASE = "I UNDERSTAND THIS USES REAL MONEY"
REQUIRED_LIMITS = ("stake_usd", "max_contracts_per_order", "max_daily_loss_usd", "max_trades_per_day",
                   "max_open_positions", "min_balance_usd", "max_price", "min_price",
                   "max_data_age_s", "max_decision_lag_s")

# exit codes understood by scripts/run_real.sh
EXIT_CLEAN, EXIT_CRASH, EXIT_CONFIG = 0, 1, 2


# ----------------------------------------------------------------------------- HTTP layer
class ApiError(requests.RequestException):
    """Kalshi answered with an error status: the request was received and NOT executed."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status, self.body = status, body


class Uncertain(requests.RequestException):
    """We do not know whether Kalshi executed the request (timeout, dropped connection, 5xx)."""


def load_private_key(path: str):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(Path(path).expanduser().read_bytes(), password=None)


def sign(key, ts_ms: str, method: str, path: str) -> str:
    """Kalshi request signature: base64(sign(timestamp + METHOD + path-without-query))."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    msg = (ts_ms + method.upper() + path.split("?")[0]).encode()
    if isinstance(key, Ed25519PrivateKey):
        sig = key.sign(msg)
    else:
        sig = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                       hashes.SHA256())
    return base64.b64encode(sig).decode()


class KalshiAPI:
    """Minimal Kalshi Trade API v2 client. Public calls work without a key."""

    def __init__(self, base: str, key_id: str | None = None, key_path: str | None = None,
                 session=None, clock=time.time, sleep=time.sleep, timeout: float = 4.0):
        self.base, self.key_id, self.key = base, key_id, None
        self.http = session or requests.Session()
        self.clock, self.sleep, self.timeout = clock, sleep, timeout
        if key_id and key_path:
            self.key = load_private_key(key_path)

    @classmethod
    def from_env(cls, base: str, **kw):
        kid, kp = os.getenv("KALSHI_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH")
        if not kid or not kp:
            raise SystemExit("Set the env vars KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH (see REAL_MONEY.md).")
        if not Path(kp).expanduser().is_file():
            raise SystemExit(f"KALSHI_PRIVATE_KEY_PATH does not point to a file: {kp}")
        return cls(base, kid.strip(), kp, **kw)

    def headers(self, method: str, path: str) -> dict:
        h = {"Content-Type": "application/json"} if method in ("POST", "PUT", "DELETE") else {}
        if self.key is not None:
            ts = str(int(self.clock() * 1000))
            h.update({"KALSHI-ACCESS-KEY": self.key_id, "KALSHI-ACCESS-TIMESTAMP": ts,
                      "KALSHI-ACCESS-SIGNATURE": sign(self.key, ts, method, path)})
        return h

    def _send(self, method, path, params=None, body=None):
        full = API + path
        try:
            r = self.http.request(method, self.base + full, params=params, json=body,
                                  headers=self.headers(method, full), timeout=self.timeout)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise Uncertain(f"{type(e).__name__}: {e}") from None
        if r.status_code >= 500:
            raise Uncertain(f"HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            raise ApiError(r.status_code, r.text)
        return r.json() if r.content else {}

    def get(self, path, params=None, deadline: float | None = None, tries: int = 6):
        """GETs are safe to repeat: back off on 429 / 5xx / network errors."""
        delay = 0.25
        for i in range(tries):
            try:
                return self._send("GET", path, params=params)
            except (Uncertain, ApiError) as e:
                if isinstance(e, ApiError) and e.status != 429:
                    raise
                if i == tries - 1 or (deadline and self.clock() + delay > deadline):
                    raise requests.RequestException(str(e)) from None
                self.sleep(delay)
                delay = min(delay * 2, 4.0)

    # --- market data (public)
    def open_market(self, series: str, deadline=None):
        ms = self.get("/markets", {"series_ticker": series, "status": "open"}, deadline=deadline).get("markets", [])
        return min(ms, key=lambda m: m["close_time"]) if ms else None

    def market(self, ticker: str):
        return self.get(f"/markets/{ticker}").get("market", {})

    # --- portfolio (auth)
    def balance(self) -> float:
        d = self.get("/portfolio/balance")
        return float(d["balance_dollars"]) if d.get("balance_dollars") is not None else d["balance"] / 100

    def positions(self, **params):
        return self.get("/portfolio/positions", params).get("market_positions", [])

    def settlements(self, **params):
        return self.get("/portfolio/settlements", params).get("settlements", [])

    def fills(self, **params):
        return self.get("/portfolio/fills", params).get("fills", [])

    def get_order(self, order_id: str):
        return self.get(f"/portfolio/orders/{order_id}").get("order", {})

    def find_order(self, ticker: str, client_order_id: str, min_ts: int):
        """Look up an order by our client_order_id (Get Orders has no such filter, so scan)."""
        cursor = None
        for _ in range(5):
            p = {"ticker": ticker, "min_ts": min_ts, "limit": 200}
            if cursor:
                p["cursor"] = cursor
            d = self.get("/portfolio/orders", p)
            for o in d.get("orders", []):
                if o.get("client_order_id") == client_order_id:
                    return o
            cursor = d.get("cursor")
            if not cursor:
                return None
        return None

    def create_order(self, body: dict) -> dict:
        """POST once. Never retried here: the caller decides (see Runner._place)."""
        return self._send("POST", "/portfolio/events/orders", body=body)

    def cancel_order(self, order_id: str):
        return self._send("DELETE", f"/portfolio/events/orders/{order_id}")


# ----------------------------------------------------------------------------- signal (same as bot.run)
def new_panel():
    return {f: np.full((1, 14), np.nan) for f in FIELDS}


def observe(P: dict, m: dict, minute: int, spot: float, vol: float, vol240: float, bars: dict):
    """Fill column `minute` of the panel exactly like bot.run does (keep in sync with bot.py)."""
    open_ts = bot._ts(m["open_time"])
    yb = float(m.get("yes_bid_dollars") or 0)
    ya = float(m.get("yes_ask_dollars") or 1)
    p0, p1 = bars.get(open_ts - 960), bars.get(open_ts - 60)
    strike = float(m.get("floor_strike") or 0)
    j = minute - 1
    vals = {"yes_bid": yb if yb > 0 else np.nan, "yes_ask": ya if ya < 1 else np.nan,
            "no_ask": 1 - yb if yb > 0 else np.nan, "spot": spot, "strike": strike or np.nan,
            "vol1m": vol, "vol240": vol240, "prev_ret": (p1 / p0 - 1) if p0 and p1 else np.nan,
            "ret_from_open": (spot / p1 - 1) if p1 else np.nan}
    for f in FIELDS:
        P[f][0, j] = vals.get(f, np.nan)
    P["p_model"] = model_prob(P)
    return {"yes_bid": yb, "yes_ask": ya, "strike": strike, "spot": spot, "vol1m": vol, "vol240": vol240,
            "model": float(P["p_model"][0, j]) if np.isfinite(P["p_model"][0, j]) else None}


def decide(fn, P: dict, params: dict, minute: int):
    """Same trigger as bot.run: the strategy's FIRST signal must be at this minute."""
    sides, mins = fn(P, **params)
    if sides[0] != 0 and mins[0] == minute:
        side = "yes" if sides[0] == 1 else "no"
        j = minute - 1
        price = float(P["yes_ask"][0, j] if side == "yes" else P["no_ask"][0, j])
        return side, price
    return None


def contracts_for(stake: float, price: float, cap: int) -> int:
    return min(int(math.floor(stake / price + 1e-9)), int(cap))


def order_body(ticker: str, side: str, price: float, n: int, client_order_id: str) -> dict:
    """V2 order: everything is quoted on the YES book. Buy YES at the yes ask = bid @ ask;
    buy NO at no_ask (= 1 - yes_bid) = sell YES ("ask") @ yes_bid. IOC: never rests."""
    yes_px = price if side == "yes" else 1 - price
    return {"ticker": ticker, "client_order_id": client_order_id,
            "side": "bid" if side == "yes" else "ask",
            "count": str(int(n)), "price": f"{round(yes_px, 4):.4f}",
            "time_in_force": "immediate_or_cancel", "self_trade_prevention_type": "taker_at_cross",
            "post_only": False, "reduce_only": False}


def _f(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def summarize_fills(fills: list, side: str):
    """Real count, cost and fees of our fills on `side` (cost in that side's price)."""
    n = cost = fees = 0.0
    for f in fills:
        c = _f(f.get("count_fp", f.get("count")))
        os_ = f.get("outcome_side") or f.get("side")
        px = _f(f.get("no_price_dollars")) if os_ == "no" else _f(f.get("yes_price_dollars"))
        if os_ != side:
            continue
        n += c
        cost += c * px
        fees += _f(f.get("fee_cost"))
    return round(n, 2), round(cost, 6), round(fees, 6)


def _day(ts) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


# ----------------------------------------------------------------------------- runner
class Stop(Exception):
    def __init__(self, reason, code=EXIT_CLEAN):
        super().__init__(reason)
        self.reason, self.code = reason, code


class Runner:
    def __init__(self, cfg: dict, mode: str, api: KalshiAPI, market_api: KalshiAPI | None = None,
                 log_path: Path = LOG, stop_path: Path = STOP_FILE, clock=time.time, sleep=time.sleep,
                 spot_fn=None, max_minutes: int | None = None, out=print):
        assert mode in ("DEMO", "LIVE", "DRYRUN")
        self.cfg, self.mode, self.api = cfg, mode, api
        self.mapi = market_api or api            # where quotes come from (= the exchange we trade on)
        self.dry = mode == "DRYRUN"
        self.L = cfg["limits"]
        self.series, self.params = cfg["series"], cfg["params"]
        self.fn = STRATEGIES[cfg["strategy"]][0]
        self.product = SERIES[self.series]
        self.log_path, self.stop_path = Path(log_path), Path(stop_path)
        self.clock, self.sleep, self.out = clock, sleep, out
        self.spot_fn = spot_fn or bot._spot_and_vol
        self.max_minutes = max_minutes
        self.stop_requested = False
        self.cur, self.P, self.seen, self.minutes_run = None, None, set(), 0
        self.balance = None
        self.rebuild()

    # --- persistence
    def log(self, d: dict):
        d = {"ts": round(self.clock(), 3), "mode": self.mode, "series": self.series, **d}
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a") as f:
            f.write(json.dumps(d, default=float) + "\n")

    def events(self):
        if not self.log_path.exists():
            return []
        out = []
        for line in self.log_path.read_text().splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("mode") == self.mode and e.get("series") == self.series:
                out.append(e)
        return out

    def rebuild(self):
        """Rebuild state from our own log: traded markets, open positions, today's numbers."""
        self.traded, self.pos, self.settled, self.trades_by_day, self.pnl_by_day = set(), {}, set(), {}, {}
        for e in self.events():
            ev, tk = e.get("event"), e.get("ticker")
            if ev in ("order_intent", "would_order"):
                self.traded.add(tk)
                d = _day(e["ts"])
                self.trades_by_day[d] = self.trades_by_day.get(d, 0) + 1
                self.pos[tk] = {"side": e["side"], "n": 0.0, "cost": 0.0, "fees": 0.0, "close_ts": e["close_ts"],
                                "status": "pending", "limit": e["price"],
                                "max_cost": e.get("max_cost", 0.0)}
                if ev == "would_order":   # dry run: pretend the order filled as the paper bot does
                    self.pos[tk].update(n=e["n"], cost=e["n"] * e["price"], fees=kalshi_fee(e["price"], e["n"]),
                                        status="filled")
            elif ev == "fill" and tk in self.pos:
                self.pos[tk].update(n=e["n"], cost=e["cost"], fees=e["fees"], status="filled" if e["n"] > 0 else "none")
            elif ev == "order_unknown" and tk in self.pos:
                self.pos[tk]["status"] = "unknown"
            elif ev in ("order_rejected",) and tk in self.pos:
                self.pos[tk]["status"] = "none"
            elif ev in ("settle", "dry_settle"):
                self.settled.add(tk)
                d = e.get("day") or _day(e["ts"])
                self.pnl_by_day[d] = self.pnl_by_day.get(d, 0.0) + e["pnl"]
        for tk in list(self.pos):
            if tk in self.settled or self.pos[tk]["status"] == "none":
                self.pos.pop(tk)

    # --- risk
    def today(self):
        return _day(self.clock())

    def open_risk(self):
        """Worst case still at stake: everything paid for unsettled positions (incl. unknown ones)."""
        r = 0.0
        for p in self.pos.values():
            if p["status"] == "filled":
                r += p["cost"] + p["fees"]
            elif p["status"] in ("unknown", "pending"):
                r += p.get("max_cost") or 0.0
        return r

    def day_pnl(self):
        return self.pnl_by_day.get(self.today(), 0.0)

    def open_positions(self):
        now = self.clock()
        return sum(1 for p in self.pos.values() if p["status"] in ("filled", "unknown", "pending")
                   and p["close_ts"] > now)

    def blocked(self):
        """Reason not to place a new order now, or None."""
        if self.stop_path.exists():
            raise Stop(f"kill switch: {self.stop_path} exists")
        if self.day_pnl() - self.open_risk() <= -self.L["max_daily_loss_usd"]:
            return (f"daily loss cap: settled ${self.day_pnl():+.2f}, at risk ${self.open_risk():.2f}, "
                    f"cap ${self.L['max_daily_loss_usd']:.2f} (stopped until 00:00 UTC)")
        if self.trades_by_day.get(self.today(), 0) >= self.L["max_trades_per_day"]:
            return "max trades per day reached"
        if self.open_positions() >= self.L["max_open_positions"]:
            return "max open positions reached"
        return None

    # --- main loop
    def run(self):
        self.out(f"[{self.mode}] {self.cfg['strategy']} {self.params} on {self.series}, taker IOC, "
                 f"stake ${self.L['stake_usd']}/trade, daily loss cap ${self.L['max_daily_loss_usd']}, "
                 f"log {self.log_path}")
        self.log({"event": "start", "limits": self.L, "params": self.params, "strategy": self.cfg["strategy"]})
        if not self.dry:
            self.refresh_balance()
            self.reconcile()
        day = self.today()
        try:
            while True:
                if self.stop_requested:
                    raise Stop("Ctrl+C")
                if self.stop_path.exists():
                    raise Stop(f"kill switch: {self.stop_path} exists")
                if self.today() != day:
                    self.print_day(day)
                    day = self.today()
                self.step()
                if self.max_minutes and self.minutes_run >= self.max_minutes:
                    raise Stop(f"ran {self.max_minutes} minutes")
                self.wait_minute()
        except Stop as s:
            self.out(f"stopping: {s.reason}")
            self.log({"event": "stop", "reason": s.reason})
            self.print_day(self.today())
            return s.code

    def wait_minute(self):
        """Wake 0.5 s after the next minute boundary (bot._wait(poll="minute")), in small steps
        so Ctrl+C and the STOP file are noticed quickly."""
        target = self.clock() + (60 - self.clock() % 60 + 0.5)
        while True:
            left = target - self.clock()
            if left <= 0 or self.stop_requested:
                return
            self.sleep(min(left, 1.0))

    def step(self):
        """One wake-up: observe the open market, maybe order, then housekeeping."""
        t_quote = self.clock()
        try:
            m = self.mapi.open_market(self.series, deadline=t_quote + self.L["max_data_age_s"])
        except requests.RequestException as e:
            self.out(f"  network error (market): {e}; skipping this minute")
            self.log({"event": "skip", "reason": "network_market", "error": str(e)[:200]})
            return self.housekeeping()
        if not m:
            return self.housekeeping()
        if m["ticker"] != self.cur:
            self.cur, self.P, self.seen = m["ticker"], new_panel(), set()
            if not self.dry:
                self.refresh_balance()
        open_ts = bot._ts(m["open_time"])
        minute = int((self.clock() - open_ts) // 60)
        if minute < 1 or minute > 14 or minute in self.seen:
            return self.housekeeping()
        t_spot = self.clock()
        try:
            spot, vol, vol240, bars = self.spot_fn(self.product)
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
            self.out(f"  spot data error: {e}; skipping this minute")
            self.log({"event": "skip", "reason": "network_spot", "ticker": self.cur, "minute": minute,
                      "error": str(e)[:200]})
            return self.housekeeping()
        obs = observe(self.P, m, minute, spot, vol, vol240, bars)
        self.seen.add(minute)
        self.minutes_run += 1
        t_dec = self.clock()
        lag = round(t_dec - (open_ts + 60 * minute), 2)
        age = round(t_dec - min(t_quote, t_spot), 2)
        mdl = obs["model"]
        self.out(f"{datetime.now():%H:%M:%S} {self.cur} m{minute:02d} spot={spot:.4f} K={obs['strike']:.4f} "
                 f"bid/ask={obs['yes_bid']:.3f}/{obs['yes_ask']:.3f} model={mdl if mdl is None else round(mdl, 3)} "
                 f"lag={lag}s")
        if self.cur not in self.traded:
            sig = decide(self.fn, self.P, self.params, minute)
            if sig:
                self.act(m, minute, sig, obs, lag, age, open_ts)
        self.housekeeping()

    def act(self, m, minute, sig, obs, lag, age, open_ts):
        side, price = sig
        tk = self.cur
        base = {"ticker": tk, "minute": minute, "side": side, "price": price, "lag_s": lag, "data_age_s": age,
                **obs, "yes_ask_size": m.get("yes_ask_size_fp"), "yes_bid_size": m.get("yes_bid_size_fp")}
        why = self.blocked()
        if why is None and lag > self.L["max_decision_lag_s"]:
            why = f"decision lag {lag}s > {self.L['max_decision_lag_s']}s"
        if why is None and age > self.L["max_data_age_s"]:
            why = f"data {age}s old > {self.L['max_data_age_s']}s"
        if why is None and not (self.L["min_price"] <= price <= self.L["max_price"]):
            why = f"price {price} outside [{self.L['min_price']}, {self.L['max_price']}]"
        n = contracts_for(self.L["stake_usd"], price, self.L["max_contracts_per_order"])
        if why is None and n < 1:
            why = "stake too small for one contract"
        max_cost = round(n * price + kalshi_fee(price, n), 4)
        if why is None and not self.dry and self.balance is not None and self.balance < max_cost:
            why = f"balance ${self.balance:.2f} < order cost ${max_cost:.2f}"
        if why:
            self.out(f"  signal {side.upper()} @ {price:.3f} skipped: {why}")
            self.log({"event": "signal_skipped", "reason": why, **base})
            return
        coid = str(uuid.uuid4())
        body = order_body(tk, side, price, n, coid)
        # mark the market as traded BEFORE sending, so a crash can never lead to a second order
        self.traded.add(tk)
        d = self.today()
        self.trades_by_day[d] = self.trades_by_day.get(d, 0) + 1
        self.pos[tk] = {"side": side, "n": 0.0, "cost": 0.0, "fees": 0.0, "close_ts": open_ts + 900,
                        "status": "pending", "limit": price, "max_cost": max_cost}
        if self.dry:
            self.pos[tk].update(n=n, cost=n * price, fees=kalshi_fee(price, n), status="filled")
            self.out(f"  >>> WOULD BUY {n} {side.upper()} @ {price:.3f} (max ${max_cost:.2f}), {lag}s after the minute")
            self.log({"event": "would_order", "n": n, "max_cost": max_cost, "close_ts": open_ts + 900,
                      "order": body, **base})
            return
        self.log({"event": "order_intent", "n": n, "max_cost": max_cost, "close_ts": open_ts + 900,
                  "client_order_id": coid, "order": body, **base})
        self.out(f"  >>> BUY {n} {side.upper()} @ {price:.3f} IOC (max ${max_cost:.2f}), {lag}s after the minute")
        self._place(tk, side, body, n, price)

    def _place(self, tk, side, body, n, price):
        coid, sent_at = body["client_order_id"], int(self.clock())
        order_id, resp, err = None, None, None
        for attempt in range(2):
            try:
                resp = self.api.create_order(body)
                order_id = resp.get("order_id")
                break
            except ApiError as e:
                if e.status == 429 and attempt == 0:   # rate-limited = not executed; one retry, same id
                    self.sleep(0.3)
                    continue
                if e.status == 409:                    # duplicate client_order_id: it exists, find it
                    err = "duplicate"
                    break
                self.out(f"  order REJECTED: {e}")
                self.log({"event": "order_rejected", "ticker": tk, "client_order_id": coid,
                          "status": e.status, "error": e.body[:500]})
                self.pos[tk]["status"] = "none"
                self.pos.pop(tk, None)
                return
            except Uncertain as e:
                err = str(e)
                break
        if resp is None:
            # we don't know if it went through: look it up by client_order_id, never resend blindly
            self.out(f"  order status unknown ({err}); looking it up by client_order_id ...")
            o = None
            for _ in range(3):
                try:
                    o = self.api.find_order(tk, coid, sent_at - 120)
                    if o:
                        break
                except requests.RequestException:
                    pass
                self.sleep(1.0)
            if not o:
                self.pos[tk]["status"] = "unknown"
                self.out("  could not confirm the order; NOT retrying. It will be reconciled from fills/settlements.")
                self.log({"event": "order_unknown", "ticker": tk, "client_order_id": coid, "error": err})
                return
            order_id = o.get("order_id")
            resp = {"order_id": order_id, "fill_count": o.get("fill_count_fp"), "from_lookup": True}
        self.log({"event": "order_response", "ticker": tk, "client_order_id": coid, "response": resp})
        self.record_fill(tk, side, order_id, resp, n, price)

    def record_fill(self, tk, side, order_id, resp, n, price):
        """Use the ACTUAL filled count and cost. Get Order is authoritative; fills give exact cost."""
        filled = _f(resp.get("fill_count"))
        order = {}
        try:
            order = self.api.get_order(order_id) if order_id else {}
            if order:
                filled = _f(order.get("fill_count_fp"), filled)
                if order.get("status") == "resting":   # must never happen with IOC; cancel defensively
                    self.out("  WARNING: IOC order shows as resting; cancelling it")
                    try:
                        self.api.cancel_order(order_id)
                    except (ApiError, Uncertain) as e:
                        self.log({"event": "cancel_failed", "ticker": tk, "order_id": order_id, "error": str(e)})
                    order = self.api.get_order(order_id) or order
                    filled = _f(order.get("fill_count_fp"), filled)
        except requests.RequestException as e:
            self.log({"event": "get_order_failed", "ticker": tk, "order_id": order_id, "error": str(e)[:200]})
        cost = fees = None
        src = None
        if filled > 0:
            for _ in range(3):
                try:
                    fl = self.api.fills(order_id=order_id)
                except requests.RequestException:
                    fl = []
                fn_, fc, ff = summarize_fills(fl, side)
                if fn_ >= filled - 1e-9:
                    cost, fees, src = fc, ff, "fills"
                    break
                self.sleep(0.5)
            if cost is None and order:
                cost = _f(order.get("taker_fill_cost_dollars")) + _f(order.get("maker_fill_cost_dollars"))
                fees = _f(order.get("taker_fees_dollars")) + _f(order.get("maker_fees_dollars"))
                src = "order"
            if cost is None or cost <= 0:   # last resort: worst case at our limit price
                cost, fees, src = filled * price, kalshi_fee(price, int(math.ceil(filled))), "estimate"
        else:
            cost, fees, src = 0.0, 0.0, "none"
        rec = {"event": "fill", "ticker": tk, "order_id": order_id, "side": side, "requested": n, "n": filled,
               "cost": round(cost, 6), "fees": round(fees, 6), "avg_price": round(cost / filled, 4) if filled else None,
               "limit": price, "source": src, "order_status": order.get("status")}
        self.log(rec)
        if filled > 0:
            self.pos[tk].update(n=filled, cost=cost, fees=fees, status="filled")
            part = " (PARTIAL)" if filled < n else ""
            self.out(f"  filled {filled:g}/{n} {side.upper()}{part}, cost ${cost:.2f} + fees ${fees:.2f}")
            if not self.dry:
                self.refresh_balance()
        else:
            self.pos.pop(tk, None)
            self.out("  not filled (0 contracts): no position")

    # --- settlement, balance, reconciliation
    def housekeeping(self):
        try:
            self.settle_closed()
        except requests.RequestException as e:
            self.out(f"  settlement check failed: {e}")

    def settle_closed(self):
        now = self.clock()
        for tk, p in list(self.pos.items()):
            if p["close_ts"] > now:
                continue
            if self.dry:
                res = self.mapi.market(tk).get("result")
                if res not in ("yes", "no"):
                    continue
                pnl = p["n"] * ((res == p["side"]) - p["cost"] / p["n"]) - p["fees"]
                self.finish(tk, p, {"event": "dry_settle", "ticker": tk, "result": res, "side": p["side"],
                                    "n": p["n"], "cost": p["cost"], "fees": p["fees"], "pnl": round(pnl, 4)})
                continue
            st = [s for s in self.api.settlements(ticker=tk) if s.get("ticker") == tk]
            if not st:
                if p["status"] in ("unknown", "pending") and now > p["close_ts"] + 1800:
                    # nothing settled 30 min after close: check fills to see if we ever had a position
                    if not self.api.fills(ticker=tk):
                        self.finish(tk, p, {"event": "settle", "ticker": tk, "result": None, "side": p["side"],
                                            "n": 0, "cost": 0, "fees": 0, "pnl": 0.0, "note": "no fills found"})
                continue
            s = st[0]
            res = s.get("market_result")
            revenue = _f(s.get("revenue")) / 100              # cents -> dollars
            cost_k = _f(s.get("yes_total_cost_dollars")) + _f(s.get("no_total_cost_dollars"))
            fee_k = _f(s.get("fee_cost"))
            pnl_k = revenue - cost_k - fee_k
            fl = self.api.fills(ticker=tk)
            n_f, cost_f, fees_f = summarize_fills(fl, p["side"])
            pnl_f = (n_f if res == p["side"] else 0.0) - cost_f - fees_f if fl else None
            # use the WORSE of Kalshi's settlement record and our fill-based number
            pnl = min(pnl_k, pnl_f) if pnl_f is not None else pnl_k
            self.finish(tk, p, {"event": "settle", "ticker": tk, "result": res, "side": p["side"],
                                "n": n_f if fl else _f(s.get("yes_count_fp")) + _f(s.get("no_count_fp")),
                                "cost": cost_f if fl else cost_k, "fees": fees_f if fl else fee_k,
                                "revenue": revenue, "kalshi_cost": cost_k, "kalshi_fee": fee_k,
                                "pnl_kalshi": round(pnl_k, 4), "pnl_fills": None if pnl_f is None else round(pnl_f, 4),
                                "pnl": round(pnl, 4), "settled_time": s.get("settled_time")})
            self.refresh_balance()

    def finish(self, tk, p, rec):
        d = _day(p["close_ts"] - 1)
        rec["day"] = d
        self.log(rec)
        self.settled.add(tk)
        self.pos.pop(tk, None)
        self.pnl_by_day[d] = self.pnl_by_day.get(d, 0.0) + rec["pnl"]
        self.out(f"  settled {tk}: {rec['result']} -> P&L ${rec['pnl']:+.2f} (today ${self.pnl_by_day[d]:+.2f})")

    def refresh_balance(self):
        try:
            self.balance = self.api.balance()
        except requests.RequestException as e:
            self.out(f"  balance check failed: {e}")
            return
        if self.balance < self.L["min_balance_usd"]:
            self.log({"event": "min_balance", "balance": self.balance})
            raise Stop(f"balance ${self.balance:.2f} below min_balance_usd ${self.L['min_balance_usd']:.2f}")

    def reconcile(self):
        """On start: settle anything from the log that closed while we were down, and warn about
        positions in this series that the log doesn't know about."""
        try:
            self.settle_closed()
            known = set(self.pos)
            for mp in self.api.positions():
                tk = mp.get("ticker", "")
                if tk.startswith(self.series) and _f(mp.get("position_fp")) != 0 and tk not in known:
                    self.out(f"  WARNING: open position {tk} ({mp.get('position_fp')}) not placed by this runner")
                    self.log({"event": "foreign_position", "ticker": tk, "position": mp.get("position_fp")})
        except requests.RequestException as e:
            self.out(f"  reconcile failed: {e}")

    def print_day(self, day):
        n = self.trades_by_day.get(day, 0)
        self.out(f"=== {self.mode} {day} UTC: {n} orders, settled P&L ${self.pnl_by_day.get(day, 0.0):+.2f}, "
                 f"open {len(self.pos)}" + (f", balance ${self.balance:.2f}" if self.balance is not None else ""))


# ----------------------------------------------------------------------------- CLI helpers
def load_config(path=CONFIG) -> dict:
    cfg = json.loads(Path(path).read_text())
    lim = cfg.get("limits") or {}
    missing = [k for k in REQUIRED_LIMITS if not isinstance(lim.get(k), (int, float))]
    if missing:
        raise Stop(f"{path}: missing limits {missing}", EXIT_CONFIG)
    bad = [k for k in REQUIRED_LIMITS if k != "min_balance_usd" and lim[k] <= 0]
    if bad or lim["min_balance_usd"] < 0 or not lim["min_price"] < lim["max_price"] < 1:
        raise Stop(f"{path}: invalid limits {bad or ['min_price/max_price']}", EXIT_CONFIG)
    frozen = {"series": "KXNEAR15M", "strategy": "fair_value", "execution": "taker",
              "params": {"start": 2, "end": 13, "edge": 0.12, "vol_mult": 1.0}}
    for k, v in frozen.items():
        if cfg.get(k) != v:
            raise Stop(f"{path}: '{k}' must stay {v} (frozen strategy), found {cfg.get(k)}", EXIT_CONFIG)
    return cfg


def confirm_live(inp=input) -> bool:
    print("\n*** LIVE MODE: orders will use REAL MONEY on your Kalshi account. ***")
    print(f"Type exactly:  {CONFIRM_PHRASE}")
    try:
        return inp("> ").strip() == CONFIRM_PHRASE
    except EOFError:
        return False


def check(api: KalshiAPI, series: str, mode: str):
    """Authenticated read-only checks. Places NO orders."""
    print(f"[{mode}] {api.base}  key id {api.key_id[:4]}...{api.key_id[-4:]}")
    print(f"balance: ${api.balance():.2f}")
    pos = [p for p in api.positions() if _f(p.get("position_fp")) != 0]
    print(f"open positions: {len(pos)}")
    for p in pos:
        print(f"  {p.get('ticker')}: {p.get('position_fp')} contracts (+YES/-NO), exposure ${_f(p.get('market_exposure_dollars')):.2f}")
    m = api.open_market(series)
    if m:
        print(f"{series} market visible: {m['ticker']} bid/ask {m.get('yes_bid_dollars')}/{m.get('yes_ask_dollars')} "
              f"closes {m['close_time']}")
    else:
        print(f"WARNING: no open {series} market visible right now")
    st = api.settlements(limit=5)
    print(f"recent settlements visible: {len(st)}")
    print("check OK (no orders placed)")


def main(args: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kalshi15m real")
    ap.add_argument("action", nargs="?", choices=["run", "check"], default="run")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--demo", action="store_true", help="Kalshi demo exchange, fake money (default)")
    g.add_argument("--live", action="store_true", help="REAL MONEY")
    ap.add_argument("--dry-run", action="store_true", help="signals only from public production data; no key, no orders")
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--minutes", type=int, default=None, help="stop after this many observed minutes")
    ap.add_argument("--log", default=str(LOG), help=argparse.SUPPRESS)
    a = ap.parse_args(args)
    try:
        return _main(a)
    except Stop as s:
        print(s.reason)
        return s.code


def _main(a) -> int:
    try:
        cfg = load_config(a.config)
    except Stop as s:
        print(s.reason)
        return s.code
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {a.config}: {e}")
        return EXIT_CONFIG
    base = PROD if a.live else DEMO
    mode = "LIVE" if a.live else "DEMO"
    if a.action == "check":
        try:
            check(_api_from_env(base), cfg["series"], mode)
        except (ApiError, Uncertain, requests.RequestException) as e:
            print(f"check FAILED: {e}")
            return EXIT_CONFIG
        return EXIT_CLEAN
    if a.dry_run:
        api = KalshiAPI(PROD)   # public production market data, like the paper bot; no key
        runner_kw = dict(mode="DRYRUN", api=api, log_path=Path(a.log))
    else:
        api = _api_from_env(base)
        if a.live and not confirm_live():
            print("Confirmation phrase not entered. Not starting.")
            return EXIT_CONFIG
        runner_kw = dict(mode=mode, api=api, log_path=Path(a.log))
        if a.live:
            print("LIVE: real orders enabled. Create a file named STOP in the repo root, or press Ctrl+C, to stop.")
    return supervise(cfg, runner_kw, a.minutes)


class ConfigError(Stop):
    pass


def _api_from_env(base):
    try:
        return KalshiAPI.from_env(base)
    except SystemExit as e:
        raise ConfigError(str(e), EXIT_CONFIG) from None
    except (ValueError, TypeError) as e:   # unreadable / wrong-format key file (message has no key material)
        raise ConfigError(f"could not load the private key file: {type(e).__name__}", EXIT_CONFIG) from None


def supervise(cfg, runner_kw, minutes):
    """Run, restarting in-process after unexpected errors (state is rebuilt from the log)."""
    crashes = []
    first_sigint = {"r": None}

    def on_sigint(sig, frame):
        if first_sigint["r"] is not None and not first_sigint["r"].stop_requested:
            first_sigint["r"].stop_requested = True
            print("\nCtrl+C: finishing the current step, then stopping (press again to force)")
        else:
            raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGINT, on_sigint)
    except ValueError:
        pass
    while True:
        try:
            r = Runner(cfg, max_minutes=minutes, **runner_kw)
            first_sigint["r"] = r
            return r.run()
        except Stop as s:
            print(f"stopping: {s.reason}")
            return s.code
        except KeyboardInterrupt:
            print("stopped")
            return EXIT_CLEAN
        except Exception:
            traceback.print_exc()
            if first_sigint["r"] is not None and first_sigint["r"].stop_requested:
                return EXIT_CLEAN
            now = time.time()
            crashes = [t for t in crashes if t > now - 3600] + [now]
            try:
                with Path(runner_kw.get("log_path", LOG)).open("a") as f:
                    f.write(json.dumps({"ts": now, "mode": runner_kw["mode"], "series": cfg["series"],
                                        "event": "crash", "error": traceback.format_exc()[-800:]}) + "\n")
            except OSError:
                pass
            if len(crashes) > 10:
                print("more than 10 crashes in an hour; exiting")
                return EXIT_CRASH
            print("unexpected error; restarting in 10 s (state is rebuilt from the log)")
            time.sleep(10)


# ----------------------------------------------------------------------------- report
def report(args: list[str] | None = None, log_path: Path = LOG, out=print) -> int:
    ap = argparse.ArgumentParser(prog="kalshi15m real-report")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--demo", action="store_true", help="also fetch settlements from the demo exchange")
    g.add_argument("--live", action="store_true", help="also fetch settlements from the live exchange")
    a = ap.parse_args(args)
    if not Path(log_path).exists():
        out(f"no log yet: {log_path}")
        return 0
    ev = []
    for line in Path(log_path).read_text().splitlines():
        try:
            ev.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    for mode in ("LIVE", "DEMO", "DRYRUN"):
        es = [e for e in ev if e.get("mode") == mode]
        if not es:
            continue
        orders = [e for e in es if e.get("event") in ("order_intent", "would_order")]
        fills = {e["ticker"]: e for e in es if e.get("event") == "fill"}
        sets = [e for e in es if e.get("event") in ("settle", "dry_settle")]
        skipped = [e for e in es if e.get("event") == "signal_skipped"]
        out(f"\n===== {mode} =====")
        out(f"{'day (UTC)':<12}{'orders':>7}{'filled':>7}{'settled':>8}{'wins':>6}{'cost':>9}{'fees':>8}{'P&L':>9}")
        days = sorted({e.get("day") or _day(e["ts"]) for e in sets} | {_day(e["ts"]) for e in orders})
        tot = {"o": 0, "f": 0, "s": 0, "w": 0, "c": 0.0, "fe": 0.0, "p": 0.0}
        for d in days:
            o = [e for e in orders if _day(e["ts"]) == d]
            f = [fills[e["ticker"]] for e in o if e["ticker"] in fills and fills[e["ticker"]]["n"] > 0] \
                if mode != "DRYRUN" else o
            s = [e for e in sets if (e.get("day") or _day(e["ts"])) == d and e.get("n")]
            w = sum(1 for e in s if e.get("result") == e.get("side"))
            c, fe, p = sum(e["cost"] for e in s), sum(e["fees"] for e in s), sum(e["pnl"] for e in s)
            out(f"{d:<12}{len(o):>7}{len(f):>7}{len(s):>8}{w:>6}{c:>9.2f}{fe:>8.2f}{p:>+9.2f}")
            for k, v in zip("o f s w c fe p".split(), (len(o), len(f), len(s), w, c, fe, p)):
                tot[k] += v
        out(f"{'TOTAL':<12}{tot['o']:>7}{tot['f']:>7}{tot['s']:>8}{tot['w']:>6}{tot['c']:>9.2f}{tot['fe']:>8.2f}{tot['p']:>+9.2f}")
        if tot["s"]:
            pnls = [e["pnl"] for e in sets if e.get("n")]
            avg = sum(pnls) / len(pnls)
            sd = float(np.std(pnls, ddof=1)) if len(pnls) > 1 else float("nan")
            t = avg / (sd / math.sqrt(len(pnls))) if len(pnls) > 1 and sd > 0 else float("nan")
            out(f"average P&L per settled trade ${avg:+.3f} over {len(pnls)} trades (t = {t:.2f}); "
                f"win rate {tot['w'] / tot['s']:.0%}")
        if mode != "DRYRUN" and orders:
            out(f"fill rate {tot['f'] / tot['o']:.0%}; signals skipped by limits/staleness: {len(skipped)}")
            unknown = [e["ticker"] for e in es if e.get("event") == "order_unknown"]
            if unknown:
                out(f"orders with unconfirmed status (reconciled at settlement): {unknown}")
        if (a.live and mode == "LIVE") or (a.demo and mode == "DEMO"):
            _report_kalshi(PROD if mode == "LIVE" else DEMO, {e["ticker"] for e in orders}, sets, out)
    return 0


def _report_kalshi(base, tickers, sets, out):
    try:
        api = KalshiAPI.from_env(base)
    except SystemExit as e:
        out(f"(skipping Kalshi cross-check: {e})")
        return
    logged = {e["ticker"]: e for e in sets}
    tot, n, diff = 0.0, 0, []
    try:
        for tk in sorted(tickers):
            for s in api.settlements(ticker=tk):
                if s.get("ticker") != tk:
                    continue
                pnl = _f(s.get("revenue")) / 100 - _f(s.get("yes_total_cost_dollars")) \
                    - _f(s.get("no_total_cost_dollars")) - _f(s.get("fee_cost"))
                tot += pnl
                n += 1
                if tk not in logged or abs(logged[tk]["pnl"] - pnl) > 0.02:
                    diff.append((tk, round(pnl, 2), logged.get(tk, {}).get("pnl")))
    except requests.RequestException as e:
        out(f"Kalshi fetch failed: {e}")
        return
    out(f"Kalshi settlements for our tickers: {n} markets, P&L ${tot:+.2f} (revenue - cost - fees)")
    for tk, k, lg in diff:
        out(f"  differs from log: {tk} kalshi ${k:+.2f} vs log {lg}")


if __name__ == "__main__":
    sys.exit(main())
