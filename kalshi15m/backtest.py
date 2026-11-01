"""Backtester for Kalshi 15-minute up/down markets.

Each market becomes one row of a (markets x 14) panel: column j holds what a
bot knew at the END of minute j+1 after the open (quotes, spot, strike, vol...).
Strategies (see strategies.py) look at the panel and pick at most one entry per
market. Execution is simulated two ways:

  taker  buy at the quoted ask at that minute, pay Kalshi's taker fee
  maker  rest a limit order at the bid (optionally 1c better) and only count it
         as filled if, within `wait` minutes, the opposite quote reached our
         price (when we improve the bid) or traded through it (when we join it).
         Pays the maker fee. Unfilled orders are simply missed trades.

Contracts settle at $1 / $0.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .data import load

TAKER_RATE = 0.07
MAKER_RATE = 0.0175  # Kalshi's maker fee on fee-charging series; conservative if makers are free


def kalshi_fee(price: float, contracts: int = 1, rate: float = TAKER_RATE) -> float:
    """Kalshi fee: ceil_to_cent(rate * C * P * (1-P))."""
    return math.ceil(rate * contracts * price * (1 - price) * 100 - 1e-9) / 100


# --------------------------------------------------------------------------- panel
def build_panel(series: str) -> pd.DataFrame:
    """Long table: one row per (market, minute 1..14)."""
    mk, cd, sp = load(series)
    spot = sp.drop_duplicates("ts").set_index("ts")["close"].sort_index()
    # fill missing minutes so lookups by timestamp work
    spot = spot.reindex(np.arange(spot.index.min(), spot.index.max() + 60, 60)).ffill()
    lr = np.log(spot).diff()
    vol60 = lr.rolling(60, min_periods=30).std()
    vol240 = lr.rolling(240, min_periods=120).std()

    n = len(mk)
    df = pd.DataFrame({
        "ticker": np.repeat(mk.ticker.to_numpy(), 14),
        "open_ts": np.repeat(mk.open_ts.to_numpy(), 14),
        "strike": np.repeat(mk.strike.to_numpy(), 14),
        "result": np.repeat(mk.result.to_numpy(), 14),
        "minute": np.tile(np.arange(1, 15), n),
    })
    df["series"] = series
    df["ts"] = df.open_ts + 60 * df.minute
    for c in ("ask_low", "bid_high", "trade_low", "trade_high"):
        if c not in cd.columns:
            cd[c] = np.nan
    q = cd[["ticker", "ts", "yes_bid", "yes_ask", "ask_low", "bid_high", "trade_low", "trade_high", "volume"]].drop_duplicates(["ticker", "ts"])
    df = df.merge(q, on=["ticker", "ts"], how="left")
    # Coinbase bars are stamped at the minute START, so the price at time t is the close of bar t-60
    at = lambda t: spot.reindex(t - 60).to_numpy()
    df["spot"] = at(df.ts)
    df["vol1m"] = vol60.reindex(df.ts - 60).to_numpy()
    df["vol240"] = vol240.reindex(df.ts - 60).to_numpy()
    p_prev0, p_open = at(df.open_ts - 900), at(df.open_ts)
    df["prev_ret"] = p_open / p_prev0 - 1
    df["ret_from_open"] = df.spot / p_open - 1
    # empty book shows up as bid 0 / ask 1: treat as no quote
    bad = (df.yes_bid <= 0) | (df.yes_ask >= 1) | df.yes_ask.isna() | df.yes_bid.isna()
    df.loc[bad, ["yes_bid", "yes_ask"]] = np.nan
    df["no_ask"] = 1 - df.yes_bid
    return df.sort_values(["open_ts", "minute"]).reset_index(drop=True)


FIELDS = ("yes_ask", "no_ask", "yes_bid", "ask_low", "bid_high", "trade_low", "trade_high", "spot", "strike", "vol1m", "vol240",
          "prev_ret", "ret_from_open", "volume")


class Panel:
    """Market x minute arrays (shape: markets x 14)."""

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

    @classmethod
    def concat(cls, panels):
        new = object.__new__(cls)
        order = np.argsort(np.concatenate([p.open_ts for p in panels]), kind="stable")
        for a in ("ticker", "open_ts", "result", "series"):
            setattr(new, a, np.concatenate([getattr(p, a) for p in panels])[order])
        new.P = {k: np.concatenate([p.P[k] for p in panels])[order] for k in panels[0].P}
        return new

    def __len__(self):
        return len(self.ticker)

    def subset(self, mask):
        new = object.__new__(Panel)
        new.ticker, new.open_ts, new.result, new.series = (
            a[mask] for a in (self.ticker, self.open_ts, self.result, self.series))
        new.P = {k: v[mask] for k, v in self.P.items()}
        return new


_COLS = ["ticker", "series", "ts", "side", "minute", "price", "contracts", "fee", "cost", "win", "pnl", "p_model"]


def _fees(price, n, rate):
    return np.ceil(rate * n * price * (1 - price) * 100 - 1e-9) / 100


def run(panel: Panel, strategy, stake: float = 10.0, execution: str = "taker", wait: int = 2,
        improve: float = 0.01, **params) -> pd.DataFrame:
    """Run a strategy. stake = dollars per trade (contracts = floor(stake / price))."""
    side, minute = strategy(panel.P, **params)
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
        bid_yes, bid_no = P["yes_bid"][idx, j], 1 - P["yes_ask"][idx, j]
        ask_yes, ask_no = P["yes_ask"][idx, j], P["no_ask"][idx, j]
        bid = np.where(yes, bid_yes, bid_no)
        ask = np.where(yes, ask_yes, ask_no)
        # improve the bid by `improve` if that doesn't cross the spread
        better = np.round(bid + improve, 4)
        alone = better < ask - 1e-9
        price = np.where(alone, better, bid)
        fill_j = np.full(len(idx), -1)
        for w in range(1, wait + 1):
            jj = np.minimum(j + w, 13)
            in_range = (j + w) <= 13
            # YES bid fills when the YES ask comes down to it; NO bid (= selling YES at 1-p)
            # fills when the YES bid comes up to 1-p.
            # lowest price the YES side reached (quote or trade). A NO bid at q is an offer
            # to sell YES at 1-q, so for NO we look at the highest YES price, mirrored.
            q_yes = np.fmin(P["ask_low"][idx, jj], P["trade_low"][idx, jj])
            q_no = 1 - np.fmax(P["bid_high"][idx, jj], P["trade_high"][idx, jj])
            reach = np.where(yes, q_yes, q_no)
            # alone at a new best price: any print at our price fills us.
            # joining an existing queue: only a print through our price is sure to.
            hit = np.where(alone, reach <= price + 1e-9, reach < price - 1e-9)
            new = in_range & hit & (fill_j < 0) & np.isfinite(reach)
            fill_j = np.where(new, jj, fill_j)
        rate = MAKER_RATE
    valid = np.isfinite(price) & (price > 0) & (price < 1)
    good = valid & (fill_j >= 0)
    diag = {"orders": int(valid.sum()), "fills": int(good.sum())}
    if execution == "maker" and valid.any():
        sig_win = (panel.result[idx] == 1) == yes
        ask_now = np.where(yes, P["yes_ask"][idx, j], P["no_ask"][idx, j])
        diag.update({"signal_wins": int(sig_win[valid].sum()), "fill_wins": int(sig_win[good].sum()),
                     "saved": float(np.nansum((ask_now - price)[good]))})
    idx, j, yes, price, fill_j = idx[good], j[good], yes[good], price[good], fill_j[good]
    if len(idx) == 0:
        out = pd.DataFrame(columns=_COLS)
        out.attrs["diag"] = diag
        return out
    n = np.maximum(1, np.floor(stake / price + 1e-9)).astype(int)
    fee = _fees(price, n, rate)
    win = (panel.result[idx] == 1) == yes
    pnl = n * (win.astype(float) - price) - fee
    out = pd.DataFrame({
        "ticker": panel.ticker[idx], "series": panel.series[idx], "ts": panel.open_ts[idx] + 60 * (fill_j + 1),
        "side": np.where(yes, "yes", "no"), "minute": j + 1, "price": price.round(4), "contracts": n,
        "fee": fee, "cost": n * price + fee, "win": win, "pnl": pnl.round(4),
        "p_model": panel.P["p_model"][idx, j],
    })
    out.attrs["diag"] = diag
    return out


def merge_diag(ds):
    out = {}
    for d in ds:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    if out.get("orders"):
        out["fill_rate"] = round(out["fills"] / out["orders"], 4)
    if out.get("fills") and "fill_wins" in out:
        out["signal_win_rate"] = round(out["signal_wins"] / out["orders"], 4)
        out["fill_win_rate"] = round(out["fill_wins"] / out["fills"], 4)
        out["avg_saved_c"] = round(100 * out["saved"] / out["fills"], 2)
    return out


def metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0, "t_stat": 0, "win_rate": 0, "pnl": 0, "roi": 0, "sharpe": 0, "max_dd": 0,
                "avg_price": 0, "fees": 0}
    trades = trades.sort_values("ts")
    eq = trades.pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    daily = trades.groupby(trades.ts // 86400).pnl.sum()
    sharpe = daily.mean() / daily.std() * math.sqrt(365) if len(daily) > 2 and daily.std() > 0 else 0
    sd = trades.pnl.std()
    t_stat = trades.pnl.mean() / (sd / math.sqrt(len(trades))) if len(trades) > 1 and sd > 0 else 0
    return {"trades": int(len(trades)), "t_stat": round(float(t_stat), 2),
            "win_rate": round(float(trades.win.mean()), 4),
            "pnl": round(float(trades.pnl.sum()), 2), "roi": round(float(trades.pnl.sum() / trades.cost.sum()), 4),
            "sharpe": round(float(sharpe), 2), "max_dd": round(float(dd), 2),
            "avg_price": round(float(trades.price.mean()), 3), "fees": round(float(trades.fee.sum()), 2)}
