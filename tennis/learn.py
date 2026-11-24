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
N_PARENTS, KIDS, MAX_POP = 40, 4, 20000
FWD = DATA / "forward"
FREEZE_N = 50                    # the top 50 (that also made money on the hold-out) are frozen once a UTC day
PASS_BETS, PASS_T = 50, 2.5      # forward bar: bets on matches that started after the freeze, and their t-stat
TOUR = {"KXATPMATCH": "ATP", "KXWTAMATCH": "WTA", "KXATPCHALLENGERMATCH": "ATP Challenger",
        "KXWTACHALLENGERMATCH": "WTA Challenger", "KXITFMATCH": "ITF Men", "KXITFWMATCH": "ITF Women"}


def describe(s):
    """Plain-words name of a strategy for the dashboard."""
    tour = lab.SCOPE_NAME.get(s.get("scope", "all"), "")
    return (f"{tour}: " if tour else "") + _describe(s)


def _describe(s):
    if s["fam"] == "band":
        when = "at the start" if s["M"] == 0 else (f"{-s['M']} min before the start" if s["M"] < 0 else f"{s['M']} min into the match")
        return f"Back a player priced {round(s['lo'] * 100)}–{round(s['hi'] * 100)}¢ {when}"
    if s["fam"] == "drift":
        when = "at the start" if s["M"] == 0 else f"{-s['M']} min before the start"
        moved = "fell" if s["dir"] == "down" else "rose"
        act = "back that player" if (s["dir"] == "up") == (s["act"] == "mom") else "bet against that player"
        return f"If a player's price {moved} {round(s['d'] * 100)}¢+ in the {s['L']} min before, {act} {when}"
    move = "drops" if s["dir"] == "down" else "rises"
    act = "bet on the bounce" if s["act"] == "rev" else "bet it keeps going"
    ph = {"early": "in the first hour", "late": "after the first hour", "all": "during play"}[s["phase"]]
    return f"When a price {move} {round(s['d'] * 100)}¢ in {s['w']} min {ph}, {act}"


def population():
    """The full grid (every round, so the grid can grow) plus the bred strategies still alive."""
    grid = lab.strategies()
    ids = {s["id"] for s in grid}
    bred = [s for s in (json.loads(POP.read_text()) if POP.exists() else []) if s["id"] not in ids and s.get("bred")]
    return grid + bred


def forward(ms, leaders, log=print):
    """Freeze today's leaders (once a UTC day) and score every frozen batch only on matches that START after its
    freeze, the way the crypto lab scores frozen batches on new days. -> rows for the dashboard."""
    FWD.mkdir(parents=True, exist_ok=True)
    today = int(time.time() // 86400)
    path = FWD / f"batch_{today}.json"
    if not path.exists() and leaders:
        path.write_text(json.dumps({"frozen_at": int(time.time()), "strategies": leaders[:FREEZE_N]}))
        log(f"  forward: froze {len(leaders[:FREEZE_N])} leaders")
    rows = []
    for bp in sorted(FWD.glob("batch_*.json")):
        b = json.loads(bp.read_text())
        frozen = time.strftime("%b %d", time.gmtime(b["frozen_at"]))
        new = [m for m in ms if m["start"] > b["frozen_at"]]
        strats = b["strategies"]
        if new:
            days, P, N, Q = lab.score_matrix(new, strats, log=lambda m: None)
            mt = lab.metrics(days, P, N, Q, hold_frac=0)
        for r, s in enumerate(strats):
            n = int(mt["n"][r]) if new else 0
            pnl = float(mt["pnl"][r]) if new else 0.0
            t = float(mt["t"][r]) if new and n >= 3 else None
            ok = n >= PASS_BETS and (t or -9) >= PASS_T
            rows.append({"strategy": describe(s), "code": s["id"], "frozen": frozen, "bets": n, "pnl": round(pnl, 2),
                         "per_bet_cents": round(100 * pnl / n, 1) if n else None, "t": round(t, 2) if t is not None else None,
                         "days_up": int(mt["days_up"][r]) if new else 0, "days": int(mt["days_active"][r]) if new else 0,
                         "passed": ok})
            if ok:
                notify.promoted(describe(s), n, pnl, t, log)
    rows.sort(key=lambda r: (not r["passed"], -(r["t"] if r["t"] is not None else -9), -r["bets"]))
    return rows


def round_(rng, log=print):
    t0 = time.time()
    try:
        history.update(days=60, log=log, max_s=DOWNLOAD_BUDGET_S)
    except Exception as e:
        log(f"  history update failed: {e!r}")
    ms = lab.load()
    pop = population()
    days, P, N, Q = lab.score_matrix(ms, pop, log)
    mt = lab.metrics(days, P, N, Q)
    w = lab.walk_matrix(P, N, Q)
    import numpy as np
    # leaderboard: ranked on HISTORY only (the first two thirds of the days); the hold-out (last third) is shown
    # beside it as the honesty check, like the crypto lab's search / hold split
    elig = mt["n_hist"] >= lab.MIN_BETS
    order = [int(i) for i in np.argsort(-np.where(elig, mt["t_hist"], -99)) if elig[i]]
    def row_of(i, rank):
        s = pop[i]
        n = int(mt["n"][i]); pnl = float(mt["pnl"][i])
        return {"rank": rank, "strategy": describe(s), "code": s["id"], "tour": lab.SCOPE_NAME.get(s.get("scope", "all")) or "All",
                "bets": n, "pnl": round(pnl, 2), "per_bet_cents": round(100 * pnl / n, 1) if n else None,
                "t": round(float(mt["t"][i]), 2), "days_up": int(mt["days_up"][i]), "days": int(mt["days_active"][i]),
                "win_days_pct": round(100 * mt["days_up"][i] / max(mt["days_active"][i], 1)),
                "max_dd": round(float(mt["max_dd"][i]), 2),
                "hist_bets": int(mt["n_hist"][i]), "hist_pnl": round(float(mt["pnl_hist"][i]), 2), "hist_t": round(float(mt["t_hist"][i]), 2),
                "hold_bets": int(mt["n_hold"][i]), "hold_pnl": round(float(mt["pnl_hold"][i]), 2),
                "hold_t": round(float(mt["t_hold"][i]), 2) if mt["n_hold"][i] >= 10 else None}
    board = [row_of(i, k + 1) for k, i in enumerate(order[:50])]
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "leaderboard.json").write_text(json.dumps(board, indent=0))
    held = [i for i in order if mt["n_hold"][i] >= 10 and mt["pnl_hold"][i] > 0]
    fwd = forward(ms, [pop[i] for i in held], log)
    (REPORT / "forward.json").write_text(json.dumps(fwd[:100], indent=0))
    # breed variants of the leaders that held up; drop strategies with plenty of bets and a clearly negative record
    ids = {s["id"] for s in pop}
    born = 0
    for i in (held or order)[:N_PARENTS]:
        for _ in range(KIDS):
            c = lab.mutate(pop[i], rng)
            c["bred"] = True
            if c["id"] not in ids:
                pop.append(c); ids.add(c["id"]); born += 1
    dead = {pop[i]["id"] for i in range(len(mt["n"])) if mt["n"][i] >= 3 * lab.MIN_BETS and mt["t"][i] < -2 and pop[i].get("bred")}
    POP.write_text(json.dumps([s for s in pop if s.get("bred") and s["id"] not in dead][-MAX_POP:]))
    tested = len(pop)
    row = {"ts": int(time.time()), "time": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "markets": len(ms),
           "days": len(days), "strategies": tested, "born": born, "dropped": len(dead),
           "test_days": w["test_days"],
           "top1_cents": round(100 * w["top"][1][0], 2), "top5_cents": round(100 * w["top"][5][0], 2),
           "top20_cents": round(100 * w["top"][20][0], 2), "top50_cents": round(100 * w["top"][50][0], 2),
           "all_cents": round(100 * w["all"][0], 2), "top5_bets": w["top"][5][1],
           "held_up": len(held),
           "best": board[0]["strategy"] if board else None, "best_t": board[0]["hist_t"] if board else None,
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
                                                        "pnl", "parity", "same_call", "lab_price", "practice_only")} for b in pb][-500:], indent=0))
        report.build(log=lambda m: None)
    except Exception as e:
        log(f"  paper/report failed: {e!r}")
    prog = [json.loads(ln) for ln in open(LOG) if ln.strip()]
    (REPORT / "progress.json").write_text(json.dumps(prog[-500:], indent=0))
    log(f"learn: {len(ms)} markets, {tested} strategies (+{born} bred, -{len(dead)} dropped), {len(held)} held up on the "
        f"hold-out; walk-forward top-5 {row['top5_cents']:+.2f}c/bet vs all {row['all_cents']:+.2f}c over {w['test_days']} "
        f"test days; best: {row['best']} [{row['runtime_s']}s]")
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
