"""Measure how each collected launch performed after it was first spotted.

For every launch in launches.jsonl (SOL-quoted pools only), fetch minute
candles for the WINDOW minutes after it was first seen, and compare against the
price at first sight, which is roughly what someone noticing the launch could
have bought at.

    python -m launchscope.analyze track   # follow launches as they age (run alongside collect)
    python -m launchscope.analyze build   # write outcomes.json + paths.json for the dashboard
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from . import gecko

DATA = Path(__file__).resolve().parent.parent / "data" / "launches"
LAUNCHES = DATA / "launches.jsonl"
OUTCOMES = DATA / "outcomes.jsonl"
SOL = "So11111111111111111111111111111111111111112"
WINDOW = 30  # minutes followed after first sight


def ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def outcome_label(end_x: float, traded: bool) -> str:
    if not traded:
        return "No trades after launch"
    if end_x < 0.1:
        return "Down 90% or more"
    if end_x < 0.5:
        return "Down 50–90%"
    if end_x < 2:
        return "Between −50% and 2x"
    if end_x < 5:
        return "Up 2x–5x"
    return "Up 5x or more"


def measure(launch: dict) -> dict:
    seen = ts(launch["seen_at"])
    start = seen - seen % 60
    candles = gecko.ohlcv_minute(launch["address"], before=start + (WINDOW + 1) * 60, limit=WINDOW + 5)
    by_minute = {int((c[0] - start) // 60): c for c in candles if start <= c[0] <= start + WINDOW * 60}
    # Reference: close of the minute it was spotted in (the feed's snapshot price can lag);
    # fall back to the snapshot price if nothing traded that minute.
    ref = by_minute[0][4] if 0 in by_minute else launch["price_usd"]
    later = [by_minute[m] for m in sorted(by_minute) if m > 0]  # only trades after first sight
    path = []  # multiple vs. ref at each minute after first sight, carried forward
    last = ref
    for m in range(WINDOW + 1):
        if m > 0 and m in by_minute:
            last = by_minute[m][4]
        path.append(round(last / ref, 6))
    candles = later
    traded = bool(candles)
    highs = [c[2] for c in candles] or [ref]
    peak = max(max(highs), ref)
    end_x = path[-1]
    return {
        "address": launch["address"],
        "name": launch["name"],
        "launchpad": launch["dex"],
        "created_at": launch["created_at"],
        "seen_at": launch["seen_at"],
        "start_liquidity_usd": round(launch["reserve_usd"], 2),
        "start_mcap_usd": round(launch["fdv_usd"], 2),
        "early_buys": launch["tx_m5"]["buys"],
        "early_sells": launch["tx_m5"]["sells"],
        "active_minutes": len(candles),
        "volume_usd": round(sum(c[5] for c in candles), 2),
        "peak_x": round(peak / ref, 4),
        "end_x": round(end_x, 4),
        "minutes_to_peak": int((candles[highs.index(peak)][0] - start) // 60) if peak in highs and traded else 0,
        "outcome": outcome_label(end_x, traded),
        "path": path,
    }


def track(max_launches: int, idle_exit_min: float, every: int = 1) -> None:
    done = {json.loads(l)["address"] for l in OUTCOMES.read_text().splitlines()} if OUTCOMES.exists() else set()
    idle_since = time.time()
    while len(done) < max_launches:
        launches = [json.loads(l) for l in LAUNCHES.read_text().splitlines() if l.strip()]
        launches = [l for l in launches if l["quote_token"] == SOL and l["price_usd"] > 0][::every]
        pending = [l for l in launches if l["address"] not in done]
        ready = [l for l in pending if time.time() >= ts(l["seen_at"]) + (WINDOW + 2) * 60]
        if not ready:
            # Only count as idle once every collected launch is scored (waiting for launches to age isn't idle).
            if pending:
                idle_since = time.time()
            elif time.time() - idle_since > idle_exit_min * 60:
                break
            time.sleep(20)
            continue
        idle_since = time.time()
        launch = ready[0]
        try:
            row = measure(launch)
        except Exception as e:
            print("skip", launch["address"], e, flush=True)
            done.add(launch["address"])
            continue
        with OUTCOMES.open("a") as f:
            f.write(json.dumps(row) + "\n")
        done.add(launch["address"])
        print(len(done), row["name"], row["outcome"], row["peak_x"], flush=True)


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def build() -> None:
    rows = [json.loads(l) for l in OUTCOMES.read_text().splitlines() if l.strip()]
    paths = []
    for m in range(WINDOW + 1):
        vals = [r["path"][m] for r in rows]
        paths.append({
            "minute": m,
            "p25": round(pct(vals, 0.25), 4),
            "median": round(statistics.median(vals), 4),
            "p75": round(pct(vals, 0.75), 4),
            "share_up": round(sum(v > 1 for v in vals) / len(vals), 4),
        })
    out = [{k: v for k, v in r.items() if k != "path"} for r in rows]
    (DATA / "outcomes.json").write_text(json.dumps(out))
    (DATA / "paths.json").write_text(json.dumps(paths))
    print(f"{len(out)} launches -> {DATA / 'outcomes.json'}, {DATA / 'paths.json'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["track", "build"])
    ap.add_argument("--max", type=int, default=250)
    ap.add_argument("--every", type=int, default=1, help="follow every Nth launch (evenly spaced sample)")
    ap.add_argument("--idle-exit", type=float, default=10, help="stop tracking after this many idle minutes")
    args = ap.parse_args()
    if args.mode == "track":
        track(args.max, args.idle_exit, args.every)
    else:
        build()


if __name__ == "__main__":
    main()
