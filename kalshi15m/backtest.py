"""Event-driven backtester for Kalshi 15-minute up/down markets.

For each market we build a 15-row "panel" (one row per minute after open) with
what a bot would have known at that moment:
    minute, yes_bid, yes_ask, spot, strike, realized vol, prior-window return ...
A strategy looks at the panel and returns at most one order per market:
    ("yes" | "no", minute, max_price)
Fills are taken at the quoted ask at that minute (taker), Kalshi's quadratic
taker fee is charged, and the contract settles at $1 / $0.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .data import load


def kalshi_fee(price: float, contracts: int = 1, rate: float = 0.07) -> float:
    """Kalshi taker fee: ceil_to_cent(rate * C * P * (1-P))."""
    return math.ceil(rate * contracts * price * (1 - price) * 100 - 1e-9) / 100


# --------------------------------------------------------------------------- panel
def build_panel(series: str) -> pd.DataFrame:
    mk, cd, sp = load(series)
    sp = sp.sort_values("ts")
    spot = sp.set_index("ts")["close"]
    logret = np.log(spot).diff()
    # rolling realised vol of 1-min log returns over trailing 60 min
    vol60 = logret.rolling(60, min_periods=30).std()

    rows = []
    cd = cd.sort_values(["ticker", "ts"])
    groups = dict(tuple(cd.groupby("ticker")))
    for m in mk.itertuples():
        g = groups.get(m.ticker)
        if g is None:
            continue
        g = g.set_index("ts")
        prev_open, prev_close = m.open_ts - 900, m.open_ts
        p0 = spot.get(prev_open)
        p1 = spot.get(prev_close)
        prev_ret = (p1 / p0 - 1) if (p0 and p1) else np.nan
        for k in range(1, 15):  # decision at end of minute k (14 = last full minute)
            t = m.open_ts + 60 * k
            q = g.loc[t] if t in g.index else None
            # Coinbase candle ts is the minute START; close of bar starting t-60 = price at t
            s = spot.get(t - 60)
            v = vol60.get(t - 60)
            rows.append({
                "ticker": m.ticker, "series": series, "open_ts": m.open_ts, "minute": k,
                "strike": m.strike, "result": m.result,
                "yes_bid": None if q is None else q.yes_bid,
                "yes_ask": None if q is None else q.yes_ask,
                "spot": s, "vol1m": v, "prev_ret": prev_ret,
                "ret_from_open": (s / spot.get(m.open_ts - 60) - 1) if (s and spot.get(m.open_ts - 60)) else np.nan,
            })
    df = pd.DataFrame(rows)
    # drop empty-book quotes
    bad = (df.yes_bid <= 0) | (df.yes_ask >= 1) | df.yes_ask.isna() | df.yes_bid.isna()
    df.loc[bad, ["yes_bid", "yes_ask"]] = np.nan
    df["no_ask"] = 1 - df.yes_bid
    return df


FIELDS = ("yes_ask", "no_ask", "yes_bid", "spot", "strike", "vol1m", "prev_ret", "ret_from_open")


class Panel:
    """Market x minute arrays (shape: markets x 14) built from the long panel."""

    def __init__(self, df: pd.DataFrame):
        df = df.sort_values(["open_ts", "minute"])
        meta = df.groupby("ticker", sort=False).first()
        self.ticker = meta.index.to_numpy()
        self.open_ts = meta.open_ts.to_numpy()
        self.result = meta.result.to_numpy()
        self.series = meta.series.to_numpy()
        self.P = {}
        for f in FIELDS:
            w = df.pivot(index="ticker", columns="minute", values=f)
            self.P[f] = w.reindex(index=self.ticker, columns=range(1, 15)).to_numpy(float)
        from .strategies import model_prob
        self.P["p_model"] = model_prob(self.P)

    def __len__(self):
        return len(self.ticker)

    def subset(self, mask):
        new = object.__new__(Panel)
        new.ticker, new.open_ts, new.result, new.series = (
            a[mask] for a in (self.ticker, self.open_ts, self.result, self.series))
        new.P = {k: v[mask] for k, v in self.P.items()}
        return new


_fee_vec = np.vectorize(kalshi_fee, otypes=[float])
_COLS = ["ticker", "series", "ts", "side", "minute", "price", "contracts", "fee", "cost", "win", "pnl", "p_model"]


def run(panel: Panel, strategy, stake: float = 10.0, **params) -> pd.DataFrame:
    """Run a strategy. stake = dollars per trade (contracts = floor(stake / price))."""
    side, minute = strategy(panel.P, **params)
    idx = np.nonzero(side)[0]
    if len(idx) == 0:
        return pd.DataFrame(columns=_COLS)
    j = minute[idx] - 1
    yes = side[idx] == 1
    price = np.where(yes, panel.P["yes_ask"][idx, j], panel.P["no_ask"][idx, j])
    good = np.isfinite(price) & (price > 0) & (price < 1)
    idx, j, yes, price = idx[good], j[good], yes[good], price[good]
    if len(idx) == 0:
        return pd.DataFrame(columns=_COLS)
    n = np.maximum(1, np.floor(stake / price + 1e-9)).astype(int)
    fee = _fee_vec(price, n)
    win = (panel.result[idx] == 1) == yes
    pnl = n * (win.astype(float) - price) - fee
    return pd.DataFrame({
        "ticker": panel.ticker[idx], "series": panel.series[idx], "ts": panel.open_ts[idx] + 60 * (j + 1),
        "side": np.where(yes, "yes", "no"), "minute": j + 1, "price": price.round(4), "contracts": n,
        "fee": fee, "cost": n * price + fee, "win": win, "pnl": pnl.round(4),
        "p_model": panel.P["p_model"][idx, j],
    })


def metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0, "t_stat": 0, "win_rate": 0, "pnl": 0, "roi": 0, "sharpe": 0, "max_dd": 0, "avg_price": 0, "fees": 0}
    eq = trades.pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    daily = trades.groupby(trades.ts // 86400).pnl.sum()
    sharpe = daily.mean() / daily.std() * math.sqrt(365) if len(daily) > 2 and daily.std() > 0 else 0
    sd = trades.pnl.std()
    t_stat = trades.pnl.mean() / (sd / math.sqrt(len(trades))) if len(trades) > 1 and sd > 0 else 0
    return {"trades": int(len(trades)), "t_stat": round(float(t_stat), 2), "win_rate": round(float(trades.win.mean()), 4),
            "pnl": round(float(trades.pnl.sum()), 2), "roi": round(float(trades.pnl.sum() / trades.cost.sum()), 4),
            "sharpe": round(float(sharpe), 2), "max_dd": round(float(dd), 2),
            "avg_price": round(float(trades.price.mean()), 3), "fees": round(float(trades.fee.sum()), 2)}
