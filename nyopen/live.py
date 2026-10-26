"""Live paper evaluation of the eval-farming method on NAS100, from near-real-time Dukascopy ticks.

Account: Lucid Flex 50k evaluation. Target +$3,000, $2,000 end-of-day trailing drawdown, best day <= 50% of profit.
Method (from the Andy Trades video): every trade risks the whole remaining drawdown, stop 2x the 09:30 candle's
risk, target 0.75x the stop, no breakeven. Signal: the 09:30 New York 5-minute candle closes above the 12 EMA -> long,
below -> short. Trades NQ ($20/pt) + MNQ ($2/pt); 1 point of costs.

    python -m nyopen.live --session 2026-10-27        # run any time after ~10:05 New York; rerun after ~16:05
State lives in experiments/live_eval.json; the app data in live/data.js.
"""
from __future__ import annotations

import argparse
import json
import lzma
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import data as data_mod
from .strategy import ema

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "experiments" / "live_eval.json"
APP = ROOT / "live" / "data.js"
H = {"User-Agent": "Mozilla/5.0 (research)"}
TARGET, DD, CONS, STOP_MULT, RR, COST_PTS = 3000.0, 2000.0, 0.5, 2.0, 0.75, 1.0
EXIT_HHMM = 1530


def fetch_hour(d: date, hour: int) -> pd.DataFrame | None:
    url = f"https://datafeed.dukascopy.com/datafeed/USATECHIDXUSD/{d.year}/{d.month - 1:02d}/{d.day:02d}/{hour:02d}h_ticks.bi5"
    import time
    r = None
    for attempt in range(6):
        try:
            r = requests.get(url, headers=H, timeout=40)
            if r.status_code in (200, 404):
                break
        except requests.RequestException:
            r = None
        time.sleep(2 * (attempt + 1))
    if r is None or r.status_code != 200 or r.content[:5] == b"<!DOC":
        return None
    if not r.content:
        return pd.DataFrame(columns=["time", "bid", "vol"])
    raw = lzma.decompress(r.content)
    a = np.frombuffer(raw[: len(raw) // 20 * 20], dtype=np.dtype(">u4, >u4, >u4, >f4, >f4"))
    t0 = pd.Timestamp(datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc))
    return pd.DataFrame({"time": t0 + pd.to_timedelta(a["f0"].astype("int64"), unit="ms"), "bid": a["f2"] / 1000.0, "vol": a["f4"].astype(float)})


def today_m1(d: date) -> tuple[pd.DataFrame, int]:
    """1-minute BID bars for UTC day d from hourly tick files, as far as published. Returns (bars, last hour fetched)."""
    frames, last = [], -1
    now = datetime.now(timezone.utc)
    max_hour = 23 if now.date() > d else now.hour - 1
    for hour in range(max_hour + 1):
        f = fetch_hour(d, hour)
        if f is None:
            continue
        frames.append(f)
        last = hour
    if not frames:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"]), last
    t = pd.concat(frames, ignore_index=True)
    if t.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"]), last
    g = t.set_index("time").bid.resample("1min")
    m = pd.DataFrame({"open": g.first(), "high": g.max(), "low": g.min(), "close": g.last(), "volume": t.set_index("time").vol.resample("1min").sum()}).dropna().reset_index()
    return m, last


FEE = 100.0


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"account": "Lucid Flex 50k evaluation (paper)", "start": None, "balance": 0.0, "peak": 0.0, "best_day": 0.0,
            "status": "active", "attempt": 1, "fees_spent": FEE, "past_attempts": [], "sessions": [],
            "rules": {"target": TARGET, "drawdown": DD, "consistency": CONS, "stop_mult": STOP_MULT, "rr": RR}}


def new_attempt_if_needed(st: dict, session: str) -> None:
    """His method: a blown evaluation is replaced by a new one the next session."""
    if st["status"] == "failed" and not any(x["date"] == session for x in st["sessions"]):
        st["past_attempts"].append({"attempt": st["attempt"], "balance": st["balance"], "status": "failed"})
        st.update({"attempt": st["attempt"] + 1, "fees_spent": st["fees_spent"] + FEE, "balance": 0.0, "peak": 0.0, "best_day": 0.0, "status": "active"})


def contracts_for(stake: float, stop_pts: float) -> tuple[int, int, float]:
    per_pt = stake / stop_pts
    nq = int(per_pt // 20)
    mnq = int(round((per_pt - 20 * nq) / 2))
    return nq, mnq, nq * 20 + mnq * 2


def run(session: str) -> dict:
    sd = date.fromisoformat(session)
    st = load_state()
    if st["start"] is None:
        st["start"] = session
    new_attempt_if_needed(st, session)
    # history through the previous UTC day, then today's ticks
    data_mod.download(sd - timedelta(days=10), sd - timedelta(days=1), verbose=False)
    data_mod.build_m1(verbose=False)
    hist = data_mod.load_m1()
    hist = hist[hist.time >= pd.Timestamp(sd - timedelta(days=40), tz="UTC")]
    live, last_hour = today_m1(sd)
    m1 = pd.concat([hist[hist.time < pd.Timestamp(sd, tz="UTC")], live], ignore_index=True).sort_values("time")
    bars = data_mod.resample(m1, 5)
    bars["ema"] = ema(bars.close, 12)
    bars["hhmm"] = bars.time.dt.hour * 100 + bars.time.dt.minute
    bars["date"] = bars.time.dt.date.astype(str)
    day = bars[bars.date == session].reset_index(drop=True)
    data_through = str(live.time.max()) if len(live) else "none"
    rec = next((s for s in st["sessions"] if s["date"] == session), None)
    if rec is None:
        rec = {"date": session, "attempt": st["attempt"], "status": "waiting for the 09:30 candle"}
        st["sessions"].append(rec)
    rec["data_through_utc"] = data_through
    sig = day[day.hhmm == 930]
    view = day[(day.hhmm >= 900) & (day.hhmm <= 1600)]
    rec["candles"] = [[r.time.strftime("%H:%M"), round(r.open, 2), round(r.close, 2), round(r.low, 2), round(r.high, 2)] for r in view.itertuples()]
    rec["ema"] = [round(x, 2) for x in view.ema]
    if st["status"] != "active" and rec.get("status") in (None, "waiting for the 09:30 candle"):
        rec["status"] = f"evaluation already {st['status']}; no trade"
    elif len(sig) and rec.get("status") in ("waiting for the 09:30 candle",):
        s = sig.iloc[0]
        if day.hhmm.max() < 935:
            pass
        else:
            d = 1 if s.close > s.ema else -1 if s.close < s.ema else 0
            if d == 0:
                rec["status"] = "no trade: close exactly on the EMA"
            else:
                risk = abs(s.close - (s.low if d > 0 else s.high))
                stop_pts = STOP_MULT * risk
                room = DD if st["balance"] >= 0 else DD + st["balance"]
                nq, mnq, per_pt = contracts_for(room, stop_pts)
                rec.update({"direction": "long" if d > 0 else "short", "entry_time": "09:35", "entry": round(float(s.close), 2),
                            "candle_risk_pts": round(float(risk), 2), "stop": round(float(s.close - d * stop_pts), 2),
                            "target": round(float(s.close + d * RR * stop_pts), 2), "stop_pts": round(float(stop_pts), 2),
                            "nq": nq, "mnq": mnq, "usd_per_pt": per_pt, "risk_usd": round(per_pt * stop_pts, 0),
                            "reward_usd": round(per_pt * RR * stop_pts, 0), "status": "open"})
    if rec.get("status") == "open":
        d = 1 if rec["direction"] == "long" else -1
        # walk 1-minute bars so the order of stop and target inside a 5-minute bar is known
        m1ny = m1.set_index("time").tz_convert("America/New_York").reset_index()
        m1ny["hhmm"] = m1ny.time.dt.hour * 100 + m1ny.time.dt.minute
        after = m1ny[(m1ny.time.dt.date.astype(str) == session) & (m1ny.hhmm >= 935)]
        res = None
        for r in after.itertuples():
            if r.hhmm >= EXIT_HHMM:
                res = ("time exit 15:30", float(r.open)); break
            hit_stop = r.low <= rec["stop"] if d > 0 else r.high >= rec["stop"]
            hit_tgt = r.high >= rec["target"] if d > 0 else r.low <= rec["target"]
            if hit_stop:
                res = (f"stop hit {r.time.strftime('%H:%M')}", rec["stop"]); break
            if hit_tgt:
                res = (f"target hit {r.time.strftime('%H:%M')}", rec["target"]); break
        if res is not None:
            reason, px = res
            pnl = round(((px - rec["entry"]) * d - COST_PTS) * rec["usd_per_pt"], 0)
            rec.update({"exit": round(px, 2), "exit_reason": reason, "pnl_usd": pnl, "status": "closed"})
            st["balance"] = round(st["balance"] + pnl, 0)
            st["peak"] = max(st["peak"], st["balance"])
            st["best_day"] = max(st["best_day"], pnl)
            floor = min(st["peak"] - DD, 100.0)
            if st["balance"] <= floor:
                st["status"] = "failed"
            elif st["balance"] >= TARGET and st["best_day"] <= CONS * st["balance"]:
                st["status"] = "passed"
        else:
            last = after.iloc[-1] if len(after) else None
            if last is not None:
                rec["open_pnl_usd"] = round(((float(last.close) - rec["entry"]) * d - COST_PTS) * rec["usd_per_pt"], 0)
                rec["last_price"] = round(float(last.close), 2)
    st["floor"] = min(st["peak"] - DD, 100.0)
    st["updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    STATE.write_text(json.dumps(st, indent=1))
    APP.parent.mkdir(exist_ok=True)
    warm = ROOT / "experiments" / "live_warmup.json"
    payload = {"official": st, "warmup": json.loads(warm.read_text()) if warm.exists() and STATE.name == "live_eval.json" else None}
    APP.write_text("window.LIVE_DATA = " + json.dumps(payload) + ";\n")
    return st


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--state", default=None, help="alternate state file (dry runs)")
    a = ap.parse_args()
    if a.state:
        STATE = Path(a.state)
        APP = Path(a.state).with_suffix(".js")
    st = run(a.session)
    rec = next(s for s in st["sessions"] if s["date"] == a.session)
    print(json.dumps({k: v for k, v in rec.items() if k not in ("candles", "ema")}, indent=1))
    print("account:", st["status"], "balance", st["balance"], "floor", st["floor"], "best day", st["best_day"])
