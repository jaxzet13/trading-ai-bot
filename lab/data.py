"""Market data for the lab: HistData.com 1-minute bars (bid, fixed EST timestamps), stored as dense day x minute matrices.

    python -m lab.data download            # fetch yearly/monthly zips into data/histdata/ (resumable)
    python -m lab.data build               # parse zips into data/lab/<SYMBOL>.npz

A matrix row is one New York calendar day; a column is one minute from 00:00 to 16:59 New York time (1020 columns).
Missing minutes are forward-filled as flat bars. HistData has no volume.
"""
from __future__ import annotations

import io
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "histdata"
OUT = ROOT / "data" / "lab"
M = 1020                      # minutes per day kept: 00:00 .. 16:59 New York
YEARS = range(2016, 2027)


@dataclass(frozen=True)
class Instrument:
    name: str            # our name
    pair: str            # HistData pair code
    cost: float          # round-trip cost in price units (spread + commission + slippage), conservative
    point_value: float   # $ per 1.0 price unit for one MICRO futures contract (the sizing granularity)
    micro: str           # micro futures symbol
    max_micros_50k: int  # typical max position on a 50k futures prop account, in micros
    cfd_lot_value: float # $ per 1.0 price unit per 1.0 CFD lot
    cfd_leverage: float  # typical prop CFD leverage on this instrument
    sessions: tuple      # sessions worth testing: names from lab.signals.SESSIONS


INSTRUMENTS = {
    "NAS100": Instrument("NAS100", "NSXUSD", 1.5, 2.0, "MNQ", 50, 1.0, 20, ("ny",)),
    "SPX500": Instrument("SPX500", "SPXUSD", 0.5, 5.0, "MES", 50, 1.0, 20, ("ny",)),
    "XAUUSD": Instrument("XAUUSD", "XAUUSD", 0.40, 10.0, "MGC", 50, 100.0, 20, ("ny", "london")),
    "WTI": Instrument("WTI", "WTIUSD", 0.04, 100.0, "MCL", 50, 1000.0, 10, ("ny",)),
    "DAX": Instrument("DAX", "GRXEUR", 2.0, 1.1, "FDXS", 50, 1.1, 20, ("london", "ny")),
    "UK100": Instrument("UK100", "UKXGBP", 1.5, 1.25, "-", 50, 1.25, 20, ("london",)),
    "EU50": Instrument("EU50", "ETXEUR", 2.0, 1.1, "-", 50, 1.1, 20, ("london",)),
    "EURUSD": Instrument("EURUSD", "EURUSD", 0.00010, 12500.0, "M6E", 50, 100000.0, 50, ("london", "ny")),
    "GBPUSD": Instrument("GBPUSD", "GBPUSD", 0.00014, 6250.0, "M6B", 50, 100000.0, 50, ("london", "ny")),
    "USDJPY": Instrument("USDJPY", "USDJPY", 0.013, 650.0, "MJY", 50, 650.0, 50, ("london", "ny")),
}


def _fetch(session: requests.Session, pair: str, year: int, month: int | None) -> bytes | None:
    tag = f"{year}" if month is None else f"{year}/{month}"
    url = f"https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair.lower()}/{tag}"
    for attempt in range(4):
        try:
            r = session.get(url, timeout=90)
            form = dict(re.findall(r'name="(tk|date|datemonth|platform|timeframe|fxpair)"[^>]*value="([^"]*)"', r.text))
            if r.status_code != 200 or "tk" not in form:
                return None
            z = session.post("https://www.histdata.com/get.php", data=form, headers={"Referer": url}, timeout=300)
            if z.status_code == 200 and z.content[:2] == b"PK":
                return z.content
        except requests.RequestException:
            pass
        time.sleep(3 * (attempt + 1))
    return None


def download(names: list[str] | None = None) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (research)"
    now = pd.Timestamp.now(tz="UTC")
    for name in names or list(INSTRUMENTS):
        ins = INSTRUMENTS[name]
        for y in YEARS:
            if y < now.year:
                jobs = [(y, None)]
            else:
                jobs = [(y, m) for m in range(1, now.month + 1)]
            for (yy, mm) in jobs:
                p = RAW / (f"{ins.pair}_{yy}.zip" if mm is None else f"{ins.pair}_{yy}_{mm:02d}.zip")
                if p.exists():
                    continue
                b = _fetch(s, ins.pair, yy, mm)
                if b is None:
                    print(f"  {name} {yy}{'' if mm is None else f'-{mm:02d}'}: not available", flush=True)
                    continue
                p.write_bytes(b)
                print(f"  {name} {yy}{'' if mm is None else f'-{mm:02d}'}: {len(b) / 1e6:.1f} MB", flush=True)
                time.sleep(1.0)


def _read_zip(p: Path) -> pd.DataFrame:
    zf = zipfile.ZipFile(io.BytesIO(p.read_bytes()))
    name = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
    df = pd.read_csv(io.BytesIO(zf.read(name)), sep=";", header=None, names=["ts", "o", "h", "l", "c", "v"],
                     dtype={"ts": str, "o": "float64", "h": "float64", "l": "float64", "c": "float64"})
    df["raw"] = pd.to_datetime(df.ts, format="%Y%m%d %H%M%S")
    return df[["raw", "o", "h", "l", "c"]]


def detect_clock(df: pd.DataFrame) -> str:
    """HistData documents its stamps as EST without daylight saving, but some series are on the New York wall clock.
    Compare the intraday volatility profile (06:00-12:00 raw time) of summer and winter: if the profiles line up
    unshifted, the stamps follow New York local time; if summer is one hour early, they are fixed EST."""
    rng = (df.h - df.l) / df.c
    minute = df.raw.dt.hour * 60 + df.raw.dt.minute
    month = df.raw.dt.month
    prof = lambda mask: rng[mask].groupby(minute[mask]).mean().reindex(range(300, 780)).fillna(0).to_numpy()
    summer, winter = prof(month.isin([5, 6, 7, 8, 9])), prof(month.isin([12, 1, 2]))
    summer, winter = summer / summer.mean(), winter / winter.mean()
    c_local = np.corrcoef(summer[60:420], winter[60:420])[0, 1]
    c_est = np.corrcoef(summer[0:360], winter[60:420])[0, 1]        # summer events one hour earlier on a fixed-EST clock
    return "local" if c_local >= c_est else "est"


def to_ny(df: pd.DataFrame, clock: str) -> pd.DataFrame:
    if clock == "local":
        t = df.raw.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    else:
        t = (df.raw + pd.Timedelta(hours=5)).dt.tz_localize("UTC").dt.tz_convert("America/New_York")
    out = df.assign(time=t).dropna(subset=["time"])
    return out[["time", "o", "h", "l", "c"]]


def _append_recent(name: str, df: pd.DataFrame) -> pd.DataFrame:
    """HistData lags by days to weeks. For NAS100, append newer days from the Dukascopy cache (nyopen.data) when it has them."""
    if name != "NAS100":
        return df
    try:
        from nyopen import data as ND
        m1 = ND.build_m1(verbose=False)
    except Exception:
        return df
    t = pd.to_datetime(m1["time"], utc=True).dt.tz_convert("America/New_York")
    last = df.time.max().normalize() + pd.Timedelta(days=1)
    m = (t >= last).to_numpy()
    if not m.any():
        return df
    cols = {c: m1[c].to_numpy()[m] for c in ("open", "high", "low", "close")}
    extra = pd.DataFrame({"time": t[m].to_numpy(), "o": cols["open"], "h": cols["high"], "l": cols["low"], "c": cols["close"]})
    extra["time"] = pd.to_datetime(extra["time"], utc=True).dt.tz_convert("America/New_York")
    return pd.concat([df, extra], ignore_index=True)


def build(names: list[str] | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names or list(INSTRUMENTS):
        ins = INSTRUMENTS[name]
        files = sorted(RAW.glob(f"{ins.pair}_*.zip"))
        if not files:
            print(f"{name}: no raw files")
            continue
        raw = pd.concat([_read_zip(p) for p in files], ignore_index=True).drop_duplicates("raw").sort_values("raw")
        clock = detect_clock(raw)
        df = to_ny(raw, clock)
        df = _append_recent(name, df)
        minute = (df.time.dt.hour * 60 + df.time.dt.minute).to_numpy()
        keep = minute < M
        df, minute = df[keep], minute[keep]
        day = df.time.dt.normalize().dt.tz_localize(None).to_numpy().astype("datetime64[D]")
        wd = df.time.dt.weekday.to_numpy()
        ok = wd < 5
        df, minute, day = df[ok], minute[ok], day[ok]
        days, di = np.unique(day, return_inverse=True)
        D = len(days)
        O = np.full((D, M), np.nan, np.float32); H = O.copy(); L = O.copy(); C = O.copy()
        O[di, minute] = df.o.to_numpy(np.float32); H[di, minute] = df.h.to_numpy(np.float32)
        L[di, minute] = df.l.to_numpy(np.float32); C[di, minute] = df.c.to_numpy(np.float32)
        valid = ~np.isnan(C)
        # keep days with a reasonably complete 09:30-16:00 window (or 03:00-11:00 for London-only instruments)
        w0, w1 = (180, 660) if ins.sessions[0] == "london" else (570, 960)
        good = valid[:, w0:w1].mean(axis=1) > 0.8
        days, O, H, L, C, valid = days[good], O[good], H[good], L[good], C[good], valid[good]
        # forward-fill missing minutes inside each day as flat bars; leading gaps take the first print
        for d in range(len(days)):
            c = C[d]
            idx = np.where(valid[d], np.arange(M), -1)
            np.maximum.accumulate(idx, out=idx)
            first = np.argmax(valid[d])
            idx[idx < 0] = first
            filled = c[idx]
            miss = ~valid[d]
            O[d, miss] = filled[miss]; H[d, miss] = filled[miss]; L[d, miss] = filled[miss]; C[d, miss] = filled[miss]
        np.savez_compressed(OUT / f"{name}.npz", days=days, O=O, H=H, L=L, C=C, valid=valid)
        print(f"{name}: {len(days)} days {days[0]} .. {days[-1]}, coverage {valid.mean() * 100:.0f}%, clock={clock}", flush=True)


_CACHE: dict = {}


def load(name: str) -> dict:
    if name not in _CACHE:
        z = np.load(OUT / f"{name}.npz")
        _CACHE[name] = {k: z[k] for k in z.files}
    return _CACHE[name]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "download"
    names = sys.argv[2:] or None
    if cmd == "download":
        download(names)
    elif cmd == "build":
        build(names)
