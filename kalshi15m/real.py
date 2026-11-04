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
import threading
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

ALL9 = ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXHYPE15M", "KXBNB15M", "KXNEAR15M", "KXDOGE15M",
        "KXZEC15M"]
FROZEN_RULES = {  # exactly the settings that passed the lab's holdout as "ALL" (see kalshi15m/live.json)
    "fair_value": {"strategy": "fair_value", "params": {"start": 2, "end": 13, "edge": 0.12, "vol_mult": 0.8}},
    "fair_value_v2": {"strategy": "fair_value_v2",
                      "params": {"start": 2, "end": 13, "edge": 0.12, "vol": "60", "min_price": 0.2, "max_price": 0.8}},
}


def golden_frozen() -> dict:
    """The only accepted form of each golden rule in a config: id, family, scope, holdout t, params exactly
    as lab3 froze them (+ the sized stake normaliser). Order of evaluation = golden_live.GOLDEN (best first)."""
    from . import golden_live as GL
    out = {}
    for r in GL.ORDER:
        out[r["id"]] = {k: r[k] for k in ("id", "family", "scope", "t", "params")}
        if r["kind"] in ("sized", "sized_exit"):
            out[r["id"]]["norm"] = r["norm"]
    return out


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


def _key_file_from_env(text: str) -> str:
    """For hosted runs where the key arrives as an env var (KALSHI_PRIVATE_KEY = the PEM text, with real
    or literal \\n line breaks, or base64 of the PEM). Written once to a private file outside the repo."""
    import tempfile
    text = text.strip().replace("\\n", "\n")
    if "BEGIN" not in text:
        text = base64.b64decode(text).decode()
    fd, path = tempfile.mkstemp(prefix="kalshi_", suffix=".pem")
    with os.fdopen(fd, "w") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    os.chmod(path, 0o600)
    return path


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
        if kid and not kp and os.getenv("KALSHI_PRIVATE_KEY"):
            kp = _key_file_from_env(os.environ["KALSHI_PRIVATE_KEY"])
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
        # the demo exchange keeps some long-closed markets listed as "open": only consider ones still running
        ms = [m for m in ms if bot._ts(m["close_time"]) > self.clock()] if ms else ms
        m = min(ms, key=lambda m: m["close_time"]) if ms else None
        if m is not None:
            # GET /markets quotes trail the live book by ~5-30 s (see bot.book_quote); deciding on them produced
            # phantom edges and unfillable orders on 2026-11-04. Always price from the live order book; if it
            # can't be read the step is skipped (never falls back to the stale quote).
            m = {**m, **bot.book_quote(self.get(f"/markets/{m['ticker']}/orderbook", deadline=deadline))}
        return m

    def market(self, ticker: str):
        return self.get(f"/markets/{ticker}").get("market", {})

    # --- portfolio (auth)
    def balance(self) -> float:
        d = self.get("/portfolio/balance")
        return float(d["balance_dollars"]) if d.get("balance_dollars") is not None else d["balance"] / 100

    def balances(self) -> tuple[float, float]:
        """(total, crypto) in dollars. crypto = exchange shard 2 (balance_breakdown, a dollar string), where
        crypto markets trade from; the total when the breakdown is absent (subaccount-restricted keys)."""
        d = self.get("/portfolio/balance")
        total = float(d["balance_dollars"]) if d.get("balance_dollars") is not None else d["balance"] / 100
        bd = {int(x["exchange_index"]): float(x["balance"]) for x in d.get("balance_breakdown") or []}
        return total, bd.get(2, total if not bd else 0.0)

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


def exit_order_body(ticker: str, held: str, sell_price: float, n: int, client_order_id: str) -> dict:
    """Sell a held position (golden scalp exit), IOC + reduce-only, quoted on the YES book like order_body:
    sell YES at the yes bid = "ask" @ bid; sell NO at the no bid = buy YES ("bid") @ 1 - no bid (= yes ask)."""
    yes_px = sell_price if held == "yes" else 1 - sell_price
    return {"ticker": ticker, "client_order_id": client_order_id,
            "side": "ask" if held == "yes" else "bid",
            "count": str(int(n)), "price": f"{round(yes_px, 4):.4f}",
            "time_in_force": "immediate_or_cancel", "self_trade_prevention_type": "taker_at_cross",
            "post_only": False, "reduce_only": True}


def exit_fill_summary(fills: list, held: str):
    """Contracts sold, proceeds and fees of the fills of an exit order. A fill's yes/no prices are the
    traded YES price and 1 minus it, so the held side's price is the sale price whatever outcome_side says."""
    k = proceeds = fees = 0.0
    for f in fills:
        c = _f(f.get("count_fp", f.get("count")))
        k += c
        proceeds += c * _f(f.get("yes_price_dollars" if held == "yes" else "no_price_dollars"))
        fees += _f(f.get("fee_cost"))
    return round(k, 2), round(proceeds, 6), round(fees, 6)


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


# Account-wide limits (optional; limits keys max_total_open_risk_usd / max_total_daily_loss_usd). In multi-coin
# mode every coin has its own Runner (thread) and its own per-coin limits; these add caps across ALL coins that
# share one account (same mode and log). The lock makes check-then-reserve atomic across coin threads.
_ACCOUNT_LOCK = threading.RLock()
_ACCOUNT_RUNNERS: list = []


class Runner:
    def __init__(self, cfg: dict, mode: str, api: KalshiAPI, market_api: KalshiAPI | None = None,
                 log_path: Path = LOG, stop_path: Path = STOP_FILE, clock=time.time, sleep=time.sleep,
                 spot_fn=None, max_minutes: int | None = None, out=print, stop_event=None, engine=None):
        assert mode in ("DEMO", "LIVE", "DRYRUN")
        self.cfg, self.mode, self.api = cfg, mode, api
        self.mapi = market_api or api            # where quotes come from (= the exchange we trade on)
        self.dry = mode == "DRYRUN"
        self.L = cfg["limits"]
        self.series, self.params = cfg["series"], cfg["params"]
        # golden mode (config key "golden_rules"): lab3's 16 golden rules via golden_live, best first
        self.golden = "golden_rules" in cfg
        if self.golden:
            from . import golden_live as GL
            ids = {r["id"] for r in cfg["golden_rules"]}
            self.golden_ids = [rid for rid in GL.rules_for(self.series) if rid in ids]   # best first
            self.rules = [(rid, None, GL.RULES[rid]["params"]) for rid in self.golden_ids]
            self.engine = engine or GL.engine(self.series)
        else:
            # one or more rules on this coin; the first that fires takes the market (one bet per market)
            rules = cfg.get("rules") or [{"name": cfg["strategy"], "strategy": cfg["strategy"], "params": cfg["params"]}]
            self.rules = [(r["name"], STRATEGIES[r["strategy"]][0], r["params"]) for r in rules]
        self.fn = self.rules[0][1] if self.rules else None
        self.stop_event = stop_event
        self.product = SERIES[self.series]
        self.log_path, self.stop_path = Path(log_path), Path(stop_path)
        with _ACCOUNT_LOCK:
            _ACCOUNT_RUNNERS[:] = [r for r in _ACCOUNT_RUNNERS if r.series != self.series
                                   or r.mode != mode or r.log_path != self.log_path]   # in-process restarts
            _ACCOUNT_RUNNERS.append(self)
        self.clock, self.sleep, self.out = clock, sleep, out
        self.spot_fn = spot_fn or bot._spot_and_vol
        self.max_minutes = max_minutes
        self.stop_requested = False
        self.cur, self.P, self.seen, self.minutes_run = None, None, set(), 0
        self.balance = None
        self.crypto_balance = None               # shard 2, only tracked with limits.stake_pct_of_balance
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
                                "max_cost": e.get("max_cost", 0.0), "rule": e.get("rule"), "minute": e.get("minute")}
                if ev == "would_order":   # dry run: pretend the order filled as the paper bot does
                    self.pos[tk].update(n=e["n"], cost=e["n"] * e["price"], fees=kalshi_fee(e["price"], e["n"]),
                                        status="filled")
            elif ev == "fill" and tk in self.pos:
                self.pos[tk].update(n=e["n"], cost=e["cost"], fees=e["fees"], status="filled" if e["n"] > 0 else "none",
                                    order_id=e.get("order_id"))
            elif ev == "order_unknown" and tk in self.pos:
                self.pos[tk]["status"] = "unknown"
            elif ev in ("order_rejected",) and tk in self.pos:
                self.pos[tk]["status"] = "none"
            elif ev == "exit" and tk in self.pos:            # early exit (scalp rules): part or all sold
                p = self.pos[tk]
                p.update(n=e["remaining"], cost=e["remaining_cost"], fees=e["remaining_fees"],
                         exited=p.get("exited", 0.0) + e["n"], exit_pnl=p.get("exit_pnl", 0.0) + e["pnl"])
                p.setdefault("exit_orders", []).append(e.get("order_id"))
                d = e.get("day") or _day(e["ts"])
                if e["ts"] >= self.L.get("daily_loss_ignore_before_ts", 0):
                    self.pnl_by_day[d] = self.pnl_by_day.get(d, 0.0) + e["pnl"]
                if e["remaining"] <= 1e-9:
                    self.settled.add(tk)
            elif ev == "exit_unknown" and tk in self.pos:
                self.pos[tk]["exit_unknown"] = e.get("client_order_id") or True
            elif ev == "exit_rejected" and tk in self.pos:
                self.pos[tk]["exit_blocked"] = True
            elif ev in ("settle", "dry_settle"):
                self.settled.add(tk)
                d = e.get("day") or _day(e["ts"])
                # daily_loss_ignore_before_ts (optional): P&L logged before this time is left out of the daily
                # loss cap (used once, by the account holder's choice, after losses caused by a fixed bug)
                if e["ts"] >= self.L.get("daily_loss_ignore_before_ts", 0):
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

    def account_peers(self):
        """Every runner trading the same account in this process (this one included)."""
        with _ACCOUNT_LOCK:
            return [r for r in _ACCOUNT_RUNNERS if r.mode == self.mode and r.log_path == self.log_path]

    def account_open_risk(self):
        return sum(r.open_risk() for r in self.account_peers())

    def account_day_pnl(self):
        return sum(r.day_pnl() for r in self.account_peers())

    def blocked(self, new_cost: float = 0.0):
        """Reason not to place a new order now, or None. new_cost: worst-case cost of the order being considered."""
        if self.stop_path.exists():
            raise Stop(f"kill switch: {self.stop_path} exists")
        tot_risk, tot_loss = self.L.get("max_total_open_risk_usd"), self.L.get("max_total_daily_loss_usd")
        if tot_loss is not None and self.account_day_pnl() - self.account_open_risk() - new_cost <= -tot_loss:
            return (f"account daily loss cap: all coins settled ${self.account_day_pnl():+.2f}, at risk "
                    f"${self.account_open_risk():.2f} (+${new_cost:.2f}), cap ${tot_loss:.2f} (stopped until 00:00 UTC)")
        if tot_risk is not None and self.account_open_risk() + new_cost > tot_risk:
            return (f"account open-risk cap: ${self.account_open_risk():.2f} already at risk across all coins "
                    f"+ ${new_cost:.2f} > ${tot_risk:.2f}")
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
        what = (f"golden rules (best first) {[r[0] for r in self.rules]}" if self.golden
                else f"{self.cfg['strategy']} {self.params}")
        pct = self.L.get("stake_pct_of_balance")
        stake = (f"stake max(${self.L['stake_usd_min']}, {pct:.0%} of the crypto balance) (${self.L['stake_usd']} "
                 f"while unknown)" if pct else f"stake ${self.L['stake_usd']}/trade")
        self.out(f"[{self.mode}] {what} on {self.series}, taker IOC, "
                 f"{stake}, daily loss cap ${self.L['max_daily_loss_usd']}, "
                 f"log {self.log_path}")
        self.log({"event": "start", "limits": self.L, "params": self.params, "strategy": self.cfg["strategy"],
                  "rules": [r[0] for r in self.rules]})
        day = self.today()
        if self.golden:
            self.prepare_engine()
        try:
            if not self.dry:
                try:
                    self.api.balance()
                except ApiError as e:
                    if e.status in (401, 403):
                        raise Stop(f"Kalshi rejected the API key ({e}). Check KALSHI_KEY_ID / KALSHI_PRIVATE_KEY_PATH "
                                   f"and that the key belongs to the {'demo' if self.mode == 'DEMO' else 'real'} "
                                   f"exchange.", EXIT_CONFIG) from None
                except requests.RequestException:
                    pass
                self.refresh_balance()
                self.reconcile()
            while True:
                if self.halted():
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

    def halted(self):
        return self.stop_requested or (self.stop_event is not None and self.stop_event.is_set())

    def prepare_engine(self):
        """Golden mode: load + catch up the spot history before the first decision (update() retries
        later if this fails, e.g. Coinbase unreachable)."""
        t0 = time.time()
        try:
            self.engine.prepare()
            self.out(f"  {self.series}: spot history ready ({time.time() - t0:.1f}s)")
        except (requests.RequestException, OSError, ValueError) as e:
            self.out(f"  {self.series}: spot history not ready ({e}); will retry each minute")
            self.log({"event": "skip", "reason": "engine_prepare", "error": str(e)[:200]})

    def wait_minute(self):
        """Wake 0.5 s after the next minute boundary (bot._wait(poll="minute")), in small steps
        so Ctrl+C and the STOP file are noticed quickly."""
        target = self.clock() + (60 - self.clock() % 60 + 0.5)
        while True:
            left = target - self.clock()
            if left <= 0 or self.halted() or self.stop_path.exists():
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
            if self.golden:
                obs = self.observe_golden(m, minute, open_ts)
            else:
                spot, vol, vol240, bars = self.spot_fn(self.product)
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
            self.out(f"  spot data error: {e}; skipping this minute")
            self.log({"event": "skip", "reason": "network_spot", "ticker": self.cur, "minute": minute,
                      "error": str(e)[:200]})
            return self.housekeeping()
        if not self.golden:
            obs = observe(self.P, m, minute, spot, vol, vol240, bars)
        spot = obs["spot"]
        self.seen.add(minute)
        self.minutes_run += 1
        t_dec = self.clock()
        lag = round(t_dec - (open_ts + 60 * minute), 2)
        age = round(t_dec - min(t_quote, t_spot), 2)
        mdl = obs["model"]
        self.out(f"{datetime.now():%H:%M:%S} {self.cur} m{minute:02d} spot={spot:.4f} K={obs['strike']:.4f} "
                 f"bid/ask={obs['yes_bid']:.3f}/{obs['yes_ask']:.3f} model={mdl if mdl is None else round(mdl, 3)} "
                 f"lag={lag}s" + (f" ({'synthetic' if obs.get('synthetic') else 'candle'} bar, quote {t_spot - t_quote:.2f}s"
                                  f" + spot {obs.get('engine_s', 0):.2f}s)" if self.golden else ""))
        if self.golden:
            self.manage_exit(minute, obs, lag, age)
            if self.cur not in self.traded:
                sigs = self.engine.signals(self.P, minute, self.golden_ids)
                if sigs:
                    best = sigs[0]
                    self.act(m, minute, (best.side, best.price),
                             {**obs, "rule": best.rule, "also_signalled": [s.rule for s in sigs[1:]]},
                             lag, age, open_ts, signal=best)
        elif self.cur not in self.traded:
            for name, fn, params in self.rules:
                sig = decide(fn, self.P, params, minute)
                if sig:
                    self.act(m, minute, sig, {**obs, "rule": name}, lag, age, open_ts)
                    break
        self.housekeeping()

    def observe_golden(self, m, minute, open_ts):
        """Quotes + strike exactly like observe(); spot fields and every lab3 feature from the golden engine
        (Coinbase candles; the bar that just closed from the live ticker until Coinbase publishes it)."""
        obs = observe(self.P, m, minute, np.nan, np.nan, np.nan, {})
        info = self.engine.update(self.P, open_ts, minute)
        j = minute - 1
        pm = self.P["p_model"][0, j]
        obs.update(spot=info["spot"], vol1m=info["vol1m"], vol240=info["vol240"],
                   model=float(pm) if np.isfinite(pm) else None, synthetic=info["synthetic"],
                   engine_s=info["update_s"])
        return obs

    def act(self, *a, **kw):
        if self.L.get("max_total_open_risk_usd") is None and self.L.get("max_total_daily_loss_usd") is None:
            return self._act(*a, **kw)
        with _ACCOUNT_LOCK:        # check + reserve across coins atomically (orders on other coins wait briefly)
            return self._act(*a, **kw)

    def _act(self, m, minute, sig, obs, lag, age, open_ts, signal=None):
        side, price = sig
        tk = self.cur
        base = {"ticker": tk, "minute": minute, "side": side, "price": price, "lag_s": lag, "data_age_s": age,
                **obs, "yes_ask_size": m.get("yes_ask_size_fp"), "yes_bid_size": m.get("yes_bid_size_fp")}
        stake = self.base_stake()
        if self.L.get("stake_pct_of_balance") or signal is not None:
            base.update(base_stake=round(stake, 4), balance_crypto=self.crypto_balance)
        if signal is not None:                      # golden rule: its model value, and Kelly stake if "sized"
            base["q"] = round(signal.q, 6)
            if signal.kind in ("sized", "sized_exit"):
                from . import golden_live as GL
                stake, kel = GL.sized_stake(signal.rule, signal.q, price, stake)
                base.update(kelly=round(kel, 6), stake=round(stake, 4), norm=GL.RULES[signal.rule]["norm"])
        why = self.blocked()
        if why is None and lag > self.L["max_decision_lag_s"]:
            why = f"decision lag {lag}s > {self.L['max_decision_lag_s']}s"
        if why is None and age > self.L["max_data_age_s"]:
            why = f"data {age}s old > {self.L['max_data_age_s']}s"
        if why is None and not (self.L["min_price"] <= price <= self.L["max_price"]):
            why = f"price {price} outside [{self.L['min_price']}, {self.L['max_price']}]"
        # walk_cents (default off): thin books often show only a few contracts at the best price. Let the IOC
        # order reach up to walk_cents deeper, but never closer than walk_keep_edge to the rule's model value.
        limit = price
        if signal is not None and self.L.get("walk_cents"):
            lim2 = min(price + self.L["walk_cents"] / 100, signal.q - self.L.get("walk_keep_edge", 0.06))
            lim2 = math.floor(lim2 * 100 + 1e-9) / 100
            if price < lim2 <= self.L["max_price"]:
                limit = lim2
                base["limit"] = limit
        n = contracts_for(stake, limit, self.L["max_contracts_per_order"])
        if why is None and n < 1:
            why = "stake too small for one contract"
        max_cost = round(n * limit + kalshi_fee(limit, n), 4)
        if why is None and (self.L.get("max_total_open_risk_usd") is not None
                            or self.L.get("max_total_daily_loss_usd") is not None):
            why = self.blocked(max_cost)
        if why is None and not self.dry and self.balance is not None and self.balance < max_cost:
            why = f"balance ${self.balance:.2f} < order cost ${max_cost:.2f}"
        if why is None and not self.dry and self.L.get("stake_pct_of_balance") and self.crypto_balance is not None \
                and self.crypto_balance < max_cost:
            why = f"crypto (shard 2) balance ${self.crypto_balance:.2f} < order cost ${max_cost:.2f}"
        if why:
            self.out(f"  signal {side.upper()} @ {price:.3f} skipped: {why}")
            self.log({"event": "signal_skipped", "reason": why, **base})
            return
        coid = str(uuid.uuid4())
        body = order_body(tk, side, limit, n, coid)
        # mark the market as traded BEFORE sending, so a crash can never lead to a second order
        self.traded.add(tk)
        d = self.today()
        self.trades_by_day[d] = self.trades_by_day.get(d, 0) + 1
        self.pos[tk] = {"side": side, "n": 0.0, "cost": 0.0, "fees": 0.0, "close_ts": open_ts + 900,
                        "status": "pending", "limit": price, "max_cost": max_cost, "rule": obs.get("rule"),
                        "minute": minute}
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
            self.pos[tk].update(n=filled, cost=cost, fees=fees, status="filled", order_id=order_id)
            part = " (PARTIAL)" if filled < n else ""
            self.out(f"  filled {filled:g}/{n} {side.upper()}{part}, cost ${cost:.2f} + fees ${fees:.2f}")
            if not self.dry:
                self.refresh_balance()
        else:
            self.pos.pop(tk, None)
            self.out("  not filled (0 contracts): no position")

    # --- early exit (golden "scalp" rules: sell back at the bid once it reaches the model's fair value)
    def manage_exit(self, minute, obs, lag, age):
        """Each minute after the entry: if the held side's bid >= the entering rule's model value, sell the
        whole filled position (IOC, reduce-only). Not blocked by the entry limits (daily loss, open positions,
        trade count, balance); the STOP file, and stale data / decision lag, do apply."""
        from . import golden_live as GL
        tk = self.cur
        p = self.pos.get(tk)
        if not p or p.get("status") != "filled" or p["n"] <= 0 or p.get("rule") not in GL.RULES:
            return
        if GL.RULES[p["rule"]]["kind"] not in ("scalp", "sized_exit") or p.get("exit_blocked") or p.get("exit_unknown"):
            return
        hit = GL.exit_check(p["rule"], self.P, minute, p["side"], p.get("minute") or 99)
        if not hit:
            return
        sell, q = hit
        n = int(math.floor(p["n"] + 1e-9))
        base = {"ticker": tk, "minute": minute, "side": p["side"], "rule": p["rule"], "sell_price": sell,
                "model_value": round(q, 6), "held": p["n"], "lag_s": lag, "data_age_s": age,
                "yes_bid": obs.get("yes_bid"), "yes_ask": obs.get("yes_ask")}
        why = None
        if lag > self.L["max_decision_lag_s"]:
            why = f"decision lag {lag}s > {self.L['max_decision_lag_s']}s"
        elif age > self.L["max_data_age_s"]:
            why = f"data {age}s old > {self.L['max_data_age_s']}s"
        elif n < 1:
            why = "less than one whole contract held"
        if why:
            self.out(f"  exit signal {p['side'].upper()} @ {sell:.3f} skipped: {why}")
            self.log({"event": "exit_skipped", "reason": why, **base})
            return
        if self.dry:
            self.out(f"  <<< WOULD SELL {n} {p['side'].upper()} @ {sell:.3f} (model {q:.3f})")
            self._book_exit(tk, p, n, n * sell, kalshi_fee(sell, n), None, "dry", sell, minute)
            return
        coid = str(uuid.uuid4())
        body = exit_order_body(tk, p["side"], sell, n, coid)
        self.log({"event": "exit_intent", "n": n, "client_order_id": coid, "order": body, **base})
        self.out(f"  <<< SELL {n} {p['side'].upper()} @ {sell:.3f} IOC reduce-only (model {q:.3f})")
        self._place_exit(tk, p, body, n, sell, minute)

    def _place_exit(self, tk, p, body, n, sell, minute):
        coid, sent_at = body["client_order_id"], int(self.clock())
        resp, err = None, None
        for attempt in range(2):
            try:
                resp = self.api.create_order(body)
                break
            except ApiError as e:
                if e.status == 429 and attempt == 0:
                    self.sleep(0.3)
                    continue
                if e.status == 409:
                    err = "duplicate"
                    break
                # rejected = not executed: keep the position, hold it to settlement
                self.out(f"  exit order REJECTED: {e}; holding to settlement")
                self.log({"event": "exit_rejected", "ticker": tk, "client_order_id": coid, "status": e.status,
                          "error": e.body[:500]})
                p["exit_blocked"] = True
                return
            except Uncertain as e:
                err = str(e)
                break
        if resp is None:
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
                # never resend: no more exits on this market; settlement reconciles it from the fills
                p["exit_unknown"] = coid
                self.out("  could not confirm the exit order; holding the rest, reconciled at settlement")
                self.log({"event": "exit_unknown", "ticker": tk, "client_order_id": coid, "error": err})
                return
            resp = {"order_id": o.get("order_id"), "fill_count": o.get("fill_count_fp"), "from_lookup": True}
        self.log({"event": "exit_response", "ticker": tk, "client_order_id": coid, "response": resp})
        order_id = resp.get("order_id")
        filled = _f(resp.get("fill_count"))
        try:
            order = self.api.get_order(order_id) if order_id else {}
            filled = _f(order.get("fill_count_fp"), filled) if order else filled
            if order and order.get("status") == "resting":
                try:
                    self.api.cancel_order(order_id)
                except (ApiError, Uncertain) as e:
                    self.log({"event": "cancel_failed", "ticker": tk, "order_id": order_id, "error": str(e)})
                order = self.api.get_order(order_id) or order
                filled = _f(order.get("fill_count_fp"), filled)
        except requests.RequestException as e:
            self.log({"event": "get_order_failed", "ticker": tk, "order_id": order_id, "error": str(e)[:200]})
        filled = min(filled, p["n"])
        if filled <= 0:
            self.out("  exit not filled (0 contracts): still holding")
            self.log({"event": "exit_unfilled", "ticker": tk, "order_id": order_id, "limit": sell})
            return
        proceeds = fees = None
        src = None
        for _ in range(3):
            try:
                fl = self.api.fills(order_id=order_id)
            except requests.RequestException:
                fl = []
            k, pr, fe = exit_fill_summary(fl, p["side"])
            if k >= filled - 1e-9:
                proceeds, fees, src = pr, fe, "fills"
                break
            self.sleep(0.5)
        if proceeds is None:            # fills not visible yet: our limit price (IOC never sells below it)
            proceeds, fees, src = filled * sell, kalshi_fee(sell, int(math.ceil(filled))), "estimate"
        self._book_exit(tk, p, filled, proceeds, fees, order_id, src, sell, minute)
        self.refresh_balance()

    def _book_exit(self, tk, p, k, proceeds, fees2, order_id, src, sell, minute):
        """Realised P&L of the contracts sold: proceeds - their share of the entry cost and fee - exit fee
        (all sold: n * (sell - buy) - both fees). The rest of the position stays and settles normally."""
        frac = k / p["n"]
        cost_k, fee_k = p["cost"] * frac, p["fees"] * frac
        pnl = proceeds - cost_k - fee_k - fees2
        rem = p["n"] - k
        rec = {"event": "exit", "ticker": tk, "order_id": order_id, "side": p["side"], "rule": p.get("rule"),
               "minute": minute, "n": k, "limit": sell, "sell_avg": round(proceeds / k, 6), "proceeds": round(proceeds, 6),
               "exit_fees": round(fees2, 6), "entry_cost": round(cost_k, 6), "entry_fees": round(fee_k, 6),
               "pnl": round(pnl, 6), "remaining": round(rem, 6), "remaining_cost": round(p["cost"] - cost_k, 6),
               "remaining_fees": round(p["fees"] - fee_k, 6), "day": _day(p["close_ts"] - 1), "source": src,
               "close_ts": p["close_ts"]}
        self.log(rec)
        p.update(n=rec["remaining"], cost=rec["remaining_cost"], fees=rec["remaining_fees"],
                 exited=p.get("exited", 0.0) + k, exit_pnl=p.get("exit_pnl", 0.0) + rec["pnl"])
        p.setdefault("exit_orders", []).append(order_id)
        d = rec["day"]
        self.pnl_by_day[d] = self.pnl_by_day.get(d, 0.0) + rec["pnl"]
        part = "" if rem <= 1e-9 else f" (PARTIAL, {rem:g} still held)"
        self.out(f"  sold {k:g} {p['side'].upper()} @ {proceeds / k:.3f}{part}: P&L ${pnl:+.2f} "
                 f"(today ${self.pnl_by_day[d]:+.2f})")
        if rem <= 1e-9:
            self.settled.add(tk)          # closed: never settled again
            self.pos.pop(tk, None)

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
            if p.get("exited") or p.get("exit_unknown"):
                self._settle_after_exit(tk, p)
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

    def _settle_after_exit(self, tk, p):
        """Settle what is left of a position that was partly sold early (or whose exit order is unconfirmed).
        The sold part was booked by its "exit" event; only the remaining contracts are settled here, at their
        share of the entry cost, so nothing is counted twice. Kalshi's settlement record (netted position)
        is logged for reference only."""
        st = [] if self.dry else [s for s in self.api.settlements(ticker=tk) if s.get("ticker") == tk]
        res = st[0].get("market_result") if st else None
        if res not in ("yes", "no"):
            res = self.mapi.market(tk).get("result")
        if res not in ("yes", "no"):
            return
        if p.get("exit_unknown") and not self.dry:
            known = set(p.get("exit_orders") or []) | {p.get("order_id")}
            fx = [f for f in self.api.fills(ticker=tk) if f.get("order_id") not in known]
            k, proceeds, fees2 = exit_fill_summary(fx, p["side"])
            k = min(k, p["n"])
            p.pop("exit_unknown", None)
            if k > 0:
                self._book_exit(tk, p, k, proceeds, fees2, fx[0].get("order_id"), "fills_at_settlement",
                                round(proceeds / k, 4), None)
            if tk not in self.pos:
                return
        n = p["n"]
        pnl = n * (res == p["side"]) - p["cost"] - p["fees"]
        rec = {"event": "dry_settle" if self.dry else "settle", "ticker": tk, "result": res, "side": p["side"],
               "n": n, "cost": round(p["cost"], 6), "fees": round(p["fees"], 6), "pnl": round(pnl, 4),
               "after_exit": True, "exited": p.get("exited", 0.0), "exit_pnl": round(p.get("exit_pnl", 0.0), 4)}
        if st:
            s = st[0]
            revenue = _f(s.get("revenue")) / 100
            cost_k = _f(s.get("yes_total_cost_dollars")) + _f(s.get("no_total_cost_dollars"))
            rec.update(revenue=revenue, kalshi_cost=cost_k, kalshi_fee=_f(s.get("fee_cost")),
                       pnl_kalshi=round(revenue - cost_k - _f(s.get("fee_cost")), 4), settled_time=s.get("settled_time"))
        self.finish(tk, p, rec)
        if not self.dry:
            self.refresh_balance()

    def finish(self, tk, p, rec):
        d = _day(p["close_ts"] - 1)
        rec["day"] = d
        self.log(rec)
        self.settled.add(tk)
        self.pos.pop(tk, None)
        self.pnl_by_day[d] = self.pnl_by_day.get(d, 0.0) + rec["pnl"]
        self.out(f"  settled {tk}: {rec['result']} -> P&L ${rec['pnl']:+.2f} (today ${self.pnl_by_day[d]:+.2f})")

    def base_stake(self):
        """Dollars per bet before any Kelly scaling. With limits.stake_pct_of_balance (compounding):
        max(stake_usd_min, pct x crypto balance), stake_usd while the balance is unknown (e.g. dry run)."""
        pct = self.L.get("stake_pct_of_balance")
        if not pct or self.crypto_balance is None:
            return self.L["stake_usd"]
        return max(self.L["stake_usd_min"], pct * self.crypto_balance)

    def refresh_balance(self):
        try:
            if self.L.get("stake_pct_of_balance"):
                try:
                    self.balance, self.crypto_balance = self.api.balances()
                except (KeyError, ValueError, TypeError) as e:
                    self.out(f"  balance check failed: unexpected answer ({e})")
                    return
            else:
                self.balance = self.api.balance()
        except requests.RequestException as e:
            self.out(f"  balance check failed: {e}")
            return
        if self.L.get("min_balance_counts_open_bets"):
            equity = self.balance + self.account_open_risk()     # cash + what open bets cost (not yet won/lost)
        else:
            equity = self.balance
        if equity < self.L["min_balance_usd"]:
            self.log({"event": "min_balance", "balance": self.balance, "equity": round(equity, 4)})
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
    if "stake_pct_of_balance" in lim or "stake_usd_min" in lim:   # optional compounding stake (default off)
        pct, mn = lim.get("stake_pct_of_balance"), lim.get("stake_usd_min")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (pct, mn)) \
                or not 0 < pct <= 0.25 or mn <= 0:
            raise Stop(f"{path}: stake_pct_of_balance must be in (0, 0.25] and stake_usd_min > 0 (both set)",
                       EXIT_CONFIG)
    if "daily_loss_ignore_before_ts" in lim and (not isinstance(lim["daily_loss_ignore_before_ts"], (int, float))
                                                 or isinstance(lim["daily_loss_ignore_before_ts"], bool)
                                                 or lim["daily_loss_ignore_before_ts"] > time.time() + 60):
        raise Stop(f"{path}: daily_loss_ignore_before_ts must be a past unix time", EXIT_CONFIG)
    for k in ("max_total_open_risk_usd", "max_total_daily_loss_usd"):
        if k in lim and (not isinstance(lim[k], (int, float)) or isinstance(lim[k], bool) or lim[k] <= 0):
            raise Stop(f"{path}: {k} must be a positive number", EXIT_CONFIG)
    if not 0 <= lim.get("walk_cents", 0) <= 10 or not 0 <= lim.get("walk_keep_edge", 0.06) <= 0.5:
        raise Stop(f"{path}: walk_cents must be 0-10 and walk_keep_edge 0-0.5", EXIT_CONFIG)
    if "golden_rules" in cfg:   # lab3's golden rules, frozen to the exact lab3 params (see golden_live.GOLDEN)
        frozen = golden_frozen()
        if cfg.get("execution") != "taker" or not cfg.get("series") or not isinstance(cfg["series"], list) \
                or not set(cfg["series"]) <= set(ALL9) or "rules" in cfg or not cfg["golden_rules"]:
            raise Stop(f"{path}: golden config needs series = a list within {ALL9}, execution taker, "
                       f"no 'rules'", EXIT_CONFIG)
        ids = [r.get("id") if isinstance(r, dict) else None for r in cfg["golden_rules"]]
        for r, rid in zip(cfg["golden_rules"], ids):
            if rid not in frozen or r != frozen[rid]:
                raise Stop(f"{path}: golden rule {rid} must stay exactly {frozen.get(rid, list(frozen))}", EXIT_CONFIG)
        if len(set(ids)) != len(ids):
            raise Stop(f"{path}: duplicate golden rule", EXIT_CONFIG)
        cfg.setdefault("strategy", "golden")
        cfg.setdefault("params", {r["id"]: r["params"] for r in cfg["golden_rules"]})
        return cfg
    if "rules" in cfg:   # the pooled 9-coin rules (passed the strict holdout bar as a group)
        if cfg.get("execution") != "taker" or not cfg.get("series") or not set(cfg["series"]) <= set(ALL9):
            raise Stop(f"{path}: series must be a subset of {ALL9}, execution taker", EXIT_CONFIG)
        for r in cfg["rules"]:
            want = FROZEN_RULES.get(r.get("name"))
            if not want or {k: r.get(k) for k in ("strategy", "params")} != want:
                raise Stop(f"{path}: rule {r.get('name')} must stay one of {FROZEN_RULES}", EXIT_CONFIG)
        cfg.setdefault("strategy", "+".join(r["name"] for r in cfg["rules"]))
        cfg.setdefault("params", {r["name"]: r["params"] for r in cfg["rules"]})
        return cfg
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
    try:
        bd = {int(x["exchange_index"]): float(x["balance"]) for x in api.get("/portfolio/balance").get("balance_breakdown", [])}
        if bd:
            print(f"  by exchange shard: {bd}  (crypto markets trade from shard 2)")
            if bd.get(2, 0.0) <= 0:
                print("  WARNING: no money on shard 2, so crypto orders will be rejected (insufficient_shard_balance).")
                print("  Move funds with:  python -m kalshi15m real move-to-crypto --demo|--live --usd AMOUNT")
    except (requests.RequestException, KeyError, ValueError, TypeError):
        pass
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
    ap.add_argument("action", nargs="?", choices=["run", "check", "move-to-crypto"], default="run")
    ap.add_argument("--usd", type=float, default=None, help="move-to-crypto: dollars to move from shard 0 to shard 2")
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
    if cfg.get("log") and a.log == str(LOG):
        a.log = str(ROOT / cfg["log"])
    coins = cfg["series"] if isinstance(cfg["series"], list) else [cfg["series"]]
    if a.action == "move-to-crypto":
        if not a.usd or a.usd <= 0:
            print("give --usd AMOUNT")
            return EXIT_CONFIG
        api = _api_from_env(base)
        body = {"client_transfer_id": str(uuid.uuid4()), "source": "event_contract", "destination": "event_contract",
                "amount": int(round(a.usd * 10000)), "source_exchange_shard": 0, "destination_exchange_shard": 2}
        try:
            print(api._send("POST", "/portfolio/intra_exchange_instance_transfer", body=body))
        except requests.RequestException as e:
            print(f"transfer FAILED: {e}")
            return EXIT_CONFIG
        print(f"moved ${a.usd:.2f} to the crypto shard (2); no orders placed")
        return EXIT_CLEAN
    if a.action == "check":
        try:
            api = _api_from_env(base)
            check(api, coins[0], mode)
            for c in coins[1:]:
                m = api.open_market(c)
                print(f"{c}: {'open market ' + m['ticker'] if m else 'WARNING: no open market visible'}")
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
    if isinstance(cfg["series"], list):
        return supervise_many(cfg, coins, runner_kw, a.minutes)
    return supervise(cfg, runner_kw, a.minutes)


def supervise_many(cfg, coins, runner_kw, minutes):
    """One runner thread per coin (each: one bet per market, its own limits). Ctrl+C or STOP stops all."""
    import threading
    stop = threading.Event()
    codes = {}

    def one(coin):
        codes[coin] = supervise({**cfg, "series": coin}, {**runner_kw, "stop_event": stop}, minutes)
    threads = [threading.Thread(target=one, args=(c,), daemon=True) for c in coins]
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(0.5)
    except KeyboardInterrupt:
        print("\nCtrl+C: stopping all coins after their current step")
        stop.set()
        for t in threads:
            t.join(20)
        return EXIT_CLEAN
    bad = [c for c in codes.values() if c not in (EXIT_CLEAN, None)]
    return max(bad) if bad else EXIT_CLEAN


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
    ap.add_argument("--log", default=None, help="log file, e.g. data/kalshi15m/real_all9_log.jsonl")
    a = ap.parse_args(args)
    if a.log:
        log_path = Path(a.log)
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
        exits = [e for e in es if e.get("event") == "exit" and e.get("n")]     # golden scalp: sold early
        hx = bool(exits)
        skipped = [e for e in es if e.get("event") == "signal_skipped"]
        out(f"\n===== {mode} =====")
        out(f"{'day (UTC)':<12}{'orders':>7}{'filled':>7}{'settled':>8}" + (f"{'exits':>6}" if hx else "")
            + f"{'wins':>6}{'cost':>9}{'fees':>8}{'P&L':>9}")
        days = sorted({e.get("day") or _day(e["ts"]) for e in sets + exits} | {_day(e["ts"]) for e in orders})
        tot = {"o": 0, "f": 0, "s": 0, "x": 0, "w": 0, "c": 0.0, "fe": 0.0, "p": 0.0}
        for d in days:
            o = [e for e in orders if _day(e["ts"]) == d]
            f = [fills[e["ticker"]] for e in o if e["ticker"] in fills and fills[e["ticker"]]["n"] > 0] \
                if mode != "DRYRUN" else o
            s = [e for e in sets if (e.get("day") or _day(e["ts"])) == d and e.get("n")]
            x = [e for e in exits if (e.get("day") or _day(e["ts"])) == d]
            w = sum(1 for e in s if e.get("result") == e.get("side")) + sum(1 for e in x if e["pnl"] > 0)
            c = sum(e["cost"] for e in s) + sum(e["entry_cost"] for e in x)
            fe = sum(e["fees"] for e in s) + sum(e["entry_fees"] + e["exit_fees"] for e in x)
            p = sum(e["pnl"] for e in s) + sum(e["pnl"] for e in x)
            out(f"{d:<12}{len(o):>7}{len(f):>7}{len(s):>8}" + (f"{len(x):>6}" if hx else "")
                + f"{w:>6}{c:>9.2f}{fe:>8.2f}{p:>+9.2f}")
            for k, v in zip("o f s x w c fe p".split(), (len(o), len(f), len(s), len(x), w, c, fe, p)):
                tot[k] += v
        out(f"{'TOTAL':<12}{tot['o']:>7}{tot['f']:>7}{tot['s']:>8}" + (f"{tot['x']:>6}" if hx else "")
            + f"{tot['w']:>6}{tot['c']:>9.2f}{tot['fe']:>8.2f}{tot['p']:>+9.2f}")
        by_tk = {}                  # one number per market: exits + settlement of what was left
        for e in [e for e in sets if e.get("n")] + exits:
            by_tk[e["ticker"]] = by_tk.get(e["ticker"], 0.0) + e["pnl"]
        if tot["s"] or tot["x"]:
            pnls = list(by_tk.values()) if hx else [e["pnl"] for e in sets if e.get("n")]
            avg = sum(pnls) / len(pnls)
            sd = float(np.std(pnls, ddof=1)) if len(pnls) > 1 else float("nan")
            t = avg / (sd / math.sqrt(len(pnls))) if len(pnls) > 1 and sd > 0 else float("nan")
            what = "closed trade (exits + settlements, per market)" if hx else "settled trade"
            out(f"average P&L per {what} ${avg:+.3f} over {len(pnls)} trades (t = {t:.2f}); "
                f"win rate {tot['w'] / (tot['s'] + tot['x']):.0%}")
        if hx or any(e.get("event") in ("exit_unfilled", "exit_rejected", "exit_unknown", "exit_skipped") for e in es):
            full = sum(1 for e in exits if e.get("remaining", 0) <= 1e-9)
            un = sum(1 for e in es if e.get("event") == "exit_unfilled")
            out(f"early exits: {len(exits)} ({full} sold everything, {len(exits) - full} partial), exit P&L "
                f"${sum(e['pnl'] for e in exits):+.2f}; exit orders not filled: {un}, rejected: "
                f"{sum(1 for e in es if e.get('event') == 'exit_rejected')}, unconfirmed: "
                f"{sum(1 for e in es if e.get('event') == 'exit_unknown')}")
        if mode != "DRYRUN" and orders:
            out(f"fill rate {tot['f'] / tot['o']:.0%}; signals skipped by limits/staleness: {len(skipped)}")
            unknown = [e["ticker"] for e in es if e.get("event") == "order_unknown"]
            if unknown:
                out(f"orders with unconfirmed status (reconciled at settlement): {unknown}")
        _report_rules(orders, fills, by_tk, mode, out)
        if (a.live and mode == "LIVE") or (a.demo and mode == "DEMO"):
            _report_kalshi(PROD if mode == "LIVE" else DEMO, {e["ticker"] for e in orders}, sets, out,
                           exited={e["ticker"] for e in exits})
    return 0


def _report_rules(orders, fills, by_tk, mode, out):
    """Per-rule breakdown when several rules share the log (golden: best first, with how often lower-ranked
    rules signalled the same market at the same minute and were de-duplicated)."""
    rules = sorted({e.get("rule") for e in orders if e.get("rule")})
    if len(rules) < 2:
        return
    try:
        from . import golden_live as GL
        rules.sort(key=lambda r: GL.PRIORITY.get(r, 99))
    except ImportError:
        pass
    out(f"{'by rule':<22}{'orders':>7}{'filled':>7}{'closed':>7}{'P&L':>9}{'others also fired':>19}")
    for r in rules:
        o = [e for e in orders if e.get("rule") == r]
        f = o if mode == "DRYRUN" else [e for e in o if e["ticker"] in fills and fills[e["ticker"]]["n"] > 0]
        closed = [e["ticker"] for e in o if e["ticker"] in by_tk]
        pnl = sum(by_tk[t] for t in closed)
        dup = sum(1 for e in o if e.get("also_signalled"))
        out(f"{r:<22}{len(o):>7}{len(f):>7}{len(closed):>7}{pnl:>+9.2f}{dup:>19}")


def _report_kalshi(base, tickers, sets, out, exited=()):
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
                if tk in exited:            # sold early: Kalshi's record covers only what was left
                    continue
                if tk not in logged or abs(logged[tk]["pnl"] - pnl) > 0.02:
                    diff.append((tk, round(pnl, 2), logged.get(tk, {}).get("pnl")))
    except requests.RequestException as e:
        out(f"Kalshi fetch failed: {e}")
        return
    out(f"Kalshi settlements for our tickers: {n} markets, P&L ${tot:+.2f} (revenue - cost - fees)"
        + (f"; {len(exited)} markets sold early are not compared" if exited else ""))
    for tk, k, lg in diff:
        out(f"  differs from log: {tk} kalshi ${k:+.2f} vs log {lg}")


if __name__ == "__main__":
    sys.exit(main())
