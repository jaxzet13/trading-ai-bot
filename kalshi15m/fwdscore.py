"""Forward lab, daily scoring (python -m kalshi15m fwdlab score): every frozen candidate of
data/lab/fwd_candidates.json on the markets since FWD_START, each bet settled by Kalshi's own trade records.
See kalshi15m/fwdlab.py for what is frozen and how it is graded.
"""
from __future__ import annotations

import json
import math
import pickle
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import NormalDist

from . import data as D

ROOT = Path(__file__).resolve().parent.parent
LABDIR = ROOT / "data" / "lab"
FWD_DIR = ROOT / "data" / "kalshi15m" / "fwd"
TAPE_DIR = FWD_DIR / "tape"
TB_DIR = ROOT / "data" / "kalshi15m" / "tradebars"
OUT = LABDIR / "fwd_results.json"
KALSHI = "https://external-api.kalshi.com/trade-api/v2"
COINBASE = "https://api.exchange.coinbase.com"
THIN = {"KXNEAR15M", "KXHYPE15M", "KXDOGE15M", "KXBNB15M"}      # spot rebuilt from Coinbase's trade list
SPOT_LOOKBACK = 15 * 86400
# the real-money test's account (labrm.ACCOUNT), per bet
STAKE, MAX_N, MIN_ONE, PMIN, PMAX, WALK, KEEP = 0.5, 10, 1.0, 0.03, 0.95, 0.05, 0.08
WINDOW = (1.0, 3.0)                       # the order reaches Kalshi 1-3 s after the decision minute ends
GATE = {"min_days": 7, "min_filled": 30, "alpha": 0.05}


def _fwd_start():
    from .fwdlab import FWD_START
    return FWD_START


# --------------------------------------------------------------------------- data
_S = requests.Session()
_PACE = [0.16]


def _get(url, params, tries=30):
    for a in range(tries):
        try:
            r = _S.get(url, params=params, timeout=20)
        except requests.RequestException:
            time.sleep(3)
            continue
        if r.status_code == 429:            # Kalshi allows ~10 reads/s per IP (the paper run shares it)
            _PACE[0] = min(_PACE[0] * 1.25, 1.0)
            time.sleep(1.0 + a)
            continue
        r.raise_for_status()
        time.sleep(_PACE[0])
        _PACE[0] = max(_PACE[0] * 0.9, 0.13)
        return r.json()
    raise RuntimeError(f"{url}: unavailable")


def fetch_markets(series, log=print):
    """Settled markets since FWD_START + their 1-minute candles (each market fetched once)."""
    t_start = _fwd_start()
    now = int(time.time())
    mk = D.fetch_markets(series, max(1, math.ceil((now - t_start) / 86400) + 1))
    mk = mk[mk.open_ts >= t_start] if len(mk) else mk
    mpath, cpath = FWD_DIR / f"{series}_markets.csv", FWD_DIR / f"{series}_candles.csv"
    old_mk = pd.read_csv(mpath) if mpath.exists() else mk.iloc[:0]
    old_cd = pd.read_csv(cpath) if cpath.exists() else pd.DataFrame()
    mk = pd.concat([old_mk, mk], ignore_index=True).drop_duplicates("ticker").sort_values("open_ts")
    have = set(old_cd.ticker) if len(old_cd) else set()
    new = mk[~mk.ticker.isin(have)]
    if len(new):
        cd = None
        for attempt in range(3):           # Kalshi's candlestick endpoint rate-limits hard while the bots poll
            try:
                cd = D.fetch_candles(series, new)
                break
            except requests.HTTPError as e:
                log(f"  {series} candles: {e.response.status_code if e.response is not None else e}; waiting 60 s")
                time.sleep(60)
        if cd is None:                     # leave these markets for the next check
            log(f"  {series}: {len(new)} new markets skipped this time (Kalshi rate limit)")
            mk = mk[~mk.ticker.isin(new.ticker)]
        else:
            old_cd = pd.concat([old_cd, cd], ignore_index=True) if len(old_cd) else cd
    mk.to_csv(mpath, index=False)
    old_cd.drop_duplicates(["ticker", "ts"]).to_csv(cpath, index=False)
    return mk


def _coinbase_trade_bars(product, back_to, log=print):
    """1-minute bars from Coinbase's public trade list, newest back to `back_to` (as kalshi15m.tradebars):
    -> (bars DataFrame, oldest trade time fetched)."""
    bars, after, oldest, n = {}, None, None, 0
    while True:
        params = {"limit": 1000}
        if after:
            params["after"] = after
        tr = _get(f"{COINBASE}/products/{product}/trades", params)
        n += 1
        if not tr:
            break
        for x in tr:
            t = datetime.fromisoformat(x["time"].replace("Z", "+00:00")).timestamp()
            px, sz, tid = float(x["price"]), float(x["size"]), int(x["trade_id"])
            m = int(t // 60 * 60)
            b = bars.get(m)
            if b is None:
                bars[m] = [px, px, px, px, sz, tid, tid]
            else:
                if tid < b[5]:
                    b[0], b[5] = px, tid
                if tid > b[6]:
                    b[3], b[6] = px, tid
                b[1], b[2], b[4] = max(b[1], px), min(b[2], px), b[4] + sz
        oldest = min(datetime.fromisoformat(x["time"].replace("Z", "+00:00")).timestamp() for x in tr)
        after = str(min(int(x["trade_id"]) for x in tr))
        if oldest < back_to:
            break
        time.sleep(0.2)
    df = pd.DataFrame([(ts, b[2], b[1], b[0], b[3], b[4]) for ts, b in sorted(bars.items())],
                      columns=["ts", "low", "high", "open", "close", "volume"])
    return df, oldest


def fetch_spot(series, log=print):
    """Spot bars from FWD_START - 15 days to now: Coinbase candles for liquid coins, trade-built bars for the thin
    ones (their candles include trades the live feed never shows)."""
    path = FWD_DIR / f"{series}_spot.csv"
    now = int(time.time())
    sp = pd.read_csv(path) if path.exists() else None
    if series in THIN:
        if sp is None:                             # start from the full trade-built history
            sp = pd.read_csv(TB_DIR / f"{D.SERIES[series]}_bars.csv")
            sp = sp[sp.ts >= _fwd_start() - SPOT_LOOKBACK]
        last = int(sp.ts.max())
        new, oldest = _coinbase_trade_bars(D.SERIES[series], last - 120, log)
        if len(new) and oldest is not None:
            cut = int(oldest // 60 * 60) + 60       # first minute the new fetch covers completely
            sp = pd.concat([sp[sp.ts < cut], new[new.ts >= cut]], ignore_index=True)
        sp = sp[sp.ts < now // 60 * 60]            # the current minute is not finished
    else:
        t0 = int(sp.ts.max()) + 60 if sp is not None and len(sp) else _fwd_start() - SPOT_LOOKBACK
        if t0 < now - 120:
            new = D.fetch_spot(D.SERIES[series], t0, now - 60)
            sp = new if sp is None else pd.concat([sp, new], ignore_index=True)
    sp.drop_duplicates("ts").sort_values("ts")[["ts", "low", "high", "open", "close", "volume"]].to_csv(path, index=False)


_TL = threading.local()
_RATE = {"lock": threading.Lock(), "next": 0.0, "gap": 0.1}       # <= 10 requests/s in all (Kalshi allows ~20)


def _window(tk, t):
    """Kalshi trades on tk with time in [t, t + 4] s: [(ts, taker_side, yes_price, no_price, count)]."""
    if not hasattr(_TL, "s"):
        _TL.s = requests.Session()
    rows, cursor = [], None
    for _page in range(50):
        params = {"ticker": tk, "limit": 1000, "min_ts": int(t), "max_ts": int(t) + 4}
        if cursor:
            params["cursor"] = cursor
        for a in range(40):
            with _RATE["lock"]:
                wait = _RATE["next"] - time.time()
                _RATE["next"] = max(_RATE["next"], time.time()) + _RATE["gap"]
            if wait > 0:
                time.sleep(wait)
            try:
                r = _TL.s.get(f"{KALSHI}/markets/trades", params=params, timeout=20)
            except requests.RequestException:
                time.sleep(2)
                continue
            if r.status_code == 429:
                with _RATE["lock"]:
                    _RATE["gap"] = min(_RATE["gap"] * 1.2, 0.5)
                time.sleep(1 + a)
                continue
            r.raise_for_status()
            break
        else:
            raise RuntimeError("Kalshi trades: rate limited")
        d = r.json()
        rows += [(datetime.fromisoformat(x["created_time"].replace("Z", "+00:00")).timestamp(), x["taker_side"],
                  float(x["yes_price_dollars"]), float(x["no_price_dollars"]), float(x["count_fp"]))
                 for x in d.get("trades", [])]
        cursor = d.get("cursor")
        if not cursor or len(d.get("trades", [])) < 1000:
            break
    return sorted(rows)


def fetch_tape(series, want, log=print):
    """Kalshi's trades in the seconds an order (or early sale) placed at the end of minute j would reach Kalshi, for
    every (ticker, j) in `want` -> {(ticker, j): trades in [minute end, minute end + 4 s]} (the fill window is 1-3 s).
    Settled markets: each window fetched once, cached in data/kalshi15m/fwd/tape/{series}.pkl."""
    TAPE_DIR.mkdir(parents=True, exist_ok=True)
    path = TAPE_DIR / f"{series}.pkl"
    tape = pickle.load(open(path, "rb")) if path.exists() else {}
    todo = sorted(w for w in set(want) if (w[0], w[1]) not in tape)      # cache key: (ticker, minute)
    t0 = time.time()
    with ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(_window, tk, t): (tk, j) for tk, j, t in todo}
        for k, f in enumerate(as_completed(futs)):
            tape[futs[f][:2]] = f.result()
            if (k + 1) % 500 == 0:
                pickle.dump(tape, open(path, "wb"))
                log(f"  {series} tape {k + 1}/{len(todo)} windows ({time.time() - t0:.0f}s)")
    pickle.dump(tape, open(path, "wb"))
    if todo:
        log(f"  {series} tape: {len(todo)} new windows ({time.time() - t0:.0f}s)")
    return tape


# --------------------------------------------------------------------------- fills from the tape
class Fills:
    """Per market x decision minute x side: for each limit in cents, the first trade price at or under it in the
    order's 1-3 s window and how many contracts traded there (entries), and the best price the held side could
    have been sold at (someone buying the other side; exits). Same rules as labrm.entry_fill / exit_fill."""

    def __init__(self, ctx, tape):
        nm = len(ctx.open_ts)
        self.first = np.full((nm, 14, 2, 101), np.nan)
        self.avail = np.zeros((nm, 14, 2, 101))
        self.exit_max = np.full((nm, 14, 2), -np.inf)
        self.has = np.zeros((nm, 14), bool)
        cents = np.arange(101) / 100
        for m, (tk, ots) in enumerate(zip(ctx.panel.ticker, ctx.open_ts)):
            for j in range(14):
                tr = tape.get((tk, j))
                if tr is None:
                    continue
                self.has[m, j] = True
                t = ots + 60 * (j + 1)
                tr = [x for x in tr if t + WINDOW[0] <= x[0] <= t + WINDOW[1]]
                if not tr:
                    continue
                side = np.array([x[1] == "yes" for x in tr])
                yp, np_ = np.array([x[2] for x in tr]), np.array([x[3] for x in tr])
                cnt = np.array([x[4] for x in tr])
                for s, (is_s, px) in enumerate(((~side, np_), (side, yp))):          # 0 = NO, 1 = YES
                    if is_s.any():
                        p_e, c_e = px[is_s], cnt[is_s]
                        ok = p_e[None, :] <= cents[:, None] + 1e-9                     # (101, trades), time order
                        self.avail[m, j, s] = (ok * c_e[None, :]).sum(1)
                        self.first[m, j, s] = np.where(ok.any(1), p_e[np.argmax(ok, 1)], np.nan)
                    if (~is_s).any():                                                 # someone bought the other side
                        self.exit_max[m, j, s] = px[~is_s].max()


def _bets(tr):
    """The order each lab3 trade becomes on the real account (before the tape says whether it filled)."""
    from . import lab3
    from .backtest import TAKER_RATE
    price, q = tr["price"], tr["q"]
    lim2 = np.floor(np.minimum(price + WALK, q - KEEP) * 100 + 1e-9) / 100
    limit = np.where((price < lim2) & (lim2 <= PMAX), lim2, price)
    n = np.minimum(np.floor(tr["stake"] * STAKE / 10.0 / limit + 1e-9), MAX_N)
    n = np.where((n < 1) & (limit + lab3._fee(limit, 1, TAKER_RATE) <= MIN_ONE), 1, n)
    keep = (price >= PMIN) & (price <= PMAX) & (n >= 1)
    return {"m": tr["m"], "j": tr["j"], "yes": tr["yes"].astype(int), "limit": limit, "n": n, "keep": keep,
            "exit_j": tr["exit_j"], "sell": tr["sell"]}


def settle(ctx, fills, b):
    """Real bets -> (placed, filled, pnl, day) per trade, Kalshi's trade records deciding every fill."""
    from . import lab3
    from .backtest import TAKER_RATE
    m, j, yes = b["m"], b["j"], b["yes"]
    keep = b["keep"] & fills.has[m, j]
    c = np.clip(np.round(b["limit"] * 100).astype(int), 0, 100)
    avail, fp = fills.avail[m, j, yes, c], fills.first[m, j, yes, c]
    nf = np.minimum(b["n"], np.floor(avail + 1e-9))
    filled = keep & (nf >= 1) & np.isfinite(fp)
    nf = np.where(filled, nf, 0)
    fp = np.where(filled, fp, 0.0)
    cost = nf * fp + lab3._fee(fp, nf, TAKER_RATE)
    res = (ctx.result[m] == 1) == (yes == 1)
    pnl = nf * res - cost
    ej, sell = b["exit_j"], b["sell"]
    has_exit = filled & (ej >= 0) & np.isfinite(sell)
    if has_exit.any():
        sold = has_exit & (fills.exit_max[m, np.clip(ej, 0, 13), yes] >= sell - 1e-9)
        pnl = np.where(sold, nf * sell - lab3._fee(np.where(sold, sell, 0.0), nf, TAKER_RATE) - cost, pnl)
    day = ((ctx.open_ts[m] + 60 * (j + 1)) // 86400).astype(int)
    return {"placed": keep, "filled": filled, "pnl": np.where(filled, pnl, 0.0), "day": day}


# --------------------------------------------------------------------------- scoring
def _t(v):
    v = np.asarray(v, float)
    return float(v.mean() / v.std(ddof=1) * math.sqrt(len(v))) if len(v) > 2 and v.std(ddof=1) > 0 else 0.0


def contexts(coins, log=print):
    from . import backtest as B
    from . import lab2, lab3
    lab3.REAL = False                      # classic positions; reality comes from the tape
    lab3._SPOT.clear()
    for s in coins:
        lab3._SPOT[(s, "main")] = lab3.Spot(FWD_DIR / f"{s}_spot.csv")
    out = {}
    try:
        with lab2._source(FWD_DIR):
            for s in coins:
                p = B.Panel(B.build_panel(s))
                lab3.add_features(p, s, "main")
                out[s] = lab3.Ctx(s, p.subset(np.asarray(p.open_ts, np.int64) >= _fwd_start()))
    finally:
        lab3._SPOT.clear()
    return out


def score(download=True, log=print):
    from . import lab3
    t0 = time.time()
    C = json.loads((LABDIR / "fwd_candidates.json").read_text())
    coins = C["coins"]
    FWD_DIR.mkdir(parents=True, exist_ok=True)
    if download:
        for s in coins:
            mk = fetch_markets(s, log)
            fetch_spot(s, log)
            log(f"  {s}: {len(mk)} forward markets ({time.time() - t0:.0f}s)")
    ctxs = contexts(coins, log)
    # pass 1: every candidate's orders (signals need no tape); collect the (market, minute) windows they need
    bets, want, fam = [], {s: set() for s in coins}, None
    for c in sorted(C["candidates"], key=lambda c: c["family"]):
        if c["family"] != fam:                 # model probabilities are cached per family (as lab3's search)
            fam = c["family"]
            for x in ctxs.values():
                x.cache = {}
        per = {}
        for coin in (coins if c["scope"] == "ALL" else [c["scope"]]):
            ctx = ctxs[coin]
            side, minute, p = lab3.signal(ctx, c["family"], c["params"])
            tr = lab3.execute(ctx, c["family"], c["params"], side, minute, p, norm=(c.get("norms") or {}).get(coin))
            if not len(tr["m"]):
                continue
            b = _bets(tr)
            per[coin] = b
            tk, ots = ctx.panel.ticker, ctx.open_ts
            for k in np.nonzero(b["keep"])[0]:
                mm, jj = int(b["m"][k]), int(b["j"][k])
                want[coin].add((tk[mm], jj, int(ots[mm]) + 60 * (jj + 1)))
                ej = int(b["exit_j"][k])
                if ej >= 0:
                    want[coin].add((tk[mm], ej, int(ots[mm]) + 60 * (ej + 1)))
        bets.append((c, per))
    for x in ctxs.values():
        x.cache = {}
    log(f"  {len(bets)} strategies' orders ready; {sum(len(v) for v in want.values()):,} order windows ({time.time() - t0:.0f}s)")
    tapes = {s: fetch_tape(s, want[s], log) for s in coins} if download else \
        {s: pickle.load(open(TAPE_DIR / f"{s}.pkl", "rb")) for s in coins}
    fills = {s: Fills(ctxs[s], tapes[s]) for s in coins}
    log(f"  fills ready ({time.time() - t0:.0f}s)")
    rows = []
    for c, per in bets:
        parts = [settle(ctxs[coin], fills[coin], b) for coin, b in per.items()]
        if parts:
            f = np.concatenate([x["filled"] for x in parts])
            pn = np.concatenate([x["pnl"] for x in parts])[f]
            dy = np.concatenate([x["day"] for x in parts])[f]
            placed = int(sum(x["placed"].sum() for x in parts))
        else:
            pn, dy, placed = np.array([]), np.array([], int), 0
        daily = pd.Series(pn).groupby(dy).sum() if len(pn) else pd.Series(dtype=float)
        rows.append({"id": c["id"], "family": c["family"], "scope": c["scope"], "rank": c["rank"],
                     "params": c["params"], "t_before": c["t_before"], "placed": placed, "filled": int(len(pn)),
                     "pnl": round(float(pn.sum()), 2), "t": round(_t(pn), 2),
                     "win_rate": round(float((pn > 0).mean()), 3) if len(pn) else None,
                     "days_up": int((daily > 0).sum()), "days": int(len(daily))})
    n = len(rows)
    bar = float(NormalDist().inv_cdf(1 - GATE["alpha"] / max(n, 1)))
    days = (time.time() - _fwd_start()) / 86400
    for r in rows:
        r["status"] = ("pass" if days >= GATE["min_days"] and r["filled"] >= GATE["min_filled"] and r["pnl"] > 0
                       and r["t"] >= bar else "fail" if r["filled"] >= GATE["min_filled"] and r["pnl"] <= 0 else "open")
    traded = [r for r in rows if r["filled"]]
    pos = [r for r in traded if r["pnl"] > 0]
    by = lambda key: {k: {"n": len(g), "traded": sum(1 for r in g if r["filled"]),
                          "profitable": sum(1 for r in g if r["pnl"] > 0),
                          "best_t": max((r["t"] for r in g), default=None),
                          "median_pnl": float(np.median([r["pnl"] for r in g if r["filled"]])) if any(r["filled"] for r in g) else None}
                      for k, g in pd.Series(rows).groupby([r[key] for r in rows])}
    # leaderboard: t-stats on a handful of bets mean nothing, so rank those with >= 10 filled bets first
    top = sorted(rows, key=lambda r: (r["filled"] < 10, -r["t"], -r["pnl"]))
    out = {"generated": int(time.time()), "fwd_start": _fwd_start(), "frozen_at": C["frozen_at"], "days": round(days, 2),
           "markets": {s: int(len(ctxs[s].open_ts)) for s in coins}, "n_candidates": n, "bar_t": round(bar, 2),
           "gate": GATE, "traded": len(traded), "profitable": len(pos),
           "traded10": sum(1 for r in rows if r["filled"] >= 10),
           "profitable10": sum(1 for r in rows if r["filled"] >= 10 and r["pnl"] > 0),
           "passed": sum(r["status"] == "pass" for r in rows),
           "by_scope": by("scope"), "by_family": by("family"), "top": top[:60],
           "selection": C.get("selection"), "runtime_s": int(time.time() - t0)}
    OUT.write_text(json.dumps(out, indent=1, default=float))
    log(f"fwdlab score: {n} strategies on {days:.1f} forward days; {len(traded)} placed a filled bet, "
        f"{len(pos)} profitable; bar t >= {bar:.2f}; {out['passed']} passed ({time.time() - t0:.0f}s)")
    for r in top[:10]:
        log(f"  {r['id']:32s} ${r['pnl']:>7.2f}  {r['filled']:>4} filled  t {r['t']:>5}  [{r['status']}]")
    return out
