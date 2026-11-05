"""Tests for kalshi15m/real.py. No credentials, no network: the HTTP layer is a fake Kalshi.

    python -m pytest tests/test_real.py -q      (or)      python tests/test_real.py
"""
from __future__ import annotations

import base64
import json
import math
import random
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kalshi15m import bot, real  # noqa: E402
from kalshi15m.backtest import kalshi_fee  # noqa: E402

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa  # noqa: E402

CFG = json.loads(real.CONFIG.read_text())
T0 = 1_800_000_000 - 1_800_000_000 % 900          # a market open time (multiple of 15 min)


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def tmpdir():
    import atexit
    import shutil
    d = tempfile.mkdtemp(prefix="kalshi_real_test_")
    atexit.register(shutil.rmtree, d, True)
    return Path(d)


def write_key(d: Path, kind="rsa"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if kind == "rsa" \
        else ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    p = d / f"test_{kind}.pem"
    p.write_bytes(pem)
    return key.public_key(), p


def verify(pub, headers, method, path):
    msg = (headers["KALSHI-ACCESS-TIMESTAMP"] + method + path.split("?")[0]).encode()
    sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
    if isinstance(pub, ed25519.Ed25519PublicKey):
        pub.verify(sig, msg)
    else:
        pub.verify(sig, msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                   hashes.SHA256())


# ----------------------------------------------------------------------------- fake Kalshi over HTTP
class Resp:
    def __init__(self, status, data):
        self.status_code, self._d = status, data
        self.text = json.dumps(data)
        self.content = self.text.encode()

    def json(self):
        return self._d


class FakeKalshi:
    """A tiny in-memory Kalshi. Plug it in as KalshiAPI(session=...)."""

    def __init__(self, clock, pub=None, quotes=None):
        self.clock, self.pub = clock, pub
        self.quotes = quotes or (lambda tk, minute: (0.38, 0.40))     # (yes_bid, yes_ask)
        self.orders, self.fills_, self.posts, self.calls = {}, [], [], []
        self.fill_qty = lambda body: int(body["count"])               # how many contracts fill
        self.post_fail = []          # queue of failure modes for the next POSTs
        self.results = {}            # ticker -> "yes"/"no"
        self.balance_cents = 100_00
        self.shard2 = None           # dollars on the crypto shard (adds balance_breakdown when set)

    # market helpers
    def market_at(self, t):
        o = int(t // 900 * 900)
        return self.market_dict(o)

    def market_dict(self, o):
        tk = f"KXNEAR15M-T{o}"
        minute = int((self.clock() - o) // 60)
        yb, ya = self.quotes(tk, minute)
        res = self.results.get(tk, "") if self.clock() >= o + 900 else ""
        return {"ticker": tk, "open_time": iso(o), "close_time": iso(o + 900), "floor_strike": 4.0,
                "yes_bid_dollars": f"{yb:.4f}", "yes_ask_dollars": f"{ya:.4f}", "status": "active",
                "yes_ask_size_fp": "100.00", "yes_bid_size_fp": "100.00", "result": res}

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        u = urlparse(url)
        path = u.path
        self.calls.append((method, path, params, json))
        assert path.startswith("/trade-api/v2/"), path
        if path.startswith("/trade-api/v2/portfolio"):
            assert self.pub is not None and headers and "KALSHI-ACCESS-SIGNATURE" in headers
            verify(self.pub, headers, method, path)      # raises if the signature is wrong
        p = path[len("/trade-api/v2"):]
        params = params or {}
        if method == "GET" and p == "/markets":
            return Resp(200, {"markets": [self.market_at(self.clock())], "cursor": ""})
        if method == "GET" and p.startswith("/markets/") and p.endswith("/orderbook"):
            tk = p.split("/")[-2]
            yb, ya = self.quotes(tk, int((self.clock() - int(tk.split("-T")[1])) // 60))
            self.book_reads = getattr(self, "book_reads", 0) + 1
            return Resp(200, {"orderbook_fp": {"yes_dollars": [[f"{yb - 0.01:.4f}", "50.00"], [f"{yb:.4f}", "100.00"]] if yb > 0 else [],
                                               "no_dollars": [[f"{1 - ya - 0.01:.4f}", "50.00"], [f"{1 - ya:.4f}", "100.00"]] if ya < 1 else []}})
        if method == "GET" and p.startswith("/markets/"):
            tk = p.split("/")[-1]
            o = int(tk.split("-T")[1])
            return Resp(200, {"market": self.market_dict(o)})
        if p == "/portfolio/balance":
            d = {"balance": self.balance_cents, "balance_dollars": f"{self.balance_cents / 100:.4f}"}
            if self.shard2 is not None:
                d["balance_breakdown"] = [{"exchange_index": 0, "balance": f"{self.balance_cents / 100 - self.shard2:.4f}"},
                                          {"exchange_index": 2, "balance": f"{self.shard2:.4f}"}]
            return Resp(200, d)
        if p == "/portfolio/positions":
            return Resp(200, {"market_positions": [], "cursor": ""})
        if method == "POST" and p == "/portfolio/events/orders":
            return self.post(json)
        if method == "GET" and p.startswith("/portfolio/orders/"):
            return Resp(200, {"order": self.orders[p.split("/")[-1]]})
        if method == "GET" and p == "/portfolio/orders":
            os_ = [o for o in self.orders.values() if o["ticker"] == params.get("ticker")]
            return Resp(200, {"orders": os_, "cursor": ""})
        if method == "GET" and p == "/portfolio/fills":
            fl = [f for f in self.fills_ if ("order_id" not in params or f["order_id"] == params["order_id"])
                  and ("ticker" not in params or f["ticker"] == params["ticker"])]
            return Resp(200, {"fills": fl, "cursor": ""})
        if method == "GET" and p == "/portfolio/settlements":
            return Resp(200, {"settlements": self.settlements(params.get("ticker")), "cursor": ""})
        if method == "DELETE":
            return Resp(200, {})
        raise AssertionError(f"unexpected {method} {p}")

    def post(self, body):
        mode = self.post_fail.pop(0) if self.post_fail else None
        if mode == "timeout_before":
            raise requests.Timeout("read timed out")
        if mode == "429":
            return Resp(429, {"error": "too many requests"})
        if mode == "400":
            return Resp(400, {"error": {"code": "invalid_order", "message": "bad"}})
        if any(o["client_order_id"] == body["client_order_id"] for o in self.orders.values()):
            return Resp(409, {"error": {"code": "duplicate", "message": "exists"}})
        self.posts.append(body)
        oid = f"oid{len(self.orders) + 1}"
        n = int(body["count"])
        k = min(self.fill_qty(body), n)
        yes_px = float(body["price"])
        side = "yes" if body["side"] == "bid" else "no"
        px = yes_px if side == "yes" else 1 - yes_px
        fee = kalshi_fee(px, k) if k else 0.0
        self.orders[oid] = {"order_id": oid, "client_order_id": body["client_order_id"], "ticker": body["ticker"],
                            "status": "executed" if k == n else "canceled", "outcome_side": side,
                            "book_side": body["side"], "fill_count_fp": f"{k:.2f}",
                            "remaining_count_fp": "0.00", "initial_count_fp": f"{n:.2f}",
                            "taker_fill_cost_dollars": f"{k * px:.4f}", "taker_fees_dollars": f"{fee:.4f}",
                            "maker_fill_cost_dollars": "0.0000", "maker_fees_dollars": "0.0000",
                            "yes_price_dollars": f"{yes_px:.4f}", "no_price_dollars": f"{1 - yes_px:.4f}"}
        if k:
            self.fills_.append({"fill_id": f"f{oid}", "order_id": oid, "ticker": body["ticker"], "outcome_side": side,
                                "book_side": body["side"], "count_fp": f"{k:.2f}",
                                "yes_price_dollars": f"{yes_px:.4f}", "no_price_dollars": f"{1 - yes_px:.4f}",
                                "is_taker": True, "fee_cost": f"{fee:.4f}"})
        if mode == "timeout_after":
            raise requests.ConnectionError("connection reset after send")
        return Resp(201, {"order_id": oid, "client_order_id": body["client_order_id"], "fill_count": f"{k:.2f}",
                          "remaining_count": "0.00", "ts_ms": int(self.clock() * 1000)})

    def settlements(self, ticker):
        out = []
        for tk in {f["ticker"] for f in self.fills_}:
            if ticker and tk != ticker:
                continue
            o = int(tk.split("-T")[1])
            if self.clock() < o + 900 or tk not in self.results:
                continue
            fl = [f for f in self.fills_ if f["ticker"] == tk]
            side = fl[0]["outcome_side"]
            n = sum(float(f["count_fp"]) for f in fl)
            cost = sum(float(f["count_fp"]) * float(f[f"{side}_price_dollars"]) for f in fl)
            fee = sum(float(f["fee_cost"]) for f in fl)
            res = self.results[tk]
            out.append({"ticker": tk, "market_result": res, "yes_count_fp": f"{n if side == 'yes' else 0:.2f}",
                        "no_count_fp": f"{n if side == 'no' else 0:.2f}",
                        "yes_total_cost_dollars": f"{cost if side == 'yes' else 0:.4f}",
                        "no_total_cost_dollars": f"{cost if side == 'no' else 0:.4f}",
                        "revenue": int(round(n * 100)) if res == side else 0, "fee_cost": f"{fee:.4f}",
                        "settled_time": iso(o + 901)})
        return out


def spot_up(product):
    """Spot 1% above the 4.0 strike with tiny vol: model says YES ~ 100%."""
    return 4.04, 0.001, 0.001, {}


def make_runner(d, clock, fake, key_path, mode="LIVE", spot_fn=spot_up, cfg=CFG):
    api = real.KalshiAPI("https://fake", "test-key-id", str(key_path), session=fake, clock=clock, sleep=clock.sleep)
    return real.Runner(cfg, mode, api, log_path=d / "real_log.jsonl", stop_path=d / "STOP",
                       clock=clock, sleep=clock.sleep, spot_fn=spot_fn, out=lambda *a: None)


def at_minute(clock, o, minute):
    clock.t = o + 60 * minute + 0.5


def events(r, name):
    return [e for e in r.events() if e["event"] == name]


def setup(**kw):
    d = tmpdir()
    pub, kp = write_key(d)
    clock = Clock(T0 + 0.5)
    fake = FakeKalshi(clock, pub, **kw)
    return d, clock, fake, kp


# ----------------------------------------------------------------------------- tests
def test_signature_rsa_and_ed25519():
    d = tmpdir()
    for kind in ("rsa", "ed25519"):
        pub, kp = write_key(d, kind)
        api = real.KalshiAPI("https://x", "kid", str(kp), clock=lambda: 1703123456.789)
        h = api.headers("GET", "/trade-api/v2/portfolio/orders?limit=5")
        assert h["KALSHI-ACCESS-KEY"] == "kid"
        assert h["KALSHI-ACCESS-TIMESTAMP"] == "1703123456789"          # milliseconds
        verify(pub, h, "GET", "/trade-api/v2/portfolio/orders")         # query stripped before signing
        try:
            verify(pub, h, "GET", "/trade-api/v2/portfolio/balance")
            raise AssertionError("signature should not verify for another path")
        except AssertionError:
            raise
        except Exception:
            pass
    # the real request path is signed (fake server verifies every /portfolio call)
    d, clock, fake, kp = setup()
    api = real.KalshiAPI("https://fake", "kid", str(kp), session=fake, clock=clock)
    assert api.balance() == 100.0
    assert "PRIVATE KEY" not in json.dumps(api.headers("GET", "/trade-api/v2/portfolio/balance"))


def test_order_body_fields_and_units():
    b = real.order_body("KXNEAR15M-X", "yes", 0.37, 5, "cid")
    assert b == {"ticker": "KXNEAR15M-X", "client_order_id": "cid", "side": "bid", "count": "5", "price": "0.3700",
                 "time_in_force": "immediate_or_cancel", "self_trade_prevention_type": "taker_at_cross",
                 "post_only": False, "reduce_only": False}
    b = real.order_body("KXNEAR15M-X", "no", 0.64, 3, "cid")      # buy NO @ 0.64 = sell YES @ 0.36
    assert b["side"] == "ask" and b["price"] == "0.3600" and b["count"] == "3"
    assert real.order_body("T", "no", 0.955, 2, "c")["price"] == "0.0450"   # deci-cent tick near the edges
    assert real.contracts_for(2.0, 0.40, 50) == 5
    assert real.contracts_for(2.0, 0.10, 50) == 20                  # no float floor bug (2 // 0.1 == 19)
    assert real.contracts_for(200.0, 0.10, 50) == 50                # max_contracts_per_order
    assert "buy_max_cost" not in b                                  # not a V2 field; cap enforced locally


def test_full_fill_then_settlement():
    d, clock, fake, kp = setup()
    r = make_runner(d, clock, fake, kp)
    o = T0
    at_minute(clock, o, 1); r.step()
    assert not fake.posts                                         # start=2: no trade at minute 1
    at_minute(clock, o, 2); r.step()
    assert len(fake.posts) == 1
    body = fake.posts[0]
    assert body["side"] == "bid" and body["price"] == "0.4000" and body["count"] == "5"
    assert body["time_in_force"] == "immediate_or_cancel"
    f = events(r, "fill")[-1]
    assert f["n"] == 5 and abs(f["cost"] - 2.0) < 1e-9 and f["source"] == "fills"
    intent = events(r, "order_intent")[-1]
    assert intent["order"] == body and "KALSHI" not in json.dumps(intent)
    at_minute(clock, o, 3); r.step()
    assert len(fake.posts) == 1                                   # one bet per market
    fake.results[f"KXNEAR15M-T{o}"] = "yes"
    at_minute(clock, o + 900, 1); r.step()
    s = events(r, "settle")[-1]
    exp = 5 * 1.0 - 2.0 - kalshi_fee(0.40, 5)
    assert abs(s["pnl"] - exp) < 1e-6 and abs(s["pnl_kalshi"] - exp) < 1e-6
    assert abs(r.day_pnl() - exp) < 1e-6


def test_partial_fill_uses_actual_count_and_cost():
    d, clock, fake, kp = setup()
    fake.fill_qty = lambda body: 2
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    f = events(r, "fill")[-1]
    assert f["requested"] == 5 and f["n"] == 2 and abs(f["cost"] - 0.80) < 1e-9
    p = r.pos[f"KXNEAR15M-T{T0}"]
    assert p["n"] == 2 and abs(p["cost"] - 0.80) < 1e-9
    assert abs(r.open_risk() - (0.80 + kalshi_fee(0.40, 2))) < 1e-9


def test_zero_fill_means_no_position_and_no_second_order():
    d, clock, fake, kp = setup()
    fake.fill_qty = lambda body: 0
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    assert events(r, "fill")[-1]["n"] == 0
    assert r.pos == {} and r.open_risk() == 0 and r.open_positions() == 0
    at_minute(clock, T0, 3); r.step()
    assert len(fake.posts) == 1
    r2 = make_runner(d, clock, fake, kp)                          # restart: still no position
    assert r2.pos == {} and f"KXNEAR15M-T{T0}" in r2.traded


def test_no_side_order():
    d, clock, fake, kp = setup()
    r = make_runner(d, clock, fake, kp, spot_fn=lambda p: (3.96, 0.001, 0.001, {}))   # model: NO ~ 100%
    at_minute(clock, T0, 2); r.step()
    b = fake.posts[0]
    assert b["side"] == "ask" and b["price"] == "0.3800"           # NO ask = 1 - yes_bid = 0.62
    f = events(r, "fill")[-1]
    assert f["side"] == "no" and f["n"] == 3 and abs(f["cost"] - 3 * 0.62) < 1e-9


def test_daily_loss_stop():
    d, clock, fake, kp = setup()
    day = real._day(clock())
    (d / "real_log.jsonl").write_text(json.dumps({"ts": clock() - 100, "mode": "LIVE", "series": "KXNEAR15M",
                                                  "event": "settle", "ticker": "KXNEAR15M-OLD", "pnl": -20.0,
                                                  "day": day}) + "\n")
    r = make_runner(d, clock, fake, kp)
    assert r.day_pnl() == -20.0
    at_minute(clock, T0, 2); r.step()
    assert not fake.posts
    assert "daily loss cap" in events(r, "signal_skipped")[-1]["reason"]
    # other modes' losses don't count, and a new UTC day resets
    r_demo = make_runner(d, clock, fake, kp, mode="DEMO")
    assert r_demo.day_pnl() == 0.0
    clock.t += 86400
    assert r.blocked() is None


def test_daily_loss_counts_open_risk():
    d, clock, fake, kp = setup()
    day = real._day(clock())
    (d / "real_log.jsonl").write_text(json.dumps({"ts": clock() - 100, "mode": "LIVE", "series": "KXNEAR15M",
                                                  "event": "settle", "ticker": "KXNEAR15M-OLD", "pnl": -18.5,
                                                  "day": day}) + "\n")
    cfg = json.loads(json.dumps(CFG)); cfg["limits"]["max_open_positions"] = 5
    r = make_runner(d, clock, fake, kp, cfg=cfg)
    at_minute(clock, T0, 2); r.step()
    assert len(fake.posts) == 1                     # -18.5 is above the cap: trades
    assert "daily loss cap" in r.blocked()          # -18.5 - ~2.07 at risk <= -20: no more orders


def test_kill_switch():
    d, clock, fake, kp = setup()
    r = make_runner(d, clock, fake, kp)
    (d / "STOP").write_text("")
    at_minute(clock, T0, 2)
    try:
        r.step()
        raise AssertionError("should stop")
    except real.Stop as s:
        assert "kill switch" in s.reason and s.code == real.EXIT_CLEAN
    assert not fake.posts
    assert r.run() == real.EXIT_CLEAN               # run() exits cleanly (run_real.sh won't restart)
    assert events(r, "stop")[-1]["reason"].startswith("kill switch")


def test_one_bet_per_market_across_restart():
    d, clock, fake, kp = setup()
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    assert len(fake.posts) == 1
    r2 = make_runner(d, clock, fake, kp)            # crash + restart mid-market
    assert f"KXNEAR15M-T{T0}" in r2.traded and r2.pos[f"KXNEAR15M-T{T0}"]["n"] == 5
    at_minute(clock, T0, 3); r2.step()              # fresh panel: minute 3 is its first signal
    assert len(fake.posts) == 1
    assert r2.trades_by_day[real._day(clock())] == 1
    # dry-run history does not block live trading and vice versa
    r3 = make_runner(d, clock, fake, kp, mode="DEMO")
    assert f"KXNEAR15M-T{T0}" not in r3.traded


def test_no_double_order_when_response_lost():
    d, clock, fake, kp = setup()
    fake.post_fail = ["timeout_after"]              # Kalshi executed it, we lost the response
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    assert len(fake.posts) == 1 and len(fake.orders) == 1
    assert sum(1 for c in fake.calls if c[0] == "POST") == 1          # never resent
    f = events(r, "fill")[-1]
    assert f["n"] == 5 and f["order_id"] == "oid1"
    assert events(r, "order_response")[-1]["response"]["from_lookup"] is True


def test_no_retry_when_order_status_unknown():
    d, clock, fake, kp = setup()
    fake.post_fail = ["timeout_before"]             # never reached Kalshi, but we can't know that
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    assert sum(1 for c in fake.calls if c[0] == "POST") == 1 and not fake.orders
    assert events(r, "order_unknown")
    at_minute(clock, T0, 3); r.step()
    assert sum(1 for c in fake.calls if c[0] == "POST") == 1          # no blind retry later either
    assert r.open_positions() == 1                                      # unknown counts as open
    r2 = make_runner(d, clock, fake, kp)
    assert r2.pos[f"KXNEAR15M-T{T0}"]["status"] == "unknown"
    # 30 min after close with no fills and no settlement -> resolved as no position
    clock.t = T0 + 900 + 1801
    r2.housekeeping()
    assert events(r2, "settle")[-1]["note"] == "no fills found" and r2.pos == {}


def test_rate_limited_order_retries_once_with_same_id():
    d, clock, fake, kp = setup()
    fake.post_fail = ["429"]
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert len(posts) == 2 and posts[0][3]["client_order_id"] == posts[1][3]["client_order_id"]
    assert len(fake.orders) == 1


def test_rejected_order_is_not_a_position():
    d, clock, fake, kp = setup()
    fake.post_fail = ["400"]
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    assert events(r, "order_rejected") and r.pos == {}
    assert sum(1 for c in fake.calls if c[0] == "POST") == 1


def test_stale_data_and_lag_skip():
    d, clock, fake, kp = setup()

    def slow_spot(p):
        clock.t += 6                                # Coinbase took 6 s
        return spot_up(p)
    r = make_runner(d, clock, fake, kp, spot_fn=slow_spot)
    at_minute(clock, T0, 2); r.step()
    assert not fake.posts
    reason = events(r, "signal_skipped")[-1]["reason"]
    assert "lag" in reason or "old" in reason


def test_min_balance_stops():
    d, clock, fake, kp = setup()
    fake.balance_cents = 500                         # $5 < min_balance_usd 10
    r = make_runner(d, clock, fake, kp)
    assert r.run() == real.EXIT_CLEAN
    assert events(r, "min_balance") and not fake.posts


def test_price_sanity_limits():
    d, clock, fake, kp = setup(quotes=lambda tk, m: (0.96, 0.97))
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    assert not fake.posts


def test_live_confirmation_and_config():
    assert real.confirm_live(lambda p: real.CONFIRM_PHRASE)
    assert not real.confirm_live(lambda p: "yes")
    assert not real.confirm_live(lambda p: (_ for _ in ()).throw(EOFError()))
    d = tmpdir()
    cfg = json.loads(json.dumps(CFG)); del cfg["limits"]["max_daily_loss_usd"]
    (d / "c.json").write_text(json.dumps(cfg))
    try:
        real.load_config(d / "c.json")
        raise AssertionError("missing limit must refuse")
    except real.Stop as s:
        assert s.code == real.EXIT_CONFIG
    cfg = json.loads(json.dumps(CFG)); cfg["params"]["edge"] = 0.05
    (d / "c.json").write_text(json.dumps(cfg))
    try:
        real.load_config(d / "c.json")
        raise AssertionError("changed strategy must refuse")
    except real.Stop:
        pass
    assert real.main(["--live", "--config", str(d / "c.json")]) == real.EXIT_CONFIG
    assert real.load_config()["limits"]["stake_usd"] == 2.0


def test_report_runs():
    d, clock, fake, kp = setup()
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    fake.results[f"KXNEAR15M-T{T0}"] = "no"
    at_minute(clock, T0 + 900, 1); r.step()
    lines = []
    real.report([], log_path=d / "real_log.jsonl", out=lines.append)
    txt = "\n".join(lines)
    assert "LIVE" in txt and "TOTAL" in txt and "-2.0" in txt


# ----------------------------------------------------------------------------- parity with the paper bot
class SynthMarket:
    """Deterministic synthetic NEAR markets: spot random walk, noisy quotes around fair value."""

    def __init__(self, clock, seed=7):
        self.clock, self.seed = clock, seed

    def _rng(self, *k):
        return random.Random(hash((self.seed,) + k) & 0xFFFFFFFF)

    def spot(self, o, minute):
        s = 4.0
        for i in range(max(minute, 0) + 1):
            s *= math.exp(self._rng("s", o, i).gauss(0, 0.0015))
        return s

    def strike(self, o):
        return round(self.spot(o, 0), 4)

    def market(self, o):
        minute = int((self.clock() - o) // 60)
        rg = self._rng("q", o, minute)
        sp, k = self.spot(o, minute), self.strike(o)
        tau = max(15 - minute, 1)
        p = 0.5 * (1 + math.erf(math.log(sp / k) / (0.0015 * math.sqrt(tau)) / math.sqrt(2)))
        mid = min(max(p + rg.gauss(0, 0.12), 0.02), 0.98)
        yb, ya = round(mid - 0.005, 2), round(mid + 0.005, 2)
        if ya <= yb:
            ya = yb + 0.01
        if rg.random() < 0.05:
            yb = 0.0                                 # sometimes no bid
        res = ("yes" if self.spot(o, 15) >= k else "no") if self.clock() >= o + 900 else ""
        return {"ticker": f"KXNEAR15M-T{o}", "open_time": iso(o), "close_time": iso(o + 900), "floor_strike": k,
                "yes_bid_dollars": f"{yb:.4f}", "yes_ask_dollars": f"{min(ya, 1):.4f}", "result": res,
                "status": "active"}

    def open_market(self, series, deadline=None):
        return self.market(int(self.clock() // 900 * 900))

    def market_by_ticker(self, tk):
        return self.market(int(tk.split("-T")[1]))

    # what bot.Kalshi exposes
    def req(self, method, path, **kw):
        return {"market": self.market_by_ticker(path.split("/")[-1])}

    def spot_fn(self, product):
        o = int(self.clock() // 900 * 900)
        minute = int((self.clock() - o) // 60)
        rg = self._rng("v", o)
        vol = 0.0012 + rg.random() * 0.001
        bars = {o - 960: self.spot(o - 900, 0), o - 60: self.spot(o - 900, 14)}
        return self.spot(o, minute), vol, vol * 1.1, bars


class _Done(Exception):
    pass


def test_signals_identical_to_paper_bot():
    """Run bot.run (paper) and the real runner (dry-run) on the same synthetic minute data:
    they must place the same bets (market, minute, side, price)."""
    d = tmpdir()
    start, end = T0 + 0.5, T0 + 900 * 16
    params = CFG["params"]

    # --- paper bot
    clock = Clock(start)
    syn = SynthMarket(clock)

    def sleep(s):
        clock.t += s
        if clock.t > end:
            raise _Done
    saved = (bot.time, bot.Kalshi, bot._spot_and_vol, bot.LOG, bot.STATUS)
    try:
        bot.time = types.SimpleNamespace(time=clock, sleep=sleep)
        bot.Kalshi = lambda *a, **k: syn
        bot._spot_and_vol = syn.spot_fn
        bot.LOG, bot.STATUS = d / "paper.jsonl", d / "status.json"
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                bot.run(series="KXNEAR15M", strategy="fair_value", params=params, stake=2.0, poll="minute",
                        execution="taker", max_daily_loss=1e9, max_trades_per_day=10**6)
            except _Done:
                pass
    finally:
        bot.time, bot.Kalshi, bot._spot_and_vol, bot.LOG, bot.STATUS = saved
    paper = [json.loads(x) for x in (d / "paper.jsonl").read_text().splitlines()]
    paper = [(e["ticker"], e["ts"], e["side"], round(e["price"], 4)) for e in paper if e["event"] == "buy"]

    # --- real runner, dry-run
    clock2 = Clock(start)
    syn2 = SynthMarket(clock2)
    mapi = types.SimpleNamespace(open_market=syn2.open_market, market=syn2.market_by_ticker)
    cfg = json.loads(json.dumps(CFG))
    cfg["limits"].update(max_daily_loss_usd=1e9, max_trades_per_day=10**6, max_open_positions=10**6,
                         min_price=0.0001, max_price=0.9999)

    def sleep2(s):
        clock2.t += s
        if clock2.t > end:
            raise real.Stop("done")
    r = real.Runner(cfg, "DRYRUN", mapi, log_path=d / "real.jsonl", stop_path=d / "STOP", clock=clock2,
                    sleep=sleep2, spot_fn=syn2.spot_fn, out=lambda *a: None)
    r.run()
    mine = [e for e in r.events() if e["event"] == "would_order"]
    mine = [(e["ticker"], int(e["ts"]), e["side"], round(e["price"], 4)) for e in mine]
    assert len(paper) >= 3, f"synthetic data produced too few trades to compare: {paper}"
    assert mine == paper, f"\npaper {paper}\nreal  {mine}"



def test_all9_config_loads_and_rules_are_frozen():
    from kalshi15m import real as R
    path = Path(__file__).resolve().parent.parent / "kalshi15m" / "real_all9.json"
    cfg = R.load_config(path)
    assert cfg["series"] == R.ALL9 and [r["name"] for r in cfg["rules"]] == ["fair_value", "fair_value_v2"]
    bad = json.loads(path.read_text())
    bad["rules"][0]["params"]["edge"] = 0.05
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.json"
        p.write_text(json.dumps(bad))
        try:
            R.load_config(p)
            raise AssertionError("tampered rule accepted")
        except R.Stop:
            pass

# ----------------------------------------------------------------------------- golden rules (lab3) mode
GOLDEN_CFG_PATH = Path(__file__).resolve().parent.parent / "kalshi15m" / "real_golden_demo.json"


def golden_cfg(rule_ids=None, compounding=False, **limits):
    """The golden demo config for one coin. Unless compounding=True, a fixed $4 stake / 40 contracts so the
    expected order sizes below are easy to read."""
    cfg = real.load_config(GOLDEN_CFG_PATH)
    cfg = json.loads(json.dumps(cfg))
    cfg["series"] = "KXNEAR15M"                   # what supervise_many hands each coin's runner
    if rule_ids is not None:
        cfg["golden_rules"] = [r for r in cfg["golden_rules"] if r["id"] in rule_ids]
    if not compounding:
        for k in ("stake_pct_of_balance", "stake_usd_min"):
            cfg["limits"].pop(k)
        cfg["limits"].update(stake_usd=4.0, max_contracts_per_order=40)
    cfg["limits"].update(**limits)
    return cfg


def golden_engine(clock, flat_from=None, level=4.0, lag_bars=1):
    """A real GoldenEngine on synthetic NEAR spot bars (23 days, iid 1-minute noise around `level`, exactly
    `level` from `flat_from` on so the model says 50%). Coinbase is faked: candles published `lag_bars`
    minutes late, the ticker = the close of the bar that just ended."""
    import pandas as pd
    from kalshi15m import golden_live as GL
    rng = random.Random(3)
    flat_from = T0 - 600 if flat_from is None else flat_from
    ts = list(range(T0 - 23 * 86400, T0 + 4 * 900, 60))
    px = [level if t >= flat_from else level * math.exp(0.001 * rng.gauss(0, 1)) for t in ts]
    df = pd.DataFrame({"ts": ts, "low": px, "high": px, "open": px, "close": px, "volume": 1.0})
    cols = ["ts", "low", "high", "open", "close", "volume"]

    def fetch_candles(**kw):
        T = int(clock() // 60 * 60)
        rows = df[(df.ts <= T - 60 * (1 + lag_bars)) & (df.ts > T - 60 * 15)]
        return rows[cols].values.tolist()[::-1]

    def fetch_ticker():
        T = int(clock() // 60 * 60)
        return float(df.close[df.ts == T - 60].iloc[0])
    return GL.GoldenEngine("KXNEAR15M", history=df[df.ts <= T0 - 180], fetch_candles=fetch_candles,
                           fetch_ticker=fetch_ticker, clock=clock, data_dir=None)


def golden_runner(d, clock, fake, kp, mode="LIVE", rule_ids=None, eng=None, compounding=False, **limits):
    api = real.KalshiAPI("https://fake", "test-key-id", str(kp), session=fake, clock=clock, sleep=clock.sleep)
    return real.Runner(golden_cfg(rule_ids, compounding, **limits), mode, api, log_path=d / "real_log.jsonl",
                       stop_path=d / "STOP", clock=clock, sleep=clock.sleep, out=lambda *a: None,
                       engine=eng or golden_engine(clock))


def scalp_quotes(tk, minute):                        # cheap YES at entry, bid above fair value (0.5) after
    return (0.28, 0.30) if minute <= 2 else (0.52, 0.54)


def test_exit_order_body():
    b = real.exit_order_body("KXNEAR15M-X", "yes", 0.52, 13, "cid")      # sell YES at the yes bid
    assert b == {"ticker": "KXNEAR15M-X", "client_order_id": "cid", "side": "ask", "count": "13", "price": "0.5200",
                 "time_in_force": "immediate_or_cancel", "self_trade_prevention_type": "taker_at_cross",
                 "post_only": False, "reduce_only": True}
    b = real.exit_order_body("KXNEAR15M-X", "no", 0.46, 7, "cid")        # sell NO at no bid 0.46 = buy YES @ 0.54
    assert b["side"] == "bid" and b["price"] == "0.5400" and b["count"] == "7" and b["reduce_only"] is True
    fl = [{"order_id": "o", "count_fp": "4.00", "outcome_side": "no", "yes_price_dollars": "0.5200",
           "no_price_dollars": "0.4800", "fee_cost": "0.0700"},
          {"order_id": "o", "count_fp": "1.00", "outcome_side": "yes", "yes_price_dollars": "0.5300",
           "no_price_dollars": "0.4700", "fee_cost": "0.0200"}]
    assert real.exit_fill_summary(fl, "yes") == (5.0, round(4 * 0.52 + 0.53, 6), 0.09)
    assert real.exit_fill_summary(fl, "no") == (5.0, round(4 * 0.48 + 0.47, 6), 0.09)


def test_golden_config_frozen():
    cfg = real.load_config(GOLDEN_CFG_PATH)
    assert [r["id"] for r in cfg["golden_rules"]] == [r["id"] for r in __import__("kalshi15m.golden_live").golden_live.GOLDEN]
    assert cfg["limits"] == {"stake_usd": 10.0, "stake_pct_of_balance": 0.10, "stake_usd_min": 1.0,
                             "max_contracts_per_order": 100, "max_daily_loss_usd": 20.0, "max_trades_per_day": 40,
                             "max_open_positions": 1, "min_balance_usd": 2.0, "max_price": 0.95, "min_price": 0.03,
                             "max_data_age_s": 5.0, "max_decision_lag_s": 5.0}
    assert cfg["log"] == "data/kalshi15m/real_all9_log.jsonl" and cfg["series"] == real.ALL9
    raw = json.loads(GOLDEN_CFG_PATH.read_text())

    def refused(mut):
        c = json.loads(json.dumps(raw))
        mut(c)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            p.write_text(json.dumps(c))
            try:
                real.load_config(p)
                return False
            except real.Stop as s:
                return s.code == real.EXIT_CONFIG
    assert refused(lambda c: c["golden_rules"][2]["params"].update(edge=0.10))       # tampered param
    assert refused(lambda c: c["golden_rules"][1].update(norm=0.1))                  # tampered sized norm
    assert refused(lambda c: c["golden_rules"][0].update(t=9.9))                     # tampered priority
    assert refused(lambda c: c["golden_rules"][0].update(id="scalp:KXBTC15M"))       # unknown rule
    assert refused(lambda c: c["golden_rules"].append(c["golden_rules"][0]))         # duplicate
    assert refused(lambda c: c.update(rules=json.loads((GOLDEN_CFG_PATH.parent / "real_all9.json").read_text())["rules"]))
    assert refused(lambda c: c.update(series=["KXBTC15M", "KXFOO15M"]))
    assert not refused(lambda c: c.update(golden_rules=c["golden_rules"][:3]))       # a subset is fine
    assert refused(lambda c: c["limits"].update(stake_pct_of_balance=0.30))          # compounding: (0, 0.25]
    assert refused(lambda c: c["limits"].update(stake_pct_of_balance=0))
    assert refused(lambda c: c["limits"].pop("stake_usd_min"))
    assert refused(lambda c: c["limits"].update(stake_usd_min=-1))
    for name in ("real.json", "real_10.json", "real_all9.json", "real_all9_demo.json"):   # old configs unchanged
        p = GOLDEN_CFG_PATH.parent / name
        if p.exists():
            assert "golden_rules" not in real.load_config(p)


def test_golden_best_rule_wins_and_others_logged():
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    r = golden_runner(d, clock, fake, kp)
    at_minute(clock, T0, 1); r.step()
    assert not fake.posts                                         # every rule starts at minute >= 2
    at_minute(clock, T0, 2); r.step()
    assert len(fake.posts) == 1
    b = fake.posts[0]
    assert b["side"] == "bid" and b["price"] == "0.3000" and b["count"] == str(int(4.0 / 0.30)) and not b["reduce_only"]
    it = events(r, "order_intent")[-1]
    from kalshi15m import golden_live as GL
    assert it["rule"] == "scalp:ALL" and abs(it["q"] - 0.5) < 1e-12
    also = it["also_signalled"]
    assert {"sized:ALL", "fv_shape:ALL", "fv_ref:ALL"} <= set(also) and "scalp:ALL" not in also
    assert also == sorted(also, key=GL.PRIORITY.get)              # best first
    assert all(GL.PRIORITY[x] > 0 for x in also)
    assert r.pos[f"KXNEAR15M-T{T0}"]["rule"] == "scalp:ALL"


def test_golden_sized_stake():
    from kalshi15m import golden_live as GL
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    r = golden_runner(d, clock, fake, kp, rule_ids={"sized:ALL"})
    at_minute(clock, T0, 2); r.step()
    it = events(r, "order_intent")[-1]
    kel = (0.5 - 0.30) / (1 - 0.30)
    stake = 4.0 * min(kel / GL.RULES["sized:ALL"]["norm"], 5)
    assert it["rule"] == "sized:ALL" and abs(it["kelly"] - kel) < 1e-6 and abs(it["stake"] - stake) < 1e-4
    assert fake.posts[0]["count"] == str(real.contracts_for(stake, 0.30, 40)) == "14"
    assert abs(it["max_cost"] - (14 * 0.30 + kalshi_fee(0.30, 14))) < 1e-9
    # the per-order contract cap still applies to sized stakes
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    r = golden_runner(d, clock, fake, kp, rule_ids={"sized:ALL"}, max_contracts_per_order=10)
    at_minute(clock, T0, 2); r.step()
    assert fake.posts[0]["count"] == "10"


def test_golden_scalp_full_exit_no_double_count():
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    r = golden_runner(d, clock, fake, kp, rule_ids={"scalp:ALL"})
    tk = f"KXNEAR15M-T{T0}"
    at_minute(clock, T0, 2); r.step()
    at_minute(clock, T0, 3); r.step()
    assert len(fake.posts) == 2
    x = fake.posts[1]
    assert x["side"] == "ask" and x["price"] == "0.5200" and x["count"] == "13" and x["reduce_only"] is True
    assert x["time_in_force"] == "immediate_or_cancel"
    e = events(r, "exit")[-1]
    exp = 13 * (0.52 - 0.30) - kalshi_fee(0.30, 13) - kalshi_fee(0.52, 13)
    assert e["n"] == 13 and e["remaining"] == 0 and abs(e["pnl"] - exp) < 1e-6 and e["source"] == "fills"
    assert tk not in r.pos and tk in r.settled and abs(r.day_pnl() - exp) < 1e-6
    at_minute(clock, T0, 4); r.step()
    assert len(fake.posts) == 2                                   # nothing left to sell, no re-entry
    fake.results[tk] = "no"
    at_minute(clock, T0 + 900, 1); r.step()
    assert not events(r, "settle") and abs(r.day_pnl() - exp) < 1e-6     # never settled again
    r2 = golden_runner(d, clock, fake, kp, rule_ids={"scalp:ALL"})        # restart: same state from the log
    assert tk in r2.traded and tk not in r2.pos and abs(r2.day_pnl() - exp) < 1e-6
    lines = []
    real.report([], log_path=d / "real_log.jsonl", out=lines.append)
    txt = "\n".join(lines)
    assert "exits" in txt and f"{exp:+.2f}" in txt and "early exits: 1 (1 sold everything" in txt


def test_golden_scalp_partial_then_settle():
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    fake.fill_qty = lambda body: 5 if body["reduce_only"] else int(body["count"])
    r = golden_runner(d, clock, fake, kp, rule_ids={"scalp:ALL"})
    tk = f"KXNEAR15M-T{T0}"
    at_minute(clock, T0, 2); r.step()
    at_minute(clock, T0, 3); r.step()
    at_minute(clock, T0, 4); r.step()                             # sells 5 more of the remaining 8
    ex = events(r, "exit")
    assert [e["n"] for e in ex] == [5, 5] and ex[-1]["remaining"] == 3
    assert [p["count"] for p in fake.posts] == ["13", "13", "8"]       # entry, sell all 13 (5 fill), sell the 8 left
    p = r.pos[tk]
    assert p["n"] == 3 and abs(p["cost"] - 3 * 0.30) < 1e-6
    assert abs(r.open_risk() - (3 * 0.30 + kalshi_fee(0.30, 13) * 3 / 13)) < 1e-6
    fake.results[tk] = "yes"
    at_minute(clock, T0 + 900, 1); r.step()
    s = events(r, "settle")[-1]
    fee_e = kalshi_fee(0.30, 13)
    sold = 2 * (5 * 0.52 - kalshi_fee(0.52, 5))
    exp_total = sold + 3 * 1.0 - 13 * 0.30 - fee_e
    assert s["after_exit"] and s["n"] == 3 and abs(s["pnl"] - (3 - 0.9 - fee_e * 3 / 13)) < 1e-4
    assert abs(sum(e["pnl"] for e in ex) + s["pnl"] - exp_total) < 1e-4
    assert abs(r.day_pnl() - exp_total) < 1e-4 and tk not in r.pos
    r2 = golden_runner(d, clock, fake, kp, rule_ids={"scalp:ALL"})
    assert tk not in r2.pos and abs(r2.day_pnl() - exp_total) < 1e-4
    lines = []
    real.report([], log_path=d / "real_log.jsonl", out=lines.append)
    assert "early exits: 2 (0 sold everything, 2 partial)" in "\n".join(lines)


def test_golden_exit_zero_fill_retries_and_ignores_entry_limits():
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    r = golden_runner(d, clock, fake, kp, rule_ids={"scalp:ALL"})
    tk = f"KXNEAR15M-T{T0}"
    at_minute(clock, T0, 2); r.step()
    fake.fill_qty = lambda body: 0 if body["reduce_only"] else int(body["count"])
    r.pnl_by_day[r.today()] = -1000.0                             # daily loss cap hit: no NEW orders ...
    assert "daily loss cap" in r.blocked()
    at_minute(clock, T0, 3); r.step()
    assert events(r, "exit_unfilled") and r.pos[tk]["n"] == 13 and not events(r, "exit")
    fake.fill_qty = lambda body: int(body["count"])
    at_minute(clock, T0, 4); r.step()                             # ... but exits still go out
    assert events(r, "exit")[-1]["n"] == 13 and tk not in r.pos
    assert [p["reduce_only"] for p in fake.posts] == [False, True, True]


def test_golden_exit_rejected_holds_to_settlement():
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    r = golden_runner(d, clock, fake, kp, rule_ids={"scalp:ALL"})
    tk = f"KXNEAR15M-T{T0}"
    at_minute(clock, T0, 2); r.step()
    fake.post_fail = ["400"]
    at_minute(clock, T0, 3); r.step()
    at_minute(clock, T0, 4); r.step()
    assert events(r, "exit_rejected") and sum(1 for c in fake.calls if c[0] == "POST") == 2   # no retry
    fake.results[tk] = "yes"
    at_minute(clock, T0 + 900, 1); r.step()
    s = events(r, "settle")[-1]
    assert abs(s["pnl"] - (13 - 13 * 0.30 - kalshi_fee(0.30, 13))) < 1e-6 and not s.get("after_exit")


def test_golden_exit_unknown_reconciled_at_settlement():
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    r = golden_runner(d, clock, fake, kp, rule_ids={"scalp:ALL"})
    tk = f"KXNEAR15M-T{T0}"
    at_minute(clock, T0, 2); r.step()
    fake.post_fail = ["timeout_before"]                          # exit never reached Kalshi (we can't know)
    at_minute(clock, T0, 3); r.step()
    assert events(r, "exit_unknown") and r.pos[tk]["exit_unknown"]
    at_minute(clock, T0, 4); r.step()
    assert sum(1 for c in fake.calls if c[0] == "POST") == 2     # never resent
    fake.results[tk] = "no"
    at_minute(clock, T0 + 900, 1); r.step()
    s = events(r, "settle")[-1]
    assert s["after_exit"] and s["n"] == 13 and abs(s["pnl"] - (-13 * 0.30 - kalshi_fee(0.30, 13))) < 1e-6
    assert not events(r, "exit") and tk not in r.pos


def test_golden_dry_run_exit():
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    r = golden_runner(d, clock, fake, kp, mode="DRYRUN", rule_ids={"scalp:ALL", "sized:ALL"})
    tk = f"KXNEAR15M-T{T0}"
    at_minute(clock, T0, 2); r.step()
    at_minute(clock, T0, 3); r.step()
    assert not fake.posts and events(r, "would_order")[-1]["rule"] == "scalp:ALL"
    e = events(r, "exit")[-1]
    assert e["source"] == "dry" and abs(e["pnl"] - (13 * 0.22 - kalshi_fee(0.30, 13) - kalshi_fee(0.52, 13))) < 1e-6
    fake.results[tk] = "yes"
    at_minute(clock, T0 + 900, 1); r.step()
    assert not events(r, "dry_settle")


def test_golden_stale_spot_feed_skips():
    from kalshi15m import golden_live as GL
    d, clock, fake, kp = setup(quotes=lambda tk, m: (0.28, 0.30))
    eng = golden_engine(clock, lag_bars=30)                       # Coinbase stopped publishing candles
    eng.max_candle_lag_s = 300
    r = golden_runner(d, clock, fake, kp, eng=eng)
    at_minute(clock, T0, 2); r.step()
    assert len(fake.posts) == 1                                   # newest candle 4 min old: still fine
    at_minute(clock, T0 + 900, 3); r.step()                       # next market: newest candle 18 min old
    assert len(fake.posts) == 1 and events(r, "skip")[-1]["reason"] == "network_spot"
    assert "Coinbase candle" in events(r, "skip")[-1]["error"]
    assert issubclass(GL.StaleData, requests.RequestException)


def test_stake_grows_with_balance():
    """limits.stake_pct_of_balance: base stake = max(stake_usd_min, pct x crypto-shard balance), refreshed per
    market and after fills; sized rules scale that base; unaffordable orders are skipped and logged."""
    from kalshi15m import golden_live as GL
    sizes = {}
    for shard2 in (5.0, 50.0, 200.0):
        d, clock, fake, kp = setup(quotes=scalp_quotes)
        fake.balance_cents = int((shard2 + 30) * 100)                       # some money left on shard 0 too
        fake.shard2 = shard2
        r = golden_runner(d, clock, fake, kp, rule_ids={"scalp:ALL"}, compounding=True)
        at_minute(clock, T0, 2); r.step()
        it = events(r, "order_intent")[-1]
        base = max(1.0, 0.10 * shard2)
        assert abs(it["base_stake"] - base) < 1e-9 and it["balance_crypto"] == shard2
        sizes[shard2] = int(fake.posts[0]["count"])
        assert sizes[shard2] == min(int(base / 0.30 + 1e-9), 100)
    assert sizes == {5.0: 3, 50.0: 16, 200.0: 66}                            # bets grow with the account
    # sized rule: Kelly multiplies the compounding base
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    fake.shard2 = 50.0
    r = golden_runner(d, clock, fake, kp, rule_ids={"sized:ALL"}, compounding=True)
    at_minute(clock, T0, 2); r.step()
    it = events(r, "order_intent")[-1]
    stake = 5.0 * (0.2 / 0.7) / GL.RULES["sized:ALL"]["norm"]
    assert abs(it["stake"] - stake) < 1e-4 and fake.posts[0]["count"] == str(int(stake / 0.30))
    # balance unknown (e.g. dry run) -> stake_usd
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    r = golden_runner(d, clock, fake, kp, mode="DRYRUN", rule_ids={"scalp:ALL"}, compounding=True)
    at_minute(clock, T0, 2); r.step()
    assert events(r, "would_order")[-1]["n"] == int(10.0 / 0.30)
    # the crypto shard cannot pay for the order -> skipped with the reason, no crash, nothing sent
    d, clock, fake, kp = setup(quotes=scalp_quotes)
    fake.shard2 = 0.50
    r = golden_runner(d, clock, fake, kp, rule_ids={"scalp:ALL"}, compounding=True, min_balance_usd=0.1)
    at_minute(clock, T0, 2); r.step()
    assert not fake.posts and "crypto (shard 2) balance $0.50 < order cost" in events(r, "signal_skipped")[-1]["reason"]
    # the old configs keep their fixed stake
    d, clock, fake, kp = setup()
    fake.shard2 = 500.0
    r = make_runner(d, clock, fake, kp)
    at_minute(clock, T0, 2); r.step()
    # (the crypto-shard balance is now always read, for the money limits; the stake stays fixed)
    assert r.crypto_balance == 500.0 and fake.posts[0]["count"] == "5" and "base_stake" not in events(r, "order_intent")[-1]


def test_golden_engine_synthetic_bar_then_official():
    from kalshi15m import golden_live as GL
    clock = Clock(T0 + 60.5)
    eng = golden_engine(clock, flat_from=T0 + 10 ** 6)
    P = real.new_panel()
    real.observe(P, {"open_time": iso(T0), "floor_strike": 4.0, "yes_bid_dollars": "0.4", "yes_ask_dollars": "0.42"},
                 1, float("nan"), float("nan"), float("nan"), {})
    info = eng.update(P, T0, 1)
    assert info["synthetic"] and info["bar_ts"] == T0 and abs(P["spot"][0, 0] - eng.fetch_ticker()) < 1e-12
    for k in ("vol_ewma30", "r1", "emp21_1.0", "tod_ratio", "vol240"):
        assert math.isfinite(P[k][0, 0]), k
    clock.t += 60
    eng.update(P, T0, 2)
    assert not eng.official[(T0 - eng.t0) // 60]                  # published, but still provisional (GL.SETTLE_S)
    clock.t += GL.SETTLE_S
    eng.update(P, T0, 2 + GL.SETTLE_S // 60)
    assert eng.official[(T0 - eng.t0) // 60]                      # bar T0 is now a settled, official candle


def _account_cfg(series="KXNEAR15M", **lim):
    cfg = json.loads(json.dumps(CFG)); cfg["series"] = series; cfg["limits"].update(lim)
    return cfg


def test_account_open_risk_cap_spans_coins():
    d, clock, fake, kp = setup()
    lim = {"max_total_open_risk_usd": 3.0}
    other = make_runner(d, clock, fake, kp, cfg=_account_cfg("KXBTC15M", **lim))
    other.pos["KXBTC15M-X"] = {"side": "yes", "n": 3.0, "cost": 1.5, "fees": 0.05, "close_ts": T0 + 900,
                               "status": "filled"}
    r = make_runner(d, clock, fake, kp, cfg=_account_cfg(**lim))
    assert abs(r.account_open_risk() - 1.55) < 1e-9
    at_minute(clock, T0, 2); r.step()
    assert not fake.posts                                          # 1.55 at risk + this order (~2) > 3
    assert "account open-risk cap" in events(r, "signal_skipped")[-1]["reason"]
    # a runner on another account (different log) does not count
    d2 = tmpdir()
    r2 = make_runner(d2, clock, fake, kp, cfg=_account_cfg(**lim))
    assert r2.account_open_risk() == 0.0


def test_account_daily_loss_cap_spans_coins():
    d, clock, fake, kp = setup()
    day = real._day(clock())
    (d / "real_log.jsonl").write_text(json.dumps({"ts": clock() - 100, "mode": "LIVE", "series": "KXBTC15M",
                                                  "event": "settle", "ticker": "KXBTC15M-OLD", "pnl": -1.9,
                                                  "day": day}) + "\n")
    lim = {"max_total_daily_loss_usd": 2.0}
    make_runner(d, clock, fake, kp, cfg=_account_cfg("KXBTC15M", **lim))
    r = make_runner(d, clock, fake, kp, cfg=_account_cfg(**lim))
    assert r.day_pnl() == 0.0 and abs(r.account_day_pnl() + 1.9) < 1e-9   # NEAR itself lost nothing today
    at_minute(clock, T0, 2); r.step()
    assert not fake.posts
    assert "account daily loss cap" in events(r, "signal_skipped")[-1]["reason"]


def test_min_balance_can_count_open_bets():
    d, clock, fake, kp = setup()
    fake.balance_cents = 900                       # $9 cash < min 10, but $2 sits in an open bet
    cfg = _account_cfg(min_balance_counts_open_bets=True)
    r = make_runner(d, clock, fake, kp, cfg=cfg)
    r.pos["KXNEAR15M-X"] = {"side": "yes", "n": 4.0, "cost": 2.0, "fees": 0.0, "close_ts": T0 + 900,
                            "status": "filled"}
    r.refresh_balance()                            # no Stop: equity $11
    r.pos.clear()
    try:
        r.refresh_balance()
        raise AssertionError("expected Stop")
    except real.Stop:
        pass


def test_account_limits_validated():
    d = tmpdir()
    for bad in (0, -1, "2", True):
        cfg = _account_cfg(max_total_open_risk_usd=bad)
        (d / "c.json").write_text(json.dumps(cfg))
        try:
            real.load_config(d / "c.json")
            raise AssertionError(f"accepted {bad!r}")
        except real.Stop:
            pass


def test_quotes_come_from_the_live_order_book():
    """GET /markets quotes are stale; the runner must price from /orderbook (best level = highest price)."""
    from kalshi15m import bot as B
    q = B.book_quote({"orderbook_fp": {"yes_dollars": [["0.3600", "10"], ["0.3800", "5"]],
                                       "no_dollars": [["0.5800", "7"], ["0.5900", "3"]]}})
    assert q["yes_bid_dollars"] == "0.3800" and q["yes_ask_dollars"] == "0.4100" and q["yes_ask_size_fp"] == "3.00"
    e = B.book_quote({"orderbook_fp": {"yes_dollars": [], "no_dollars": None}})
    assert e["yes_bid_dollars"] == "0.0000" and e["yes_ask_dollars"] == "1.0000"
    d, clock, fake, kp = setup()
    r = make_runner(d, clock, fake, kp)
    m = r.mapi.open_market("KXNEAR15M")
    assert m["quote_source"] == "orderbook" and fake.book_reads == 1


def test_daily_loss_ignore_before_ts():
    d, clock, fake, kp = setup()
    day = real._day(clock())
    (d / "real_log.jsonl").write_text(json.dumps({"ts": clock() - 100, "mode": "LIVE", "series": "KXNEAR15M",
                                                  "event": "settle", "ticker": "KXNEAR15M-OLD", "pnl": -20.0,
                                                  "day": day}) + "\n")
    cfg = _account_cfg(daily_loss_ignore_before_ts=clock() - 50)
    r = make_runner(d, clock, fake, kp, cfg=cfg)
    assert r.day_pnl() == 0.0 and r.blocked() is None       # the old loss is left out of the cap
    cfg = _account_cfg(daily_loss_ignore_before_ts=clock() - 500)
    r = make_runner(d, clock, fake, kp, cfg=cfg)
    assert r.day_pnl() == -20.0 and "daily loss cap" in r.blocked()


def test_window_caps_span_coins():
    d, clock, fake, kp = setup()
    lim = {"max_entries_per_window_side": 1, "max_open_positions": 5}
    other = make_runner(d, clock, fake, kp, cfg=_account_cfg("KXBTC15M", **lim))
    o = int(clock() // 900 * 900)
    other.entries["KXBTC15M-X"] = (o + 900, "yes", 0.5)
    r = make_runner(d, clock, fake, kp, cfg=_account_cfg(**lim))
    at_minute(clock, T0, 2); r.step()
    assert not fake.posts                                   # one YES already in this window on another coin
    assert "window cap" in events(r, "signal_skipped")[-1]["reason"]
    assert r.window_block(o + 900, "no", 0.5) is None       # the other side is still allowed
    assert r.window_block(o + 1800, "yes", 0.5) is None     # and the next window


def test_window_cost_cap_and_entries_survive_restart():
    d, clock, fake, kp = setup()
    lim = {"max_window_cost_usd": 3.0, "max_open_positions": 5}
    r = make_runner(d, clock, fake, kp, cfg=_account_cfg(**lim))
    at_minute(clock, T0, 2); r.step()
    assert len(fake.posts) == 1
    tk = next(iter(r.entries))
    spent = r.entries[tk][2]
    assert spent > 0
    r2 = make_runner(d, clock, fake, kp, cfg=_account_cfg(**lim))     # rebuilt from the log
    assert abs(r2.entries[tk][2] - spent) < 1e-9
    assert "window cost cap" in r2.window_block(r2.entries[tk][0], "no", 3.0)


def test_golden_engine_ignores_provisional_candles():
    """Coinbase revises a just-published 1-minute candle for a few minutes. The engine must price the bar that
    just closed from the live ticker, and only take candles older than GL.SETTLE_S as official."""
    import pandas as pd
    from kalshi15m import golden_live as GL
    clock = Clock(T0 + 600 + 0.5)
    ts = list(range(T0 - 23 * 86400, T0 + 900, 60))
    df = pd.DataFrame({"ts": ts, "low": 4.0, "high": 4.0, "open": 4.0, "close": 4.0, "volume": 1.0})
    cols = ["ts", "low", "high", "open", "close", "volume"]

    def fetch_candles(**kw):            # every bar published instantly, but the newest 3 carry a wrong close
        T = int(clock() // 60 * 60)
        rows = df[(df.ts < T) & (df.ts > T - 60 * 15)][cols].values.tolist()
        for r in rows:
            if r[0] >= T - 180:
                r[4] = 9.0
        return rows[::-1]
    eng = GL.GoldenEngine("KXNEAR15M", history=df[df.ts <= T0 - 180], fetch_candles=fetch_candles,
                          fetch_ticker=lambda: 4.0, clock=clock, data_dir=None)
    eng.prepare()
    T = T0 + 600
    info = eng._ensure(T, None)
    i = (T - 60 - eng.t0) // 60
    assert info["synthetic"] and eng.sp.c[i] == 4.0                   # ticker, not the provisional 9.0
    assert not eng.official[(T - 120 - eng.t0) // 60]                  # young candles are not official
    assert eng.official[(T - 60 - GL.SETTLE_S - eng.t0) // 60]         # settled ones are


def test_min_one_contract():
    d, clock, fake, kp = setup()
    r = make_runner(d, clock, fake, kp, cfg=_account_cfg(stake_usd=0.1))      # $0.10 < one 40c contract
    at_minute(clock, T0, 2); r.step()
    assert not fake.posts and "stake too small" in events(r, "signal_skipped")[-1]["reason"]
    d, clock, fake, kp = setup()
    r = make_runner(d, clock, fake, kp, cfg=_account_cfg(stake_usd=0.1, min_one_contract_max_usd=1.0))
    at_minute(clock, T0, 2); r.step()
    assert len(fake.posts) == 1 and fake.posts[0]["count"] == "1"
    d, clock, fake, kp = setup()
    r = make_runner(d, clock, fake, kp, cfg=_account_cfg(stake_usd=0.1, min_one_contract_max_usd=0.2))  # too dear
    at_minute(clock, T0, 2); r.step()
    assert not fake.posts


def test_take_profit_stops_for_good():
    d, clock, fake, kp = setup()
    fake.balance_cents = 700                         # $7.00 >= target $7
    cfg = _account_cfg(take_profit_balance_usd=7.0, min_balance_usd=0.5)
    r = make_runner(d, clock, fake, kp, cfg=cfg)
    assert r.run() == real.EXIT_CLEAN
    assert events(r, "target_reached") and not fake.posts and r.target_path.exists()
    fake.balance_cents = 500                         # even after a dip, a restarted runner does not trade again
    r2 = make_runner(d, clock, fake, kp, cfg=cfg)
    assert r2.run() == real.EXIT_CLEAN and not fake.posts


def test_money_limits_use_the_crypto_shard_only():
    """Money parked on another shard must not count: $10 on shard 0, $3 on the crypto shard."""
    d, clock, fake, kp = setup()
    fake.balance_cents, fake.shard2 = 1300, 3.0
    cfg = _account_cfg(take_profit_balance_usd=7.0, min_balance_usd=0.5)
    r = make_runner(d, clock, fake, kp, cfg=cfg)
    r.refresh_balance()                               # $3 crypto < $7: no target
    assert r.crypto_balance == 3.0 and not r.target_path.exists()
    fake.shard2 = 0.4                                 # $0.40 crypto < $0.50 stop, though $13 total
    try:
        r.refresh_balance()
        raise AssertionError("expected the min-balance stop")
    except real.Stop:
        pass


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                import traceback
                fails += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{'ALL PASSED' if not fails else f'{fails} FAILED'}")
    sys.exit(1 if fails else 0)
