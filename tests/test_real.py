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
        if method == "GET" and p.startswith("/markets/"):
            tk = p.split("/")[-1]
            o = int(tk.split("-T")[1])
            return Resp(200, {"market": self.market_dict(o)})
        if p == "/portfolio/balance":
            return Resp(200, {"balance": self.balance_cents, "balance_dollars": f"{self.balance_cents / 100:.4f}"})
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
