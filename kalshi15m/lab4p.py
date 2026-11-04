"""Lab 4P: lab4's golden hunt re-run with Pyth (Kalshi's settlement source) as the price anchor.

    nice -n 19 python -m kalshi15m lab4p probe      # what Pyth history is reachable (Hermes / Benchmarks)
    nice -n 19 python -m kalshi15m lab4p validate   # Kalshi's Pyth record vs results, chain continuity, Yahoo sign
    nice -n 19 python -m kalshi15m lab4p models     # the hunt (lab3/lab4 protocol) -> data/lab/lab4p_part_models.json
    nice -n 19 python -m kalshi15m lab4p judge      # one strict bar -> data/lab/lab4_results.json (old file kept
                                                    #   as data/lab/lab4_results_yahoo.json)
    nice -n 19 python -m kalshi15m lab4p hermes     # (needs PYTH_API_KEY) 1-minute Pyth history from Hermes

Why this exists: lab4 used Yahoo 1-minute bars; Kalshi settles FX / yields / metals / energy on Pyth, and Yahoo's
15-minute up/down sign matched Kalshi's result only 88-98% of the time.

What Pyth data is reachable (checked Nov 4 2026, see `probe`): Hermes' feed METADATA is public (feed ids below), but
every price endpoint - /v2/updates/price/{t}, /v2/updates/price/latest, the SSE stream, the v1 /api endpoints, and
Benchmarks /v1/updates/price - answers 401 "unauthorized" without an API key, for crypto feeds too. Pythnet's public
RPC blocks this IP, and no EVM chain carries on-chain pushes of these FX / commodity / rate feeds. So no 1-minute
Pyth history could be fetched.

The workaround: Kalshi itself publishes the exact Pyth print at both ends of every 15-minute window - the market's
floor_strike (Pyth at the open) and its expiration_value (Pyth at the close). That is an exact Pyth price on every
quarter hour for the whole Kalshi history (from Jul 31 for gold/silver/WTI), 100% consistent with the results. It
gives no Pyth path INSIDE a window, so the hunt has two kinds of families:
  * Pyth-exact families (no Yahoo at all): decisions use only Pyth quarter-hour prints known at the open (previous
    window moves, quarter-hour volatility, how often this hour's window ended exactly unchanged = a guaranteed YES,
    since YES means "at least the open") plus Kalshi's own quotes. These use the full Kalshi candle history from
    Sep 4 (Kalshi's live-API cutoff; older candles cost one request per market).
  * Yahoo-path families (the control fv_ref and a tie-aware variant): need an intra-window price, so they only trade
    where Yahoo 1-minute bars exist (Oct 5+), exactly as lab4 did (strike = the feed's own price at the open).
Protocol = lab4's (see lab4.py): one calendar cut (holdout = most recent 25% of the median span), 5 calendar folds,
walk-forward shortlist, tune on search only, ONE holdout run, one-minute-late check, Bonferroni over every holdout
test (lab4's crypto xmkt/range candidates are carried over and counted), beat the re-tuned fv_ref control, <= 40% of
profit from one day, $0.10/trade and $2/day economic floor, taker fees, fills at the quoted ask only.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import time
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
import requests

from . import backtest as B
from . import data_fx as F
from . import lab3 as L3
from . import lab4 as L4
from .strategies import MIN, _valid, ndtr

LAB = L4.LAB
PDIR = F.LDIR / "pyth"
PART = LAB / "lab4p_part_models.json"
VALID = LAB / "lab4p_validation.json"
PROBE = PDIR / "probe.json"
OUT = L4.OUT
YAHOO_COPY = LAB / "lab4_results_yahoo.json"
HERMES = "https://hermes.pyth.network"
ARCH_BEFORE = L4.ARCH_BEFORE

# Kalshi series -> Pyth feed named in its rules (Hermes symbol, feed id). FX: "the USD/JPY exchange rate as published
# by Pyth Network"; yields: "the 1-minute Pyth candlestick for 10-year U.S. Treasury ... US10Y"; metals / energy:
# "the 1-minute Pyth COPPER candlestick". Where Pyth lists more than one candidate (24/7 index vs market-hours feed),
# the market-hours feed is used; exact = the symbol is the only Pyth feed for that name.
PYTH = {
    "KXEURUSD15M": ("FX.EUR/USD", "a995d00bb36a63cef7fd2c287dc105fc8f3d93779f062f09551b0af3e81ec30b", "exact"),
    "KXUSDJPY15M": ("FX.USD/JPY", "ef2c98c804ba503c6a707e38be4dfbb16683775f195b091252bf24693042fd52", "exact"),
    "KXGBPUSD15M": ("FX.GBP/USD", "84c2dde9633d93d1bcad84e7dc41c9d56578b7ec52fabedc1f335d673df0a7c1", "exact"),
    "KXAUDUSD15M": ("FX.AUD/USD", "67a6f93030420c1c9e3fe37c1ab6b77966af82f995944a9fefce357a22854a80", "exact"),
    "KXUSDCAD15M": ("FX.USD/CAD", "3112b03a41c910ed446852aacf67118cb1bec67b2cd0b9a214c58cc0eaa2ecca", "exact"),
    "KX2YRRATE15M": ("InterestRate.US2Y", "7d01ec0cb9d38918cd497f97b24cb6cea5552993f5da05863886e6a2d33ee0aa", "exact"),
    "KX5YRRATE15M": ("InterestRate.US5Y", "7d220b081152db0d74a93d3ce383c61d0ec5250c6dd2b2cdb2d1e4b8919e1a6e", "exact"),
    "KX10YRRATE15M": ("InterestRate.US10Y", "9c196541230ba421baa2a499214564312a46bb47fb6b61ef63db2f70d3ce34c1", "exact"),
    "KX30YRRATE15M": ("InterestRate.US30Y", "424c69939fc52a459f6dde758d80f74a3628c0e9b48bfc142df1270c9b9131be", "exact"),
    "KXGOLD15M": ("Metal.XAU/USD", "765d2ba906dbc32ca17cc11f5310a89e9ee1f6420508c63861f2f8ba4ee34bb2", "by name (24/7 index feed also exists)"),
    "KXSILVER15M": ("Metal.XAG/USD", "f2fb02c32b055c805e7238d628e5e9dadef274376114eb1f012337cabe93871e", "by name (24/7 index feed also exists)"),
    "KXPLATINUM15M": ("Metal.XPT/USD", "398e4bbc7cbf89d6648c21e08019d878967677753b3096799595c78f805a34e5", "exact"),
    "KXPALLADIUM15M": ("Metal.XPD/USD", "80367e9664197f37d89a07a804dffd2101c479c7c4e8490501bc9d9e1e7f9021", "exact"),
    "KXCOPPER15M": ("Commodities.Index.COPPER/USD", "4073f4c331bf7920a3887536093b57c78ea535e88ac09c761e5b949221c33414", "exact"),
    "KXWTI15M": ("Commodities.Index.WTI1M/USD", "f2464139c45f26097e0173b03207c4a490dbd8bf1b72dfbf064eeb832c7c2933", "by name (constant 1-month WTI)"),
    "KXNATGAS15M": ("Commodities.Index.NATGAS/USD", "45f95717fbe158e896415d1cea33814d73e54169022a8f7bcbb815ebef92f71c", "exact"),
    "KXBRENT15M": ("Commodities.Index.BRENT/USD", "f33ce961935076ef4dc98be75cf2126046eac1bffdcd7a0fa05ccf18b746fda6", "by name (1-month Brent also exists)"),
}
SERIES = [s for g in ("FX", "RATES", "METALS", "ENERGY") for s in L4.GROUPS_ALL[g]]
SERIES = [s for s in SERIES if s in PYTH]
QUICK_FVREF = 3                  # lab4 thinned the control's grid to every 3rd config; same here (fv_ref only)

np.seterr(all="ignore")


# =========================================================================== Pyth reachability
def _hermes_session(key=None):
    s = requests.Session()
    key = key or os.environ.get("PYTH_API_KEY") or os.environ.get("PYTH_HERMES_KEY")
    if key:
        s.headers["Authorization"] = f"Bearer {key}"
        s.headers["x-api-key"] = key
    return s


def probe():
    """Record which Pyth endpoints answer from here (status codes), so the report can say what was tried."""
    PDIR.mkdir(parents=True, exist_ok=True)
    fid = PYTH["KXEURUSD15M"][1]
    t = int(time.time()) // 60 * 60 - 3 * 86400
    s = _hermes_session()
    urls = {
        "hermes_feed_metadata": f"{HERMES}/v2/price_feeds?query=EUR/USD&asset_type=fx",
        "hermes_price_at_time": f"{HERMES}/v2/updates/price/{t}?ids[]={fid}&parsed=true",
        "hermes_price_latest": f"{HERMES}/v2/updates/price/latest?ids[]={fid}&parsed=true",
        "hermes_v1_latest_price_feeds": f"{HERMES}/api/latest_price_feeds?ids[]={fid}",
        "hermes_v1_get_price_feed": f"{HERMES}/api/get_price_feed?id={fid}&publish_time={t}",
        "benchmarks_price_at_time": f"https://benchmarks.pyth.network/v1/updates/price/{t}?ids[]={fid}&parsed=true",
        "benchmarks_tradingview_history": ("https://benchmarks.pyth.network/v1/shims/tradingview/history?symbol=FX.EUR/USD"
                                           f"&resolution=1&from={t}&to={t + 3600}"),
    }
    out = {"checked": int(time.time()), "with_api_key": "Authorization" in s.headers, "endpoints": {}}
    for k, u in urls.items():
        try:
            r = s.get(u, timeout=20)
            out["endpoints"][k] = {"status": r.status_code, "body": r.text[:80]}
        except requests.RequestException as e:
            out["endpoints"][k] = {"status": None, "body": str(e)[:80]}
        print(f"  {k:32s} {out['endpoints'][k]['status']} {out['endpoints'][k]['body'][:60]!r}", flush=True)
        time.sleep(0.5)
    out["history_available"] = out["endpoints"]["hermes_price_at_time"]["status"] == 200
    PROBE.write_text(json.dumps(out, indent=1))
    return out


def hermes_history(start_ts=None, end_ts=None, rate=2.0, key=None):
    """1-minute Pyth prices for every feed in PYTH from Hermes (one request per minute, all feeds batched),
    cached per UTC day under data/kalshi15m/lab4/pyth/hermes_YYYY-MM-DD.csv. Only works with an API key
    (PYTH_API_KEY); without one Hermes answers 401. <= `rate` requests/second, exponential back-off on 429."""
    s = _hermes_session(key)
    ids = {v[1]: k for k, v in PYTH.items()}
    if start_ts is None:
        start_ts = min(int(pd.read_csv(F.LDIR / f"{x}_markets_all.csv", usecols=["open_ts"]).open_ts.min())
                       for x in PYTH if (F.LDIR / f"{x}_markets_all.csv").exists())
    end_ts = end_ts or int(time.time()) - 120
    gap, last = 1.0 / rate, 0.0
    for day in range(int(start_ts) // 86400, int(end_ts) // 86400 + 1):
        path = PDIR / f"hermes_{pd.to_datetime(day * 86400, unit='s'):%Y-%m-%d}.csv"
        done = set(pd.read_csv(path, usecols=["ts"]).ts) if path.exists() else set()
        rows = []
        for t in range(max(day * 86400, start_ts // 60 * 60), min((day + 1) * 86400, end_ts), 60):
            if t in done:
                continue
            for i in range(8):
                dt = time.time() - last
                if dt < gap:
                    time.sleep(gap - dt)
                last = time.time()
                r = s.get(f"{HERMES}/v2/updates/price/{t}", params=[("ids[]", x) for x in ids] + [("parsed", "true")],
                          timeout=30)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(min(60, 2 ** (i + 1)))
                    continue
                break
            if r.status_code == 401:
                raise RuntimeError("Hermes answered 401: set PYTH_API_KEY (Pyth's price endpoints need a key now)")
            if r.status_code == 404:                     # no update at that second (market closed)
                rows.append({"ts": t})
                continue
            r.raise_for_status()
            row = {"ts": t}
            for p in r.json().get("parsed", []):
                q = p["price"]
                row[ids.get(p["id"], p["id"])] = int(q["price"]) * 10 ** int(q["expo"])
                row[ids.get(p["id"], p["id"]) + "_pt"] = int(q["publish_time"])
            rows.append(row)
            if len(rows) >= 60:
                pd.DataFrame(rows).to_csv(path, mode="a", header=not path.exists(), index=False)
                rows = []
        if rows:
            pd.DataFrame(rows).to_csv(path, mode="a", header=not path.exists(), index=False)
        print(f"  hermes {path.name}", flush=True)


# =========================================================================== Kalshi's own Pyth record
def markets_all(series):
    mk = pd.read_csv(F.LDIR / f"{series}_markets_all.csv")
    mk = mk[(mk.close_ts - mk.open_ts) == 900].copy()
    return mk.sort_values("open_ts").reset_index(drop=True)


def quarter_prints(series):
    """Exact Pyth prints on the quarter hours from Kalshi: strike at each open, expiration value at each close."""
    mk = markets_all(series)
    a = pd.Series(mk.strike.to_numpy(float), index=mk.open_ts.to_numpy(np.int64))
    b = pd.Series(mk.settle_value.to_numpy(float), index=mk.close_ts.to_numpy(np.int64))
    q = a[np.isfinite(a)].groupby(level=0).first().combine_first(b[np.isfinite(b)].groupby(level=0).first())
    return q.sort_index()


def validate():
    """Per series: (1) Kalshi's result vs the up/down of its own Pyth prints (open = strike, close = expiration
    value), (2) chain continuity: the next window's strike equals this window's expiration value (two separate
    Pyth publications), (3) Yahoo's 15-minute sign vs Kalshi's result (what lab4 had), (4) exact ties."""
    out = {}
    for s in PYTH:
        if not (F.LDIR / f"{s}_markets_all.csv").exists():
            continue
        mk = markets_all(s)
        ok = np.isfinite(mk.strike) & np.isfinite(mk.settle_value)
        m = mk[ok]
        match = float(((m.settle_value >= m.strike) == (m.result == 1)).mean()) if len(m) else None
        nxt = m.set_index("open_ts").strike
        prv = m.set_index("close_ts").settle_value
        common = nxt.index.intersection(prv.index)
        cont = float(np.isclose(nxt.loc[common].to_numpy(), prv.loc[common].to_numpy(), rtol=0, atol=1e-9).mean())
        r = {"pyth_feed": PYTH[s][0], "pyth_feed_id": PYTH[s][1], "feed_match": PYTH[s][2],
             "markets": int(len(mk)), "markets_with_pyth_prints": int(ok.sum()),
             "first": f"{pd.to_datetime(mk.open_ts.min(), unit='s'):%Y-%m-%d %H:%M}",
             "last": f"{pd.to_datetime(mk.close_ts.max(), unit='s'):%Y-%m-%d %H:%M}",
             "span_days": round(float(mk.close_ts.max() - mk.open_ts.min()) / 86400, 1),
             "result_matches_pyth_updown": None if match is None else round(match, 5),
             "mismatches": int(((m.settle_value >= m.strike) != (m.result == 1)).sum()),
             "chain_continuity": round(cont, 5), "chain_pairs": int(len(common)),
             "tie_rate": round(float((m.settle_value == m.strike).mean()), 4)}
        sp_path = L4.spot_path(s)
        if sp_path.exists():
            sp = pd.read_csv(sp_path).drop_duplicates("ts").set_index("ts")["close"].sort_index()
            sp = sp.reindex(np.arange(sp.index.min(), sp.index.max() + 60, 60)).ffill()
            r["yahoo_sign_agreement"] = L4.fidelity(s, m, sp)
            mm = m[(m.open_ts - 60 >= sp.index.min()) & (m.close_ts - 60 <= sp.index.max())]
            r["yahoo_overlap_markets"] = int(len(mm))
        out[s] = r
        print(f"  {s:16s} {r['span_days']:5.1f}d {r['markets_with_pyth_prints']:5d} mk  result==pyth "
              f"{r['result_matches_pyth_updown']}  chain {r['chain_continuity']}  ties {r['tie_rate']}  "
              f"yahoo {r.get('yahoo_sign_agreement')}", flush=True)
    VALID.write_text(json.dumps(out, indent=1))
    return out


# =========================================================================== panel
def _candles(series):
    parts = [p for p in (F.LDIR / f"{series}_candles.part.csv", PDIR / f"{series}_candles_ext.part.csv") if p.exists()]
    if not parts:
        return pd.DataFrame(columns=["ticker", "ts"])
    cd = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
    return cd[cd.ts > 0].drop_duplicates(["ticker", "ts"])


def _et_hour(ts):
    return pd.to_datetime(np.asarray(ts, np.int64), unit="s").tz_localize("UTC").tz_convert("America/New_York").hour.to_numpy()


def pyth_features(series, open_ts):
    """Per market, known at its open (only Pyth prints at or before the open, ties only from windows that closed
    by then): previous-window log moves, quarter-hour vol, and this ET hour's trailing 14-day tie rate."""
    q = quarter_prints(series)
    grid = np.arange(q.index.min(), q.index.max() + 900, 900)
    lq = np.log(q.reindex(grid))
    r = lq.diff()
    volq = r.rolling(96, min_periods=24).std()
    at = lambda s_, t: s_.reindex(np.asarray(t, np.int64)).to_numpy()
    o = np.asarray(open_ts, np.int64)
    f = {"pq_strike": at(q, o), "pq_r1": at(lq, o) - at(lq, o - 900), "pq_r4": at(lq, o) - at(lq, o - 3600),
         "pq_volq": at(volq, o)}
    mk = markets_all(series)
    mk = mk[np.isfinite(mk.strike) & np.isfinite(mk.settle_value)]
    tie = (mk.settle_value == mk.strike).to_numpy(float)
    h_m = _et_hour(mk.open_ts)
    h_o = _et_hour(o)
    tie_h = np.full(len(o), np.nan)
    tie_all = np.full(len(o), np.nan)
    ct = mk.close_ts.to_numpy(np.int64)
    order = np.argsort(ct)
    ct_s, tie_s = ct[order], tie[order]
    cs = np.r_[0, np.cumsum(tie_s)]
    for i, t in enumerate(o):                                   # all hours, trailing 14 days
        lo, hi = np.searchsorted(ct_s, t - 14 * 86400, "left"), np.searchsorted(ct_s, t, "right")
        if hi - lo >= 50:
            tie_all[i] = (cs[hi] - cs[lo]) / (hi - lo)
    for h in np.unique(h_o):
        sel = h_m[order] == h
        cth, tih = ct_s[sel], tie_s[sel]
        csh = np.r_[0, np.cumsum(tih)]
        idx = np.nonzero(h_o == h)[0]
        lo = np.searchsorted(cth, o[idx] - 14 * 86400, "left")
        hi = np.searchsorted(cth, o[idx], "right")
        n = hi - lo
        k = csh[hi] - csh[lo]
        tie_h[idx] = (k + 8 * tie_all[idx]) / (n + 8)          # shrunk toward the all-hours rate (NaN if unknown)
    f["pq_tie_h"] = tie_h
    f["pq_tie_all"] = tie_all
    return f


def build_panel_p(series):
    """lab4's panel over the whole Kalshi candle history (Sep 4+). Yahoo columns (spot, strike = Yahoo price at the
    open, vol1m, vol240, prev_ret) are NaN where Yahoo has no data; Pyth-exact columns are added by load_p."""
    mk = markets_all(series)
    mk = mk[np.isfinite(mk.strike) & (mk.open_ts >= ARCH_BEFORE)]
    cd = _candles(series)
    mk = mk[mk.ticker.isin(set(cd.ticker))].reset_index(drop=True)
    sp_path = L4.spot_path(series)
    sp = pd.read_csv(sp_path).drop_duplicates("ts").set_index("ts")["close"].sort_index()
    lo = min(int(sp.index.min()), int(mk.open_ts.min()) - 4 * 3600)
    hi = max(int(sp.index.max()), int(mk.close_ts.max()))
    full = sp.reindex(np.arange(sp.index.min(), sp.index.max() + 60, 60)).ffill()
    spot = full.reindex(np.arange(lo - lo % 60, hi + 60, 60))       # NaN outside Yahoo's span (no ffill there)
    lr = np.log(spot).diff()
    vol60 = lr.rolling(60, min_periods=30).std()
    vol240 = lr.rolling(240, min_periods=120).std()
    at = lambda t: spot.reindex(np.asarray(t) - 60).to_numpy()
    mk["kalshi_strike"] = mk.strike
    mk["strike"] = at(mk.open_ts)                                   # lab4: the feed's own price at the open
    n = len(mk)
    df = pd.DataFrame({
        "ticker": np.repeat(mk.ticker.to_numpy(), 14), "open_ts": np.repeat(mk.open_ts.to_numpy(), 14),
        "strike": np.repeat(mk.strike.to_numpy(), 14), "result": np.repeat(mk.result.to_numpy(), 14),
        "minute": np.tile(np.arange(1, 15), n)})
    df["series"] = series
    df["ts"] = df.open_ts + 60 * df.minute
    for c in ("ask_low", "bid_high", "trade_low", "trade_high", "volume"):
        if c not in cd.columns:
            cd[c] = np.nan
    q = cd[["ticker", "ts", "yes_bid", "yes_ask", "ask_low", "bid_high", "trade_low", "trade_high", "volume"]]
    df = df.merge(q.drop_duplicates(["ticker", "ts"]), on=["ticker", "ts"], how="left")
    df["spot"] = at(df.ts)
    df["vol1m"] = vol60.reindex(df.ts - 60).to_numpy()
    df["vol240"] = vol240.reindex(df.ts - 60).to_numpy()
    p_prev0, p_open = at(df.open_ts - 900), at(df.open_ts)
    df["prev_ret"] = p_open / p_prev0 - 1
    df["ret_from_open"] = df.spot / p_open - 1
    bad = (df.yes_bid <= 0) | (df.yes_ask >= 1) | df.yes_ask.isna() | df.yes_bid.isna()
    df.loc[bad, ["yes_bid", "yes_ask"]] = np.nan
    df["no_ask"] = 1 - df.yes_bid
    df = df.sort_values(["open_ts", "minute"]).reset_index(drop=True)
    has = df.groupby("ticker").yes_ask.transform(lambda s: s.notna().any())
    return df[has].reset_index(drop=True), mk


def testable_p():
    sv = json.loads(L4.SURVEY.read_text()) if L4.SURVEY.exists() else {}
    out, why = [], {}
    for s in sum(L4.GROUPS_ALL.values(), []):
        r = sv.get(s, {})
        if not r.get("markets"):
            why[s] = "no settled markets on Kalshi"
        elif s not in PYTH:
            why[s] = "no Pyth feed mapped"
        elif r.get("span_days", 0) < L4.MIN_DAYS:
            why[s] = f"only {r.get('span_days')} days of markets (< {L4.MIN_DAYS})"
        elif r.get("median_volume", 0) < L4.MIN_MED_VOLUME:
            why[s] = f"too thin: median {r.get('median_volume')} contracts per market (< {L4.MIN_MED_VOLUME})"
        elif _candles(s).empty or not L4.spot_path(s).exists():
            why[s] = "not downloaded"
        else:
            out.append(s)
            why[s] = "testable"
    return out, why


def load_p(series_list, verbose=True):
    full, info = {}, {}
    for s in series_list:
        L3._SPOT[(s, "main")] = L3.Spot(L4.spot_path(s))
        df, mk = build_panel_p(s)
        if df.empty:
            continue
        p = B.Panel(df)
        L3.add_features(p, s, "main")
        f = pyth_features(s, p.open_ts)
        for k, v in f.items():
            p.P[k] = np.repeat(np.asarray(v, float)[:, None], 14, axis=1)
        full[s] = p
        sp = pd.read_csv(L4.spot_path(s)).drop_duplicates("ts").set_index("ts")["close"].sort_index()
        sp = sp.reindex(np.arange(sp.index.min(), sp.index.max() + 60, 60)).ffill()
        info[s] = {"mk": mk.assign(strike=mk.kalshi_strike), "sp": sp}
        if verbose:
            yh = np.isfinite(p.P["spot"][:, 0]).mean()
            print(f"  {s}: {len(p)} markets {pd.to_datetime(p.open_ts.min(), unit='s'):%m-%d}.."
                  f"{pd.to_datetime(p.open_ts.max(), unit='s'):%m-%d} (Yahoo path on {yh:.0%})", flush=True)
    return full, info


# =========================================================================== families (registered into lab3's table)
def _win(start, end):
    return ((MIN >= start) & (MIN <= end))[None, :]


@L3.family("pq_open", "Pyth open-print fair value",
           "Pyth-exact, no intra-window price. Fair value of YES at the start of the window from Pyth's own quarter-hour "
           "prints: this hour's recent rate of windows that ended exactly unchanged (an unchanged price settles YES) plus "
           "a tilt from the previous window's Pyth move. Buy in the first minutes when the ask is below that by the edge.",
           {"end": [1, 2, 3], "a": [-0.4, -0.2, 0.0, 0.2, 0.4], "lag": [1, 4], "tie": [0, 1],
            "edge": [0.02, 0.03, 0.04, 0.06, 0.08], "band": ["25-75", "10-90"]}, heat=("edge", "a"))
def f_pq_open(ctx, c):
    P = ctx.P
    z = P[f"pq_r{c['lag']}"] / (P["pq_volq"] * math.sqrt(c["lag"]))
    tie = np.nan_to_num(P["pq_tie_h"], nan=0.0) if c["tie"] else 0.0
    p = tie + (1 - tie) * ndtr(c["a"] * z)
    p = np.where(np.isfinite(P["pq_volq"]) & (P["pq_volq"] > 0), p, np.nan)
    pk = ("pq_open", c["a"], c["lag"], c["tie"])
    y, n = L3.fv_masks(ctx, p, pk, 1, c["end"], c["edge"], c["band"])
    return y, n, p


@L3.family("pq_prev", "Pyth previous-window bet",
           "Pyth-exact. At the first minute, bet with (trend) or against (reversal) the previous window's Pyth move when "
           "it was at least pz quarter-hour standard deviations, if the ask is no more than max_price.",
           {"mode": ["with", "against"], "pz": [0.5, 1.0, 1.5, 2.0, 2.5], "lag": [1, 4],
            "max_price": [0.45, 0.50, 0.53, 0.56], "end": [1, 2]}, heat=("pz", "max_price"))
def f_pq_prev(ctx, c):
    P = ctx.P
    z = P[f"pq_r{c['lag']}"] / (P["pq_volq"] * math.sqrt(c["lag"]))
    up, dn = z >= c["pz"], z <= -c["pz"]
    if c["mode"] == "against":
        up, dn = dn, up
    w = _win(1, c["end"])
    ya, na = P["yes_ask"], P["no_ask"]
    y = w & up & _valid(ya) & (ya <= c["max_price"])
    n = w & dn & _valid(na) & (na <= c["max_price"])
    return y, n, np.where(up, 1.0, 0.0)


@L3.family("pq_tie", "Unchanged-price YES",
           "Pyth-exact. YES wins when Pyth ends the window exactly at the opening print. In hours where that has "
           "happened often lately (trailing 14 days, same ET hour), buy YES early if it costs no more than "
           "0.5 + half the tie rate - edge.",
           {"tmin": [0.02, 0.04, 0.06, 0.08], "edge": [0.0, 0.01, 0.02, 0.03], "end": [1, 2, 3]}, heat=("edge", "tmin"))
def f_pq_tie(ctx, c):
    P = ctx.P
    tie = P["pq_tie_h"]
    fair = tie + (1 - tie) * 0.5
    ya = P["yes_ask"]
    y = _win(1, c["end"]) & np.isfinite(tie) & (tie >= c["tmin"]) & _valid(ya) & (ya <= fair - c["edge"])
    return y, np.zeros_like(y), fair


_FAV = {"55-70": (0.55, 0.70), "70-85": (0.70, 0.85), "85-95": (0.85, 0.95), "90-98": (0.90, 0.98),
        "55-95": (0.55, 0.95), "02-10": (0.02, 0.10), "05-15": (0.05, 0.15), "10-30": (0.10, 0.30),
        "15-45": (0.15, 0.45), "02-45": (0.02, 0.45)}


@L3.family("pq_favls", "Favourite / long-shot (quotes only)",
           "Kalshi quotes only (they already reflect the live Pyth price). Late in the window, buy whichever side's ask "
           "sits in a price band: favourites (55-98c) if traders under-price near-certainties, long shots (2-45c) if "
           "they under-price comebacks. Settled by Pyth, so the outcome is exact.",
           {"pband": list(_FAV), "start": [4, 8, 11, 13], "end": [12, 14]}, heat=("start", "pband"))
def f_pq_favls(ctx, c):
    P = ctx.P
    lo, hi = _FAV[c["pband"]]
    w = _win(c["start"], max(c["start"], c["end"]))
    ya, na = P["yes_ask"], P["no_ask"]
    y = w & _valid(ya) & (ya >= lo) & (ya <= hi)
    n = w & _valid(na) & (na >= lo) & (na <= hi)
    return y, n, np.full(ya.shape, np.nan)


@L3.family("pq_qmom", "Quote momentum (quotes only)",
           "Kalshi quotes only. When the YES mid has moved by at least d over the last L minutes, follow the move "
           "(traders are slow to price the live Pyth move) or fade it (they over-react).",
           {"mode": ["follow", "fade"], "L": [1, 2, 3], "d": [0.05, 0.10, 0.15, 0.20], "start": [2, 5, 8],
            "end": [10, 13], "band": ["10-90", "20-80"]}, heat=("d", "L"))
def f_pq_qmom(ctx, c):
    P = ctx.P
    key = ("mid",)
    if key not in ctx.cache:
        mid = (P["yes_bid"] + P["yes_ask"]) / 2
        ctx.cache[key] = pd.DataFrame(mid.T).ffill().to_numpy().T
    mid = ctx.cache[key]
    L = c["L"]
    dm = np.full(mid.shape, np.nan)
    dm[:, L:] = mid[:, L:] - mid[:, :-L]
    up, dn = dm >= c["d"], dm <= -c["d"]
    if c["mode"] == "fade":
        up, dn = dn, up
    by, bn, _, _ = ctx.band(c["band"])
    w = _win(c["start"], c["end"])
    return w & up & by, w & dn & bn, np.full(mid.shape, np.nan)


@L3.family("fv_tie", "Live model + Pyth unchanged-price chance",
           "The live bell-curve fair value on the Yahoo path (as lab4), plus the Pyth-exact chance that the window ends "
           "exactly unchanged (which settles YES): fair YES = tie + (1 - tie) x model.",
           {"start": [2, 4, 7], "end": [10, 13], "edge": [0.05, 0.07, 0.09, 0.12, 0.16], "band": ["10-90", "20-80"],
            "vm": [0.8, 1.0, 1.25], "vol": ["60", "blend"]}, heat=("edge", "vm"))
def f_fv_tie(ctx, c):
    p0 = ctx.prob(vol=c["vol"], vm=c["vm"])
    tie = np.nan_to_num(ctx.P["pq_tie_h"], nan=0.0)
    p = tie + (1 - tie) * p0
    pk = ("fv_tie", c["vol"], c["vm"])
    y, n = L3.fv_masks(ctx, p, pk, c["start"], c["end"], c["edge"], c["band"])
    return y, n, p


P_FAMS = ["pq_open", "pq_prev", "pq_tie", "pq_favls", "pq_qmom"]
Y_FAMS = ["fv_ref", "fv_tie"]
FAMS = Y_FAMS + P_FAMS
PYTH_EXACT = set(P_FAMS)

_describe0 = L3.describe


def _describe(fam, p):
    if fam == "pq_open":
        return (f"{p['edge'] * 100:.0f}c edge, minutes 1-{p['end']}, {'tie chance + ' if p['tie'] else ''}"
                f"{p['a']:+g} x previous {15 * p['lag']}-min Pyth move" + (f", {p['band'][:2]}-{p['band'][3:]}c only"))
    if fam == "pq_prev":
        return (f"{'with' if p['mode'] == 'with' else 'against'} a {p['pz']}+ sd previous {15 * p['lag']}-min Pyth move, "
                f"ask <= {p['max_price'] * 100:.0f}c, minutes 1-{p['end']}")
    if fam == "pq_tie":
        return f"hour's tie rate >= {p['tmin']:.0%}, {p['edge'] * 100:.0f}c edge, minutes 1-{p['end']}"
    if fam == "pq_favls":
        lo, hi = _FAV[p["pband"]]
        return f"{'favourite' if lo >= 0.5 else 'long shot'} at {lo * 100:.0f}-{hi * 100:.0f}c, minutes {p['start']}-{max(p['start'], p['end'])}"
    if fam == "pq_qmom":
        return (f"{p['mode']} a {p['d'] * 100:.0f}c+ mid move over {p['L']} min, minutes {p['start']}-{p['end']}, "
                f"{p['band'][:2]}-{p['band'][3:]}c only")
    return _describe0(fam, p)


L3.describe = _describe

_grid_list0 = L3.grid_list


def _grid_list(grid):
    out = _grid_list0(grid)
    if grid is L3.FAMILIES["fv_ref"]["grid"] and not L3.G.get("quick"):
        return out[::QUICK_FVREF]
    return out


L3.grid_list = _grid_list


# =========================================================================== the hunt
def models(workers=2):
    """lab4.models with lab4p's loader (Pyth-exact features, full Kalshi candle history) and lab4p's families."""
    L4.testable_list = lambda verbose=True: testable_p()
    L4.load4 = load_p
    L4.SKIP_FAMILIES = set()
    L4.GROUPS.clear()
    part = L4.models(workers=workers, quick=0, families=FAMS, out=PART)
    return part


# =========================================================================== judge -> lab4_results.json
CAVEATS = [
    "No 1-minute Pyth history was obtainable. Hermes' price endpoints (history AND latest), Pyth Benchmarks and the "
    "v1 API all answer 401 without an API key (checked Nov 4 2026, for crypto feeds too); Pythnet's public RPC blocks "
    "this IP and no public EVM chain carries on-chain pushes of these feeds. What IS exact: Kalshi's own record of the "
    "Pyth print at both ends of every window (strike at the open, expiration value at the close). Those match Kalshi's "
    "result on 100% of markets (one silver market excepted) and chain perfectly (each window's strike = the previous "
    "window's close print), so they are Pyth.",
    "So the Pyth-exact families (pq_*) decide only from information that exists at that moment with exact Pyth data: "
    "Pyth quarter-hour prints up to the open, Kalshi's own quotes, and the clock. They run on the whole Kalshi candle "
    "history from Sep 4 (Kalshi's live-API cutoff; older candles cost one request per market and were not fetched). "
    "Families that need the price INSIDE the window (the fv_ref control and fv_tie) still use Yahoo 1-minute bars "
    "(Oct 5+ only), with the Yahoo price at the open as their strike, exactly as lab4 did; their search window is "
    "therefore only the Yahoo part of it.",
    "One common holdout cut for every series (25% of the median series span); Treasury yields (15 days of markets) "
    "and AUD/CAD (27 days) have little or no search history before it, so they mostly cannot reach the holdout.",
    "Backtest fills assume the quoted ask had enough size for a $10 order; the yields are thin (median ~200 contracts "
    "per market). The one-minute-late column shows how much survives a one-minute delay.",
    "lab4's crypto structural candidates (xmkt pairs / hourly ladders, coin-race range sums) are carried over unchanged "
    "from lab4 and counted in the Bonferroni bar; they never depended on Yahoo.",
    "The fv_ref control grid is thinned to every 3rd configuration, as in lab4; the Pyth-exact grids are run in full.",
    "Exact feed: Kalshi names 'Pyth' + the asset; the Hermes feed ids listed per series are the Pyth feeds with that "
    "name (for gold/silver/WTI/Brent Pyth also lists a 24/7 or constant-maturity index; see coins[*].pyth_feed_match). "
    "No result here depends on the id, because no Pyth price could be downloaded by id.",
]


def judge():
    if OUT.exists() and not YAHOO_COPY.exists():
        shutil.copy2(OUT, YAHOO_COPY)
    L4.PART_MODELS = PART
    L4.CAVEATS = CAVEATS
    tmp = LAB / "lab4p_judge_tmp.json"
    res = L4.judge(out_path=tmp)
    tmp.unlink(missing_ok=True)
    pm = json.loads(PART.read_text())
    val = json.loads(VALID.read_text()) if VALID.exists() else validate()
    probe_r = json.loads(PROBE.read_text()) if PROBE.exists() else None
    for s, c in res["coins"].items():
        v = val.get(s, {})
        c.update({"pyth_feed": v.get("pyth_feed"), "pyth_feed_id": v.get("pyth_feed_id"),
                  "pyth_feed_match": v.get("feed_match"),
                  "pyth_result_match": v.get("result_matches_pyth_updown"), "pyth_chain_continuity": v.get("chain_continuity"),
                  "pyth_tie_rate": v.get("tie_rate"), "yahoo_sign_agreement": v.get("yahoo_sign_agreement"),
                  "underlying": f"Pyth {v.get('pyth_feed')} quarter-hour prints (Kalshi) + Yahoo {F.UNDERLYING[s][1]} path"})
    for c in res["candidates"]:
        c["data"] = "pyth_exact" if c["family"] in PYTH_EXACT else ("yahoo_path" if c["family"] in Y_FAMS or
                                                                    c["family"] in ("pertune", "ens_best") else "crypto")
    for b in res["baselines"]:
        b["data"] = "yahoo_path"
    for r in res["markets_surveyed"]:
        s = r["series"]
        v = val.get(s)
        if not v:
            continue
        cinfo = pm["coins"].get(s)
        base = (f"Pyth feed {v['pyth_feed']}; Kalshi's own Pyth prints match its result on "
                f"{v['result_matches_pyth_updown'] * 100:.2f}% of {v['markets_with_pyth_prints']} markets "
                f"({v['first'][:10]} to {v['last'][:10]}), chain continuity {v['chain_continuity'] * 100:.2f}%"
                + (f"; Yahoo's sign agreed only {v['yahoo_sign_agreement'] * 100:.1f}%" if v.get("yahoo_sign_agreement") else ""))
        if cinfo:
            r["testable"] = True
            r["tested_markets"] = cinfo["markets"]
            r["note"] = (f"Tested on {cinfo['markets']} markets with Kalshi candles (Sep 4+; Yahoo path for the control "
                         f"only from Oct 5). " + base + ".")
        else:
            r["note"] = (pm["why"].get(s, "not tested")[0].upper() + pm["why"].get(s, "not tested")[1:] + ". " + base + ".")
    m = res["method"]
    m["data_sources"] = {
        "kalshi": "public trade API (markets incl. floor_strike / expiration_value = Pyth prints, 1-minute candlesticks; "
                  "Sep 4 - Oct 6 candles fetched for this run)",
        "pyth": "exact Pyth prints at every window open/close from Kalshi's market records; feed ids from Hermes "
                "/v2/price_feeds (metadata is public); NO Pyth 1-minute history (all price endpoints need a key)",
        "yahoo_path": "Yahoo 1-minute bars (Oct 5+) as the intra-window path for fv_ref / fv_tie only, as in lab4",
        "crypto": "Coinbase 1-minute candles (lab4 xmkt / range parts, carried over)",
        "tried_and_failed": [f"{k}: HTTP {v['status']}" for k, v in (probe_r or {}).get("endpoints", {}).items()
                             if v.get("status") != 200] + [
            "Pythnet public RPC (pythnet.rpcpool.com): 403 'IP blocked'",
            "On-chain Pyth PriceFeedUpdate events (Base, Arbitrum, Ethereum, Optimism, BSC, Avalanche, Mantle, "
            "Berachain): no updates of these FX / commodity / rate feeds in the sampled hours",
            "app.pyth.com price history (the settlement-source website): behind sign-in + bot protection, not used"],
    }
    m["pyth_validation"] = val
    m["pyth_probe"] = probe_r
    m["summary"].insert(1, "Pyth 1-minute history was not obtainable (401 without a key); the Pyth-exact families "
                           "use Kalshi's own exact Pyth prints at every window open/close plus Kalshi quotes.")
    m["variant"] = "lab4p: Pyth-anchored re-run (see kalshi15m/lab4p.py)"
    OUT.write_text(json.dumps(res, default=L3._jd))
    print(f"-> {OUT} (old Yahoo-only results kept at {YAHOO_COPY})")
    return res


def main(args):
    cmd = args[0] if args else "help"
    if cmd == "probe":
        probe()
    elif cmd == "validate":
        validate()
    elif cmd == "models":
        models(workers=int(args[1]) if len(args) > 1 else 2)
    elif cmd == "judge":
        judge()
    elif cmd == "hermes":
        hermes_history()
    else:
        print(__doc__)
