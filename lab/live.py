"""Paper prop-firm bot: trades the Lab's surviving NAS100 strategies day by day on simulated prop accounts.

    python -m lab.live config     # once: freeze the strategies (needs experiments/lab/raw.npy)
    python -m lab.live            # refresh data, replay every day since START, write experiments/lab_live.json + terminal/data.js

The strategies are the two biggest surviving families from the search (NAS100 NY time-of-day momentum and open candle),
two representatives each, chosen on train + valid evidence only. Rules are frozen in lab/live_config.json; never edit
them because of a few losing days.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from . import data as D

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path(__file__).with_name("live_config.json")
OUT = ROOT / "experiments" / "lab_live.json"
APP = ROOT / "terminal"
START = "2026-11-02"      # first paper session
LIVE_FROM = "2026-11-25"  # sessions before this were replayed from recorded data the day the bot was built

ACCOUNTS = [
    {"name": "FTMO 2-step 100k", "kind": "cfd", "size": 100_000, "dd": 10_000, "daily": 5_000, "targets": [10_000, 5_000], "min_days": 4,
     "fee": 540, "monthly": 0, "activation": 0, "refund": True, "split": 0.8, "eval_risk": 0.15, "funded_risk": 0.20, "payout_every": 14},
    {"name": "Topstep 50k", "kind": "futures", "size": 50_000, "dd": 2_000, "daily": 1_000, "targets": [3_000], "min_days": 2,
     "fee": 49, "monthly": 49, "activation": 149, "refund": False, "split": 0.9, "eval_risk": 0.15, "funded_risk": 0.20,
     "max_micros": 50, "consistency": 0.5, "win_days": 5, "win_day_min": 150, "payout_cap": 2_000, "payout_frac": 0.5},
]


def make_config() -> None:
    from .report import dedupe
    raw = np.load(ROOT / "experiments" / "lab" / "raw.npy", allow_pickle=True)[0]
    clusters: dict = {}
    for c in dedupe(raw["cands"]):
        clusters.setdefault((c["inst"], c["sess"], c["spec"]["family"]), []).append(c)
    fams = sorted([v for v in clusters.values() if len(v) >= 3], key=lambda v: -len(v))[:2]
    strats = [{"id": f"{v[0]['spec']['family']}-{i + 1}", "inst": c["inst"], "sess": c["sess"], "spec": c["spec"], "cfg": [float(x) for x in c["cfg"]],
               "desc": c["desc"], "train": c["train"], "valid": c["valid"], "test": c["test"]} for v in fams for i, c in enumerate(v[:2])]
    CONFIG.write_text(json.dumps({"strategies": strats}, indent=1, default=float))
    print("wrote", CONFIG, [s["id"] for s in strats])


def refresh() -> None:
    """Best effort: newest HistData month and any new Dukascopy days, then rebuild the NAS100 matrix."""
    import pandas as pd
    now = pd.Timestamp.now(tz="UTC")
    try:
        p = D.RAW / f"{D.INSTRUMENTS['NAS100'].pair}_{now.year}_{now.month:02d}.zip"
        old = p.read_bytes() if p.exists() else None
        if p.exists():
            p.unlink()
        D.download(["NAS100"])
        if not p.exists() and old:
            p.write_bytes(old)
    except Exception as e:  # noqa: BLE001
        print("histdata refresh failed:", e)
    try:
        from nyopen import data as ND
        ND.download((now - pd.Timedelta(days=12)).date(), now.date(), verbose=False)
    except Exception as e:  # noqa: BLE001
        print("dukascopy refresh failed:", e)
    D.build(["NAS100"])
    D._CACHE.clear()


def collect(cfg: dict) -> tuple[list[dict], list[dict], list[str]]:
    """All looks and trades since START. A look is one strategy checking one session."""
    from .kernel import trades
    from .report import signal
    from .search import UNIT
    from .signals import SESSIONS, bars5
    z = D.load("NAS100"); bars5(z)
    days = z["days"].astype("datetime64[D]")
    keep = np.where(days >= np.datetime64(START))[0]
    looks, out = [], []
    qf, nf, upm, lev = UNIT["NAS100"]
    for s in cfg["strategies"]:
        t, dr, ref = signal(s["inst"], s["sess"], s["spec"])
        R, MAE, MFE, SD, PX, TX = trades(z["O"], z["H"], z["L"], z["C"], z["atr5"], t, dr, ref, SESSIONS[s["sess"]][1], D.INSTRUMENTS["NAS100"].cost, np.array(s["cfg"]))
        for i in keep:
            took = bool(SD[i] > 0)
            looks.append({"day": str(days[i]), "strategy": s["id"], "traded": took})
            if took:
                out.append({"day": str(days[i]), "strategy": s["id"], "minute": int(t[i]), "dir": int(dr[i]), "entry": float(PX[i]), "stop_dist": float(SD[i]),
                            "exit_minute": int(TX[i]), "r": float(R[i]), "mae": float(MAE[i]), "rpu": float(np.ravel(SD[i] * qf(PX[i:i + 1]))[0]), "upm": float(upm)})
    out.sort(key=lambda x: (x["day"], x["minute"]))
    return looks, out, [str(days[i]) for i in keep]


def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def run_account(a: dict, trades_: list[dict], days: list[str]) -> dict:
    st = {"attempt": 0, "fees": 0.0, "payouts": 0.0, "passed": 0, "failed": 0}
    events, curve, tlog = [], [], []
    acc: dict = {}

    def new_attempt(day: str) -> None:
        st["attempt"] += 1
        st["fees"] += a["fee"]
        acc.clear()
        acc.update(phase=0, funded=False, bal=float(a["size"]), floor=float(a["size"] - a["dd"]), peak=float(a["size"]), days=0, best_day=0.0,
                   win_days=0, last_payout=day, start_day=day, month_mark=day, refunded=False)
        events.append({"day": day, "type": "buy", "text": f"Evaluation #{st['attempt']} bought (${a['fee']})"})

    new_attempt(days[0])
    by_day: dict = {}
    for t in trades_:
        by_day.setdefault(t["day"], []).append(t)
    for day in days:
        if acc.get("dead"):
            new_attempt(day)
        d0 = acc["bal"]; halted = False; n = 0
        if a["monthly"] and not acc["funded"] and (np.datetime64(day) - np.datetime64(acc["month_mark"])).astype(int) >= 30:
            st["fees"] += a["monthly"]; acc["month_mark"] = day
        for t in by_day.get(day, []):
            if halted or acc.get("dead"):
                break
            room = acc["bal"] - acc["floor"]
            day_room = a["daily"] - (d0 - acc["bal"])
            risk = (a["funded_risk"] if acc["funded"] else a["eval_risk"]) * a["dd"]
            risk = min(risk, 0.5 * room if acc["funded"] else room, day_room)
            if a["kind"] == "futures":
                per_micro = t["rpu"] * t["upm"]
                micros = int(min(a["max_micros"], risk // per_micro))
                if micros < 1:
                    continue
                risk = micros * per_micro; size = f"{micros} MNQ"
            else:
                if risk <= 0:
                    continue
                size = f"{risk / t['rpu']:.2f} units"
            pnl = t["r"] * risk
            low = acc["bal"] + min(t["r"], -abs(t["mae"]), 0.0) * risk
            acc["bal"] += pnl; n += 1
            tlog.append({"day": day, "time": hhmm(t["minute"]), "exit": hhmm(t["exit_minute"]), "strategy": t["strategy"], "side": "long" if t["dir"] > 0 else "short",
                         "entry": round(t["entry"], 1), "size": size, "risk": round(risk), "r": round(t["r"], 2), "pnl": round(pnl), "attempt": st["attempt"],
                         "phase": "funded" if acc["funded"] else f"eval {acc['phase'] + 1}", "live": day >= LIVE_FROM})
            if a["kind"] == "cfd" and (low <= acc["floor"] or d0 - min(low, acc["bal"]) >= a["daily"]):
                acc["dead"] = True
            if a["kind"] == "futures" and d0 - acc["bal"] >= a["daily"]:
                halted = True
        pnl_day = acc["bal"] - d0
        if n:
            acc["days"] += 1
            acc["best_day"] = max(acc["best_day"], pnl_day)
            if acc["funded"] and pnl_day >= a.get("win_day_min", 0):
                acc["win_days"] += 1
        if acc["bal"] <= acc["floor"]:
            acc["dead"] = True
        if a["kind"] == "futures" and not acc.get("dead"):  # end-of-day trailing floor, stops at the start balance
            acc["peak"] = max(acc["peak"], acc["bal"])
            acc["floor"] = min(max(acc["floor"], acc["peak"] - a["dd"]), float(a["size"]))
        if acc.get("dead"):
            st["failed"] += 1
            events.append({"day": day, "type": "fail", "text": f"{'Funded account' if acc['funded'] else 'Evaluation'} #{st['attempt']} lost"})
        elif not acc["funded"]:
            prof = acc["bal"] - a["size"]
            cons_ok = (not a.get("consistency")) or acc["best_day"] <= a["consistency"] * max(prof, 1)
            if prof >= a["targets"][acc["phase"]] and acc["days"] >= a["min_days"] and cons_ok:
                if acc["phase"] + 1 < len(a["targets"]):
                    acc.update(phase=acc["phase"] + 1, bal=float(a["size"]), days=0, best_day=0.0)
                    events.append({"day": day, "type": "pass", "text": f"Phase {acc['phase']} passed on attempt #{st['attempt']}"})
                else:
                    st["passed"] += 1; st["fees"] += a["activation"]
                    acc.update(funded=True, bal=float(a["size"]), floor=float(a["size"] - a["dd"]), peak=float(a["size"]), days=0, win_days=0, last_payout=day)
                    events.append({"day": day, "type": "funded", "text": f"Attempt #{st['attempt']} passed: funded account opened"})
        else:
            prof = acc["bal"] - a["size"]
            pay = 0.0
            if a["kind"] == "cfd" and prof > 0 and (np.datetime64(day) - np.datetime64(acc["last_payout"])).astype(int) >= a["payout_every"]:
                pay = prof
            if a["kind"] == "futures" and acc["win_days"] >= a["win_days"] and prof > 0:
                pay = min(prof * a["payout_frac"], a["payout_cap"])
            if pay > 0:
                got = pay * a["split"] + (a["fee"] if a["refund"] and not acc["refunded"] else 0)
                acc["refunded"] = True
                st["payouts"] += got; acc["bal"] -= pay; acc["win_days"] = 0; acc["last_payout"] = day
                events.append({"day": day, "type": "payout", "text": f"Payout ${got:,.0f}"})
        curve.append({"day": day, "bal": round(acc["bal"], 2), "floor": round(acc["floor"], 2), "pnl": round(pnl_day, 2), "attempt": st["attempt"],
                      "phase": "funded" if acc["funded"] else f"eval {acc['phase'] + 1}", "live": day >= LIVE_FROM})
    target = None if acc["funded"] else a["size"] + a["targets"][acc["phase"]]
    return {"name": a["name"], "rules": {k: a[k] for k in ("size", "dd", "daily", "targets", "fee", "split", "eval_risk", "funded_risk")},
            "status": "lost, new evaluation next session" if acc.get("dead") else ("funded" if acc["funded"] else f"evaluation phase {acc['phase'] + 1}"),
            "balance": round(acc["bal"], 2), "floor": round(acc["floor"], 2), "target": target, "attempts": st["attempt"], "passed": st["passed"], "failed": st["failed"],
            "fees": round(st["fees"], 2), "payouts": round(st["payouts"], 2), "net": round(st["payouts"] - st["fees"], 2),
            "win_days": acc["win_days"] if acc["funded"] else None, "curve": curve, "events": events, "trades": tlog}


def run(do_refresh: bool = True) -> dict:
    cfg = json.loads(CONFIG.read_text())
    if do_refresh:
        refresh()
    looks, tr, days = collect(cfg)
    r = np.array([t["r"] for t in tr]) if tr else np.zeros(0)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    per = {}
    for s in cfg["strategies"]:
        rs = np.array([t["r"] for t in tr if t["strategy"] == s["id"]])
        per[s["id"]] = {"desc": s["desc"], "looks": sum(1 for l in looks if l["strategy"] == s["id"]), "trades": int(len(rs)),
                        "sum_r": float(rs.sum()) if len(rs) else 0.0, "backtest_r": {"train": s["train"]["mean"], "valid": s["valid"]["mean"], "test": s["test"]["mean"]}}
    out = {"start": START, "live_from": LIVE_FROM, "last_session": days[-1] if days else None, "sessions": len(days), "live_sessions": sum(1 for d in days if d >= LIVE_FROM),
           "looks": len(looks), "trades": len(tr), "expectancy_r": float(r.mean()) if len(r) else 0.0, "sum_r": float(r.sum()), "win_rate": float((r > 0).mean()) if len(r) else 0.0,
           "pf": float(wins / losses) if losses > 0 else None, "strategies": per, "accounts": [run_account(a, tr, days) for a in ACCOUNTS] if days else [],
           "day_log": [{"day": d, "live": d >= LIVE_FROM, "looks": sum(1 for l in looks if l["day"] == d), "trades": sum(1 for t in tr if t["day"] == d),
                        "r": round(sum(t["r"] for t in tr if t["day"] == d), 2)} for d in days]}
    OUT.write_text(json.dumps(out, indent=1))
    APP.mkdir(exist_ok=True)
    (APP / "data.js").write_text("window.TERMINAL_DATA = " + json.dumps(out) + ";\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "config":
        make_config()
    else:
        o = run("--no-refresh" not in sys.argv)
        print(f"sessions {o['sessions']} ({o['live_sessions']} live) last {o['last_session']} | looks {o['looks']} trades {o['trades']} | sum {o['sum_r']:+.2f}R exp {o['expectancy_r']:+.3f}R")
        for a in o["accounts"]:
            print(f"  {a['name']}: {a['status']}, balance {a['balance']:,.0f}, attempts {a['attempts']}, passed {a['passed']}, fees {a['fees']:.0f}, payouts {a['payouts']:.0f}, net {a['net']:+.0f}")
            for e in a["events"]:
                print("    ", e["day"], e["text"])
