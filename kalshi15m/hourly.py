"""Kalshi HOURLY crypto "directional" markets (KXBTCD, KXETHD, ...): download, backtest, holdout.

    python -m kalshi15m hourly [--series KXBTCD KXETHD ...] [--days 45] [--skip-download]

Each hourly event is a ladder of "above strike K at the top of the hour" markets. YES pays $1 if the
60-second average of the CF Benchmarks index before close is above the strike.

1. Download (resumable, cached in data/kalshi15m/hourly/): every settled market of the last `days`,
   Coinbase 1-minute spot, and 1-minute candles for the 4 strikes nearest spot at the start of the
   hour (only for events where at least one of those 4 traded).
2. Panel: one row per (event, strike), columns = minutes 1..59 after the hour started; column j is
   the state at the END of minute j+1 (quotes from the candle ending then, spot = close of the
   Coinbase bar that started a minute earlier).
3. Strategies x {one trade per strike, one trade per event} x {taker, maker}; same fill rules and
   fees as backtest.run.
4. The last HOLDOUT_DAYS are locked. Walk-forward on the rest (per coin and pooled), shortlist,
   tune on the whole search period, freeze, run once on the holdout.
"""
from __future__ import annotations

import itertools
import json
import math
import time
from multiprocessing import Pool
from statistics import NormalDist

import numpy as np
import pandas as pd

from .backtest import MAKER_RATE, TAKER_RATE, _fees, merge_diag, metrics
from .data import DATA_DIR, KALSHI, _Rate, _get, _ts, _candle_row, fetch_spot

HDIR = DATA_DIR / "hourly"
OUT = DATA_DIR.parent / "lab"
SERIES = {"KXBTCD": "BTC-USD", "KXETHD": "ETH-USD", "KXSOLD": "SOL-USD", "KXXRPD": "XRP-USD",
          "KXHYPED": "HYPE-USD", "KXBNBD": "BNB-USD", "KXDOGED": "DOGE-USD"}
M = 59                       # minutes per panel row
MIN = np.arange(1, M + 1)
N_STRIKES = 4
HOLDOUT_DAYS = 12
N_FOLDS = 5                  # 5 time segments -> 4 out-of-sample test folds
MIN_TRADES = 30
T_SHORTLIST = 1.5
STAKE = 10.0
EXECUTIONS = ("taker", "maker")

_lim = _Rate(4.0)


def _kget(path, params):
    _lim.wait()
    return _get(f"{KALSHI}{path}", params)


# =========================================================================== download
def _mrow(m):
    if m.get("result") not in ("yes", "no") or m.get("floor_strike") is None:
        return None
    return {"ticker": m["ticker"], "event": m.get("event_ticker") or m["ticker"].rsplit("-", 1)[0],
            "open_ts": _ts(m["open_time"]), "close_ts": _ts(m["close_time"]),
            "strike": float(str(m["floor_strike"]).replace(",", "")),
            "strike_type": m.get("strike_type"),
            "result": 1 if m["result"] == "yes" else 0,
            "volume": float(m.get("volume_fp") or m.get("volume") or 0)}


def _event_tickers(series: str, days: int):
    """Hourly event tickers are labelled by the closing hour in New York time: KXBTCD-26NOV0114."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    now = int(time.time()) // 3600 * 3600
    out = []
    for t in range(now - days * 86400, now, 3600):
        d = datetime.fromtimestamp(t, timezone.utc).astimezone(ny)
        out.append(f"{series}-{d:%y}{d.strftime('%b').upper()}{d:%d%H}")
    return out


def fetch_hourly_markets(series: str, days: int) -> pd.DataFrame:
    """One request per hourly event (paging the whole series is ~12 s per 1000 markets; per event
    is ~0.3 s for the full ladder). Resumable via a part file."""
    from concurrent.futures import ThreadPoolExecutor
    part, done_p = HDIR / f"{series}_markets.part.csv", HDIR / f"{series}_mdone.txt"
    done = set(done_p.read_text().split()) if done_p.exists() else set()
    todo = [e for e in _event_tickers(series, days) if e not in done]
    print(f"  {series}: {len(done)} event listings cached, {len(todo)} to fetch")

    def one(ev):
        d = _kget("/markets", {"event_ticker": ev, "limit": 1000})
        return [r for r in map(_mrow, d.get("markets", [])) if r]

    with ThreadPoolExecutor(8) as ex:
        for i in range(0, len(todo), 100):
            chunk = todo[i:i + 100]
            rows = [r for rs in ex.map(one, chunk) for r in rs]
            if rows:
                pd.DataFrame(rows).to_csv(part, mode="a", header=not part.exists(), index=False)
            with open(done_p, "a") as f:
                f.write("\n".join(chunk) + "\n")
            print(f"  {series} event listings {min(i + 100, len(todo))}/{len(todo)}", flush=True)
    if not part.exists():
        return pd.DataFrame()
    return pd.read_csv(part).drop_duplicates("ticker").reset_index(drop=True)


def _spot_series(sp: pd.DataFrame) -> pd.Series:
    s = sp.drop_duplicates("ts").set_index("ts")["close"].sort_index()
    return s.reindex(np.arange(s.index.min(), s.index.max() + 60, 60)).ffill()


def select(mk: pd.DataFrame, spot: pd.Series) -> pd.DataFrame:
    """Hourly events only; 4 strikes nearest spot at the start of the hour; events with volume."""
    mk = mk[(mk.strike_type == "greater") & (mk.close_ts % 3600 == 0)].copy()
    mk["t0"] = mk.close_ts - 3600
    mk["s0"] = spot.reindex(mk.t0 - 60).to_numpy()  # Coinbase bar ts = minute start
    mk = mk[np.isfinite(mk.s0)]
    mk["dist"] = (mk.strike - mk.s0).abs()
    mk = mk.sort_values(["event", "dist"]).groupby("event", sort=False).head(N_STRIKES)
    live = mk.groupby("event").volume.transform("max") > 0
    return mk[live].sort_values(["close_ts", "strike"]).reset_index(drop=True)


def fetch_hourly_candles(series: str, sel: pd.DataFrame, part, done_path):
    done = set(done_path.read_text().split()) if done_path.exists() else set()
    evs = sel.groupby("event", sort=False)
    todo = [e for e in sel.event.unique() if e not in done]
    print(f"  {series}: {len(done)} events cached, {len(todo)} to fetch")
    groups, cur = [], []
    for e in todo:
        trial = cur + [e]
        g = pd.concat([evs.get_group(x) for x in trial])
        span = (g.close_ts.max() - g.t0.min()) / 60 + 4
        if cur and (len(g) > 24 or len(g) * span > 7500):
            groups.append(cur)
            trial = [e]
        cur = trial
    if cur:
        groups.append(cur)
    t_start = time.time()
    for i, grp in enumerate(groups):
        g = pd.concat([evs.get_group(x) for x in grp])
        d = _kget("/markets/candlesticks", {"market_tickers": ",".join(g.ticker),
                                            "start_ts": int(g.t0.min()) - 60, "end_ts": int(g.close_ts.max()) + 60,
                                            "period_interval": 1})
        rows = []
        for m in d.get("markets", []):
            tk = m.get("market_ticker") or m.get("ticker")
            rows += [_candle_row(tk, c) for c in m.get("candlesticks", [])]
        if rows:
            pd.DataFrame(rows).to_csv(part, mode="a", header=not part.exists(), index=False)
        with open(done_path, "a") as f:
            f.write("\n".join(grp) + "\n")
        if (i + 1) % 20 == 0 or i + 1 == len(groups):
            el = time.time() - t_start
            print(f"  {series} candle requests {i + 1}/{len(groups)} ({el:.0f}s)", flush=True)


def download(series_list, days: int = 45):
    HDIR.mkdir(parents=True, exist_ok=True)
    for s in series_list:
        product = SERIES[s]
        mpath, spath = HDIR / f"{s}_markets.csv", HDIR / f"{s}_spot.csv"
        if mpath.exists():
            mk = pd.read_csv(mpath)
            print(f"{s}: {len(mk)} markets cached")
        else:
            print(f"{s}: fetching settled markets ...")
            mk = fetch_hourly_markets(s, days)
            if mk.empty:
                print(f"{s}: no markets, skipping")
                continue
            mk.to_csv(mpath, index=False)
        if not spath.exists():
            print(f"{s}: fetching Coinbase {product} spot ...")
            try:
                sp = fetch_spot(product, int(mk.close_ts.min()) - 3600 - 5 * 3600, int(mk.close_ts.max()) + 120)
            except Exception as e:  # noqa: BLE001
                print(f"{s}: spot download failed ({e}), skipping")
                continue
            sp.to_csv(spath, index=False)
        sp = pd.read_csv(spath)
        if sp.empty:
            print(f"{s}: no spot data, skipping")
            continue
        sel = select(mk, _spot_series(sp))
        sel.to_csv(HDIR / f"{s}_selected.csv", index=False)
        n_ev = mk[(mk.close_ts % 3600 == 0)].event.nunique()
        print(f"{s}: {n_ev} hourly events, {sel.event.nunique()} with a traded near-money strike "
              f"-> {len(sel)} markets")
        fetch_hourly_candles(s, sel, HDIR / f"{s}_candles.part.csv", HDIR / f"{s}_done.txt")


# =========================================================================== panel
def ndtr(z):
    """Normal CDF, Abramowitz-Stegun 7.1.26 (|err| < 1.5e-7), vectorised, NaN-safe."""
    z = np.asarray(z, float)
    x = np.abs(z) / math.sqrt(2)
    t = 1 / (1 + 0.3275911 * x)
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return 0.5 * (1 + np.sign(z) * y)


FIELDS = ("yes_bid", "yes_ask", "ask_low", "bid_high", "trade_low", "trade_high", "volume")
VOLS = ("60", "240")
VMULTS = (0.8, 1.0, 1.25)


class HPanel:
    """(event, strike) x minute arrays, shape (rows, 59)."""

    def __init__(self, series: str):
        sel = pd.read_csv(HDIR / f"{series}_selected.csv")
        cd = pd.read_csv(HDIR / f"{series}_candles.part.csv").drop_duplicates(["ticker", "ts"])
        spot = _spot_series(pd.read_csv(HDIR / f"{series}_spot.csv"))
        lr = np.log(spot).diff()
        v60, v240 = lr.rolling(60, min_periods=30).std(), lr.rolling(240, min_periods=120).std()
        sel = sel[sel.ticker.isin(set(cd.ticker))].reset_index(drop=True)
        n = len(sel)
        self.ticker = sel.ticker.to_numpy()
        self.event = sel.event.to_numpy()
        self.open_ts = sel.t0.to_numpy().astype(np.int64)
        self.result = sel.result.to_numpy()
        self.series = np.full(n, series, dtype=object)
        ts = self.open_ts[:, None] + 60 * MIN[None, :]
        P = {}
        cd = cd.set_index(["ticker", "ts"]).sort_index()
        key = pd.MultiIndex.from_arrays([np.repeat(self.ticker, M), ts.ravel()])
        q = cd.reindex(key)
        for f in FIELDS:
            P[f] = np.array(q[f].to_numpy(float).reshape(n, M))
        # a minute with no candle: quotes unchanged, nothing traded
        for f, extreme in (("yes_bid", "bid_high"), ("yes_ask", "ask_low")):
            miss = np.isnan(P[f])
            P[f] = np.array(pd.DataFrame(P[f]).ffill(axis=1).to_numpy(float))
            P[extreme] = np.where(miss, P[f], P[extreme])
        bad = (P["yes_bid"] <= 0) | (P["yes_ask"] >= 1) | np.isnan(P["yes_bid"]) | np.isnan(P["yes_ask"])
        P["yes_bid"][bad] = np.nan
        P["yes_ask"][bad] = np.nan
        P["no_ask"] = 1 - P["yes_bid"]
        P["spot"] = spot.reindex(ts.ravel() - 60).to_numpy().reshape(n, M)
        P["vol60"] = v60.reindex(ts.ravel() - 60).to_numpy().reshape(n, M)
        P["vol240"] = v240.reindex(ts.ravel() - 60).to_numpy().reshape(n, M)
        P["strike"] = np.repeat(sel.strike.to_numpy()[:, None], M, axis=1)
        P["tau"] = np.repeat((60 - MIN)[None, :], n, axis=0).astype(float)
        # settlement averages the last 60 s, so the final minute only adds ~1/3 minute of variance
        tau_eff = np.maximum(60 - MIN - 2 / 3, 1 / 3)[None, :]
        with np.errstate(invalid="ignore", divide="ignore"):
            lm = np.log(P["spot"] / P["strike"])
            for v in VOLS:
                sd = P["vol" + v] * np.sqrt(tau_eff)
                P["z" + v] = lm / sd
                for k in VMULTS:
                    P[f"p{v}_{k}"] = ndtr(lm / (sd * k))
        self.P = P

    @classmethod
    def concat(cls, panels):
        new = object.__new__(cls)
        order = np.argsort(np.concatenate([p.open_ts for p in panels]), kind="stable")
        for a in ("ticker", "event", "open_ts", "result", "series"):
            setattr(new, a, np.concatenate([getattr(p, a) for p in panels])[order])
        new.P = {k: np.concatenate([p.P[k] for p in panels])[order] for k in panels[0].P}
        return new

    def __len__(self):
        return len(self.ticker)

    def subset(self, mask):
        new = object.__new__(HPanel)
        for a in ("ticker", "event", "open_ts", "result", "series"):
            setattr(new, a, getattr(self, a)[mask])
        new.P = {k: v[mask] for k, v in self.P.items()}
        return new


# =========================================================================== strategies
# Each returns (side, minute, score): side +1 YES / -1 NO / 0, minute 1..59, score = how strong
# the signal was (used to pick the single best strike per event in "@event" mode).
def _valid(px):
    return np.isfinite(px) & (px > 0) & (px < 1)


def _first(y, n, score):
    any_ = y | n
    has = any_.any(axis=1)
    j = np.argmax(any_, axis=1)
    r = np.arange(len(j))
    side = np.where(y[r, j], 1, -1) * has
    sc = np.where(has, score[r, j] if score.ndim == 2 else score, -np.inf)
    return side.astype(int), j + 1, sc


def _at(minute, y, n, score):
    side = np.where(y, 1, np.where(n, -1, 0)).astype(int)
    return side, np.full(len(side), minute), np.where(side != 0, score, -np.inf)


def fair_value(P, start=5, end=50, edge=0.08, vol="60", vol_mult=1.0, band=(0.1, 0.9)):
    """Lognormal fair value (driftless, trailing realised vol) vs the ask: buy the first side that
    is cheap by `edge` between minutes start..end, inside the price band."""
    p = P[f"p{vol}_{vol_mult}"]
    ya, na = P["yes_ask"], P["no_ask"]
    lo, hi = band
    ok = np.isfinite(p) & ((MIN >= start) & (MIN <= end))[None, :]
    with np.errstate(invalid="ignore"):
        ey, en = p - ya, (1 - p) - na
        y = ok & _valid(ya) & (ya >= lo) & (ya <= hi) & (ey >= edge)
        n = ok & _valid(na) & (na >= lo) & (na <= hi) & (en >= edge)
    return _first(y, n, np.where(y, ey, en))


def fair_value_bid(P, start=5, end=50, edge=0.05, vol="60", vol_mult=1.0, band=(0.1, 0.9)):
    """Fair value vs the BID: made for resting limit orders."""
    p = P[f"p{vol}_{vol_mult}"]
    yb, nb = P["yes_bid"], 1 - P["yes_ask"]
    lo, hi = band
    ok = np.isfinite(p) & ((MIN >= start) & (MIN <= end))[None, :]
    with np.errstate(invalid="ignore"):
        ey, en = p - yb, (1 - p) - nb
        y = ok & _valid(yb) & (yb >= lo) & (yb <= hi) & (ey >= edge)
        n = ok & _valid(nb) & (nb >= lo) & (nb <= hi) & (en >= edge)
    return _first(y, n, np.where(y, ey, en))


def late_favorite(P, minute=55, lo=0.8, hi=0.95):
    """In the final minutes buy whichever side is priced lo..hi."""
    j = minute - 1
    ya, na = P["yes_ask"][:, j], P["no_ask"][:, j]
    with np.errstate(invalid="ignore"):
        y = _valid(ya) & (ya >= lo) & (ya <= hi)
        n = ~y & _valid(na) & (na >= lo) & (na <= hi)
    return _at(minute, y, n, np.where(y, ya, na))


def longshot(P, minute=30, max_price=0.1, mode="buy"):
    """mode=buy: buy the side priced <= max_price. mode=fade: buy the OTHER side (the favourite)."""
    j = minute - 1
    ya, na = P["yes_ask"][:, j], P["no_ask"][:, j]
    with np.errstate(invalid="ignore"):
        cy = _valid(ya) & (ya <= max_price)
        cn = ~cy & _valid(na) & (na <= max_price)
    if mode == "buy":
        return _at(minute, cy, cn, -np.where(cy, ya, na))
    fy, fn = cn & _valid(ya), cy & _valid(na)  # YES is the favourite when NO is cheap
    return _at(minute, fy, fn, np.where(fy, ya, na))


def spot_lag(P, start=10, end=55, move_sd=2.0, max_price=0.85):
    """Spot is `move_sd` sd (for the time left) beyond the strike but the leader still costs <= cap."""
    z = P["z60"]
    win = ((MIN >= start) & (MIN <= end))[None, :]
    with np.errstate(invalid="ignore"):
        y = win & (z >= move_sd) & _valid(P["yes_ask"]) & (P["yes_ask"] <= max_price)
        n = win & (z <= -move_sd) & _valid(P["no_ask"]) & (P["no_ask"] <= max_price)
    return _first(y, n, np.abs(np.nan_to_num(z)))


def closing_value(P, minute=57, edge=0.1, vol_mult=1.0, band=(0.05, 0.95)):
    """Single minute near the close: buy the side the spot price says is underpriced."""
    j = minute - 1
    p = P[f"p60_{vol_mult}"][:, j]
    ya, na = P["yes_ask"][:, j], P["no_ask"][:, j]
    lo, hi = band
    with np.errstate(invalid="ignore"):
        ey, en = p - ya, (1 - p) - na
        y = np.isfinite(p) & _valid(ya) & (ya >= lo) & (ya <= hi) & (ey >= edge)
        n = ~y & np.isfinite(p) & _valid(na) & (na >= lo) & (na <= hi) & (en >= edge)
    return _at(minute, y, n, np.where(y, ey, en))


def _drop_bad(grid):
    keys = list(grid)
    out = []
    for vals in itertools.product(*(grid[k] for k in keys)):
        d = dict(zip(keys, vals))
        if d.get("start", 0) < d.get("end", 99) and d.get("lo", 0) < d.get("hi", 1):
            out.append(d)
    return out


BASE = {
    "fair_value": (fair_value, "Lognormal fair value vs the ask.",
                   {"start": [5, 20, 40], "end": [45, 57], "edge": [0.05, 0.08, 0.12, 0.16],
                    "vol": ["60", "240"], "vol_mult": [0.8, 1.0, 1.25], "band": [(0.1, 0.9), (0.25, 0.75)]}),
    "fair_value_bid": (fair_value_bid, "Lognormal fair value vs the bid (for limit orders).",
                       {"start": [5, 30], "end": [45, 57], "edge": [0.03, 0.06, 0.1],
                        "vol": ["60", "240"], "vol_mult": [0.8, 1.0, 1.25], "band": [(0.1, 0.9), (0.25, 0.75)]}),
    "late_favorite": (late_favorite, "Buy the 70-98c side in the final minutes.",
                      {"minute": [45, 50, 54, 57, 58], "lo": [0.7, 0.8, 0.9], "hi": [0.95, 0.98]}),
    "longshot": (longshot, "Buy the cheap side, or fade it by buying the favourite.",
                 {"minute": [10, 30, 45, 55], "max_price": [0.05, 0.1, 0.15, 0.25], "mode": ["buy", "fade"]}),
    "spot_lag": (spot_lag, "Spot far from strike in sd units but the leader still cheap.",
                 {"start": [10, 30], "end": [50, 58], "move_sd": [1.0, 1.5, 2.0, 3.0],
                  "max_price": [0.6, 0.75, 0.85, 0.92]}),
    "closing_value": (closing_value, "Last 1-5 minutes: spot-implied value vs the ask.",
                      {"minute": [55, 56, 57, 58, 59], "edge": [0.05, 0.1, 0.15, 0.2],
                       "vol_mult": [0.8, 1.0, 1.25], "band": [(0.05, 0.95), (0.15, 0.85)]}),
}


def _per_event(fn):
    def wrapped(P, _event=None, **kw):
        side, minute, score = fn(P, **kw)
        if _event is None:
            return side, minute, score
        s = np.where(side != 0, score, -np.inf)
        df = pd.DataFrame({"e": _event, "s": s, "i": np.arange(len(s))})
        best = df.sort_values("s", ascending=False, kind="stable").drop_duplicates("e").i.to_numpy()
        keep = np.zeros(len(s), bool)
        keep[best] = True
        return np.where(keep, side, 0), minute, score
    wrapped.per_event = True
    return wrapped


STRATEGIES = {}
for _n, (_f, _d, _g) in BASE.items():
    STRATEGIES[_n] = (_f, _d, _drop_bad(_g))
    STRATEGIES[_n + "@event"] = (_per_event(_f), _d + " One trade per event (most extreme strike).", _drop_bad(_g))


# =========================================================================== execution
_COLS = ["ticker", "series", "ts", "side", "minute", "price", "contracts", "fee", "cost", "win", "pnl"]


def run(panel: HPanel, fn, stake=STAKE, execution="taker", wait=2, improve=0.01, **params):
    """Same fill rules and fees as backtest.run, for 59-minute rows."""
    if getattr(fn, "per_event", False):
        params = dict(params, _event=panel.event)
    side, minute, _ = fn(panel.P, **params)
    idx = np.nonzero(side)[0]
    if len(idx) == 0:
        return pd.DataFrame(columns=_COLS)
    j = minute[idx] - 1
    yes = side[idx] == 1
    P = panel.P
    if execution == "taker":
        price = np.where(yes, P["yes_ask"][idx, j], P["no_ask"][idx, j])
        fill_j = j
        rate = TAKER_RATE
    else:
        bid = np.where(yes, P["yes_bid"][idx, j], 1 - P["yes_ask"][idx, j])
        ask = np.where(yes, P["yes_ask"][idx, j], P["no_ask"][idx, j])
        better = np.round(bid + improve, 4)
        alone = better < ask - 1e-9
        price = np.where(alone, better, bid)
        fill_j = np.full(len(idx), -1)
        for w in range(1, wait + 1):
            jj = np.minimum(j + w, M - 1)
            in_range = (j + w) <= M - 1
            q_yes = np.fmin(P["ask_low"][idx, jj], P["trade_low"][idx, jj])
            q_no = 1 - np.fmax(P["bid_high"][idx, jj], P["trade_high"][idx, jj])
            reach = np.where(yes, q_yes, q_no)
            hit = np.where(alone, reach <= price + 1e-9, reach < price - 1e-9)
            new = in_range & hit & (fill_j < 0) & np.isfinite(reach)
            fill_j = np.where(new, jj, fill_j)
        rate = MAKER_RATE
    valid = np.isfinite(price) & (price > 0) & (price < 1)
    good = valid & (fill_j >= 0)
    diag = {"orders": int(valid.sum()), "fills": int(good.sum())}
    idx, j, yes, price, fill_j = idx[good], j[good], yes[good], price[good], fill_j[good]
    if len(idx) == 0:
        out = pd.DataFrame(columns=_COLS)
        out.attrs["diag"] = diag
        return out
    n = np.maximum(1, np.floor(stake / price + 1e-9)).astype(int)
    fee = _fees(price, n, rate)
    win = (panel.result[idx] == 1) == yes
    pnl = n * (win.astype(float) - price) - fee
    out = pd.DataFrame({"ticker": panel.ticker[idx], "series": panel.series[idx],
                        "ts": panel.open_ts[idx] + 60 * (fill_j + 1), "side": np.where(yes, "yes", "no"),
                        "minute": j + 1, "price": price.round(4), "contracts": n, "fee": fee,
                        "cost": n * price + fee, "win": win, "pnl": pnl.round(4)})
    out.attrs["diag"] = diag
    return out


# =========================================================================== evaluation
_PANELS: dict = {}
_CUT = None


def _jsonable(p):
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}


def walk_forward(panel, fn, combos, execution):
    t0, t1 = panel.open_ts.min(), panel.open_ts.max() + 1
    edges = np.linspace(t0, t1, N_FOLDS + 1).astype(int)
    folds, oos, diags = [], [], []
    for k in range(1, N_FOLDS):
        train = panel.subset(panel.open_ts < edges[k])
        test = panel.subset((panel.open_ts >= edges[k]) & (panel.open_ts < edges[k + 1]))
        best, best_m = None, None
        for params in combos:
            m = metrics(run(train, fn, execution=execution, **params))
            if m["trades"] >= MIN_TRADES and (best_m is None or m["pnl"] > best_m["pnl"]):
                best, best_m = params, m
        if best is None:
            folds.append({"params": None, "test_pnl": 0.0, "test_trades": 0})
            continue
        tr = run(test, fn, execution=execution, **best)
        diags.append(tr.attrs.get("diag", {}))
        folds.append({"start": int(edges[k]), "end": int(edges[k + 1]), "params": _jsonable(best),
                      "train_pnl": best_m["pnl"], "test_pnl": metrics(tr)["pnl"], "test_trades": len(tr)})
        oos.append(tr)
    oos = [t for t in oos if not t.empty]
    oos = pd.concat(oos, ignore_index=True) if oos else pd.DataFrame(columns=_COLS)
    return folds, oos, merge_diag(diags)


def split(p):
    return p.subset(p.open_ts < _CUT), p.subset(p.open_ts >= _CUT)


def _scope(scope, part):
    if scope == "ALL":
        return HPanel.concat([split(p)[part] for p in _PANELS.values()])
    return split(_PANELS[scope])[part]


def _task(args):
    scope, name, ex = args
    fn, _, combos = STRATEGIES[name]
    folds, oos, diag = walk_forward(_scope(scope, 0), fn, combos, ex)
    return {"scope": scope, "strategy": name, "execution": ex, "oos": metrics(oos),
            "fold_win": round(float(np.mean([f["test_pnl"] > 0 for f in folds])), 2),
            "fill_rate": diag.get("fill_rate"), "folds": folds}


def _final(args):
    scope, name, ex = args
    fn, _, combos = STRATEGIES[name]
    search = _scope(scope, 0)
    best, best_m = None, None
    for params in combos:
        m = metrics(run(search, fn, execution=ex, **params))
        if m["trades"] >= MIN_TRADES and (best_m is None or m["pnl"] > best_m["pnl"]):
            best, best_m = params, m
    if best is None:
        return None
    tr = run(_scope(scope, 1), fn, execution=ex, **best)
    hm = metrics(tr)
    t = tr.sort_values("ts") if len(tr) else tr
    curve = t.pnl.cumsum().round(2).tolist() if len(tr) else []
    step = max(1, len(curve) // 300)
    return {"scope": scope, "strategy": name, "execution": ex, "params": _jsonable(best), "search_tuned": best_m,
            "holdout": hm, "fill_rate": merge_diag([tr.attrs.get("diag", {})]).get("fill_rate"),
            "curve": [[int(t.ts.iloc[i]), curve[i]] for i in range(0, len(curve), step)]}


def main(series=None, workers=4, days=45, skip_download=False):
    global _PANELS, _CUT
    t0 = time.time()
    series = list(series or SERIES)
    if not skip_download:
        download(series, days)
    print("building panels ...")
    for s in series:
        if (HDIR / f"{s}_candles.part.csv").exists() and (HDIR / f"{s}_selected.csv").exists():
            p = HPanel(s)
            if len(p) >= 200:
                _PANELS[s] = p
                print(f"  {s}: {len(p)} (event, strike) rows, {len(set(p.event))} events")
    _CUT = int(max(p.open_ts.max() for p in _PANELS.values()) + 3600 - HOLDOUT_DAYS * 86400)
    info = {}
    for s, p in _PANELS.items():
        a, b = split(p)
        liq = np.isfinite(p.P["yes_ask"]).mean()
        sprd = np.nanmedian(p.P["yes_ask"] - p.P["yes_bid"])
        info[s] = {"markets": len(p), "events": int(len(set(p.event))), "start": int(p.open_ts.min()),
                   "end": int(p.open_ts.max() + 3600), "holdout_start": _CUT, "holdout_markets": len(b),
                   "search_markets": len(a), "quoted_frac": round(float(liq), 3),
                   "median_spread": round(float(sprd), 3),
                   "traded_minutes_frac": round(float((np.nan_to_num(p.P["volume"]) > 0).mean()), 3)}
        print(f"  {s}: {info[s]}")
    scopes = list(_PANELS) + (["ALL"] if len(_PANELS) > 1 else [])
    tasks = [(sc, n, ex) for sc in scopes for n in STRATEGIES for ex in EXECUTIONS]
    print(f"search: {len(tasks)} walk-forwards over {len(scopes)} scopes ...")
    search = []
    with Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(_task, tasks)):
            search.append(r)
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{len(tasks)}  ({time.time() - t0:.0f}s)", flush=True)
    short = [r for r in search if r["oos"]["pnl"] > 0 and r["oos"]["t_stat"] >= T_SHORTLIST
             and r["oos"]["trades"] >= 50 and r["fold_win"] >= 0.5]
    short.sort(key=lambda r: -r["oos"]["t_stat"])
    print(f"shortlist: {len(short)} of {len(search)}")
    for r in short:
        print(f"  {r['scope']:8s} {r['strategy']:22s} {r['execution']}: search OOS ${r['oos']['pnl']} "
              f"t={r['oos']['t_stat']} trades={r['oos']['trades']} folds+={r['fold_win']}")
    with Pool(workers) as pool:
        finals = [f for f in pool.map(_final, [(r["scope"], r["strategy"], r["execution"]) for r in short]) if f]
    k = max(1, len(finals))
    t_bar = round(NormalDist().inv_cdf(1 - 0.05 / k), 2)
    for f in finals:
        h = f["holdout"]
        f["passed"] = bool(h["pnl"] > 0 and h["t_stat"] >= 2)
        f["passed_strict"] = bool(h["pnl"] > 0 and h["t_stat"] >= t_bar)
    finals.sort(key=lambda f: -f["holdout"]["t_stat"])
    res = {"generated": int(time.time()), "market": "hourly", "holdout_days": HOLDOUT_DAYS, "holdout_start": _CUT,
           "n_folds": N_FOLDS - 1, "stake": STAKE, "t_shortlist": T_SHORTLIST, "t_bar_strict": t_bar,
           "coins": info, "n_strategies": len(STRATEGIES),
           "n_combos": sum(len(c) for _, _, c in STRATEGIES.values()),
           "search": search, "finals": finals, "benchmarks": [], "runtime_s": int(time.time() - t0)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hourly_results.json").write_text(json.dumps(res, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(f"\nHOLDOUT (final exam), strict bar t >= {t_bar} for {k} tests:")
    for f in finals:
        h = f["holdout"]
        print(f"  {'PASS' if f['passed_strict'] else ('pass' if f['passed'] else 'fail')}  {f['scope']:8s} "
              f"{f['strategy']:22s} {f['execution']}: ${h['pnl']} on {h['trades']} trades, t={h['t_stat']}  {f['params']}")
    print(f"done in {time.time() - t0:.0f}s -> {OUT / 'hourly_results.json'}")
    return res
