"""ZEC forward test: the gate before scalp:KXZEC15M may trade real money (python -m kalshi15m zecfwd).

Every run
  1. downloads the ZEC markets that settled since FWD_START (the end of all data the rule was chosen or checked
     on), with their 1-minute Kalshi candles, plus ZEC and BTC Coinbase 1-minute bars, into data/kalshi15m/fwd/;
  2. replays the frozen rule on those markets exactly as the backtest does (lab3 signal + execute);
  3. counts a bet only if Kalshi's trade records show it would have filled: labrm.simulate with the real-money
     test's account and limits, the order arriving 1-3 s after the decision, early sales checked the same way.
     This is the same check the rule already passed on the exam days (Oct 17 - Nov 4);
  4. checks the paper run (real_zec_dry.json -> data/kalshi15m/real_zec_dry_log.jsonl): were its orders the
     replay's bets, and would they have filled;
  5. grades the gate below and writes data/lab/zec_forward.json (shown on the app's Real money tab).

The gate was fixed on Nov 5 before any forward data was looked at. ALL must hold:
  - at least 7 forward days and 30 forward bets that would have filled;
  - the forward bets made money;
  - every out-of-sample bet so far (exam days + newest days + forward) taken together has t >= 1.65
    (one-sided 95%: unlikely to be luck);
  - where the paper run was running, at least 90% of its orders were bets the replay also made (once it has 10).
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as D
from . import labrm as R

ROOT = Path(__file__).resolve().parent.parent
LABDIR = ROOT / "data" / "lab"
FWD_DIR = ROOT / "data" / "kalshi15m" / "fwd"
OUT = LABDIR / "zec_forward.json"
OOS_CACHE = LABDIR / "zec_oos_bets.json"
PAPER_LOG = ROOT / "data" / "kalshi15m" / "real_zec_dry_log.jsonl"
COIN, REF, RULE_ID = "KXZEC15M", "KXBTC15M", "scalp:KXZEC15M"
# 2026-11-04 20:15 UTC: the end of labrm's newest period, the last data the rule was ever run on
FWD_START = 1793823300
GATE = {"min_days": 7, "min_filled": 30, "t_all": 1.65, "paper_agree": 0.90, "paper_min": 10}
ACCOUNT_X = {"start_balance": 11.90, "min_balance": 6.0}       # as labx validate (the rule's tape check)
SPOT_LOOKBACK = 15 * 86400


def _rule():
    from . import golden_live as GL
    r = GL.RULES[RULE_ID]
    return {"family": r["family"], "params": r["params"]}


# --------------------------------------------------------------------------- 1. data
def fetch(log=print):
    FWD_DIR.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    mk = D.fetch_markets(COIN, max(1, math.ceil((now - FWD_START) / 86400) + 1))
    mk = mk[mk.open_ts >= FWD_START].reset_index(drop=True) if len(mk) else mk
    mpath, cpath = FWD_DIR / f"{COIN}_markets.csv", FWD_DIR / f"{COIN}_candles.csv"
    old_mk = pd.read_csv(mpath) if mpath.exists() else pd.DataFrame(columns=mk.columns)
    old_cd = pd.read_csv(cpath) if cpath.exists() else pd.DataFrame()
    mk = pd.concat([old_mk, mk], ignore_index=True).drop_duplicates("ticker").sort_values("open_ts")
    have = set(old_cd.ticker) if len(old_cd) else set()
    new = mk[~mk.ticker.isin(have)]
    if len(new):            # settled markets' candles never change: fetch each market once
        cd = D.fetch_candles(COIN, new)
        old_cd = pd.concat([old_cd, cd], ignore_index=True) if len(old_cd) else cd
    mk.to_csv(mpath, index=False)
    old_cd.drop_duplicates(["ticker", "ts"]).to_csv(cpath, index=False)
    for series in (COIN, REF):
        sp_path = FWD_DIR / f"{series}_spot.csv"
        sp = pd.read_csv(sp_path) if sp_path.exists() else pd.DataFrame(columns=["ts", "low", "high", "open", "close", "volume"])
        t0 = int(sp.ts.max()) + 60 if len(sp) else FWD_START - SPOT_LOOKBACK
        if t0 < now - 120:
            sp = pd.concat([sp, D.fetch_spot(D.SERIES[series], t0, now - 60)], ignore_index=True)
        sp.drop_duplicates("ts").sort_values("ts").to_csv(sp_path, index=False)
    log(f"forward data: {len(mk)} ZEC markets since {pd.to_datetime(FWD_START, unit='s')} UTC, "
        f"{len(new)} new")
    return mk


# --------------------------------------------------------------------------- 2-3. replay + tape check
def _sim(pos, label):
    from . import labx
    R.OUT = LABDIR / "zec_forward_progress.json"     # never the Real money tab's results file
    R.ACCOUNT.update(ACCOUNT_X)
    return labx._sim(pos, label)


def _bets(trades):
    return [{"t": int(x["t"]), "tk": x.get("tk"), "pnl": round(float(x["pnl"]), 4)} for x in trades if x["filled"]]


def oos_bets(log=print):
    """The rule's exam-day and newest-day bets on Kalshi's trade tape (as labx validate), computed once."""
    if OOS_CACHE.exists():
        return json.loads(OOS_CACHE.read_text())
    from . import lab3, labx
    from . import lab5 as L
    lab3.REAL = False
    lab3.G["quick"] = 0
    lab3._SPOT.clear()
    lab3.load(verbose=False)
    R.OUT = LABDIR / "zec_forward_progress.json"
    seen = R.load_periods(download=False)
    p2_start = R.STATE["periods"][1]["start"]
    rule = _rule()
    per = {"exam": labx._positions_from_lab3(lab3.run_rule("hold", COIN, rule))}
    rec = []
    for wh in ("p1", "p2"):
        if L.G.get(wh):
            lab3.G[wh] = L.G[wh]
            ps = labx._positions_from_lab3(lab3.run_rule(wh, COIN, rule))
            rec += [p for p in ps if wh == "p1" or (p["tk"] not in seen and p["t"] >= p2_start)]
    per["recent"] = sorted(rec, key=lambda p: (p["t"], p["coin"]))
    out = {}
    for pid, pos in per.items():
        s, trades, _ = _sim(pos, f"zec {pid}")
        out[pid] = {"stats": s, "bets": _bets(trades)}
        log(f"  {pid}: ${s['pnl']:+.2f}, {s['filled']} of {s['bets']} filled, t {s['t']}")
    lab3._SPOT.clear()
    labx.pickle_tape()
    OOS_CACHE.write_text(json.dumps(out, default=float))
    return out


def forward_positions():
    from . import backtest as B
    from . import lab2, lab3, labx
    lab3.REAL = False
    lab3._SPOT.clear()
    lab3._SPOT[(COIN, "main")] = lab3.Spot(FWD_DIR / f"{COIN}_spot.csv")
    lab3._SPOT[(REF, "main")] = lab3.Spot(FWD_DIR / f"{REF}_spot.csv")
    try:
        with lab2._source(FWD_DIR):
            p = B.Panel(B.build_panel(COIN))
        lab3.add_features(p, COIN, "main")
        ctx = lab3.Ctx(COIN, p.subset(np.asarray(p.open_ts, np.int64) >= FWD_START))
        lab3.G["fwd"] = {COIN: ctx}
        df = lab3.run_rule("fwd", COIN, _rule())
    finally:
        lab3._SPOT.clear()
    return (labx._positions_from_lab3(df) if len(df) else []), len(ctx)


# --------------------------------------------------------------------------- 4. paper run
def paper(pos):
    """The paper run's orders: same as the replay's bets? would they have filled on the tape?"""
    if not PAPER_LOG.exists():
        return {"orders": 0}
    ev = []
    for line in PAPER_LOG.read_text().splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            ev.append(e)
    starts = [e["ts"] for e in ev if e.get("event") == "start"]
    orders = [e for e in ev if e.get("event") == "would_order" and e.get("ticker")]
    rep = {p["tk"]: p for p in pos}
    agree, fills, rows = 0, 0, []
    for e in orders:
        tk, side, minute = e["ticker"], e.get("side"), e.get("minute")
        r = rep.get(tk)
        same = bool(r and r["side"] == side and r["minute"] == minute)
        agree += same
        open_ts = r["win"] if r else None
        t = (open_ts + 60 * minute) if open_ts else int(e["ts"])
        yes_px = float((e.get("order") or {}).get("price") or "nan")
        limit = yes_px if side == "yes" else 1 - yes_px
        f = R.entry_fill(tk, side, int(t), limit) if math.isfinite(limit) else None
        fills += f is not None
        rows.append({"ticker": tk, "side": side, "minute": minute, "same_as_replay": same, "would_fill": f is not None,
                     "ts": int(e["ts"])})
    return {"orders": len(orders), "agree": agree, "would_fill": fills, "first_start": min(starts) if starts else None,
            "last_event": int(max(e["ts"] for e in ev)) if ev else None, "recent": rows[-20:]}


# --------------------------------------------------------------------------- 5. gate
def _t(v):
    v = np.asarray(v, float)
    return float(v.mean() / v.std(ddof=1) * math.sqrt(len(v))) if len(v) > 2 and v.std(ddof=1) > 0 else None


def run(download=True, log=print):
    from . import labx
    if download:
        fetch(log)
    base = oos_bets(log)
    pos, n_mk = forward_positions()
    s, trades, curve = _sim(pos, "zec forward") if pos else ({"pnl": 0.0, "bets": 0, "filled": 0, "t": None,
                                                               "days": 0, "winning_days": 0}, [], [])
    labx.pickle_tape()
    fb = _bets(trades)
    days = (int(time.time()) - FWD_START) / 86400
    allb = [b["pnl"] for k in ("exam", "recent") for b in base[k]["bets"]] + [b["pnl"] for b in fb]
    t_all = _t(allb)
    pp = paper(pos)
    daily = {}
    for b in fb:
        d = pd.to_datetime(b["t"], unit="s").strftime("%Y-%m-%d")
        daily[d] = round(daily.get(d, 0.0) + b["pnl"], 4)
    checks = [
        {"id": "days", "label": f"At least {GATE['min_days']} forward days", "ok": days >= GATE["min_days"],
         "value": round(days, 1)},
        {"id": "filled", "label": f"At least {GATE['min_filled']} forward bets that would have filled",
         "ok": s["filled"] >= GATE["min_filled"], "value": s["filled"]},
        {"id": "profit", "label": "Forward bets made money", "ok": s["filled"] > 0 and s["pnl"] > 0,
         "value": round(s["pnl"], 2)},
        {"id": "t_all", "label": f"All out-of-sample bets together: t of at least {GATE['t_all']}",
         "ok": t_all is not None and t_all >= GATE["t_all"], "value": None if t_all is None else round(t_all, 2)},
        {"id": "paper", "label": f"Paper run's orders match the replay ({GATE['paper_agree']:.0%}, once it has "
                                 f"{GATE['paper_min']})",
         "ok": pp.get("orders", 0) >= GATE["paper_min"] and pp["agree"] / pp["orders"] >= GATE["paper_agree"],
         "value": f"{pp.get('agree', 0)} of {pp.get('orders', 0)}"},
    ]
    ready = all(c["ok"] for c in checks)
    lost = s["filled"] >= GATE["min_filled"] and days >= GATE["min_days"] and s["pnl"] <= 0
    out = {"generated": int(time.time()), "rule": RULE_ID, "fwd_start": FWD_START, "gate": GATE,
           "status": "ready" if ready else ("failed" if lost else "waiting"),
           "checks": checks, "forward": {**s, "markets": n_mk, "daily": daily, "curve": curve[-300:]},
           "exam": base["exam"]["stats"], "recent": base["recent"]["stats"],
           "all_oos": {"bets": len(allb), "pnl": round(float(sum(allb)), 2), "t": None if t_all is None else round(t_all, 2)},
           "paper": pp}
    OUT.write_text(json.dumps(out, indent=1, default=float))
    log(f"ZEC forward: {s['filled']} of {s['bets']} bets filled over {days:.1f} days, ${s['pnl']:+.2f}, "
        f"t {s['t']}; all out-of-sample {len(allb)} bets t {out['all_oos']['t']}; paper {pp.get('orders', 0)} "
        f"orders ({pp.get('agree', 0)} same as replay); status {out['status']}")
    for c in checks:
        log(f"  [{'x' if c['ok'] else ' '}] {c['label']}: {c['value']}")
    return out


def main(args=None):
    run(download=not (args and "--no-download" in args))
