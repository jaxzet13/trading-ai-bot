"""Swap the thin coins' Coinbase candle spot files for bars rebuilt from Coinbase's trade list
(python -m kalshi15m cleanspot [--restore]).

For NEAR, HYPE, DOGE and BNB, every *_spot.csv the research uses (data/kalshi15m, archive/, lab5/, rm/) is
replaced by the trade-built bars of kalshi15m.tradebars over the same time span; the originals are kept in
data/kalshi15m/candle_spot_backup/<dir>/ (--restore puts them back). BTC, ETH, SOL, XRP and ZEC keep their
candles: their live trade stream matched the final candles exactly (2026-11-05 checks).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "kalshi15m"
BACKUP = D / "candle_spot_backup"
DIRS = ["", "archive", "lab5", "rm"]
COINS = {"KXNEAR15M": "NEAR-USD", "KXHYPE15M": "HYPE-USD", "KXDOGE15M": "DOGE-USD", "KXBNB15M": "BNB-USD"}


def swap(log=print):
    for series, prod in COINS.items():
        tb = D / "tradebars" / f"{prod}_bars.csv"
        if not tb.exists():
            raise SystemExit(f"{tb} missing: run python -m kalshi15m tradebars {prod} first")
        bars = pd.read_csv(tb).sort_values("ts")
        for sub in DIRS:
            f = D / sub / f"{series}_spot.csv"
            if not f.exists():
                continue
            bk = BACKUP / (sub or "main") / f.name
            bk.parent.mkdir(parents=True, exist_ok=True)
            if not bk.exists():
                shutil.copy2(f, bk)
            orig = pd.read_csv(bk)
            lo, hi = int(orig.ts.min()), int(orig.ts.max())
            if bars.ts.min() > lo + 3600:
                raise SystemExit(f"{prod}: trade bars start {pd.to_datetime(bars.ts.min(), unit='s')}, after "
                                 f"{f} starts ({pd.to_datetime(lo, unit='s')}); fetch further back first")
            new = bars[(bars.ts >= lo) & (bars.ts <= hi)][list(orig.columns)]
            new.to_csv(f, index=False)
            same = orig.merge(new, on="ts", suffixes=("_c", "_t"))
            diff = float((abs(same.close_c - same.close_t) > 1e-12).mean()) if len(same) else float("nan")
            log(f"{(sub or 'main'):8s} {series}: {len(orig)} candle minutes -> {len(new)} trade minutes; "
                f"closes differ in {diff:.1%} of shared minutes")


def restore(log=print):
    for sub in DIRS:
        for f in (BACKUP / (sub or "main")).glob("*_spot.csv"):
            shutil.copy2(f, D / sub / f.name)
            log(f"restored {sub or 'main'}/{f.name}")


def main(args=None):
    restore() if args and "--restore" in args else swap()


if __name__ == "__main__":
    main(sys.argv[1:])
