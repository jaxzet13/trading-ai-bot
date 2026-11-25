"""Edge model (python -m kalshi15m edge train | walk | loop | status): ONE model of where Kalshi's 15-minute
crypto prices are wrong, instead of thousands of threshold rules picked off a leaderboard.

Why (Nov 24 review of every stored market, Aug 31 - Nov 24, 9 coins, 1.6 M price observations):
  * Kalshi's prices are almost exactly right on average. A YES priced 35c wins 34.6% of the time; the simple
    fair-value model the old rules were built on does not beat the market by itself (its "8c edge" bets win at
    the market's price, not the model's), so a taker pays the fee (~1.5c) and half the spread for nothing.
  * The 489 real bets since Nov 12 made +$22.19 with a t-stat of 1.2: not distinguishable from luck, and
    almost flat after the first three days. Picking the leaderboard's best of thousands is mostly picking noise.
  * A few effects ARE real, small and stable in every month: prices under-react to the coin's own last 5-10
    minutes, over-react to Bitcoin's move and to the previous 15-minute window, and lag the vol model a little
    on the thinner coins. Each is ~1c per standard deviation; together they reach 4-8c in the tails.

The model: P(YES) = sigmoid(logit(mid price) + x . b), a logistic regression whose starting point is the market's
own price. x = 21 signed features known at the decision minute (see FEATURES). One pooled fit on all coins, then
one fit per coin shrunk toward the pooled one (ridge LAM_COIN). Refit on the last ROLL_DAYS days.

Bets: at minutes START..END of a market, buy the side whose predicted win probability beats its ask by THR
after Kalshi's fee; one bet per market; never outside PMIN..PMAX.

Honest scoring (walk()): every prediction is made by a model fitted only on EARLIER days (first WARM_DAYS days
train only; refit every REFIT_DAYS). The bet is filled at that minute's ask (real fills since Nov 12 averaged
0.3c better than that ask) and pays the settlement minus the fee. Coins trade live only while their own
walk-forward record is good (LIVE_ON / LIVE_OFF, with hysteresis).

Sizing (stake_usd): a fraction KELLY of the Kelly stake for the predicted edge after a HAIRCUT, so bets grow
with the balance and with the size of the mispricing, never with the hour of the day.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from .strategies import ndtr

ROOT = Path(__file__).resolve().parent.parent
MODEL = Path(__file__).resolve().parent / "edge_model.json"
LABDIR = ROOT / "data" / "lab"
REPORT = LABDIR / "edge_walk.json"
STOP = ROOT / "STOP_EDGE"

BASE = ["dl", "dl240", "r1z", "r3z", "r5z", "r10z", "refz", "refr1", "refr3", "prevz", "zown"]
INTER = ["dl", "refz", "r1z", "r5z", "prevz"]
FEATURES = BASE + [f + s for f in INTER for s in ("_late", "_early")]
LATE, EARLY = 10, 5                 # minute >= LATE / minute <= EARLY interactions
THR, START, END, PMIN, PMAX = 0.05, 4, 13, 0.05, 0.95
ROLL_DAYS, WARM_DAYS, REFIT_DAYS = 35, 28, 3
LAM_POOL, LAM_COIN = 20.0, 300.0
LIVE_ON, LIVE_OFF = 1.5, 0.5        # a coin goes live at walk-forward t >= LIVE_ON and stays until t < LIVE_OFF
KELLY, HAIRCUT = 0.3, 0.6           # stake = KELLY x Kelly fraction of (HAIRCUT x predicted edge)
COMMON_START = 1788134400           # Aug 31 2026: all 9 coins have data from here
MIN = np.arange(1, 15)
TAKER = 0.07


def fee(p):
    return TAKER * p * (1 - p)


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def features(P):
    """Panel arrays (markets x 14) -> (X (markets, 14, len(FEATURES)), offset = logit(mid), ok mask).
    The same code runs on the batch panel (training, scoring) and on the live 1-row panel."""
    g = lambda k: np.asarray(P[k], float)
    spot, strike, v, v240 = g("spot"), g("strike"), g("vol1m"), g("vol240")
    ya, yb = g("yes_ask"), g("yes_bid")
    tau = (15 - MIN)[None, :].astype(float)
    with np.errstate(all="ignore"):
        x = np.log(spot / strike)
        q, q240 = ndtr(x / (v * np.sqrt(tau))), ndtr(x / (v240 * np.sqrt(tau)))
        mid = (ya + yb) / 2
        off = _logit(mid)
        c4 = lambda a: np.clip(a, -4, 4)
        F = {"dl": np.clip(_logit(q) - off, -3, 3), "dl240": np.clip(_logit(q240) - off, -3, 3),
             "r1z": c4(g("r1") / v), "r3z": c4(g("r3") / (v * math.sqrt(3))), "r5z": c4(g("r5") / (v * math.sqrt(5))),
             "r10z": c4(g("r10") / (v * math.sqrt(10))),
             "refz": c4(g("ref_z")), "refr1": c4(g("ref_r1") / g("ref_v60")),
             "refr3": c4(g("ref_r3") / (g("ref_v60") * math.sqrt(3))),
             "prevz": c4(g("prev_ret") / (v * math.sqrt(15))),
             "zown": c4(x / (v * np.sqrt(MIN[None, :].astype(float))))}
    late = (MIN >= LATE)[None, :].astype(float)
    early = (MIN <= EARLY)[None, :].astype(float)
    for f in INTER:
        F[f + "_late"], F[f + "_early"] = F[f] * late, F[f] * early
    X = np.stack([np.broadcast_to(F[k], ya.shape) for k in FEATURES], axis=-1)
    ok = np.isfinite(ya) & np.isfinite(yb) & (mid >= 0.04) & (mid <= 0.96) & np.isfinite(X).all(-1)
    return X, off, ok


def fit(X, y, off, lam, prior=None, iters=15):
    """Ridge logistic regression with a fixed offset (Newton steps). prior: shrink toward it instead of 0."""
    k = X.shape[1]
    pr = np.zeros(k) if prior is None else np.asarray(prior, float)
    b = pr.copy()
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(off + X @ b)))
        w = p * (1 - p)
        step = np.linalg.solve((X * w[:, None]).T @ X + lam * np.eye(k), X.T @ (y - p) - lam * (b - pr))
        b = b + step
        if np.abs(step).max() < 1e-7:
            break
    return b


def fit_all(X, y, off, coin):
    """-> (pooled betas, {coin: betas shrunk toward the pooled fit})."""
    bp = fit(X, y, off, LAM_POOL)
    return bp, {c: fit(X[coin == c], y[coin == c], off[coin == c], LAM_COIN, prior=bp) for c in np.unique(coin)}


def prob(off, X, b):
    return 1 / (1 + np.exp(-(off + X @ np.asarray(b, float))))


# ----------------------------------------------------------------------------- data
def load_panels(coins=None, log=print):
    """{series: {ticker, open_ts, result, P}}: the stored backtest data (to Nov 1) + the forward download
    (Nov 4 on, data/kalshi15m/fwd, kept current by refresh()), with every lab3 feature column."""
    from . import backtest as B, lab2, lab3
    from .fwdscore import FWD_DIR
    out = {}
    for s in (coins or lab3.COINS):
        ref = "KXETH15M" if s == "KXBTC15M" else "KXBTC15M"
        lab3._SPOT.clear()
        try:
            pm = B.Panel(B.build_panel(s))
            lab3.add_features(pm, s, "main")
        except (OSError, ValueError, KeyError) as e:
            log(f"  {s}: stored data unavailable ({e!r}); forward data only")
            pm = None
        lab3._SPOT.clear()
        try:
            lab3._SPOT[(s, "main")] = lab3.Spot(FWD_DIR / f"{s}_spot.csv")
            lab3._SPOT[(ref, "main")] = lab3.Spot(FWD_DIR / f"{ref}_spot.csv")
            with lab2._source(FWD_DIR):
                pf = B.Panel(B.build_panel(s))
            lab3.add_features(pf, s, "main")
        finally:
            lab3._SPOT.clear()
        if pm is not None:
            pm = pm.subset(~np.isin(pm.ticker, pf.ticker) & (np.asarray(pm.open_ts) < np.asarray(pf.open_ts).min()))
            p = B.Panel.concat([pm, pf])
        else:
            p = pf
        out[s] = {"ticker": p.ticker, "open_ts": np.asarray(p.open_ts, np.int64), "result": np.asarray(p.result, int),
                  "P": p.P}
    return out


def rows(panels, start=COMMON_START):
    """Flat training/scoring table from load_panels(): one row per market x minute with a usable quote."""
    cols = {k: [] for k in ("coin", "m", "j", "ots", "ya", "yb", "y", "off")}
    Xs = []
    for s, d in panels.items():
        X, off, ok = features(d["P"])
        ok &= (d["open_ts"] >= start)[:, None]
        mi, ji = np.nonzero(ok)
        Xs.append(X[mi, ji])
        cols["coin"].append(np.full(len(mi), s))
        cols["m"].append(mi)
        cols["j"].append(MIN[ji])
        cols["ots"].append(d["open_ts"][mi])
        cols["ya"].append(np.asarray(d["P"]["yes_ask"], float)[mi, ji])
        cols["yb"].append(np.asarray(d["P"]["yes_bid"], float)[mi, ji])
        cols["y"].append((d["result"][mi] == 1).astype(float))
        cols["off"].append(off[mi, ji])
    R = {k: np.concatenate(v) for k, v in cols.items()}
    R["X"] = np.concatenate(Xs)
    R["day"] = R["ots"] // 86400
    return R


def refresh(log=print):
    """Download newly settled markets, their candles and the spot bars for all 9 coins (the forward lab's
    downloader; one coin failing does not stop the others)."""
    from . import lab3
    from .fwdscore import FWD_DIR, fetch_markets, fetch_spot
    FWD_DIR.mkdir(parents=True, exist_ok=True)
    for s in lab3.COINS:
        try:
            mk = fetch_markets(s, log)
            fetch_spot(s, log)
            log(f"  {s}: {len(mk)} forward markets")
        except Exception as e:
            log(f"  {s}: refresh failed ({e!r}); using the data already saved")


# ----------------------------------------------------------------------------- bets
def pick(p_yes, ya, yb, thr=THR):
    """Which side (if any) the model buys at these quotes -> (side, price, q, net edge) arrays; side 0 = none,
    1 = YES at ya, -1 = NO at 1 - yb."""
    na = 1 - yb
    ey, en = p_yes - ya - fee(ya), (1 - p_yes) - na - fee(na)
    oky = (ey >= thr) & (ya >= PMIN) & (ya <= PMAX)
    okn = (en >= thr) & (na >= PMIN) & (na <= PMAX) & ~oky
    side = np.where(oky, 1, np.where(okn, -1, 0))
    return side, np.where(oky, ya, na), np.where(oky, p_yes, 1 - p_yes), np.where(oky, ey, en)


def bets(R, p_yes, thr=THR, start=START, end=END):
    """First qualifying minute of each market -> dict of arrays (one bet per market, filled at the ask)."""
    side, price, q, e = pick(p_yes, R["ya"], R["yb"], thr)
    idx = np.nonzero((side != 0) & (R["j"] >= start) & (R["j"] <= end) & np.isfinite(p_yes))[0]
    idx = idx[np.lexsort((R["j"][idx], R["ots"][idx], R["coin"][idx]))]
    key = np.char.add(R["coin"][idx], R["m"][idx].astype(str))
    _, first = np.unique(key, return_index=True)
    idx = idx[np.sort(first)]
    win = np.where(side[idx] == 1, R["y"][idx], 1 - R["y"][idx])
    return {"coin": R["coin"][idx], "ots": R["ots"][idx], "j": R["j"][idx], "side": side[idx], "price": price[idx],
            "q": q[idx], "edge": e[idx], "win": win, "pnl": win - price[idx] - fee(price[idx]), "day": R["day"][idx]}


def _t(v):
    v = np.asarray(v, float)
    s = v.std(ddof=1) if len(v) > 2 else 0.0
    return float(v.mean() / s * math.sqrt(len(v))) if s > 0 else 0.0


def summary(b, days):
    """Stats of a set of bets over the given test days (day-level t-stat: days with no bets count as 0)."""
    b = _sub(b, np.isin(b["day"], days))
    dd = np.array([b["pnl"][b["day"] == d].sum() for d in days])
    n = len(b["pnl"])
    cum = np.cumsum(dd)
    return {"bets": int(n), "per_day": round(n / max(len(days), 1), 1),
            "cents_per_bet": round(100 * float(b["pnl"].mean()), 2) if n else 0.0,
            "pnl": round(float(b["pnl"].sum()), 2), "usd_per_day": round(float(dd.mean()), 3) if len(dd) else 0.0,
            "t": round(_t(dd), 2), "days_up": int((dd > 0).sum()), "days": int(len(dd)),
            "win_rate": round(float(b["win"].mean()), 3) if n else 0.0,
            "avg_price": round(float(b["price"].mean()), 3) if n else 0.0,
            "worst_day": round(float(dd.min()), 2) if len(dd) else 0.0,
            "max_drawdown": round(float((np.maximum.accumulate(np.maximum(cum, 0)) - cum).max()), 2) if len(dd) else 0.0}


def _sub(b, mask):
    return {k: v[mask] for k, v in b.items()}


# ----------------------------------------------------------------------------- walk-forward + training
def walk_predict(R, log=print):
    """Out-of-sample P(YES) for every row from the WARM_DAYS-th day on: the model that predicts day d was fitted
    on the ROLL_DAYS days before d only (refit every REFIT_DAYS)."""
    days = np.unique(R["day"])
    p = np.full(len(R["y"]), np.nan)
    bc = None
    for i, d in enumerate(days):
        if i < WARM_DAYS:
            continue
        if bc is None or (i - WARM_DAYS) % REFIT_DAYS == 0:
            tr = (R["day"] < d) & (R["day"] >= d - ROLL_DAYS)
            _, bc = fit_all(R["X"][tr], R["y"][tr], R["off"][tr], R["coin"][tr])
        te = R["day"] == d
        for c, b in bc.items():
            mk = te & (R["coin"] == c)
            p[mk] = prob(R["off"][mk], R["X"][mk], b)
    return p, days[WARM_DAYS:]


def live_coins(per_coin, current=()):
    """Coins that trade live: walk-forward t >= LIVE_ON to start, kept while t >= LIVE_OFF."""
    cur = set(current)
    return sorted(c for c, s in per_coin.items() if s["t"] >= LIVE_ON or (c in cur and s["t"] >= LIVE_OFF))


def walk(R=None, log=print):
    """The honest scorecard -> dict (also written to data/lab/edge_walk.json)."""
    if R is None:
        R = rows(load_panels(log=log))
    p, tdays = walk_predict(R, log)
    b = bets(R, p)
    out = {"updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "thr": THR, "start": START, "end": END,
           "test_days": int(len(tdays)), "first_test_day": time.strftime("%Y-%m-%d", time.gmtime(int(tdays[0]) * 86400)),
           "last_test_day": time.strftime("%Y-%m-%d", time.gmtime(int(tdays[-1]) * 86400)),
           "all": summary(b, tdays)}
    out["per_coin"] = {c: summary(_sub(b, b["coin"] == c), tdays) for c in np.unique(R["coin"])}
    cur = _load_model().get("live_coins", []) if MODEL.exists() else []
    out["live_coins"] = live_coins(out["per_coin"], cur)
    lb = _sub(b, np.isin(b["coin"], out["live_coins"]))
    out["live"] = summary(lb, tdays)
    h = len(tdays) // 2
    out["live_first_half"], out["live_second_half"] = summary(lb, tdays[:h]), summary(lb, tdays[h:])
    out["by_threshold"] = {f"{th:.2f}": summary(_sub(bb := bets(R, p, th), np.isin(bb["coin"], out["live_coins"])), tdays)
                           for th in (0.03, 0.04, 0.05, 0.06)}
    out["daily"] = [{"day": time.strftime("%Y-%m-%d", time.gmtime(int(d) * 86400)),
                     "bets": int((lb["day"] == d).sum()), "pnl": round(float(lb["pnl"][lb["day"] == d].sum()), 2)}
                    for d in tdays]
    wk = (lb["day"] - tdays[0]) // 7
    out["weekly"] = [{"week": int(w) + 1, "bets": int((wk == w).sum()), "pnl": round(float(lb["pnl"][wk == w].sum()), 2)}
                     for w in np.unique(wk)]
    # calibration of the predicted shift from the market's mid price (out of sample)
    ok = np.isfinite(p)
    shift, res = p[ok] - (R["ya"][ok] + R["yb"][ok]) / 2, R["y"][ok] - (R["ya"][ok] + R["yb"][ok]) / 2
    edges = [-1, -0.06, -0.04, -0.02, 0, 0.02, 0.04, 0.06, 1]
    out["calibration"] = [{"predicted_c": round(100 * float(shift[m].mean()), 2), "actual_c": round(100 * float(res[m].mean()), 2),
                           "n": int(m.sum())}
                          for lo, hi in zip(edges[:-1], edges[1:]) if (m := (shift > lo) & (shift <= hi)).sum() > 200]
    LABDIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(out, indent=1))
    a, l = out["all"], out["live"]
    log(f"edge walk: {out['test_days']} unseen days; all 9 coins {a['per_day']} bets/day {a['cents_per_bet']:+.2f}c/bet "
        f"t {a['t']}; live coins {[c[2:-3] for c in out['live_coins']]} {l['per_day']} bets/day "
        f"{l['cents_per_bet']:+.2f}c/bet ${l['usd_per_day']:+.2f}/day t {l['t']} ({l['days_up']}/{l['days']} days up)")
    return out


def train(R=None, live=None, log=print):
    """Fit on the newest ROLL_DAYS days and write kalshi15m/edge_model.json (what the live bot loads)."""
    if R is None:
        R = rows(load_panels(log=log))
    last = int(R["day"].max())
    tr = R["day"] > last - ROLL_DAYS
    bp, bc = fit_all(R["X"][tr], R["y"][tr], R["off"][tr], R["coin"][tr])
    old = _load_model() if MODEL.exists() else {}
    m = {"trained": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "trained_ts": int(time.time()),
         "rows": int(tr.sum()), "days": int(len(np.unique(R["day"][tr]))),
         "data_to": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(R["ots"].max()) + 900)),
         "features": FEATURES, "thr": THR, "start": START, "end": END,
         "pooled": [round(float(x), 6) for x in bp],
         "coins": {c: [round(float(x), 6) for x in b] for c, b in bc.items()},
         "live_coins": sorted(live) if live is not None else old.get("live_coins", [])}
    MODEL.write_text(json.dumps(m, indent=1))
    log(f"edge model trained on {m['rows']:,} price rows over {m['days']} days (to {m['data_to']}); "
        f"live coins {[c[2:-3] for c in m['live_coins']]}")
    return m


# ----------------------------------------------------------------------------- live
_M = {"mtime": None, "model": None}


def _load_model():
    mt = MODEL.stat().st_mtime
    if _M["mtime"] != mt:
        _M["model"], _M["mtime"] = json.loads(MODEL.read_text()), mt
    return _M["model"]


def live_signal(series, P, minute, model=None):
    """The model's bet for this coin at this minute of the live 1-row panel -> dict(side, price, q, edge, p_yes)
    or None. None also when the coin is not live, a feature is missing, or the model file is stale/absent."""
    m = model or (_load_model() if MODEL.exists() else None)
    if not m or series not in m.get("live_coins", []) or series not in m["coins"] or m["features"] != FEATURES:
        return None
    if not m["start"] <= minute <= m["end"]:
        return None
    j = minute - 1
    X, off, ok = features(P)
    if not ok[0, j]:
        return None
    p = float(prob(off[0, j], X[0, j], m["coins"][series]))
    side, price, q, e = pick(np.array([p]), np.array([float(P["yes_ask"][0, j])]), np.array([float(P["yes_bid"][0, j])]),
                             m["thr"])
    if side[0] == 0:
        return None
    return {"side": "yes" if side[0] == 1 else "no", "price": float(price[0]), "q": float(q[0]), "edge": float(e[0]),
            "p_yes": p}


def live_eval(series, P, minute, model=None):
    """What the model thinks right now, bet or not -> dict(p_yes, edge_yes, edge_no) or None (missing feature /
    no model). For the runner's console line and for checking the live path."""
    m = model or (_load_model() if MODEL.exists() else None)
    if not m or series not in m["coins"] or m["features"] != FEATURES:
        return None
    j = minute - 1
    X, off, ok = features(P)
    if not ok[0, j]:
        return None
    p = float(prob(off[0, j], X[0, j], m["coins"][series]))
    ya, yb = float(P["yes_ask"][0, j]), float(P["yes_bid"][0, j])
    return {"p_yes": p, "edge_yes": p - ya - fee(ya), "edge_no": (1 - p) - (1 - yb) - fee(1 - yb),
            "live": series in m.get("live_coins", [])}


def stake_usd(balance, q, price, kelly=KELLY, haircut=HAIRCUT):
    """Dollars to put on a bet: kelly x balance x Kelly fraction, where the Kelly fraction of a binary bet bought
    at `price` (+ fee) with win probability q is (q - cost) / (1 - cost); the predicted edge is cut by `haircut`
    first (out of sample the model's predicted edge was about 0.5-0.75 of the realized one)."""
    cost = price + fee(price)
    e = haircut * (q - cost)
    if balance is None or e <= 0 or cost >= 1:
        return 0.0
    return float(kelly * balance * e / (1 - cost))


# ----------------------------------------------------------------------------- dashboard
REAL_LOG = ROOT / "data" / "kalshi15m" / "real_top5_live_log.jsonl"
DASH = ROOT / "dashboard"


def _runner_alive(needle="kalshi15m real --live --config kalshi15m/real_top5_live.json"):
    """Is the real-money runner process up (scan /proc; False where /proc is unavailable)."""
    try:
        for d in Path("/proc").iterdir():
            if d.name.isdigit():
                try:
                    if needle in (d / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace"):
                        return True
                except OSError:
                    continue
    except OSError:
        pass
    return False


def real_record(log_path=REAL_LOG, now=None):
    """Every real bet in the live log -> totals (all / old rules / edge model), a running-profit curve, the
    latest bets and whether the runner looks alive (an event in the last 3 minutes)."""
    now = now or time.time()
    ev = [json.loads(ln) for ln in open(log_path) if ln.strip()] if Path(log_path).exists() else []
    intent, bal, last_ts = {}, None, 0
    bets = []
    for e in ev:
        last_ts = max(last_ts, e.get("ts", 0))
        k, tk = e.get("event"), e.get("ticker")
        if e.get("balance_crypto") is not None:
            bal = e["balance_crypto"]
        if k == "order_intent":
            intent[tk] = e
        elif k == "fill" and tk in intent and e.get("n", 0) > 0:
            i = intent[tk]
            bets.append({"ticker": tk, "ts": i["ts"], "coin": e["series"][2:-3], "side": e["side"], "n": e["n"],
                         "price": e.get("avg_price") or i.get("price"), "rule": i.get("rule") or "", "edge": i.get("edge"),
                         "pnl": None, "fees": e.get("fees") or 0.0})
        elif k in ("settle", "exit") and isinstance(e.get("pnl"), (int, float)):
            for b in reversed(bets):
                if b["ticker"] == tk:
                    b["pnl"] = (b["pnl"] or 0.0) + e["pnl"]
                    b["settled_ts"] = e["ts"]
                    break
    done = [b for b in bets if b["pnl"] is not None]
    is_edge = lambda b: b["rule"].startswith("edge:")
    tot = lambda bs: {"bets": len(bs), "pnl": round(sum(b["pnl"] for b in bs), 2), "contracts": round(sum(b["n"] for b in bs), 2),
                      "fees": round(sum(b["fees"] for b in bs), 2), "wins": sum(1 for b in bs if b["pnl"] > 0)}
    first_edge = next((b["ts"] for b in bets if is_edge(b)), None)
    curve, cum = [], 0.0
    step = max(1, len(done) // 240)
    for i, b in enumerate(done):
        cum += b["pnl"]
        if i % step == 0 or i == len(done) - 1:
            curve.append({"cum": round(cum, 2), "n": i + 1, "ts": b["ts"],
                          "label": time.strftime("%b %d %H:%M", time.gmtime(b.get("settled_ts", b["ts"])))})
    sw = next((i for i, p in enumerate(curve) if first_edge and p["ts"] >= first_edge), None)
    recent = [{"time": time.strftime("%b %d %H:%M", time.gmtime(b["ts"])), "coin": b["coin"], "side": b["side"],
               "price": b["price"], "n": b["n"], "edge": b["edge"], "pnl": None if b["pnl"] is None else round(b["pnl"], 2)}
              for b in bets[-25:]][::-1]
    return {"running": _runner_alive(), "balance": bal, "all": tot(done), "edge": tot([b for b in done if is_edge(b)]),
            # old rules before the switch, and the old rules put back next to the model on Nov 25 (bets since)
            "old": tot([b for b in done if not is_edge(b) and not (first_edge and b["ts"] >= first_edge)]),
            "restored": tot([b for b in done if not is_edge(b) and first_edge and b["ts"] >= first_edge]),
            "curve": curve, "switch_index": sw, "recent": recent,
            "switched_ts": first_edge}


FILLQ = ROOT / "data" / "kalshi15m" / "edge_fill_quality.json"


def fill_quality(log_path=REAL_LOG, fetch=None):
    """Does the real bot get the prices the scorecard assumes? For every order the model sent: was it filled, at
    what price against the quoted ask, and - for orders that did NOT fill - what the bet would have paid at the
    quoted price (the market's result from Kalshi, cached). Missing mostly winners while filling mostly losers
    (adverse selection) would make the live edge smaller than the test's; this measures it."""
    import requests
    cache = json.loads(FILLQ.read_text()).get("results", {}) if FILLQ.exists() else {}

    def result(tk):
        if tk in cache:
            return cache[tk]
        try:
            m = (fetch or (lambda t: requests.get(f"https://external-api.kalshi.com/trade-api/v2/markets/{t}", timeout=10).json()))(tk)
            r = (m.get("market") or {}).get("result")
        except (requests.RequestException, ValueError):
            return None
        if r in ("yes", "no"):
            cache[tk] = r
        return cache.get(tk)

    ev = [json.loads(ln) for ln in open(log_path) if ln.strip()] if Path(log_path).exists() else []
    intent, rows = {}, []
    dropped = repriced = 0          # since orders are re-priced on the live book at send time (real.reprice)
    for e in ev:
        k, tk = e.get("event"), e.get("ticker")
        if k == "signal_skipped" and str(e.get("rule", "")).startswith("edge:") and any(
                w in str(e.get("reason", "")) for w in ("edge after the price moved", "the ask moved", "at send time")):
            dropped += 1
        if k == "order_intent" and str(e.get("rule", "")).startswith("edge:"):
            repriced += int("exec_price" in e)
            intent[tk] = e
        elif k == "fill" and tk in intent:
            i = intent.pop(tk)
            n = e.get("n") or 0
            row = {"ticker": tk, "ts": i["ts"], "side": i["side"], "quoted": i["price"], "edge": i.get("edge"),
                   "filled": n > 0, "fill_price": e.get("avg_price") if n > 0 else None,
                   "repriced": "exec_price" in i}
            sb, sa = i.get("send_yes_bid"), i.get("send_yes_ask")
            if sb is not None and sa is not None and sb > 0 and sa < 1:      # ask of our side when the order went out
                row["moved"] = round((sa if i["side"] == "yes" else 1 - sb) - i["price"], 4)
            r = result(tk) if i.get("close_ts", 0) + 120 < time.time() else None
            if r:
                win = 1.0 if r == i["side"] else 0.0
                row["at_quote_pnl"] = round(win - i["price"] - fee(i["price"]), 4)       # what the scorecard assumes
                if n > 0:
                    row["real_pnl"] = round(win - row["fill_price"] - fee(row["fill_price"]), 4)
            rows.append(row)
    f = [r for r in rows if r["filled"]]
    u = [r for r in rows if not r["filled"]]
    mean = lambda xs: round(100 * sum(xs) / len(xs), 2) if xs else None
    out = {"updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "orders": len(rows), "filled": len(f),
           "fill_rate": round(len(f) / len(rows), 3) if rows else None,
           "fill_minus_quote_c": mean([r["fill_price"] - r["quoted"] for r in f]),
           "filled_real_c": mean([r["real_pnl"] for r in f if "real_pnl" in r]),
           "filled_at_quote_c": mean([r["at_quote_pnl"] for r in f if "at_quote_pnl" in r]),
           "unfilled_would_have_c": mean([r["at_quote_pnl"] for r in u if "at_quote_pnl" in r]),
           "all_at_quote_c": mean([r["at_quote_pnl"] for r in rows if "at_quote_pnl" in r]),
           "unfilled_settled": sum(1 for r in u if "at_quote_pnl" in r),
           # how far our side's ask had moved by the time the order went out (orders logged with the send-time book)
           "moved_known": sum(1 for r in rows if "moved" in r),
           "moved_filled_c": mean([r["moved"] for r in f if "moved" in r]),
           "moved_unfilled_c": mean([r["moved"] for r in u if "moved" in r]),
           "unfilled_within_1c": sum(1 for r in u if "moved" in r and r["moved"] <= 0.0101),
           "unfilled_within_2c": sum(1 for r in u if "moved" in r and r["moved"] <= 0.0201),
           "unfilled_moved_known": sum(1 for r in u if "moved" in r),
           # orders priced on the live book at send time, and signals dropped there because the edge was gone
           "repriced_orders": repriced, "dropped_at_send": dropped,
           "repriced_filled": sum(1 for r in f if r.get("repriced")),
           "repriced_sent": sum(1 for r in rows if r.get("repriced")), "results": cache}
    FILLQ.write_text(json.dumps(out, indent=1))
    return out


def report(log=print):
    """Write dashboard/index.html (the page published as the crypto dashboard) from the scorecard, the model and
    the real-money log."""
    w = json.loads(REPORT.read_text())
    m = _load_model()
    r = real_record()
    tennis = None
    try:
        t = json.loads((ROOT / "data" / "tennis" / "report" / "summary.json").read_text())[0]
        lg = [json.loads(ln) for ln in open(ROOT / "data" / "tennis" / "learn_log.jsonl") if ln.strip()]
        tennis = {k: t.get(k, 0) for k in ("real_bets", "real_won", "real_pnl", "real_open")}
        tennis["markets"] = lg[-1]["markets"] if lg else 0
    except (OSError, ValueError, KeyError, IndexError):
        pass
    try:
        fq = {k: v for k, v in fill_quality().items() if k != "results"}
    except Exception as e:
        log(f"  fill quality failed: {e!r}")
        fq = None
    data = {"updated": time.strftime("%b %d %H:%M UTC", time.gmtime()), "walk": w, "fills": fq,
            "model": {k: m[k] for k in ("trained", "rows", "days", "data_to")},
            "real": {k: r[k] for k in ("running", "balance", "all", "edge", "restored", "curve", "switch_index", "recent")},
            "old": r["old"], "tennis": tennis,
            "switched": time.strftime("%b %d %H:%M UTC", time.gmtime(r["switched_ts"])) if r["switched_ts"] else "Nov 24"}
    html = (Path(__file__).resolve().parent / "edge_dashboard.html").read_text()
    assert "/*DATA*/null" in html
    DASH.mkdir(exist_ok=True)
    (DASH / "index.html").write_text(html.replace("/*DATA*/null", json.dumps(data).replace("</", "<\\/")))
    (DASH / "edge.json").write_text(json.dumps(data, indent=1))
    log(f"edge report: dashboard/index.html written ({r['all']['bets']} real bets, {r['edge']['bets']} by the model)")
    return data


# ----------------------------------------------------------------------------- loop / CLI
def cycle(log=print, download=True):
    if download:
        refresh(log)
    R = rows(load_panels(log=log))
    w = walk(R, log)
    return train(R, live=w["live_coins"], log=log), w


def loop(gap_s=3 * 3600, log=print):
    """24/7: new data, the walk-forward scorecard and a fresh fit every gap_s. Stop: touch STOP_EDGE."""
    while not STOP.exists():
        t0 = time.time()
        try:
            cycle(log)
            report(log)
        except Exception as e:
            log(f"edge cycle failed: {e!r}")
        log(f"edge cycle done ({time.time() - t0:.0f}s)")
        while time.time() - t0 < gap_s and not STOP.exists():
            time.sleep(30)


def main(args):
    cmd = args[0] if args else "status"
    if cmd == "train":
        cycle(download="no-download" not in args)
    elif cmd == "walk":
        walk()
    elif cmd == "loop":
        loop()
    elif cmd == "report":
        report()
    elif cmd == "status":
        if not MODEL.exists():
            print("no edge model yet: python -m kalshi15m edge train")
            return 1
        m = _load_model()
        print(f"model trained {m['trained']} on {m['rows']:,} rows / {m['days']} days; live coins {m['live_coins']}")
        if REPORT.exists():
            w = json.loads(REPORT.read_text())
            print(json.dumps({k: w[k] for k in ("test_days", "all", "live", "live_first_half", "live_second_half")}, indent=1))
            for c, s in w["per_coin"].items():
                print(f"  {c}: {s['per_day']} bets/day {s['cents_per_bet']:+.2f}c/bet t {s['t']}"
                      f"{'  LIVE' if c in w['live_coins'] else ''}")
    else:
        print("usage: python -m kalshi15m edge train [no-download] | walk | loop | report | status")
        return 2
    return 0
