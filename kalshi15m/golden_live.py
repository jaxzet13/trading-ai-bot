"""Live lab3 features + the 16 golden rules, shared by the real-money runner (real.py) and the paper bot.

lab3 (kalshi15m/lab3.py) found 16 "golden" rules on a backtest panel whose extra columns come from
lab3.add_features. This module builds the SAME columns for the one market a live bot is watching, minute
by minute, so that lab3's own family functions (lab3.signal / lab3.FAMILIES) run unchanged on the live
1-row panel. tests/test_golden_live.py replays holdout markets minute by minute through this code and
checks every rule picks the same side / minute / price as lab3.signal on the batch panel.

    from kalshi15m import golden_live as GL
    eng = GL.engine("KXDOGE15M")            # one shared engine per coin (thread-safe, any number of threads)
    eng.prepare()                           # once, at thread start: spot history from disk + Coinbase catch-up
    # each minute, after filling column `minute` of the 1-row panel P exactly like bot.run / real.observe:
    info = eng.update(P, open_ts, minute, spot_now=ticker_price)   # spot_now optional (fetched if needed)
    sigs = eng.signals(P, minute)           # golden rules for this coin that fire NOW, best (highest holdout t) first
    sig = eng.decide("fv_lag:ALL", P, minute)                     # one rule: Signal or None
    stake, kelly = GL.sized_stake(sig.rule, sig.q, sig.price, base_stake)    # "sized" rules
    hit = eng.exit_check("scalp:ALL", P, minute, held_side, entry_minute)    # "scalp" rules: (sell, q) or None

How the spot history is kept (identical to the batch panel, which uses Coinbase 1-minute candle closes):
  * at start: data/kalshi15m/<series>_spot.csv + data/kalshi15m/<series>_spot_live.csv (our cached catch-up)
    + Coinbase candles fetched once to reach the present (serialised across coins, gently); only the last
    22 days are kept (the longest lookback is the 21-day bootstrap);
  * every minute T (decision 0.5 s after T): the latest Coinbase candles (one request, shared by all threads
    of the coin). The backtest's spot at T is the close of the 1-minute bar that started at T-60; Coinbase
    usually publishes that bar a few seconds late, so until it does we use a synthetic bar whose close is
    the live ticker price (high/low carried forward). It is replaced by the official bar on the next minute.
    Minutes with no candle are forward-filled, exactly as lab3.Spot / backtest.build_panel do.
  * update() overwrites column `minute` of spot, vol1m, vol240, prev_ret, ret_from_open with the values
    build_panel would compute from those bars, applies build_panel's empty-book rule to the quotes (no bid
    or no ask -> both NaN), and adds every lab3.add_features column (vols, returns, time-of-day, bootstrap
    probabilities). Per-day work (bootstrap samples, time-of-day factors) and per-minute work are cached
    per coin, so 100+ threads cost one computation.
  * BTC/ETH reference columns (ref_*) are left NaN: no golden rule uses them (families fv_btcdrift and
    fv_cross are refused by decide()).
"""
from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import lab3
from .data import COINBASE, DATA_DIR, SERIES
from .strategies import model_prob

ALL9 = list(SERIES)
KEEP_DAYS = 22                    # spot history kept in memory (bootstrap lookback is 21 days)
VOL_TAIL = 7200                   # bars used for the rolling/EWMA vols (EWMA half-life 120: 0.5**60 ~ 1e-18)
SETTLE_S = 240                    # Coinbase revises a 1-minute candle for a few minutes after first publishing it
                                  # (measured 2026-11-04: the bar that just closed was often 0.1-0.3% off its final
                                  # close, the value lab3 trains/tests on). Candles younger than this are only a
                                  # fallback; the bar that just closed always comes from the live ticker.
MAX_CANDLE_LAG_S = 1800           # newest Coinbase bar older than this -> refuse (dead feed). Thin coins
                                  # legitimately go up to 13 min without a trade (HYPE, last 30 days)
FETCH_GAP_S = 0.35                # pause between catch-up requests (the bots share one IP)

# The 16 golden rules of data/lab/lab3_results.json, best first (priority = holdout t-stat). Params are
# copied exactly (tests/test_golden_live.py checks them against the results file). "norm" = average Kelly
# fraction of the rule's trades on the SEARCH window (lab3._sized_norms), the stake normaliser of "sized".
GOLDEN = [
    {"id": "scalp:ALL", "family": "scalp", "scope": "ALL", "t": 6.71,
     "params": {"vm": 0.8, "edge": 0.12, "start": 2, "end": 13, "band": "05-95", "exit": "conv0"}},
    {"id": "sized:ALL", "family": "sized", "scope": "ALL", "t": 6.14,
     "params": {"start": 2, "end": 13, "edge": 0.13, "band": "05-95", "vm": 1.0, "cap": 5}, "norm": None},
    {"id": "fv_lag:ALL", "family": "fv_lag", "scope": "ALL", "t": 5.74,
     "params": {"start": 2, "end": 13, "edge": 0.12, "band": "05-95", "r": 1, "k": 0.25, "qlag": "lag", "vm": 0.8}},
    {"id": "fv_shape:ALL", "family": "fv_shape", "scope": "ALL", "t": 5.67,
     "params": {"start": 2, "end": 13, "edge": 0.14, "band": "05-95", "a": 1.1, "vm": 1.0}},
    {"id": "fv_drift:ALL", "family": "fv_drift", "scope": "ALL", "t": 5.33,
     "params": {"start": 2, "end": 13, "edge": 0.18, "band": "05-95", "L": 1, "a": 0.25, "vm": 1.0}},
    {"id": "fv_emp:ALL", "family": "fv_emp", "scope": "ALL", "t": 5.3,
     "params": {"start": 2, "end": 13, "edge": 0.14, "band": "05-95", "lb": 21, "vm": 1.0}},
    {"id": "fv_drift:KXDOGE15M", "family": "fv_drift", "scope": "KXDOGE15M", "t": 5.27,
     "params": {"start": 2, "end": 13, "edge": 0.2, "band": "05-95", "L": 1, "a": 0.25, "vm": 0.8}},
    {"id": "fv_vol:ALL", "family": "fv_vol", "scope": "ALL", "t": 5.22,
     "params": {"start": 2, "end": 13, "edge": 0.13, "band": "05-95", "vol": "ewma30", "vm": 0.9}},
    {"id": "scalp:KXDOGE15M", "family": "scalp", "scope": "KXDOGE15M", "t": 5.16,
     "params": {"vm": 0.8, "edge": 0.14, "start": 3, "end": 13, "band": "05-95", "exit": "conv0"}},
    {"id": "fv_ref:ALL", "family": "fv_ref", "scope": "ALL", "t": 5.13,
     "params": {"start": 2, "end": 13, "edge": 0.14, "band": "05-95", "vol": "max", "vm": 0.8}},
    {"id": "ens_fixed:ALL", "family": "ens_fixed", "scope": "ALL", "t": 5.0,
     "params": {"start": 2, "end": 13, "edge": 0.14, "band": "05-95", "members": "fv+v2", "mode": "first", "vm": 0.8}},
    {"id": "fv_t:ALL", "family": "fv_t", "scope": "ALL", "t": 4.72,
     "params": {"start": 2, "end": 13, "edge": 0.13, "band": "05-95", "nu": 4, "vol": "60", "vm": 1.25}},
    {"id": "sized:KXDOGE15M", "family": "sized", "scope": "KXDOGE15M", "t": 4.38,
     "params": {"start": 4, "end": 13, "edge": 0.13, "band": "05-95", "vm": 1.0, "cap": 5}, "norm": None},
    {"id": "sized:KXHYPE15M", "family": "sized", "scope": "KXHYPE15M", "t": 4.22,
     "params": {"start": 2, "end": 12, "edge": 0.14, "band": "05-95", "vm": 1.25, "cap": 5}, "norm": None},
    {"id": "fv_liq:KXHYPE15M", "family": "fv_liq", "scope": "KXHYPE15M", "t": 3.89,
     "params": {"start": 2, "end": 12, "edge": 0.13, "band": "05-95", "max_spr": 0.1, "quote": "any", "min_vol": 0,
                "vm": 1.0}},
    {"id": "fv_shape:KXHYPE15M", "family": "fv_shape", "scope": "KXHYPE15M", "t": 3.86,
     "params": {"start": 2, "end": 12, "edge": 0.14, "band": "05-95", "a": 0.7, "vm": 0.8}},
]
SIZED_NORMS = {"sized:ALL": 0.26276383779910073,          # computed by compute_sized_norms(); reproduces
               "sized:KXDOGE15M": 0.260929335166002,      # lab3's holdout of each sized rule exactly
               "sized:KXHYPE15M": 0.22610238553831677}
for _r in GOLDEN:
    _r["kind"] = lab3.FAMILIES[_r["family"]]["kind"]          # hold | sized | scalp
    if _r["kind"] == "sized":
        _r["norm"] = SIZED_NORMS[_r["id"]]
# Combinations of golden pieces, each tested as ONE fixed rule (no tuning) on the search window, the
# locked holdout and the older archive (scratchpad combo.py, Nov 3): #2's entries and Kelly stakes
# (sized:ALL) with #1's early exit (conv0). Holdout $8,034 / t 6.95; archive $6,607 / t 5.81; search t 11.3.
EXTRA = [
    # lab5 (data/lab/lab5_results.json) x_exit:ALL: scalp entry at 13c, stakes on kelly**1.5 capped 5x, exit when the
    # bid is within 2c of fair value. Holdout $7,025 / t 10.15; archive $6,763 / t 8.62; fresh $1,130 / t 3.89;
    # cumulative Bonferroni bar 3.35 over 124 holdout tests.
    {"id": "x_exit:ALL", "family": "scalp", "scope": "ALL", "t": 10.15, "kind": "sized_exit",
     "params": {"vm": 0.8, "edge": 0.13, "start": 2, "end": 13, "band": "05-95", "cap": 5, "pow": 1.5, "exit": "conv2"},
     "norm": 0.22693348935173294},
    {"id": "sized_exit:ALL", "family": "sized", "scope": "ALL", "t": 6.95, "kind": "sized_exit",
     "params": {"start": 2, "end": 13, "edge": 0.13, "band": "05-95", "vm": 1.0, "cap": 5, "exit": "conv0"},
     "norm": SIZED_NORMS["sized:ALL"]},
    # lab5 x_cap:ALL: scalp entry (12c), Kelly stakes capped 3x, exit at fair value (conv0); lab5 also capped
    # same-direction bets per 15-minute window at 6 across coins (the live runner's max_entries_per_window_side
    # does that job, set per account). Holdout $7,144 / t 9.06 (lab5); the only strategy that passed the 3-day
    # real-money test (labrm, Nov 1-4: +$14.62 at a $0.50 base, profitable in both periods, t 2.2).
    {"id": "x_cap:ALL", "family": "scalp", "scope": "ALL", "t": 9.06, "kind": "sized_exit",
     "params": {"vm": 0.8, "edge": 0.12, "start": 2, "end": 13, "band": "05-95", "cap": 3, "exit": "conv0"},
     "norm": 0.3412936032571755},
]
ORDER = EXTRA + GOLDEN                                        # best first
RULES = {r["id"]: r for r in ORDER}
PRIORITY = {r["id"]: i for i, r in enumerate(ORDER)}


def rules_for(series: str) -> list[str]:
    """Golden rule ids that apply to this coin, best first."""
    return [r["id"] for r in ORDER if r["scope"] in ("ALL", series)]


def sized_stake(rule_id: str, q: float, price: float, stake: float):
    """lab3 "sized": stake * min(kelly / norm, cap), kelly = max((q - price) / (1 - price), 1e-4).
    -> (dollars to stake, kelly)."""
    r = RULES[rule_id]
    kel = max((q - price) / (1 - price), 1e-4)
    w = kel ** r["params"].get("pow", 1)          # lab5 x_exit sizes on kelly**1.5
    return stake * min(w / r["norm"], r["params"]["cap"]), kel


@dataclass
class Signal:
    rule: str            # golden rule id, e.g. "fv_lag:ALL"
    side: str            # "yes" | "no"
    price: float         # the taker price of that side at this minute (yes_ask or no_ask = 1 - yes_bid)
    minute: int          # 1..14 (always the minute asked about)
    q: float             # the rule's model probability of the side bought, at this minute
    p: np.ndarray        # the rule's model probability of YES, shape (1, 14)
    priority: int        # 0 = best rule

    @property
    def kind(self):
        return RULES[self.rule]["kind"]

    def __iter__(self):                  # side, price, p = engine.decide(...)
        return iter((self.side, self.price, self.p))


class StaleData(requests.RequestException):
    """The spot feed is too old to trade on (treated like a network error by the runners)."""


# ----------------------------------------------------------------------------- spot bars
class LiveSpot(lab3.Spot):
    """lab3.Spot-compatible view (same arrays: t0, ts, c, h, l, lc, lr, v60) built from arrays on a full
    minute grid that are already forward-filled, plus v240 (backtest.build_panel's vol240)."""

    def __init__(self, t0: int, c, h, l):
        self.t0 = int(t0)
        self.ts = self.t0 + 60 * np.arange(len(c), dtype=np.int64)
        self.c, self.h, self.l = c, h, l
        self.lc = np.log(self.c)
        self.lr = np.r_[np.nan, np.diff(self.lc)]
        s = pd.Series(self.lr)
        self.v60 = s.rolling(60, min_periods=30).std().to_numpy()
        self.v240 = s.rolling(240, min_periods=120).std().to_numpy()


def _now_minute(t):
    return int(t // 60 * 60)


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


_FETCH_LOCK = threading.Lock()        # catch-up downloads: one coin at a time
_POOL = __import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=12, thread_name_prefix="golden-tick")


def coinbase_candles(product: str, start: int | None = None, end: int | None = None, timeout: float = 4.0,
                     session=requests):
    """Coinbase 1-minute candles [[ts, low, high, open, close, volume], ...] (latest ~300 when no range)."""
    params = {"granularity": 60}
    if start is not None:
        params.update(start=_iso(start), end=_iso(end))
    try:
        r = session.get(f"{COINBASE}/products/{product}/candles", params=params, timeout=timeout)
    except (requests.Timeout, requests.ConnectionError) as e:
        raise requests.RequestException(f"coinbase candles: {e}") from None
    if r.status_code != 200:
        raise requests.RequestException(f"coinbase candles HTTP {r.status_code}: {r.text[:120]}")
    d = r.json()
    if not isinstance(d, list):
        raise requests.RequestException(f"coinbase candles: unexpected answer {str(d)[:120]}")
    return d


def coinbase_ticker(product: str, timeout: float = 4.0, session=requests) -> float:
    try:
        r = session.get(f"{COINBASE}/products/{product}/ticker", timeout=timeout)
        return float(r.json()["price"])
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        raise requests.RequestException(f"coinbase ticker: {e}") from None


# ----------------------------------------------------------------------------- the engine
class GoldenEngine:
    """Live lab3 features for one coin. One instance per coin, shared by every thread (see engine())."""

    COLS = ("ts", "low", "high", "open", "close", "volume")

    def __init__(self, series: str, history: pd.DataFrame | None = None, fetch_candles=None, fetch_ticker=None,
                 clock=time.time, sleep=time.sleep, data_dir: Path | None = DATA_DIR, persist: bool = True,
                 max_candle_lag_s: float = MAX_CANDLE_LAG_S, stream="auto"):
        self.series, self.product = series, SERIES[series]
        # Coinbase trade stream (kalshi15m.streams): exact 1-minute bars at decision time. Only with the real
        # network feeds (tests pass fakes) and unless KALSHI15M_NO_STREAMS is set.
        if stream == "auto":
            from . import streams as _streams
            stream = _streams.coinbase() if fetch_candles is None and fetch_ticker is None else None
        self.stream = stream
        self.rule_ids = rules_for(series)
        self._history = history
        self.fetch_candles = fetch_candles or (lambda **kw: coinbase_candles(self.product, **kw))
        self.fetch_ticker = fetch_ticker or (lambda: coinbase_ticker(self.product))
        self.clock, self.sleep = clock, sleep
        self.data_dir = Path(data_dir) if data_dir else None
        self.persist = persist and self.data_dir is not None
        self.max_candle_lag_s = max_candle_lag_s
        self._lock = threading.RLock()
        self.ready = False
        self.stats = {"fetch_s": 0.0, "compute_s": 0.0, "minutes": 0, "synthetic": 0}

    # --- history
    @property
    def cache_path(self):
        return self.data_dir / f"{self.series}_spot_live.csv" if self.data_dir else None

    def prepare(self):
        """Load the spot history and catch up to now. Idempotent and thread-safe; call at thread start."""
        with self._lock:
            if self.ready:
                return self
            now = self.clock()
            ws = (int(now) // 86400 - KEEP_DAYS) * 86400
            if self._history is not None:
                df = self._history
                main_last = int(df.ts.max()) if len(df) else 0
            else:
                try:
                    main = pd.read_csv(self.data_dir / f"{self.series}_spot.csv")
                except (OSError, ValueError) as e:
                    raise StaleData(f"{self.series}: cannot read the spot history ({e})") from None
                main_last = int(main.ts.max())
                parts = [main[main.ts >= ws]]
                if self.cache_path.exists():
                    try:
                        parts.append(pd.read_csv(self.cache_path))
                    except (OSError, ValueError, pd.errors.ParserError):
                        pass
                df = pd.concat(parts, ignore_index=True)
            df = df[list(self.COLS)].drop_duplicates("ts", keep="last").sort_values("ts")
            df = df[df.ts >= ws]
            if self._history is None:
                df = self._catch_up(df, max(ws, int(df.ts.max()) + 60 if len(df) else ws), now)
                self._save_cache(df, main_last, now)
            self._main_last = main_last
            self._load_frame(df)
            self._T = 0
            self._feat, self._emp, self._tod = {}, {}, {}
            self._persisted = int(min(df.ts.max(), _now_minute(now) - 180))
            self.ready = True
            return self

    def _catch_up(self, df, start, now):
        end = _now_minute(now) - 60
        rows = []
        if start <= end:
            with _FETCH_LOCK:
                t = start
                while t <= end:
                    t2 = min(t + 299 * 60, end)
                    rows += self.fetch_candles(start=t, end=t2)
                    t = t2 + 60
                    self.sleep(FETCH_GAP_S)
        if rows:
            new = pd.DataFrame(rows, columns=list(self.COLS))
            df = pd.concat([df, new[new.ts < _now_minute(now)]], ignore_index=True)
            df = df.drop_duplicates("ts", keep="last").sort_values("ts")
        return df

    def _save_cache(self, df, main_last, now):
        """Bars newer than the main CSV and old enough to be final -> <series>_spot_live.csv (gitignored)."""
        if not self.persist:
            return
        keep = df[(df.ts > main_last) & (df.ts <= _now_minute(now) - 180)]
        if not len(keep):
            return
        tmp = self.cache_path.with_suffix(f".tmp{os.getpid()}")
        keep.to_csv(tmp, index=False)
        os.replace(tmp, self.cache_path)

    def _append_cache(self, upto):
        if not self.persist:
            return
        lo = (self._persisted - self.t0) // 60 + 1
        hi = min((upto - self.t0) // 60, self.last_off)
        if hi < lo:
            return
        i = np.arange(lo, hi + 1)
        i = i[self.official[i]]
        if len(i):
            rows = pd.DataFrame({"ts": self.t0 + 60 * i, "low": self.ol[i], "high": self.oh[i], "open": self.oo[i],
                                 "close": self.oc[i], "volume": self.ov[i]})
            try:
                with self.cache_path.open("a") as f:
                    rows.to_csv(f, header=f.tell() == 0, index=False)
            except OSError:
                return
        self._persisted = int(self.t0 + 60 * hi)

    def _load_frame(self, df):
        """Official bars -> arrays on a full minute grid (NaN where Coinbase has no candle)."""
        if not len(df):
            raise StaleData(f"{self.series}: no spot history")
        t0 = int(df.ts.iloc[0])
        n = (int(df.ts.iloc[-1]) - t0) // 60 + 1
        idx = ((df.ts.to_numpy(np.int64) - t0) // 60)
        self.t0 = t0
        self.oc, self.oh, self.ol, self.oo, self.ov = (np.full(n, np.nan) for _ in range(5))
        self.official = np.zeros(n, bool)
        for arr, col in ((self.oc, "close"), (self.oh, "high"), (self.ol, "low"), (self.oo, "open"),
                         (self.ov, "volume")):
            arr[idx] = df[col].to_numpy(float)
        self.official[idx] = True
        self.last_off = int(idx[-1])
        self.synth = {}
        self.prov = {}
        self.exact = {}
        self._rebuild()

    def _grow(self, n):
        k = n - len(self.oc)
        if k > 0:
            pad = np.full(k, np.nan)
            self.oc, self.oh, self.ol, self.oo, self.ov = (np.r_[a, pad] for a in
                                                           (self.oc, self.oh, self.ol, self.oo, self.ov))
            self.official = np.r_[self.official, np.zeros(k, bool)]

    def _rebuild(self):
        """Effective bars = official, forward-filled (as lab3.Spot); after the newest official bar, the
        synthetic closes taken from the live ticker (high/low carried forward)."""
        c, h, l = self.oc.copy(), self.oh.copy(), self.ol.copy()
        for ts, (pc, ph, pl) in getattr(self, "prov", {}).items():    # provisional candles: fallback
            i = (ts - self.t0) // 60
            if self.last_off < i < len(c):
                c[i], h[i], l[i] = pc, ph, pl
        for ts, px in self.synth.items():                               # live ticker samples win for the close
            i = (ts - self.t0) // 60
            if self.last_off < i < len(c):
                c[i] = px
        for ts, (pc, ph, pl) in getattr(self, "exact", {}).items():    # bars built from every trade: exact
            i = (ts - self.t0) // 60
            if self.last_off < i < len(c):
                c[i], h[i], l[i] = pc, ph, pl
        ff = lambda a: pd.Series(a).ffill().to_numpy()
        self.sp = LiveSpot(self.t0, ff(c), ff(h), ff(l))

    def _trim(self, T):
        ws = (T // 86400 - KEEP_DAYS) * 86400
        if ws <= self.t0 + 86400:
            return
        k = (ws - self.t0) // 60
        sp = self.sp
        first = (sp.c[k], sp.h[k], sp.l[k])          # keep the first bar defined after the cut
        for name in ("oc", "oh", "ol", "oo", "ov", "official"):
            setattr(self, name, getattr(self, name)[k:].copy())
        if not self.official[0]:
            self.oc[0], self.oh[0], self.ol[0] = first
            self.official[0] = True
        self.t0 += 60 * k
        self.last_off -= k
        self._emp.clear()
        self._tod.clear()

    def _merge(self, candles, T, spot_now):
        """Add Coinbase candles (official bars before T) and, if the bar T-60 is still missing, a synthetic
        bar with the live price."""
        bar = T - 60
        new_off = False
        settled = T - 60 - SETTLE_S
        for row in candles:
            ts = int(row[0])
            if ts >= T or ts < self.t0:
                continue
            if ts > settled:                 # still being revised by Coinbase: fallback only, never "official"
                self.prov[ts] = (float(row[4]), float(row[2]), float(row[1]))     # close, high, low
                continue
            i = (ts - self.t0) // 60
            self._grow(i + 1)
            self.ol[i], self.oh[i], self.oo[i], self.oc[i], self.ov[i] = (float(x) for x in row[1:6])
            self.official[i] = True
            self.last_off = max(self.last_off, i)
            new_off = True
        ib = (bar - self.t0) // 60
        self._grow(ib + 1)
        last_ts = self.t0 + 60 * self.last_off
        self.synth = {ts: px for ts, px in self.synth.items() if ts > last_ts}
        self.prov = {ts: px for ts, px in self.prov.items() if ts > last_ts}
        self.exact = {ts: v for ts, v in getattr(self, "exact", {}).items() if ts > last_ts}
        synthetic = not self.official[ib] and bar not in self.exact
        if synthetic and spot_now is not None and np.isfinite(spot_now) and spot_now > 0:
            self.synth[bar] = float(spot_now)
        self._rebuild()
        return synthetic, last_ts, new_off

    def _ensure(self, T, spot_now):
        """Bring the bars up to the decision minute T (fetch once per coin and minute)."""
        if self._T >= T:
            return self._last_info
        t0 = time.perf_counter()
        # Coinbase publishes the bar that just closed a few seconds late, so the live price is almost always
        # needed: ask for it at the same time as the candles (same two requests as bot._spot_and_vol).
        tick = _POOL.submit(self.fetch_ticker) if spot_now is None else None
        try:
            candles = self.fetch_candles()
        finally:
            if tick is not None:
                try:
                    tick_px, tick_err = tick.result(), None
                except requests.RequestException as e:
                    tick_px, tick_err = None, e
        bar = T - 60
        source = "ticker"
        if self.stream is not None:
            # unsettled bars from the trade stream (the one that just closed: wait up to 1.5 s for it)
            if not hasattr(self, "exact"):
                self.exact = {}
            for ts in range(bar - SETTLE_S, bar + 60, 60):
                b = self.stream.bar(self.product, ts, wait_s=1.5 if ts == bar else 0.0)
                if isinstance(b, tuple):
                    self.exact[ts] = (b[3], b[1], b[2])                    # close, high, low
                elif b == "empty":                                           # no trades: Coinbase has no candle
                    self.exact.pop(ts, None)
                    self.synth.pop(ts, None)
            if bar in self.exact:
                source = "stream"
        # only a settled (official) bar or the trade stream may stand in for the live price; a just-published
        # REST candle may not
        have = (0 <= (bar - self.t0) // 60 < len(self.official) and self.official[(bar - self.t0) // 60]) \
            or bar in getattr(self, "exact", {})
        if tick is not None:
            if tick_err is not None and not have:
                raise tick_err
            spot_now = tick_px
        fetch_s = time.perf_counter() - t0
        self._trim(T)
        synthetic, last_ts, _ = self._merge(candles, T, spot_now)
        if T - 60 - last_ts > self.max_candle_lag_s:
            raise StaleData(f"{self.series}: newest Coinbase candle is {T - 60 - last_ts}s old")
        if self.persist and T - self._persisted >= 900 + 180:
            self._append_cache(T - 180)
        self._T = T
        self.stats["fetch_s"] += fetch_s
        self.stats["synthetic"] += int(synthetic)
        self._last_info = {"bar_ts": bar, "synthetic": bool(synthetic), "newest_candle_ts": int(last_ts),
                           "fetch_s": round(fetch_s, 3), "spot_source": source}
        return self._last_info

    # --- features (lab3.add_features, one market x one minute)
    def _emp_day(self, day):
        """Sorted bootstrap samples of lab3._emp_probs for one calendar day: {lb: {tau: array} | None}."""
        sp = self.sp
        dstart = int(day) * 86400
        N = len(sp.lc)
        out = {}
        for lb in (7, 21):
            lo, hi = sp.idx(dstart - lb * 86400), sp.idx(dstart - 900)
            if hi - lo < 1440:
                out[lb] = None
                continue
            per = {}
            for j in range(14):
                tau = 14 - j
                top = min(hi, N - tau)
                u = (sp.lc[lo + tau:top + tau] - sp.lc[lo:top]) / (sp.v60[lo:top] * math.sqrt(tau))
                s = u[::2]
                s = np.sort(s[np.isfinite(s)])
                per[tau] = s if len(s) >= 500 else None
            out[lb] = per
        return out

    def _emp_samples(self, day):
        hit = self._emp.get(day)
        if hit is not None:
            return hit
        res = self._emp_day(day)
        # cache only once every bar the samples use (up to the day start - 120 s) is an official candle
        if self.t0 + 60 * self.last_off >= day * 86400 - 120:
            for d in [d for d in self._emp if d < day - 1]:      # bounded memory: today and yesterday only
                del self._emp[d]
            self._emp[day] = res
        return res

    def _tod_day(self, day):
        hit = self._tod.get(day)
        if hit is None:
            ots = day * 86400 + 900 * np.arange(96, dtype=np.int64)
            hit = lab3._tod_ratio(self.sp, ots)
            for d in [d for d in self._tod if d < day - 1]:
                del self._tod[d]
            self._tod[day] = hit
        return hit

    def features(self, open_ts: int, minute: int, strike: float) -> dict:
        """Every column lab3.add_features (and build_panel's spot fields) would hold for this market at
        this minute, from the bars up to the decision time. Cached per (market, minute, strike)."""
        key = (int(open_ts), int(minute), float(strike))
        with self._lock:
            hit = self._feat.get(key)
            if hit is not None:
                return hit
            t0 = time.perf_counter()
            f = self._features(int(open_ts), int(minute), float(strike))
            if len(self._feat) > 64:
                self._feat.clear()
            self._feat[key] = f
            self.stats["compute_s"] += time.perf_counter() - t0
            self.stats["minutes"] += 1
            return f

    def _features(self, open_ts, minute, strike):
        sp = self.sp
        j = minute - 1
        bar = open_ts + 60 * minute - 60
        at = lambda arr, ts: float(sp.at(arr, np.array([ts]))[0])
        f = {}
        spot = at(sp.c, bar)
        f["spot"], f["vol1m"], f["vol240"] = spot, at(sp.v60, bar), at(sp.v240, bar)
        p_open, p_prev0 = at(sp.c, open_ts - 60), at(sp.c, open_ts - 960)
        f["prev_ret"] = p_open / p_prev0 - 1
        f["ret_from_open"] = spot / p_open - 1
        f["hour"] = float((open_ts % 86400) // 3600)
        f["dow"] = float(((open_ts // 86400) + 3) % 7)
        ib = (bar - sp.t0) // 60
        lo = max(0, ib + 1 - VOL_TAIL)
        if 0 <= ib < len(sp.c):
            lr = sp.lr[lo:ib + 1]
            s = pd.Series(lr)
            r2 = s ** 2
            hl = pd.Series(np.log(sp.h[lo:ib + 1] / sp.l[lo:ib + 1]) ** 2 / (4 * math.log(2)))
            prev = sp.lr[lo - 1] if lo > 0 else np.nan
            bp = pd.Series(np.abs(lr) * np.abs(np.r_[prev, lr[:-1]]))
            vols = {
                "v15": s.rolling(15, min_periods=10).std(),
                "v30": s.rolling(30, min_periods=20).std(),
                "ewma30": np.sqrt(r2.ewm(halflife=30, min_periods=30).mean()),
                "ewma60": np.sqrt(r2.ewm(halflife=60, min_periods=60).mean()),
                "ewma120": np.sqrt(r2.ewm(halflife=120, min_periods=120).mean()),
                "park": np.sqrt(hl.rolling(60, min_periods=30).mean()),
                "bpv": np.sqrt(math.pi / 2 * bp.rolling(60, min_periods=30).mean()),
            }
            for k, v in vols.items():
                f["vol_" + k] = float(np.asarray(v, float)[-1])
        else:
            for k in ("v15", "v30", "ewma30", "ewma60", "ewma120", "park", "bpv"):
                f["vol_" + k] = np.nan
        lc_now = at(sp.lc, bar)
        for L in (1, 2, 3, 5, 10, 15):
            f[f"r{L}"] = lc_now - at(sp.lc, bar - 60 * L)
        for k in ("ref_r1", "ref_r2", "ref_r3", "ref_r5", "ref_v60", "ref_z"):
            f[k] = np.nan                                  # BTC/ETH reference: not used by any golden rule
        day = open_ts // 86400
        f["tod_ratio"] = float(self._tod_day(day)[(open_ts - day * 86400) // 900, j])
        samples = self._emp_samples(day)
        tau = 14 - j
        x = np.log(np.float64(spot) / np.float64(strike))
        xz = x / (np.float64(f["vol1m"]) * math.sqrt(tau))
        for lb in (7, 21):
            s = (samples.get(lb) or {}).get(tau)
            for vm in (0.7, 0.8, 0.9, 1.0, 1.1, 1.25):
                v = np.nan
                if s is not None:
                    z = xz / vm
                    if np.isfinite(z):
                        v = 1 - np.searchsorted(s, -z, side="right") / len(s)
                f[f"emp{lb}_{vm}"] = float(v)
        return f

    # --- the per-minute call
    def update(self, P: dict, open_ts: int, minute: int, spot_now: float | None = None) -> dict:
        """Fill column `minute` of the caller's 1-row panel P with build_panel's spot fields and every
        lab3.add_features column, and apply build_panel's empty-book rule to the quotes already there.
        P must already hold this minute's yes_bid / yes_ask / no_ask / strike (bot.run / real.observe do
        that). spot_now: the live Coinbase price, used only while the bar that just closed is unpublished
        (fetched here if needed and not given). Returns timing / data info."""
        if not self.ready:
            self.prepare()
        j = minute - 1
        T = int(open_ts) + 60 * int(minute)
        t0 = time.perf_counter()
        with self._lock:
            info = dict(self._ensure(T, spot_now))
            f = self.features(open_ts, minute, float(P["strike"][0, j]))
        for k, v in f.items():
            if k not in P:
                P[k] = np.full((1, 14), np.nan)
            P[k][0, j] = v
        yb, ya = P["yes_bid"][0, j], P["yes_ask"][0, j]
        if not (np.isfinite(yb) and np.isfinite(ya) and yb > 0 and ya < 1):      # build_panel: bad -> both NaN
            P["yes_bid"][0, j] = P["yes_ask"][0, j] = np.nan
        P["no_ask"][0, j] = 1 - P["yes_bid"][0, j]
        P["p_model"] = model_prob(P)
        info.update(spot=f["spot"], vol1m=f["vol1m"], vol240=f["vol240"], update_s=round(time.perf_counter() - t0, 4))
        return info

    # --- rules
    def signals(self, P: dict, minute: int, rule_ids=None) -> list[Signal]:
        """Every rule (default: this coin's golden rules) whose FIRST signal in this market is at this
        minute, best (highest holdout t) first. One lab3.Ctx is shared, so model probabilities are computed
        once per minute."""
        ctx = _ctx(P)
        out = []
        for rid in (rule_ids if rule_ids is not None else self.rule_ids):
            s = _signal(ctx, rid, P, minute)
            if s is not None:
                out.append(s)
        return sorted(out, key=lambda s: s.priority)

    def decide(self, rule_id: str, P: dict, minute: int) -> Signal | None:
        return _signal(_ctx(P), rule_id, P, minute)

    def exit_check(self, rule_id: str, P: dict, minute: int, held_side: str, entry_minute: int):
        return exit_check(rule_id, P, minute, held_side, entry_minute)


class _Row:
    def __init__(self, P):
        self.P, self.result, self.open_ts = P, np.zeros(1, int), np.zeros(1, np.int64)


def _ctx(P):
    return lab3.Ctx("live", _Row(P))


def _signal(ctx, rule_id, P, minute):
    r = RULES[rule_id]
    if lab3.FAMILIES[r["family"]]["needs_ref"]:
        raise ValueError(f"{rule_id}: needs BTC/ETH reference columns, not supported live")
    side, mins, p = lab3.signal(ctx, r["family"], r["params"])
    if side[0] == 0 or int(mins[0]) != minute:
        return None
    j = minute - 1
    yes = side[0] == 1
    price = float(P["yes_ask"][0, j] if yes else P["no_ask"][0, j])
    if not (np.isfinite(price) and 0 < price < 1):
        return None
    q = float(p[0, j] if yes else 1 - p[0, j])
    return Signal(rule_id, "yes" if yes else "no", price, minute, q, np.array(p, float), PRIORITY[rule_id])


def exit_check(rule_id: str, P: dict, minute: int, held_side: str, entry_minute: int):
    """lab3 "scalp" exit (execute(), exit "convK"): at a minute after the entry, sell at the bid of the side
    held (YES: yes_bid, NO: 1 - yes_ask) once it is >= the rule's model value of that side - K cents.
    -> (sell price, model value) or None."""
    r = RULES[rule_id]
    ex = r["params"].get("exit", "")
    if r["kind"] not in ("scalp", "sized_exit") or not ex.startswith("conv") or minute <= entry_minute:
        return None
    j = minute - 1
    _, _, p = lab3.FAMILIES[r["family"]]["fn"](_ctx(P), r["params"])
    q = p[0, j] if held_side == "yes" else 1 - p[0, j]
    sb = P["yes_bid"][0, j] if held_side == "yes" else 1 - P["yes_ask"][0, j]
    if np.isfinite(sb) and 0 < sb < 1 and np.isfinite(q) and sb >= q - int(ex[4:]) / 100:
        return float(sb), float(q)
    return None


# ----------------------------------------------------------------------------- registry
_ENGINES: dict = {}
_REG_LOCK = threading.Lock()


def engine(series: str, **kw) -> GoldenEngine:
    """The shared engine of a coin (created on first use; kw only apply then)."""
    with _REG_LOCK:
        if series not in _ENGINES:
            _ENGINES[series] = GoldenEngine(series, **kw)
        return _ENGINES[series]


def compute_sized_norms(verbose=False) -> dict:
    """Recompute SIZED_NORMS the way lab3 does (lab3._sized_norms on the search window). Slow (loads every
    coin's backtest panel); run under `nice`. Used once to fill SIZED_NORMS and by the slow test."""
    lab3.G["quick"] = 0
    if not lab3.G["search"]:
        lab3.load(verbose=verbose)
    out = {}
    for rid in SIZED_NORMS:
        r = RULES[rid]
        out[rid] = list(lab3._sized_norms({"family": "sized", "params": r["params"]}, r["scope"]).values())[0]
    return out
