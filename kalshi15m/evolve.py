"""Strategy evolution: breed new strategies from the ones doing best on days they had never seen, and keep doing it
(python -m kalshi15m evolve once | loop | board).

Every round:
  1. score   bring every batch's forward results up to date (gen 1 downloads the new Kalshi markets and trade
             records; every other batch only fetches the trade windows its own orders need, so its fills are real).
  2. parents the strongest strategies of ALL batches on their own forward days (days after they were frozen):
             ranked by forward t-stat shrunk toward 0 when they have few fills, at most 3 per strategy type x coin
             so one idea cannot take every slot.
  3. breed   children of each parent: small parameter steps (on the family's grid, or a little past it for plain
             thresholds such as the edge), crossovers of two parents of the same strategy type, and the same
             settings moved to other coins. Anything already tested in any batch is dropped.
  4. screen  each child on the history (Sep-Nov 1) and on the forward days so far, at real-money scoring (the same
             code as fwdlab pick). Kept only if profitable in both with enough trades; best TOP_N by t-stat.
  5. freeze  the survivors become a new batch (data/lab/fwd<N>_candidates.json, N >= 3) whose forward test starts
             15+ minutes AFTER freezing. Children were bred from forward results, so step 4's second window is
             not independent: only the days after the freeze count as a test, exactly as for gen 1 and gen 2.

Searching harder finds more strategies that only look good by luck, so nothing here touches real money: the
forward results after freezing decide (kalshi15m/rotate.py, which also has to beat its own walk-forward test).
"""
from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LABDIR = ROOT / "data" / "lab"
LOG = LABDIR / "evo_log.jsonl"
FIRST_GEN = 3
N_PARENTS, PER_IDEA, TOP_N = 40, 3, 300
MIN_PARENT_FILLS = 10
MIN_SEARCH_N, MIN_HOLD_N = 100, 20
ROUND_GAP_S = int(os.environ.get("EVO_GAP_S", str(2 * 3600)))
SCORE_MAX_AGE_DAYS = 28          # batches older than this stop being re-scored (their record stays)
# plain thresholds that can step a little past the family's grid: (low, high, step)
CONT = {"edge": (0.03, 0.35, 0.01), "e0": (0.02, 0.25, 0.01), "e_tau": (-0.12, 0.15, 0.01),
        "k_spr": (0.0, 2.5, 0.25), "rel": (0.0, 0.7, 0.05), "vm": (0.5, 2.0, 0.05), "a": (-1.0, 2.0, 0.05),
        "tau_adj": (-1.5, 1.5, 0.1)}
GRID_ONLY_VM = {"fv_emp", "ens_fixed"}      # bootstrap probabilities are precomputed for the grid's vm values only


# --------------------------------------------------------------------------- batches and their forward record
def gens():
    out = [1] if (LABDIR / "fwd_candidates.json").exists() else []
    out += sorted(int(p.stem[3:].split("_")[0]) for p in LABDIR.glob("fwd*_candidates.json")
                  if p.stem[3:].split("_")[0].isdigit())
    return out


def cands_path(g):
    return LABDIR / ("fwd_candidates.json" if g == 1 else f"fwd{g}_candidates.json")


def daily_path(g):
    return LABDIR / ("fwd_daily.json" if g == 1 else f"fwd{g}_daily.json")


def key(fam, scope, params):
    return f"{fam}|{scope}|{json.dumps(params, sort_keys=True)}"


def _t(n, s, q):
    if n < 3:
        return 0.0
    var = (q - s * s / n) / (n - 1)
    return s / n / math.sqrt(var / n) if var > 0 else 0.0


def board(before_day=None):
    """Every candidate of every batch with its forward record (only days after its batch froze; before_day limits
    it to earlier days, for walk-forward tests)."""
    rows = []
    for g in gens():
        C = json.loads(cands_path(g).read_text())
        dp = daily_path(g)
        D = json.loads(dp.read_text())["days"] if dp.exists() else {}
        start = int(C.get("fwd_start") or 0)
        for c in C["candidates"]:
            v = D.get(c["id"], {})
            n = s = q = 0.0
            up = nd = 0
            for d, x in v.items():
                if before_day is not None and int(d) >= before_day:
                    continue
                s += x[0]; n += x[1]; q += x[2]
                nd += 1; up += x[0] > 0
            end = before_day * 86400 if before_day is not None else time.time()
            rows.append({"gen": g, "id": c["id"], "family": c["family"], "scope": c["scope"], "params": c["params"],
                         "norms": c.get("norms"), "kind": c.get("kind"), "fwd_start": start,
                         "fwd_days": round(max(end - start, 0) / 86400, 2), "filled": int(n), "pnl": round(s, 4),
                         "t": round(_t(n, s, q), 3), "days_up": up, "days_traded": nd,
                         "key": key(c["family"], c["scope"], c["params"])})
    return rows


def strength(r):
    """Forward t shrunk toward 0 when a strategy has few fills (a t of 3 on 10 bets is mostly luck)."""
    return r["t"] * math.sqrt(min(r["filled"], 30) / 30)


def parents(rows, k=N_PARENTS, per_idea=PER_IDEA, explore=10, seed=None):
    """Breed from the best IDEAS, not the best single settings. Walk-forward on gen 1's forward days (Nov 20): the
    40 strongest single strategies made +$0.09 per strategy the next day, less than the average (+$0.17), while the 3
    strongest members of each of the best strategy-type x coin families made +$0.36. So: rank families by their
    members' average forward $/day, take up to `per_idea` strongest members of each in order (exact duplicates
    skipped), and draw the last `explore` slots from everything else, weighted by strength, so rounds differ."""
    ok = [r for r in rows if r["filled"] >= MIN_PARENT_FILLS and r["pnl"] > 0]
    fam = {}
    for r in rows:
        if r.get("fwd_days", 0) >= 1:
            fam.setdefault((r["family"], r["scope"]), []).append(r["pnl"] / r["fwd_days"])
    score = {f: sum(v) / len(v) for f, v in fam.items()}
    by_idea = {}
    for r in sorted(ok, key=lambda r: -strength(r)):
        by_idea.setdefault((r["family"], r["scope"]), []).append(r)
    out, sigs, per = [], set(), {}

    def take(r):
        sig = (r["family"], r["scope"], r["filled"], round(r["pnl"], 2))   # same bets as a stronger one: skip
        idea = (r["family"], r["scope"])
        if sig in sigs or per.get(idea, 0) >= per_idea:
            return False
        sigs.add(sig)
        per[idea] = per.get(idea, 0) + 1
        out.append(r)
        return True

    for idea in sorted(by_idea, key=lambda f: -score.get(f, 0)):
        n = 0
        for r in by_idea[idea]:
            if n >= per_idea or len(out) >= k - explore:
                break
            n += take(r)
        if len(out) >= k - explore:
            break
    rest = [r for r in ok if r not in out and per.get((r["family"], r["scope"]), 0) < per_idea]
    rng = random.Random(seed)
    while rest and len(out) < k:
        w = [math.exp(min(strength(r), 6)) for r in rest]
        r = rest.pop(rng.choices(range(len(rest)), weights=w)[0])
        take(r)
    return out


# --------------------------------------------------------------------------- breeding
def _step(fam, k, v, grid, rng):
    vals = grid.get(k)
    if vals is None:
        return v
    if k in CONT and isinstance(v, (int, float)) and not isinstance(v, bool) and not (k == "vm" and fam in GRID_ONLY_VM):
        lo, hi, st = CONT[k]
        nv = round(min(max(v + rng.choice((-2, -1, 1, 2)) * st, lo), hi), 4)
        return nv
    if k in ("start", "end") and isinstance(v, int):
        return int(min(max(v + rng.choice((-1, 1)), 1 if k == "start" else 8), 8 if k == "start" else 13))
    if v in vals:
        i = vals.index(v) + rng.choice((-1, 1))
        return vals[min(max(i, 0), len(vals) - 1)]
    return rng.choice(vals)


def _valid(fam, p):
    from . import lab3
    if "start" in p and "end" in p and not p["start"] + 3 <= p["end"]:
        return False
    if "band" in p and p["band"] not in lab3.BANDS:
        return False
    grid = lab3.FAMILIES[fam]["grid"]
    return set(p) == set(grid)


def breed(par, seen, coins, n_mut=15, n_cross=75, n_move=6, seed=None):
    # Nov 21, first full forward day (Nov 20), each method vs original strategies on the same coins: moves to other
    # coins +$0.078/bet (962 bets), parameter steps +$0.004 (14,140), crossovers -$0.058 (1,002). One day only,
    # so the mix shifts (crossovers 150 -> 75, moves 4 -> 6 per parent) rather than dropping a method.
    from . import lab3
    rng = random.Random(seed)
    kids, out_keys = [], set(seen)

    def add(fam, scope, p, why):
        k = key(fam, scope, p)
        if k in out_keys or not _valid(fam, p):
            return
        out_keys.add(k)
        kids.append({"family": fam, "scope": scope, "params": p, "parents": why})

    for r in par:
        grid = lab3.FAMILIES[r["family"]]["grid"]
        for _ in range(n_mut):
            p = dict(r["params"])
            for kk in rng.sample(list(p), k=min(len(p), rng.choice((1, 1, 2, 3)))):
                p[kk] = _step(r["family"], kk, p[kk], grid, rng)
            add(r["family"], r["scope"], p, [f"{r['id']}@g{r['gen']}"])
        others = [c for c in coins + ["ALL"] if c != r["scope"]]
        for sc in rng.sample(others, k=min(n_move, len(others))):
            add(r["family"], sc, dict(r["params"]), [f"{r['id']}@g{r['gen']}"])
    by_fam = {}
    for r in par:
        by_fam.setdefault(r["family"], []).append(r)
    pairs = [(a, b) for v in by_fam.values() for i, a in enumerate(v) for b in v[i + 1:]]
    for a, b in rng.sample(pairs, k=min(n_cross, len(pairs))):
        p = {kk: (a["params"][kk] if rng.random() < 0.5 else b["params"][kk]) for kk in a["params"]}
        add(a["family"], rng.choice((a["scope"], b["scope"])), p, [f"{a['id']}@g{a['gen']}", f"{b['id']}@g{b['gen']}"])
    return kids


# --------------------------------------------------------------------------- screening (same scoring as fwdlab pick)
def _agg(pnl):
    pnl = np.asarray(pnl, float)
    return np.array([len(pnl), pnl.sum(), (pnl ** 2).sum()])


def _screen_task(args):
    from . import lab3
    fam, coin, cfgs = args
    cs, ch = lab3.G["search"][coin], lab3.G["hold"][coin]
    cs.cache, ch.cache = {}, {}
    sized = lab3.FAMILIES[fam]["kind"] == "sized"
    out = np.zeros((len(cfgs), 2, 3))
    kel = np.zeros((len(cfgs), 2))
    ok = np.ones(len(cfgs), bool)
    for i, c in enumerate(cfgs):
        try:
            side, minute, p = lab3.signal(cs, fam, c)
            tr = lab3.execute(cs, fam, c, side, minute, p)
            out[i, 0] = _agg(tr["pnl"])
            nrm = None
            if sized and len(tr["m"]):
                k = np.clip((tr["q"] - tr["price"]) / (1 - tr["price"]), 1e-4, None)
                kel[i] = k.sum(), len(k)
                nrm = float(k.mean())
            side, minute, p = lab3.signal(ch, fam, c)
            out[i, 1] = _agg(lab3.execute(ch, fam, c, side, minute, p, norm=nrm)["pnl"])
        except Exception:          # a setting the family code cannot run: dropped
            ok[i] = False
    cs.cache, ch.cache = {}, {}
    return fam, coin, out, kel, ok


_LOADED = {"at": 0}


def load_contexts(log=print):
    """History (search) and forward days so far (exam), exactly as fwdlab pick gen 2+. Reloaded once per round."""
    from . import fwdscore, lab3
    from .fwdlab import FWD_START
    t0 = time.time()
    lab3.G["quick"] = 0
    lab3._GRID_CACHE.clear()
    hold = fwdscore.contexts(lab3.COINS, log, start=FWD_START)
    lab3._SPOT.clear()
    lab3.REAL = True
    full = lab3.load(verbose=False)
    for s_, p_ in full.items():
        ots = np.asarray(p_.open_ts, np.int64)
        lab3.G["search"][s_] = lab3.Ctx(s_, p_.subset(ots >= lab3.G["start"]))
        lab3.G["hold"][s_] = hold[s_]
    _LOADED["at"] = time.time()
    log(f"  history + {min(len(h.open_ts) for h in hold.values())}+ forward markets per coin loaded ({time.time() - t0:.0f}s)")


def screen(kids, workers=3, log=print):
    from . import lab3
    t0 = time.time()
    tasks = {}
    for i, k in enumerate(kids):
        for coin in (lab3.COINS if k["scope"] == "ALL" else [k["scope"]]):
            tasks.setdefault((k["family"], coin), []).append(i)
    R = {}
    with Pool(workers) as pool:
        jobs = [(f, c, [kids[i]["params"] for i in idx]) for (f, c), idx in tasks.items()]
        for fam, coin, out, kel, ok in pool.imap_unordered(_screen_task, jobs, chunksize=1):
            for j, i in enumerate(tasks[(fam, coin)]):
                R[(i, coin)] = (out[j], kel[j], ok[j])
    keep = []
    for i, k in enumerate(kids):
        coins = lab3.COINS if k["scope"] == "ALL" else [k["scope"]]
        parts = [R.get((i, c)) for c in coins]
        if any(p is None or not p[2] for p in parts):
            continue
        a = sum(p[0] for p in parts)
        if not (a[0, 0] >= MIN_SEARCH_N and a[1, 0] >= MIN_HOLD_N and a[0, 1] > 0 and a[1, 1] > 0):
            continue
        k = dict(k)
        k["search"] = {"pnl": round(float(a[0, 1]), 2), "trades": int(a[0, 0]), "t": round(lab3.tstat_agg(a[0]), 2)}
        k["hold"] = {"pnl": round(float(a[1, 1]), 2), "trades": int(a[1, 0]), "t": round(lab3.tstat_agg(a[1]), 2)}
        k["t_before"] = round(lab3.tstat_agg(a.sum(0)), 2)
        if lab3.FAMILIES[k["family"]]["kind"] == "sized":
            ks = sum(p[1] for p in parts)
            v = float(ks[0] / ks[1]) if ks[1] else 1.0
            k["norms"] = {c: v for c in coins}
        keep.append(k)
    keep.sort(key=lambda k: -k["t_before"])
    log(f"  screened {len(kids)} children on {len(tasks)} family x coin tasks: {len(keep)} profitable in both "
        f"windows, keeping {min(len(keep), TOP_N)} ({time.time() - t0:.0f}s)")
    return keep[:TOP_N]


def freeze(keep, par_n, log=print):
    from . import lab3
    g = max(gens() + [FIRST_GEN - 1]) + 1
    frozen = int(time.time())
    rows = []
    for r, k in enumerate(keep):
        c = {"id": f"{k['family']}:{k['scope']}:e{g}.{r + 1}", "family": k["family"], "scope": k["scope"],
             "rank": r + 1, "kind": lab3.FAMILIES[k["family"]]["kind"], "params": k["params"],
             "search": k["search"], "hold": k["hold"], "t_before": k["t_before"], "parents": k["parents"]}
        if "norms" in k:
            c["norms"] = k["norms"]
        rows.append(c)
    out = {"generation": g, "evolved": True, "frozen_at": frozen, "fwd_start": (frozen // 900 + 2) * 900,
           "top_k": TOP_N, "families": sorted({k["family"] for k in keep}), "coins": lab3.COINS,
           "n_candidates": len(rows), "n_parents": par_n,
           "selection": (f"Evolved from the {par_n} strongest strategies of all earlier batches on their own forward "
                         f"days: parameter steps, crossovers and moves to other coins, screened on the history and the "
                         f"forward days so far at real-money scoring (profitable in both, >= {MIN_SEARCH_N} history "
                         f"and >= {MIN_HOLD_N} forward trades), best {TOP_N} by t-stat. The forward days so far were "
                         f"used to breed them, so only days after the freeze count as their test."),
           "candidates": rows}
    cands_path(g).write_text(json.dumps(out, default=float))
    log(f"  batch {g}: {len(rows)} strategies frozen, forward test starts "
        f"{time.strftime('%b %d %H:%M UTC', time.gmtime(out['fwd_start']))}")
    return g, out


# --------------------------------------------------------------------------- rounds
def _run(args, env_gen=None, log=print, timeout=7000):
    env = dict(os.environ)
    if env_gen is not None:
        env["FWD_GEN"] = str(env_gen)
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "kalshi15m"] + args, cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=timeout)
    tail = [ln for ln in (p.stdout + p.stderr).strip().splitlines() if ln.startswith("fwdlab")][-1:]
    log(f"  {' '.join(args)}{'' if env_gen is None else f' (batch {env_gen})'}: "
        f"{tail[0] if tail else 'exit ' + str(p.returncode)} ({time.time() - t0:.0f}s)")
    return p.returncode


def score_all(log=print):
    _run(["fwdlab", "score"], 1, log)                      # downloads the new markets + gen 1's trade windows
    now = time.time()
    for g in gens():
        if g == 1:
            continue
        C = json.loads(cands_path(g).read_text())
        if now < C["fwd_start"] + 900 or now - C["fwd_start"] > SCORE_MAX_AGE_DAYS * 86400:
            continue
        _run(["fwdlab", "score", "tape"], g, log)


def once(workers=3, log=print, score=True):
    t0 = time.time()
    log(f"evolve round {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    if score:
        score_all(log)
    rows = board()
    par = parents(rows, seed=int(t0))
    if not par:
        log("  no strategy has enough forward fills to breed from yet")
        return None
    from . import lab3
    kids = breed(par, {r["key"] for r in rows}, lab3.COINS, seed=int(t0))
    log(f"  {len(par)} parents (best: {par[0]['id']}@g{par[0]['gen']} t {par[0]['t']} on {par[0]['filled']} fills) "
        f"-> {len(kids)} new children")
    load_contexts(log)
    keep = screen(kids, workers, log)
    g, _ = freeze(keep, len(par), log) if keep else (None, None)
    rec = {"ts": int(time.time()), "parents": len(par), "children": len(kids), "kept": len(keep), "gen": g,
           "best_parent": f"{par[0]['id']}@g{par[0]['gen']}", "runtime_s": int(time.time() - t0)}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    try:
        from . import rotate
        rotate.run(apply=os.environ.get("EVO_ROTATE", "1") == "1", log=log)
    except Exception as e:      # rotation problems must never stop the search
        log(f"  rotate: error {e!r}")
    log(f"evolve round done ({time.time() - t0:.0f}s)")
    return rec


def loop(workers=3, log=print):
    while True:
        if (ROOT / "STOP_EVOLVE").exists():
            log("STOP_EVOLVE present: stopping")
            return
        t0 = time.time()
        try:
            once(workers, log)
        except Exception as e:
            log(f"evolve round failed: {e!r}")
        time.sleep(max(ROUND_GAP_S - (time.time() - t0), 300))


def compare(log=print):
    """Is evolution working? Per day since the first evolved batch: average P&L per filled bet of evolved strategies
    (batch 3+) vs the original ones (batch 1-2) on the SAME day, and on the same coins (each coin weighted by the
    evolved bets on it, so a batch that leans on a coin having a bad day is not blamed for the day)."""
    import collections
    gs = [g for g in gens() if daily_path(g).exists()]
    evo = [g for g in gs if g >= FIRST_GEN]
    if not evo:
        return []
    first = min(json.loads(cands_path(g).read_text())["fwd_start"] for g in evo) // 86400 + 1   # first FULL day
    agg = collections.defaultdict(lambda: [0.0, 0.0])
    for g in gs:
        C = {c["id"]: c["scope"] for c in json.loads(cands_path(g).read_text())["candidates"]}
        grp = "evo" if g >= FIRST_GEN else "orig"
        for cid, v in json.loads(daily_path(g).read_text())["days"].items():
            for d, x in v.items():
                if int(d) >= first:
                    a = agg[(grp, int(d), C.get(cid))]
                    a[0] += x[0]; a[1] += x[1]
    out = []
    for d in sorted({k[1] for k in agg}):
        e = [(sc, agg[("evo", d, sc)]) for sc in {k[2] for k in agg if k[1] == d} if agg[("evo", d, sc)][1]]
        n = sum(a[1] for _, a in e)
        if not n:
            continue
        ev = sum(a[0] for _, a in e) / n
        ow = [(a[1], agg[("orig", d, sc)]) for sc, a in e if agg[("orig", d, sc)][1]]
        orig = sum(w * o[0] / o[1] for w, o in ow) / sum(w for w, _ in ow) if ow else None
        out.append({"day": d, "evolved_per_bet": round(ev, 4), "original_same_coins_per_bet": None if orig is None else round(orig, 4),
                    "evolved_bets": int(n)})
        log(f"  {time.strftime('%b %d', time.gmtime(d * 86400))}: evolved {ev:+.3f}/bet ({int(n)} bets) vs original "
            f"{'n/a' if orig is None else f'{orig:+.3f}'}/bet on the same coins")
    if not out:
        log("  evolved vs original: no full forward day yet")
    return out


def show_board(n=25, log=print):
    rows = [r for r in board() if r["filled"] >= 10]
    rows.sort(key=lambda r: -strength(r))
    log(f"{len(gens())} batches, {sum(1 for _ in board())} strategies; top {n} by forward strength (t shrunk by fills):")
    log("evolved vs original strategies, same days:")
    compare(log)
    for r in rows[:n]:
        log(f"  {r['id'] + '@g' + str(r['gen']):40s} {r['filled']:>4} fills  ${r['pnl']:>7.2f}  t {r['t']:>5.2f}  "
            f"{r['days_up']}/{r['days_traded']} days up  ({r['fwd_days']:.1f} forward days)")


def main(args=None):
    args = list(args or [])
    w = int(args[1]) if len(args) > 1 and args[1].isdigit() else 3
    def log(m):
        print(m, flush=True)
    if not args or args[0] == "once":
        once(w, log, score="no-score" not in args)
    elif args[0] == "loop":
        loop(w, log)
    elif args[0] == "board":
        show_board(log=log)
    else:
        sys.exit("usage: python -m kalshi15m evolve once [WORKERS] [no-score] | loop [WORKERS] | board")
