"""Lab 5: execution-level variants of the two best lab3 rules (Kalshi 15-minute crypto up/down).

    nice -n 19 python -m kalshi15m lab5 download          # fresh markets after the on-disk data (once, gently)
    nice -n 19 python -m kalshi15m lab5 run [WORKERS]     # search + walk-forward + holdout + archive + fresh
                                                          #   -> data/lab/lab5_results.json

lab3 found that the best all-coin rules are the live fair-value signal with (a) Kelly-sized stakes
("sized:ALL") and (b) an early exit once the bid reaches fair value ("scalp:ALL"); the combination
("sized_exit:ALL", golden_live.EXTRA) made $8,034 at t 6.95 on lab3's locked 15-day holdout. lab5 asks
whether HOW a signal is traded (sizing, exits, re-entry, maker legs, timing, portfolio caps) or WHICH
lab3 entry it is applied to can do clearly better.

Protocol (same spirit as lab3, everything fixed before any holdout number is computed):
 1. Same data, same calendar cut, same search window / 5 folds / holdout / archive as lab3 (lab3.load).
 2. Each idea is a FAMILY = an entry rule (a lab3 family with that family's lab3-tuned ALL-coin params,
    or a small grid) x an execution grid. Only the all-coin (ALL) scope is searched: nothing per coin
    can reach the $8,000 bar.
 3. Walk-forward on the 5 search folds exactly like lab3.walk (best P&L on earlier folds traded on the
    next). Shortlist = lab3's (WF P&L > 0, t >= 1.5, >= 50 trades, >= half the folds positive) AND
    walk-forward t >= the walk-forward t of sized_exit:ALL's own family run through the same machinery
    (a candidate has to look at least as good as the bar out of sample before it may touch the holdout).
    At most MAX_HOLDOUT candidates (best WF t first) go to the holdout.
 4. Final exam: tune on the whole search window, freeze, run ONCE on the holdout, one minute late, on the
    archive and on fresh data downloaded after the holdout (data/kalshi15m/lab5/).
 5. Strict bar = one-sided Bonferroni at 5% over EVERY holdout test ever run on lab3's holdout:
    lab3's 112 + the combo test (1) + lab5's own holdout tests.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import backtest as B
from . import data as D
from . import lab3
from .lab3 import G, MIN, STAKE, N_FOLDS

OUT = D.DATA_DIR.parent / "lab" / "lab5_results.json"
FRESH = D.DATA_DIR / "lab5"
COINS = list(D.SERIES)
PRIOR_HOLDOUT_TESTS = 112 + 1          # lab3's candidates + the combo test (scratchpad combo.py, Nov 3)
MAX_HOLDOUT = 12
MAKER = B.MAKER_RATE
TAKER = B.TAKER_RATE
np.seterr(all="ignore")


# =========================================================================== fresh data (download once)
def _kalshi_get(url, params, gap=0.6):
    """<= ~1.7 requests/s (the bots share the IP); D._get backs off on 429/5xx."""
    time.sleep(gap)
    return D._get(url, params)


def download(series_list=None, days=4):
    """Settled markets opening after each coin's last market in data/kalshi15m (= after lab3's holdout),
    their 1-minute candles, and Coinbase spot (on-disk spot + new bars, so features have full history)."""
    FRESH.mkdir(parents=True, exist_ok=True)
    for series in series_list or COINS:
        if (FRESH / f"{series}_markets.csv").exists():
            print(f"{series}: cached")
            continue
        last = int(pd.read_csv(D.DATA_DIR / f"{series}_markets.csv", usecols=["open_ts"]).open_ts.max())
        now = int(time.time())
        rows, cursor = [], None
        params = {"series_ticker": series, "status": "settled", "limit": 1000, "min_close_ts": now - days * 86400}
        while True:
            if cursor:
                params["cursor"] = cursor
            d = _kalshi_get(f"{D.KALSHI}/markets", params)
            rows += [r for r in map(D._market_row, d.get("markets", [])) if r]
            cursor = d.get("cursor")
            if not cursor or not d.get("markets"):
                break
        mk = pd.DataFrame(rows).drop_duplicates("ticker").sort_values("open_ts")
        mk = mk[mk.open_ts > last].reset_index(drop=True)
        if mk.empty:
            print(f"{series}: no new markets")
            continue
        crow = []
        for chunk in D._chunks(mk):
            d = _kalshi_get(f"{D.KALSHI}/markets/candlesticks",
                            {"market_tickers": ",".join(m.ticker for m in chunk),
                             "start_ts": min(m.open_ts for m in chunk) - 60,
                             "end_ts": max(m.close_ts for m in chunk) + 60, "period_interval": 1})
            for m in d.get("markets", []):
                tk = m.get("market_ticker") or m.get("ticker")
                crow += [D._candle_row(tk, c) for c in m.get("candlesticks", [])]
        cd = pd.DataFrame(crow)
        old = pd.read_csv(D.DATA_DIR / f"{series}_spot.csv")
        s0 = int(old.ts.max()) + 60
        new = D.fetch_spot(D.SERIES[series], s0, int(mk.close_ts.max()) + 120)
        sp = pd.concat([old, new], ignore_index=True).drop_duplicates("ts").sort_values("ts")
        mk.to_csv(FRESH / f"{series}_markets.csv", index=False)
        cd.to_csv(FRESH / f"{series}_candles.csv", index=False)
        sp.to_csv(FRESH / f"{series}_spot.csv", index=False)
        print(f"{series}: {len(mk)} fresh markets {pd.to_datetime(mk.open_ts.min(), unit='s')} .. "
              f"{pd.to_datetime(mk.open_ts.max(), unit='s')}, {len(cd)} candles, {len(new)} new spot bars", flush=True)
