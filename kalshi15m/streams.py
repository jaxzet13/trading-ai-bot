"""Live market data streams, so live decisions see the same numbers the backtest uses.

* CoinbaseBars: Coinbase's public "matches" websocket (every trade). 1-minute bars are built from the trades
  exactly as Coinbase builds its candles (open/high/low/close/volume of the trades whose time falls in the
  minute). A bar is "complete" once the stream has shown it was connected for the whole minute and has seen a
  message timed after the minute's end (heartbeats arrive every second). The backtest (lab3) uses the final
  Coinbase candles; the REST candle for the minute that just ended is published late and then revised, so this
  is the only way to have the final close at decision time.

* KalshiBooks: Kalshi's authenticated "orderbook_delta" websocket. Keeps every subscribed market's order book
  (snapshot + deltas, sequence-checked) and records the best yes bid / yes ask after every change with Kalshi's
  own millisecond timestamp, so the book can be read "as of" the minute boundary, i.e. the same instant the
  backtest's 1-minute Kalshi candle closes describe.

Both run in daemon threads, reconnect with backoff, and report health; callers fall back to REST when a
stream can't vouch for a value (never guess).
"""
from __future__ import annotations

import bisect
import json
import os
import threading
import time
from datetime import datetime
from urllib.parse import urlparse

COINBASE_WS = "wss://ws-feed.exchange.coinbase.com"
KALSHI_WS = {"PROD": "wss://api.elections.kalshi.com/trade-api/ws/v2",
             "DEMO": "wss://demo-api.kalshi.co/trade-api/ws/v2"}
KALSHI_WS_PATH = "/trade-api/ws/v2"


def _ws_kwargs():
    """websocket-client options: the environment's HTTPS proxy and CA bundle, if any."""
    kw = {}
    px = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if px:
        u = urlparse(px)
        kw.update(http_proxy_host=u.hostname, http_proxy_port=u.port, proxy_type="http")
        if u.username:
            kw["http_proxy_auth"] = (u.username, u.password or "")
    ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if not ca and os.path.exists("/root/.ccr/ca-bundle.crt"):
        ca = "/root/.ccr/ca-bundle.crt"
    if ca:
        kw["sslopt"] = {"ca_certs": ca}
    return kw


def _iso_ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# =========================================================================== Coinbase
class CoinbaseBars:
    KEEP_S = 3600

    def __init__(self, products, connect=None, clock=time.time):
        self.products = sorted(set(products))
        self.clock = clock
        self._connect = connect          # tests inject a fake; default websocket-client
        self._lock = threading.Lock()
        self.bars = {p: {} for p in self.products}          # product -> {bar_start: [o, h, l, c, v]}
        self.seen_until = {p: 0.0 for p in self.products}   # newest message time per product (trade/heartbeat)
        self.up_since = None                                 # stream time from which we have every trade
        self.last_seq = {p: None for p in self.products}
        self.last_tid = {p: None for p in self.products}     # newest trade id received (Coinbase numbers trades 1, 2, 3...)
        self.hb = {p: [] for p in self.products}             # (heartbeat time, last_trade_id at that time), recent
        self.gap_bars = {p: set() for p in self.products}    # minutes in which a trade id was skipped (incomplete)
        self.messages = 0
        self.errors = 0
        self._thread = None
        self._stop = threading.Event()
        self._last_trade_t = {}

    # ---- public
    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="coinbase-ws", daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def bar(self, product: str, start: int, wait_s: float = 0.0):
        """(open, high, low, close, volume) of the 1-minute bar starting at `start`, or None if the stream
        can't vouch for it (not connected for the whole minute, or nothing seen after the minute yet).
        A complete minute with no trades -> "empty" (Coinbase publishes no candle then)."""
        deadline = time.monotonic() + wait_s
        while True:
            with self._lock:
                # complete = connected for the whole minute AND a heartbeat timed at/after the minute's end whose
                # last_trade_id we have already received (every trade up to then is in), AND no trade id skipped
                hb = next((tid for ht, tid in self.hb.get(product, []) if ht >= start + 60), None)
                have = self.last_tid.get(product)
                ok = (self.up_since is not None and self.up_since <= start
                      and hb is not None and have is not None and have >= hb
                      and start not in self.gap_bars.get(product, set()))
                if ok:
                    b = self.bars.get(product, {}).get(start)
                    return tuple(b) if b else "empty"
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.02)

    def healthy(self, product: str, now: float | None = None) -> bool:
        now = self.clock() if now is None else now
        with self._lock:
            return self.up_since is not None and now - self.seen_until.get(product, 0.0) < 5.0

    # ---- feed (also used by tests)
    def on_message(self, m: dict):
        typ = m.get("type")
        p = m.get("product_id")
        if p not in self.bars:
            return
        with self._lock:
            self.messages += 1
            if typ in ("match", "last_match"):
                seq = m.get("sequence")
                last = self.last_seq[p]
                if typ == "match" and last is not None and seq is not None and seq <= last:
                    return                                   # duplicate
                t, px, sz = _iso_ts(m["time"]), float(m["price"]), float(m.get("size") or 0.0)
                tid = m.get("trade_id")
                if tid is not None:
                    lt = self.last_tid[p]
                    if typ == "match" and lt is not None and tid > lt + 1:
                        # trades lt+1 .. tid-1 never arrived: every minute they could fall in is incomplete
                        b = int(self._last_trade_t.get(p, t) // 60 * 60)
                        while b <= t:
                            self.gap_bars[p].add(b)
                            b += 60
                    self.last_tid[p] = tid if lt is None else max(lt, tid)
                    self._last_trade_t[p] = t
                if typ == "match":
                    self.last_seq[p] = seq
                    b0 = int(t // 60 * 60)
                    b = self.bars[p].get(b0)
                    if b is None:
                        self.bars[p][b0] = [px, px, px, px, sz]
                    else:
                        b[1], b[2], b[3], b[4] = max(b[1], px), min(b[2], px), px, b[4] + sz
                self.seen_until[p] = max(self.seen_until[p], t)
            elif typ == "heartbeat":
                ht = _iso_ts(m["time"])
                self.seen_until[p] = max(self.seen_until[p], ht)
                if m.get("last_trade_id") is not None:
                    self.hb[p].append((ht, int(m["last_trade_id"])))
                    if len(self.hb[p]) > 300:
                        del self.hb[p][:150]
            cut = self.clock() - self.KEEP_S
            if self.messages % 5000 == 0:
                for bp in self.bars.values():
                    for k in [k for k in bp if k < cut]:
                        del bp[k]

    def _mark_up(self, t: float):
        with self._lock:
            self.last_tid = {p: None for p in self.products}
            self.hb = {p: [] for p in self.products}
            # every trade from the next whole minute on will be seen (subscription confirmed before it)
            self.up_since = int(t // 60 * 60) + 60
            self.last_seq = {p: None for p in self.products}

    def _mark_down(self):
        with self._lock:
            self.up_since = None

    def _run(self):
        delay = 1.0
        while not self._stop.is_set():
            ws = None
            try:
                ws = self._connect() if self._connect else _cb_connect()
                ws.send(json.dumps({"type": "subscribe", "product_ids": self.products,
                                    "channels": ["matches", "heartbeat"]}))
                while not self._stop.is_set():
                    m = json.loads(ws.recv())
                    if m.get("type") == "subscriptions":
                        self._mark_up(self.clock())
                    elif m.get("type") == "error":
                        raise RuntimeError(m.get("message"))
                    else:
                        self.on_message(m)
                    delay = 1.0
            except Exception:
                self.errors += 1
                self._mark_down()
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
            finally:
                try:
                    ws and ws.close()
                except Exception:
                    pass


def _cb_connect():
    import websocket
    return websocket.create_connection(COINBASE_WS, timeout=30, **_ws_kwargs())


_CB = None
_CB_LOCK = threading.Lock()


def coinbase(products=None):
    """Process-wide Coinbase stream (started on first use). Disabled with KALSHI15M_NO_STREAMS=1."""
    global _CB
    if os.environ.get("KALSHI15M_NO_STREAMS"):
        return None
    with _CB_LOCK:
        if _CB is None:
            from .data import SERIES
            _CB = CoinbaseBars(products or sorted(set(SERIES.values()))).start()
        return _CB


# =========================================================================== Kalshi
class _Book:
    def __init__(self):
        self.yes, self.no = {}, {}          # price (dollars, float) -> size
        self.hist_t, self.hist_q = [], []   # ms timestamps, (yes_bid, yb_size, yes_ask, ya_size)

    def best(self):
        yb = max((p for p, s in self.yes.items() if s > 0), default=None)
        nb = max((p for p, s in self.no.items() if s > 0), default=None)
        return (yb, self.yes.get(yb, 0.0) if yb is not None else 0.0,
                (1 - nb) if nb is not None else None, self.no.get(nb, 0.0) if nb is not None else 0.0)

    def record(self, ts_ms):
        q = self.best()
        if self.hist_q and self.hist_q[-1] == q:
            return
        if self.hist_t and ts_ms < self.hist_t[-1]:
            ts_ms = self.hist_t[-1]
        self.hist_t.append(ts_ms)
        self.hist_q.append(q)
        if len(self.hist_t) > 20000:
            del self.hist_t[:10000], self.hist_q[:10000]


class KalshiBooks:
    def __init__(self, api, mode="PROD", connect=None, clock=time.time):
        self.api, self.mode, self.clock = api, mode, clock
        self._connect = connect
        self._lock = threading.Lock()
        self.books = {}            # ticker -> _Book
        self.synced_since = {}     # ticker -> ms from which the book is known continuously (snapshot time)
        self.want = set()          # tickers we want
        self.subscribed = set()
        self.seq = {}              # subscription id -> last sequence number
        self.close_ts = {}         # ticker -> market close time (for pruning)
        self.last_msg = 0.0
        self.errors = 0
        self._ws = None
        self._next_id = 1
        self._thread = None
        self._stop = threading.Event()
        self._resub = threading.Event()

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="kalshi-ws", daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def track(self, ticker: str, close_ts: float | None = None):
        """Ask for this market's book (subscribed on the stream thread)."""
        with self._lock:
            if close_ts:
                self.close_ts[ticker] = close_ts
            if ticker not in self.want:
                self.want.add(ticker)
                self._resub.set()

    def as_of(self, ticker: str, t: float, wait_s: float = 0.0, close_ts: float | None = None):
        """Best (yes_bid, yb_size, yes_ask, ya_size) in force just before time t (seconds), or None if the
        stream can't vouch for it: not in sync since before t, or not alive at/after t."""
        self.track(ticker, close_ts)
        t_ms = int(round(t * 1000))
        deadline = time.monotonic() + wait_s
        while True:
            with self._lock:
                b = self.books.get(ticker)
                ok = (b is not None and ticker in self.synced_since and self.synced_since[ticker] <= t_ms
                      and self.last_msg * 1000 >= t_ms)
                if ok:
                    i = bisect.bisect_left(b.hist_t, t_ms) - 1      # last change strictly before t
                    if i >= 0:
                        return b.hist_q[i]
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.02)

    # ---- feed (also used by tests)
    def on_message(self, m: dict):
        typ, msg = m.get("type"), m.get("msg") or {}
        with self._lock:
            self.last_msg = max(self.last_msg, (m.get("sending_ts_ms") or 0) / 1000 or self.clock())
            seq, sid = m.get("seq"), m.get("sid")
            if typ in ("orderbook_snapshot", "orderbook_delta") and seq is not None:
                last = self.seq.get(sid)
                if typ == "orderbook_delta" and last is not None and seq != last + 1:
                    raise _Gap(f"sid {sid}: seq {seq} after {last}")
                self.seq[sid] = seq
            tk = msg.get("market_ticker")
            if typ == "orderbook_snapshot":
                b = _Book()
                for px, sz in msg.get("yes_dollars_fp") or []:
                    b.yes[round(float(px), 4)] = float(sz)
                for px, sz in msg.get("no_dollars_fp") or []:
                    b.no[round(float(px), 4)] = float(sz)
                ts = int(m.get("sending_ts_ms") or self.clock() * 1000)
                b.record(ts)
                self.books[tk] = b
                self.synced_since[tk] = ts
            elif typ == "orderbook_delta":
                b = self.books.get(tk)
                if b is None:
                    return
                side = b.yes if msg.get("side") == "yes" else b.no
                px = round(float(msg["price_dollars"]), 4)
                side[px] = side.get(px, 0.0) + float(msg["delta_fp"])
                if side[px] <= 1e-9:
                    side.pop(px, None)
                b.record(int(msg.get("ts_ms") or m.get("sending_ts_ms") or self.clock() * 1000))

    def _run(self):
        delay = 1.0
        while not self._stop.is_set():
            ws = None
            try:
                ws = self._connect() if self._connect else self._ws_connect()
                with self._lock:
                    self.subscribed, self.seq = set(), {}
                    self.synced_since.clear()
                ws.settimeout(1.0)
                while not self._stop.is_set():
                    if self._resub.is_set():
                        self._resub.clear()
                        with self._lock:
                            now = self.clock()
                            old = {t for t in self.want if self.close_ts.get(t, now + 1) < now - 120}
                            for t in old:                            # closed markets: forget them
                                self.want.discard(t); self.books.pop(t, None); self.synced_since.pop(t, None)
                                self.close_ts.pop(t, None)
                            todo = sorted(t for t in self.want if t not in self.subscribed)
                        if todo:
                            # one subscription per batch; Kalshi sends a snapshot for each market
                            ws.send(json.dumps({"id": self._next_id, "cmd": "subscribe",
                                                "params": {"channels": ["orderbook_delta"], "market_tickers": todo}}))
                            self._next_id += 1
                            with self._lock:
                                self.subscribed |= set(todo)
                    try:
                        raw = ws.recv()
                    except Exception as e:
                        # a timeout only means no message this second; liveness is judged from real messages
                        if type(e).__name__ in ("WebSocketTimeoutException", "TimeoutError", "timeout"):
                            if self.clock() - self.last_msg > 20:      # silent for 20 s: reconnect
                                raise
                            continue
                        raise
                    m = json.loads(raw)
                    if m.get("type") == "error":
                        raise RuntimeError(str(m.get("msg"))[:200])
                    self.on_message(m)
                    delay = 1.0
            except Exception:
                self.errors += 1
                with self._lock:
                    self.synced_since.clear()
                    self.subscribed = set()
                    self._resub.set()
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
            finally:
                try:
                    ws and ws.close()
                except Exception:
                    pass

    def _ws_connect(self):
        import websocket
        h = self.api.headers("GET", KALSHI_WS_PATH)
        return websocket.create_connection(KALSHI_WS[self.mode], header=[f"{k}: {v}" for k, v in h.items()],
                                           timeout=30, **_ws_kwargs())


class _Gap(Exception):
    pass

