"""24/7 learning loop for tennis (python -m tennis learn [once]).

Every round: download newly settled matches (history.update), score every strategy in the population on every
match (lab.score), run the walk-forward test of trusting the leaderboard (lab.walk), breed variants of the leaders
and drop proven losers, then write what the dashboard shows:
  data/tennis/report/leaderboard.json   the top strategies by t-stat, with bets, P&L and per-bet edge
  data/tennis/report/progress.json      one row per round: how many matches/strategies, and the walk-forward
                                        result of backing the top 1/5/20 vs backing everything
  data/tennis/learn_log.jsonl           the same rounds, kept
  data/tennis/population.json           every strategy alive (the starting grid plus bred ones)
"""
from __future__ import annotations

import json
import random
import time

from . import history, lab, notify
from .collect import DATA

REPORT = DATA / "report"
POP = DATA / "population.json"
LOG = DATA / "learn_log.jsonl"
ROUND_GAP_S = 20 * 60
DOWNLOAD_BUDGET_S = 8 * 60          # per round, so the first rounds learn while the 60-day history fills in
N_PARENTS, KIDS, MAX_POP = 25, 4, 6000
FWD = DATA / "forward"
FREEZE_N = 20                    # the leaderboard's top 20 is frozen once a UTC day
PASS_BETS, PASS_T = 50, 2.5      # forward bar: bets on matches that started after the freeze, and their t-stat
TOUR = {"KXATPMATCH": "ATP", "KXWTAMATCH": "WTA", "KXATPCHALLENGERMATCH": "ATP Challenger",
        "KXWTACHALLENGERMATCH": "WTA Challenger", "KXITFMATCH": "ITF Men", "KXITFWMATCH": "ITF Women"}


def describe(s):
    """Plain-words name of a strategy for the dashboard."""
    if s["fam"] == "band":
        when = "at the start" if s["M"] == 0 else (f"{-s['M']} min before the start" if s["M"] < 0 else f"{s['M']} min into the match")
        return f"Back a player priced {round(s['lo'] * 100)}–{round(s['hi'] * 100)}¢ {when}"
    move = "drops" if s["dir"] == "down" else "rises"
    act = "bet on the bounce" if s["act"] == "rev" else "bet it keeps going"
    ph = {"early": "in the first hour", "late": "after the first hour", "all": "during play"}[s["phase"]]
    return f"When a price {move} {round(s['d'] * 100)}¢ in {s['w']} min {ph}, {act}"


def population():
    if POP.exists():
        return json.loads(POP.read_text())
    return lab.strategies()


def forward(ms, ranked, log=print):
    """Freeze today's leaders (once a UTC day) and score every frozen batch only on matches that START after its
    freeze, the way the crypto lab scores frozen batches on new days. -> rows for the dashboard."""
    FWD.mkdir(parents=True, exist_ok=True)
    today = int(time.time() // 86400)
    path = FWD / f"batch_{today}.json"
    if not path.exists():
        top = [r["s"] for r in ranked if r["n"] >= lab.MIN_BETS][:FREEZE_N]
        if top:
            path.write_text(json.dumps({"frozen_at": int(time.time()), "strategies": top}))
            log(f"  forward: froze {len(top)} leaders")
    rows = []
    for bp in sorted(FWD.glob("batch_*.json")):
        b = json.loads(bp.read_text())
        new = [m for m in ms if m["start"] > b["frozen_at"]]
        if not new:
            for s in b["strategies"]:
                rows.append({"strategy": describe(s), "code": s["id"], "frozen": time.strftime("%b %d", time.gmtime(b["frozen_at"])),
                             "bets": 0, "pnl": 0.0, "t": None, "passed": False})
            continue
        d = lab.score(new, b["strategies"], log=lambda m: None)
        for s in b["strategies"]:
            n, p, t = lab.stats(d[s["id"]])
            ok = n >= PASS_BETS and t >= PASS_T
            rows.append({"strategy": describe(s), "code": s["id"], "frozen": time.strftime("%b %d", time.gmtime(b["frozen_at"])),
                         "bets": int(n), "pnl": round(p, 2), "t": round(t, 2) if n >= 3 else None, "passed": ok})
            if ok:
                notify.promoted(describe(s), int(n), p, t, log)
    rows.sort(key=lambda r: (-(r["t"] or -9), -r["bets"]))
    return rows


def round_(rng, log=print):
    t0 = time.time()
    try:
        history.update(days=60, log=log, max_s=DOWNLOAD_BUDGET_S)
    except Exception as e:
        log(f"  history update failed: {e!r}")
    ms = lab.load()
    pop = population()
    daily = lab.score(ms, pop, log)
    days = sorted({m["day"] for m in ms})
    ranked = []
    for s in pop:
        n, p, t = lab.stats(daily[s["id"]])
        up = sum(1 for v in daily[s["id"]].values() if v[0] > 0)
        ranked.append({"s": s, "n": int(n), "pnl": round(p, 2), "t": round(t, 2), "days_up": up,
                       "days": len(daily[s["id"]])})
    ranked.sort(key=lambda r: -r["t"] if r["n"] >= lab.MIN_BETS else 99)
    w = lab.walk(daily)
    # breed: variants of the leaders; drop strategies with plenty of bets and a clearly negative record
    ids = {s["id"] for s in pop}
    parents = [r["s"] for r in ranked if r["n"] >= lab.MIN_BETS][:N_PARENTS]
    born = 0
    for p in parents:
        for _ in range(KIDS):
            c = lab.mutate(p, rng)
            if c["id"] not in ids:
                pop.append(c); ids.add(c["id"]); born += 1
    dead = {r["s"]["id"] for r in ranked if r["n"] >= 3 * lab.MIN_BETS and r["t"] < -2}
    pop = [s for s in pop if s["id"] not in dead][:MAX_POP]
    POP.write_text(json.dumps(pop))
    top = [r for r in ranked if r["n"] >= lab.MIN_BETS][:15]
    REPORT.mkdir(parents=True, exist_ok=True)
    board = [{"rank": i + 1, "strategy": describe(r["s"]), "code": r["s"]["id"], "bets": r["n"], "pnl": r["pnl"],
              "per_bet_cents": round(100 * r["pnl"] / r["n"], 1) if r["n"] else None, "t": r["t"],
              "days_up": r["days_up"], "days": r["days"]} for i, r in enumerate(top)]
    (REPORT / "leaderboard.json").write_text(json.dumps(board, indent=0))
    fwd = forward(ms, ranked, log)
    (REPORT / "forward.json").write_text(json.dumps(fwd[:30], indent=0))
    row = {"ts": int(time.time()), "time": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "markets": len(ms),
           "days": len(days), "strategies": len(pop), "born": born, "dropped": len(dead),
           "test_days": w["test_days"],
           "top1_cents": round(100 * w["top"][1][0], 2), "top5_cents": round(100 * w["top"][5][0], 2),
           "top20_cents": round(100 * w["top"][20][0], 2), "all_cents": round(100 * w["all"][0], 2),
           "top5_bets": w["top"][5][1],
           "best": board[0]["strategy"] if board else None, "best_t": board[0]["t"] if board else None,
           "best_bets": board[0]["bets"] if board else None,
           "forward_bets": sum(r["bets"] for r in fwd), "forward_passed": sum(r["passed"] for r in fwd),
           "runtime_s": round(time.time() - t0)}
    with open(LOG, "a") as f:
        f.write(json.dumps(row) + "\n")
    notify.digest(row, log=log)
    try:                                          # practice runner results and the arb summary, for the dashboard
        from . import paper, report
        pb = paper.settle_and_check()
        (REPORT / "paper.json").write_text(json.dumps([{k: b.get(k) for k in ("ts", "ticker", "strategy", "side", "price",
                                                        "pnl", "parity", "practice_only")} for b in pb][-200:], indent=0))
        report.build(log=lambda m: None)
    except Exception as e:
        log(f"  paper/report failed: {e!r}")
    prog = [json.loads(ln) for ln in open(LOG) if ln.strip()]
    (REPORT / "progress.json").write_text(json.dumps(prog[-500:], indent=0))
    log(f"learn: {len(ms)} markets, {len(pop)} strategies (+{born} bred, -{len(dead)} dropped); walk-forward top-5 "
        f"{row['top5_cents']:+.2f}c/bet vs all {row['all_cents']:+.2f}c over {w['test_days']} test days; "
        f"best: {row['best']} (t {row['best_t']}, {row['best_bets']} bets) [{row['runtime_s']}s]")
    return row


def run(once=False, log=print):
    rng = random.Random()
    while True:
        t0 = time.time()
        try:
            round_(rng, log)
        except Exception as e:
            log(f"learn round failed: {e!r}")
        if once:
            return
        time.sleep(max(60, ROUND_GAP_S - (time.time() - t0)))
