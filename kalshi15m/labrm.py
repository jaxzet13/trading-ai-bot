"""Real-money backtest of the golden strategies (python -m kalshi15m labrm).

The classic lab backtests assume every order fills at the 1-minute candle close, at any (fractional) size, with
no account limits. This test re-runs the pre-registered golden strategies (no new parameter search, so the
ranking is not curve-fitted on these few days) the way the REAL account would trade them:

* entry: decided exactly as the backtest decides (same data, same minute); the order is an IOC limit at the
  ask, allowed up to `walk` cents deeper while keeping `keep_edge` below the model value (the live runner's
  walk_cents / walk_keep_edge). It FILLS only if Kalshi's real trade tape shows someone buying that side at a
  price <= the limit 1-3 s after the minute (when the live bot's order arrives); fill price = that trade's
  price; size = min(our contracts, the contracts that traded there).
* exit (rules that sell early): fills only if the tape shows the held side trading at >= the backtest's exit
  price 1-3 s after that minute; otherwise the position is held to settlement.
* the owner's account: whole contracts from the live sizing (stake_usd base, the rule's Kelly multiplier),
  1 contract when the stake is below one contract and it costs <= min_one_usd, max contracts per order,
  one bet per market, one open position per coin, per 15-minute window at most `side_cap` bets on one side
  and `window_cap` dollars, at most `open_risk` dollars at risk, daily loss caps (account and per coin),
  the balance itself (an order must be affordable; trading stops below min_balance).
* two separate periods; a strategy is "real-money golden" only if it is profitable in BOTH, with enough
  filled trades and a consistency score (t of per-trade P&L) of at least 2.

Writes data/lab/realmoney_results.json as it goes (progress for the dashboard's Real money tab).
"""
from __future__ import annotations

import json
import math
import os
import pickle
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import requests

from . import lab5 as L
from . import golden_live as GL
from .bot import kalshi_fee

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "lab" / "realmoney_results.json"
TAPE_CACHE = ROOT / "data" / "kalshi15m" / "rm_tape.pkl"
P2_DIR = ROOT / "data" / "kalshi15m" / "rm"
KALSHI = "https://external-api.kalshi.com/trade-api/v2"
COINS = ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXHYPE15M", "KXNEAR15M", "KXDOGE15M", "KXZEC15M"]

ACCOUNT = {"start_balance": 4.43, "stake_usd": 0.5, "max_contracts": 10, "min_one_usd": 1.0, "max_price": 0.95,
           "min_price": 0.03, "walk": 0.05, "keep_edge": 0.08, "window_cap_usd": 3.0, "same_side_per_window": 2,
           "max_open_risk_usd": 3.0, "daily_loss_usd": 3.0, "coin_daily_loss_usd": 1.5, "coin_trades_per_day": 15,
           "min_balance": 0.5}

# pre-registered candidates: every golden rule that lab5's simulator expresses (ALL-coin scope)
CANDS = [
    ("live_combo", "Current live setup (x_exit, then sized_exit, then scalp)", "live", None, True),
    ("x_exit:ALL", "Early sale, near fair value (x_exit)", "lab5",
     {"entry": "fv12v8", "dedge": 0.01, "timing": "none", "exit": "c2", "size": "k5p15", "norm": 0.22693348935173294}, True),
    ("sized_exit:ALL", "Bigger bets on bigger gaps + early sale", "lab3", dict(L.REF_CFG), True),
    ("scalp:ALL", "Early sale at fair value (scalp)", "lab3",
     {"entry": "fv12v8", "dedge": 0.0, "timing": "none", "exit": "c0", "size": "flat"}, True),
    ("sized:ALL", "Bigger bets on bigger gaps, hold to the end", "lab3",
     {"entry": "fv13", "dedge": 0.0, "timing": "none", "exit": "hold", "size": "k5"}, True),
    ("fv_lag:ALL", "Fair value with price-lag check", "lab3", {"entry": "lag", "exit": "hold", "size": "flat"}, True),
    ("fv_shape:ALL", "Fair value, fat-tail shape", "lab3", {"entry": "shape", "exit": "hold", "size": "flat"}, True),
    ("fv_drift:ALL", "Fair value with drift", "lab3", {"entry": "drift", "exit": "hold", "size": "flat"}, True),
    ("fv_emp:ALL", "Fair value from past moves", "lab3", {"entry": "emp", "exit": "hold", "size": "flat"}, True),
    ("fv_vol:ALL", "Fair value, smoothed volatility", "lab3", {"entry": "vol", "exit": "hold", "size": "flat"}, True),
    ("fv_ref:ALL", "Fair value, max volatility", "lab3", {"entry": "ref", "exit": "hold", "size": "flat"}, True),
    ("fv_t:ALL", "Fair value, fat-tailed (t) model", "lab3", {"entry": "t4", "exit": "hold", "size": "flat"}, True),
    ("x_entries:ALL", "Price-lag entry + early sale", "lab5",
     {"entry": "lag", "dedge": 0.01, "timing": "none", "exit": "c2", "size": "k3", "norm": 0.3790633169048206}, False),
    ("x_timing:ALL", "Enter while the gap is growing + early sale", "lab5",
     {"entry": "fv12v8", "dedge": 0.02, "timing": "grow", "exit": "c2", "size": "k3", "norm": 0.3679145776670061}, False),
    ("x_reentry:ALL", "Early sale, 14c gap, bets up to 3x (x_reentry, one bet per market)", "lab5",
     {"entry": "fv12v8", "dedge": 0.02, "timing": "none", "exit": "c2", "reentry": 2, "size": "k3",
      "norm": 0.3688183926949676}, False),
    ("x_combo:ALL", "Price-lag + growing gap + re-entry", "lab5",
     {"entry": "lag", "dedge": 0.0, "timing": "grow", "exit": "c2", "reentry": 2, "capk": 0, "prio": "first",
      "size": "k5", "norm": 0.36848604514867817}, False),
    ("x_cap:ALL", "Scalp with a per-window cap", "lab5",
     {"entry": "fv12v8", "dedge": 0.0, "timing": "none", "exit": "c0", "capk": 6, "prio": "first", "size": "k3",
      "norm": 0.3412936032571755}, False),
]
LIVE_ORDER = ["x_exit:ALL", "sized_exit:ALL", "scalp:ALL"]

STATE = {"progress": {"stage": "starting", "done": 0, "total": 0, "note": ""}, "candidates": [], "periods": []}


# =========================================================================== output
def write(status="running"):
    out = {"generated": int(time.time()), "status": status, "progress": STATE["progress"],
           "method": {"periods": STATE["periods"], "coins": COINS,
                      "account": {k: ACCOUNT[k] for k in ("start_balance", "stake_usd", "max_contracts",
                                                          "window_cap_usd", "same_side_per_window",
                                                          "max_open_risk_usd", "daily_loss_usd")},
                      "fill_model": ("A bet only counts if Kalshi's real trade records show someone trading that "
                                     "side at our price or better 1-3 seconds after the decision, which is when "
                                     "the live bot's order arrives; early sales likewise, otherwise the bet is "
                                     "held to the end."),
                      "rules": ["Same strategies and parameters as the classic backtests (nothing re-tuned on "
                                "these days).",
                                "Your exact bet sizes, contract limits, window/daily caps and starting balance.",
                                "Real-money golden = profitable in both periods, at least 20 filled bets, "
                                "consistency score (t) of 2 or more.",
                                "BNB is left out (its live data can't match the backtest's)."]},
           "candidates": STATE["candidates"], "chosen": STATE.get("chosen")}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out))
    os.replace(tmp, OUT)


# =========================================================================== trade tape
_S = requests.Session()
TAPE = pickle.load(open(TAPE_CACHE, "rb")) if TAPE_CACHE.exists() else {}
_old = Path("/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/exec_check_tape.pkl")
if _old.exists():
    try:
        for k, v in pickle.load(open(_old, "rb")).items():
            TAPE.setdefault((k[0], int(k[1]) + 3), v)           # exec_check keyed (tk, t-3, t+6)
    except Exception:
        pass
_N = [0]


def tape(tk: str, t: int):
    """Trades on market tk in [t-3, t+6] s: [(ts, taker_side, yes_price, no_price, count)], oldest first."""
    k = (tk, int(t))
    if k in TAPE:
        return TAPE[k]
    # recent markets: /markets/trades; older ones have moved to /historical/trades (same fields)
    # (Oct 1 onwards is on /markets/trades; September and earlier on /historical/trades)
    paths = ("/markets/trades",) if t >= 1790812800 else ("/historical/trades", "/markets/trades")
    for path in paths:
        out = _fetch(path, tk, t)
        if out:
            break
    TAPE[k] = out
    _N[0] += 1
    if _N[0] % 100 == 0:
        pickle.dump(TAPE, open(TAPE_CACHE, "wb"))
    return out


_PACE = [0.45]


def _fetch(path, tk, t):
    for a in range(40):
        try:
            r = _S.get(f"{KALSHI}{path}", params={"ticker": tk, "min_ts": int(t) - 3, "max_ts": int(t) + 7,
                                                   "limit": 1000}, timeout=20)
        except requests.RequestException:
            time.sleep(5)
            continue
        if r.status_code == 429:
            _PACE[0] = min(_PACE[0] * 1.3, 2.0)
            time.sleep(min(3 + 3 * a, 30))
            continue
        r.raise_for_status()
        time.sleep(_PACE[0])
        _PACE[0] = max(_PACE[0] * 0.98, 0.3)
        return sorted((datetime.fromisoformat(x["created_time"].replace("Z", "+00:00")).timestamp(), x["taker_side"],
                       float(x["yes_price_dollars"]), float(x["no_price_dollars"]), float(x["count_fp"]))
                      for x in r.json().get("trades", []))
    raise RuntimeError("Kalshi trade tape: rate limited")


def entry_fill(tk, side, t, limit):
    """(price, contracts available) of the first trade buying `side` at <= limit in [t+1, t+3], else None."""
    tr = tape(tk, t)
    hit = [(ts, (yp if side == "yes" else np_), c) for ts, s, yp, np_, c in tr
           if t + 1.0 <= ts <= t + 3.0 and s == side and (yp if side == "yes" else np_) <= limit + 1e-9]
    if not hit:
        return None
    return hit[0][1], sum(c for _, _, c in hit)


def exit_fill(tk, side, t, sell):
    """True if the held side traded at >= sell (someone bought the other side) in [t+1, t+3]."""
    for ts, s, yp, np_, c in tape(tk, t):
        if t + 1.0 <= ts <= t + 3.0 and s != side and (yp if side == "yes" else np_) >= sell - 1e-9:
            return True
    return False


# =========================================================================== backtest positions
def positions(where, cfg, norm):
    """The classic backtest's positions for one config on G[where]: list of dicts (chronological)."""
    for ctx in L.G[where].values():
        ctx.cache = {}
    E = L.episodes(where, {"dedge": 0.0, "timing": "none", **cfg})
    if not len(E["m"]):
        return []
    pnl, stake, n, fe, keep = L.evaluate(E, {"dedge": 0.0, "timing": "none", **cfg}, norm)
    out = []
    for i in np.nonzero(keep)[0]:
        coin = L.COINS[int(E["coin"][i])]
        if coin not in COINS:
            continue
        w = int(E["win_ts"][i])
        out.append({"coin": coin, "tk": L.G[where][coin].panel.ticker[int(E["m"][i])], "win": w,
                    "t": w + 60 * (int(E["fc"][i]) + 1), "minute": int(E["fc"][i]) + 1,
                    "side": "yes" if E["side"][i] == 1 else "no", "px": float(E["px"][i]), "q": float(E["q"][i]),
                    "tx": w + 60 * (int(E["xc"][i]) + 1) if np.isfinite(E["xpx"][i]) else None,
                    "xpx": float(E["xpx"][i]) if np.isfinite(E["xpx"][i]) else None,
                    "res": float(E["res"][i]), "stake10": float(stake[i]), "pnl10": float(pnl[i])})
    return sorted(out, key=lambda p: (p["t"], p["coin"]))


def norm_for(cid, cfg):
    if cfg.get("norm"):
        return cfg["norm"]
    if L.SIZES[cfg["size"]] is None:
        return 1.0
    return GL.RULES[cid]["norm"] if cid in GL.RULES else 1.0


def live_combo(per_rule):
    """The live runner: per market the first rule to fire takes it (earlier minute; ties by priority)."""
    best = {}
    for pr, rid in enumerate(LIVE_ORDER):
        for p in per_rule[rid]:
            k = p["tk"]
            cur = best.get(k)
            if cur is None or (p["t"], pr) < (cur["t"], cur["_pr"]):
                best[k] = {**p, "_pr": pr, "rule": rid}
    return sorted(best.values(), key=lambda p: (p["t"], p["coin"]))


# =========================================================================== account simulation
def simulate(pos, label=""):
    A = ACCOUNT
    bal = A["start_balance"]
    open_ = []                       # (close_t, cost, pnl, coin, day)
    day_pnl, coin_day_pnl, coin_day_n = {}, {}, {}
    win_side, win_cost, traded, coin_open_until = {}, {}, set(), {}
    trades, curve = [], [[pos[0]["t"] if pos else int(time.time()), round(bal, 4)]]

    def settle_until(t):
        nonlocal bal
        for o in sorted([o for o in open_ if o[0] <= t], key=lambda o: o[0]):
            open_.remove(o)
            bal += o[1] + o[2]
            day_pnl[o[4]] = day_pnl.get(o[4], 0.0) + o[2]
            coin_day_pnl[(o[3], o[4])] = coin_day_pnl.get((o[3], o[4]), 0.0) + o[2]
            curve.append([int(o[0]), round(bal + sum(x[1] for x in open_), 4)])

    for k, p in enumerate(pos):
        STATE["progress"]["note"] = f"{label}: bet {k + 1} of {len(pos)}"
        if k % 25 == 0:
            write()
        t = p["t"]
        settle_until(t)
        day = int(t // 86400)
        if bal + sum(o[1] for o in open_) < A["min_balance"]:
            break
        if p["tk"] in traded or coin_open_until.get(p["coin"], 0) > t:
            continue
        price = p["px"]
        if not (A["min_price"] <= price <= A["max_price"]):
            continue
        lim2 = math.floor(min(price + A["walk"], p["q"] - A["keep_edge"]) * 100 + 1e-9) / 100
        limit = lim2 if price < lim2 <= A["max_price"] else price
        stake = A["stake_usd"] * p["stake10"] / 10.0
        n = min(int(math.floor(stake / limit + 1e-9)), A["max_contracts"])
        if n < 1 and limit + kalshi_fee(limit, 1) <= A["min_one_usd"]:
            n = 1
        if n < 1:
            continue
        max_cost = n * limit + kalshi_fee(limit, n)
        risk = sum(o[1] for o in open_)
        wk = (p["win"], p["side"])
        if (day_pnl.get(day, 0.0) - risk - max_cost <= -A["daily_loss_usd"]
                or risk + max_cost > A["max_open_risk_usd"]
                or win_side.get(wk, 0) >= A["same_side_per_window"]
                or win_cost.get(p["win"], 0.0) + max_cost > A["window_cap_usd"]
                or coin_day_pnl.get((p["coin"], day), 0.0) <= -A["coin_daily_loss_usd"]
                or coin_day_n.get((p["coin"], day), 0) >= A["coin_trades_per_day"]
                or max_cost > bal):
            continue
        traded.add(p["tk"])                                     # one order per market, filled or not
        coin_day_n[(p["coin"], day)] = coin_day_n.get((p["coin"], day), 0) + 1
        f = entry_fill(p["tk"], p["side"], t, limit)
        if f is None:
            trades.append({"t": t, "filled": False})
            continue
        fp, avail = f
        nf = min(n, int(math.floor(avail + 1e-9)))
        if nf < 1:
            trades.append({"t": t, "filled": False})
            continue
        cost = nf * fp + kalshi_fee(fp, nf)
        if p["xpx"] is not None and exit_fill(p["tk"], p["side"], p["tx"], p["xpx"]):
            pnl = nf * p["xpx"] - kalshi_fee(p["xpx"], nf) - cost
            close_t = p["tx"] + 2
        else:
            pnl = nf * p["res"] - cost
            close_t = p["win"] + 900
        bal -= cost
        win_side[wk] = win_side.get(wk, 0) + 1
        win_cost[p["win"]] = win_cost.get(p["win"], 0.0) + cost
        coin_open_until[p["coin"]] = close_t
        open_.append((close_t, cost, pnl, p["coin"], day))
        trades.append({"t": t, "filled": True, "pnl": pnl, "cost": cost, "close": close_t})
    settle_until(10 ** 12)
    return trades, curve


def stats(trades, curve, t0, t1):
    tr = [x for x in trades if t0 <= x["t"] < t1]
    f = [x for x in tr if x["filled"]]
    p = np.array([x["pnl"] for x in f]) if f else np.zeros(0)
    t = float(p.mean() / p.std(ddof=1) * math.sqrt(len(p))) if len(p) > 2 and p.std(ddof=1) > 0 else None
    return {"pnl": round(float(p.sum()), 2), "trades": len(tr), "filled": len(f), "wins": int((p > 0).sum()),
            "t": round(t, 2) if t is not None else None,
            "staked": round(float(sum(x["cost"] for x in f)), 2)}


def max_dd(curve):
    peak, dd = -1e9, 0.0
    for _, v in curve:
        peak = max(peak, v)
        dd = min(dd, v - peak)
    return round(dd, 2)


# =========================================================================== main
def load_periods(download=True):
    """p1 = lab5's fresh markets (Nov 1-2); p2 = markets since (downloaded into data/kalshi15m/rm)."""
    STATE["progress"].update(stage="loading market data", note="Kalshi prices + Coinbase candles")
    write()
    L.load_fresh(verbose=False)
    L.G["p1"] = {c: ctx for c, ctx in L.G["fresh"].items() if c in COINS}
    seen = {tk for ctx in L.G["p1"].values() for tk in ctx.panel.ticker}
    p1_end = max(int(ctx.open_ts.max()) for ctx in L.G["p1"].values()) + 900
    fresh0 = L.FRESH
    L.FRESH = P2_DIR
    if download:
        STATE["progress"].update(stage="downloading recent markets", note="Nov 2 onwards")
        write()
        L.download(COINS, days=3)
    L.load_fresh(verbose=False)
    L.FRESH = fresh0
    L.G["p2"] = {c: ctx for c, ctx in L.G["fresh"].items() if c in COINS}
    p2_start = min(int(ctx.open_ts[~np.isin(ctx.panel.ticker, list(seen))].min()) for ctx in L.G["p2"].values())
    p2_end = max(int(ctx.open_ts.max()) for ctx in L.G["p2"].values()) + 900
    p1_start = min(int(ctx.open_ts.min()) for ctx in L.G["p1"].values())
    fmt = lambda a, b: f"{datetime.utcfromtimestamp(a):%b %-d %H:%M} – {datetime.utcfromtimestamp(b):%b %-d %H:%M} UTC"
    STATE["periods"] = [{"id": "p1", "label": fmt(p1_start, p1_end), "start": p1_start, "end": p1_end},
                        {"id": "p2", "label": fmt(max(p2_start, p1_end), p2_end), "start": max(p2_start, p1_end),
                         "end": p2_end}]
    return seen


def main(args=None):
    if args and "coins5" in args:
        return main_coins5(args)
    if args and "big" in args:
        return main_big(args)
    download = not (args and "--no-download" in args)
    seen = load_periods(download)
    P = {p["id"]: p for p in STATE["periods"]}
    STATE["progress"].update(stage="backtest positions", note="")
    write()
    per = {}
    for cid, label, src, cfg, ready in CANDS:
        if cfg is None:
            continue
        nm = norm_for(cid, cfg)
        a = positions("p1", cfg, nm)
        b = [p for p in positions("p2", cfg, nm) if p["tk"] not in seen and p["t"] >= P["p2"]["start"]]
        per[cid] = a + b
    per["live_combo"] = live_combo(per)
    STATE["progress"].update(stage="checking every bet against Kalshi's real trades", done=0, total=len(CANDS))
    rows = []
    for k, (cid, label, src, cfg, ready) in enumerate(CANDS):
        pos = per[cid]
        trades, curve = simulate(pos, label)
        s1 = stats(trades, curve, P["p1"]["start"], P["p1"]["end"])
        s2 = stats(trades, curve, P["p2"]["start"], P["p2"]["end"] + 900)
        tot = stats(trades, curve, 0, 10 ** 12)
        nf = tot["filled"]
        tot.update(fill_rate=round(nf / tot["trades"], 3) if tot["trades"] else None,
                   win_rate=round(tot["wins"] / nf, 3) if nf else None, max_dd=max_dd(curve),
                   end_balance=round(curve[-1][1], 2), per_dollar=round(tot["pnl"] / tot["staked"], 3) if tot["staked"] else None)
        ok_both = s1["pnl"] > 0 and s2["pnl"] > 0
        if ok_both and nf >= 20 and (tot["t"] or 0) >= 2.0:
            status, why = "real-money golden", f"profitable in both periods, {nf} filled bets, t {tot['t']}"
        elif tot["pnl"] > 0:
            status = "pass"
            why = ("profitable overall but " + ("not in both periods" if not ok_both else
                   f"only {nf} filled bets" if nf < 20 else f"consistency t {tot['t']} < 2"))
        else:
            status, why = "fail", f"lost ${-tot['pnl']:.2f} with real fills"
        rows.append({"id": cid, "label": label, "source": src, "live_ready": ready,
                     "backtest": {"pnl10": round(sum(p["pnl10"] for p in pos), 2), "trades": len(pos)},
                     "periods": {"p1": s1, "p2": s2}, "total": tot,
                     "curve": curve[:: max(1, len(curve) // 300)] + [curve[-1]], "status": status, "why": why})
        STATE["candidates"] = sorted(rows, key=lambda r: -r["total"]["pnl"])
        STATE["progress"].update(done=k + 1, note=f"finished {label}")
        write()
    pickle.dump(TAPE, open(TAPE_CACHE, "wb"))
    STATE["progress"].update(stage="done", note="")
    write("done")
    for r in STATE["candidates"]:
        print(f"{r['status']:18s} {r['id']:16s} real ${r['total']['pnl']:+7.2f} (p1 {r['periods']['p1']['pnl']:+.2f}, "
              f"p2 {r['periods']['p2']['pnl']:+.2f}) filled {r['total']['filled']}/{r['total']['trades']} "
              f"t {r['total']['t']} | classic $10 backtest ${r['backtest']['pnl10']:+.2f}")
    return STATE["candidates"]


# =========================================================================== the big run (all data)
BIG = ["live_combo", "x_cap:ALL", "scalp:ALL", "x_exit:ALL", "fv_t:ALL", "sized_exit:ALL", "sized:ALL", "x_reentry:ALL"]
OUT_OF_SAMPLE = ("arch", "hold", "recent")


def daily(trades):
    d = {}
    for x in trades:
        if x["filled"]:
            k = int(x["t"] // 86400)
            d[k] = d.get(k, 0.0) + x["pnl"]
    v = np.array(list(d.values())) if d else np.zeros(0)
    return {"days": int(len(v)), "winning_days": int((v > 0).sum()), "worst_day": round(float(v.min()), 2) if len(v) else None,
            "best_day": round(float(v.max()), 2) if len(v) else None}


def summarise_big(res, trades_by, per, periods, cands):
    rows = []
    done_ids = [p["id"] for p in periods if all(p["id"] in res[c] for c in res)]
    for cid in BIG:
        _, label, src, cfg, ready = cands[cid]
        have = [p["id"] for p in periods if p["id"] in res[cid]]
        oos_ids = [i for i in have if i in OUT_OF_SAMPLE]
        allt = [x for i in oos_ids for x in trades_by[cid][i]]
        pn = np.array([x["pnl"] for x in allt]) if allt else np.zeros(0)
        t_oos = float(pn.mean() / pn.std(ddof=1) * math.sqrt(len(pn))) if len(pn) > 2 and pn.std(ddof=1) > 0 else None
        tot_trades = sum(res[cid][i]["trades"] for i in oos_ids)
        nf = len(pn)
        staked = sum(res[cid][i]["staked"] for i in oos_ids)
        tot = {"pnl": round(float(pn.sum()), 2), "trades": tot_trades, "filled": nf,
               "fill_rate": round(nf / tot_trades, 3) if tot_trades else None,
               "wins": int((pn > 0).sum()), "win_rate": round(float((pn > 0).mean()), 3) if nf else None,
               "t": round(t_oos, 2) if t_oos is not None else None,
               "max_dd": min((res[cid][i]["max_dd"] for i in oos_ids), default=None),
               "end_balance": round(ACCOUNT["start_balance"] + float(pn.sum()), 2),
               "per_dollar": round(float(pn.sum()) / staked, 3) if staked else None,
               "scope": "out-of-sample periods tested so far: " + ", ".join(oos_ids)}
        chain, cum = [], 0.0
        for i in [p["id"] for p in periods if p["id"] in have]:
            for x in sorted(trades_by[cid][i], key=lambda x: x["close"]):
                cum += x["pnl"]
                chain.append([int(x["close"]), round(ACCOUNT["start_balance"] + cum, 4)])
        all_oos = [p["id"] for p in periods if p["id"] in OUT_OF_SAMPLE]
        complete = all(i in have for i in all_oos)
        all_pos = all(res[cid][i]["pnl"] > 0 for i in oos_ids)
        if complete and all_pos and nf >= 100 and (t_oos or 0) >= 2.0:
            status, why = "real-money golden", (f"profitable in every out-of-sample period, {nf} filled bets, "
                                                f"consistency t {t_oos:.2f}")
        elif tot["pnl"] > 0:
            bad = [p["label"] for p in periods if p["id"] in oos_ids and res[cid][p["id"]]["pnl"] <= 0]
            status = "pass"
            why = ("lost in: " + "; ".join(bad) if bad else
                   f"consistency t {t_oos:.2f} < 2" if (t_oos or 0) < 2 else
                   "not all out-of-sample periods tested yet" if not complete else f"only {nf} filled bets")
        else:
            status, why = "fail", f"lost ${-tot['pnl']:.2f} out of sample with real fills"
        rows.append({"id": cid, "label": label, "source": src, "live_ready": ready,
                     "backtest": {"pnl10": round(sum(res[cid][i]["backtest_pnl10"] for i in oos_ids), 2),
                                  "trades": sum(len(per[cid].get(i, [])) for i in oos_ids)},
                     "periods": res[cid], "total": tot, "curve": chain[:: max(1, len(chain) // 300)] + chain[-1:],
                     "status": status, "why": why})
    return sorted(rows, key=lambda r: -r["total"]["pnl"])


def main_big(args=None):
    """Every period with data: the Jul-Aug archive (SOL/NEAR/DOGE), the Sep 1 - Oct 17 search window (in-sample:
    the rules' settings were chosen there), the Oct 18 - Nov 1 final exam, and Nov 1-4. Each period is its own
    fresh $4.43 account. Verdict from the out-of-sample periods only."""
    global OUT
    OUT = ROOT / "data" / "lab" / "realmoney_results.json"
    from . import lab3
    STATE["progress"].update(stage="loading 2 months of market data", done=0, total=len(BIG), note="")
    write()
    lab3.G["quick"] = 0
    lab3.load(verbose=False)
    seen = load_periods(download=False)
    rec_start, rec_end = STATE["periods"][0]["start"], STATE["periods"][1]["end"]
    p2_start = STATE["periods"][1]["start"]
    span = lambda where: (min(int(c.open_ts.min()) for c in L.G[where].values() if len(c)),
                          max(int(c.open_ts.max()) for c in L.G[where].values() if len(c)) + 900)
    fmt = lambda a, b: f"{datetime.utcfromtimestamp(a):%b %-d} – {datetime.utcfromtimestamp(b):%b %-d}"
    periods = []
    arch_coins = [c for c in L.G.get("arch", {}) if c in COINS]
    ARCH_FROM = 1782864000                      # 2026-07-01: the last two archive months (time budget)
    if arch_coins:
        a0, a1 = span("arch")
        a0 = max(a0, ARCH_FROM)
        periods.append({"id": "arch", "label": f"{fmt(a0, a1)} archive ({', '.join(c[2:-3] for c in arch_coins)})",
                        "start": a0, "end": a1})
    s0, s1 = span("search")
    periods.append({"id": "search", "label": f"{fmt(s0, s1)} (in-sample: settings were chosen here)", "start": s0, "end": s1})
    h0, h1 = span("hold")
    periods.append({"id": "hold", "label": f"{fmt(h0, h1)} final exam", "start": h0, "end": h1})
    periods.append({"id": "recent", "label": f"{fmt(rec_start, rec_end)} newest", "start": rec_start, "end": rec_end})
    STATE["periods"] = periods
    STATE["candidates"] = []
    write()

    def where_positions(cfg, nm):
        out = {}
        for pid, wh in (("arch", "arch"), ("search", "search"), ("hold", "hold")):
            if pid in [p["id"] for p in periods]:
                out[pid] = [p for p in positions(wh, cfg, nm) if p["coin"] in COINS
                            and (pid != "arch" or p["t"] >= ARCH_FROM)]
        a = positions("p1", cfg, nm)
        b = [p for p in positions("p2", cfg, nm) if p["tk"] not in seen and p["t"] >= p2_start]
        out["recent"] = sorted(a + b, key=lambda p: (p["t"], p["coin"]))
        return out

    cands = {c[0]: c for c in CANDS}
    per = {}
    for cid in BIG:
        if cid == "live_combo":
            continue
        _, label, src, cfg, ready = cands[cid]
        per[cid] = where_positions(cfg, norm_for(cid, cfg))
    per["live_combo"] = {pid: live_combo({r: per[r][pid] for r in LIVE_ORDER}) for pid in per["x_exit:ALL"]}
    need = len({(p["tk"], p["t"]) for c in per.values() for v in c.values() for p in v} - set(TAPE))
    STATE["progress"].update(stage="checking every bet against Kalshi's real trades",
                             note=f"about {need} trade-record lookups to do")
    write()
    ORDER = [pid for pid in ("hold", "recent", "arch", "search") if pid in [p["id"] for p in periods]
             and not (pid == "search" and COINS == COINS5)]
    res = {cid: {} for cid in BIG}
    trades_by = {cid: {} for cid in BIG}
    STATE["progress"].update(total=len(BIG) * len(ORDER), done=0)
    step = 0
    for pid in ORDER:
        plabel = next(p["label"] for p in periods if p["id"] == pid)
        for cid in BIG:
            _, label, src, cfg, ready = cands[cid]
            pos = per[cid].get(pid, [])
            trades, curve = simulate(pos, f"{plabel} · {label}")
            s_ = stats(trades, curve, 0, 10 ** 12)
            s_.update(daily(trades), max_dd=max_dd(curve), backtest_pnl10=round(sum(x["pnl10"] for x in pos), 2))
            res[cid][pid] = s_
            trades_by[cid][pid] = [x for x in trades if x["filled"]]
            step += 1
            STATE["progress"].update(done=step, note=f"finished {label} on {plabel}")
            STATE["candidates"] = summarise_big(res, trades_by, per, periods, cands)
            write()
            pickle.dump(TAPE, open(TAPE_CACHE, "wb"))
    STATE["progress"].update(stage="done", note="")
    write("done")
    for r in STATE["candidates"]:
        print(f"{r['status']:18s} {r['id']:16s} out-of-sample ${r['total']['pnl']:+8.2f} t {r['total']['t']} "
              f"filled {r['total']['filled']}/{r['total']['trades']} | " +
              " ".join(f"{i} {v['pnl']:+.2f}" for i, v in r["periods"].items()))
    return STATE["candidates"]



# =========================================================================== 5-coin re-test (Nov 5)
COINS5 = ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXZEC15M"]
LIVE5 = ["x_reentry:ALL", "x_exit:ALL", "sized_exit:ALL", "sized:ALL", "fv_t:ALL"]   # real_best_live.json order


def main_coins5(args=None):
    """The real-money test again, on only the coins whose live Coinbase data equals the final candles the
    backtests use (BTC, ETH, SOL, XRP, ZEC: checked live Nov 5; NEAR, HYPE, DOGE and BNB candles include trades
    the public trade feed never shows). Out-of-sample periods only (final exam, newest; the archive has SOL)."""
    global COINS, BIG, LIVE_ORDER
    COINS = COINS5
    LIVE_ORDER = LIVE5
    BIG = ["live_combo"] + LIVE5
    for i, c in enumerate(CANDS):
        if c[0] == "live_combo":
            CANDS[i] = ("live_combo", "Current live setup (x_reentry, x_exit, sized_exit, sized, fv_t)", "live", None, True)
    return main_big(args)
