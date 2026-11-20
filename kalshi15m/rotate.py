"""Which strategies trade real money: automatic rotation, tested before it is trusted (python -m kalshi15m rotate [apply]).

The account holder asked (Nov 19) for the real-money strategies to be kept up to date: the most profitable ones in,
the bad ones out. Picking the forward leaders naively LOSES (fwdlab walk: the top 5 by forward t made less than the
average strategy on the following days), so the rule that picks is itself tested walk-forward before it may act:

  1. Candidates: every strategy of every batch (gen 1, gen 2, evolved batches) with >= MIN_DAYS forward days and
     >= MIN_FILLS filled bets on days after its batch froze, single-coin, profitable, of a family the live runner has
     been checked against (golden_live parity tests).
  2. Policies: a few ways to choose up to MAX_RULES rules, one per coin (the runner takes one bet per coin per window).
  3. Walk-forward: for every past day d, each policy chooses using only days before d, and is scored on day d (the
     summed forward-lab P&L of what it chose). The current live set is scored the same way.
  4. Apply only if the best policy beat the current live set over those days AND made money. Even then a live rule is
     replaced only by a clearly stronger one (hysteresis), so noise does not churn the account.
  5. Applying = register the new rules (kalshi15m/evolved_rules.json), rewrite the live config's rule list, check it
     loads, and restart the runner by PID once no bet is open (the watchdog brings it back within a minute). Bet
     size, the $4 floor and every limit stay as they are. Every decision goes to data/lab/rotation_log.jsonl.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABDIR = ROOT / "data" / "lab"
CFG = ROOT / "kalshi15m" / "real_top5_live.json"
REG = ROOT / "kalshi15m" / "evolved_rules.json"
ROT_LOG = LABDIR / "rotation_log.jsonl"
RUNNER_ARGS = "python3 -u -m kalshi15m real --live --config kalshi15m/real_top5_live.json"
MAX_RULES, MIN_DAYS, MIN_FILLS = 5, 7.0, 30
MIN_TEST_DAYS = 5
HYSTERESIS = 0.5          # a challenger's strength must beat the incumbent's by this much to replace it
MIN_GAP_S = 20 * 3600     # at most one rotation a day
# Account holder, Nov 20: "remove anything thats unprofitable after 25+ bets". A live rule whose REAL bets number
# CUT_MIN_BETS or more and add up to CUT_MAX_PNL or less is taken out at once, whatever the walk-forward says, and
# never comes back (kalshi15m/removed_rules.json).
CUT_MIN_BETS, CUT_MAX_PNL = 25, 0.0
REAL_LOG = ROOT / "data" / "kalshi15m" / "real_top5_live_log.jsonl"
REMOVED = ROOT / "kalshi15m" / "removed_rules.json"


def removed_ids():
    return set(json.loads(REMOVED.read_text())["rules"]) if REMOVED.exists() else set()


def real_record(path=REAL_LOG):
    """{rule id: [settled real bets, real P&L]} from the live run's log (each settlement credited to the rule that
    placed the order on that market)."""
    rule, out = {}, {}
    if not Path(path).exists():
        return out
    for ln in open(path):
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if e.get("event") == "order_intent" and e.get("rule"):
            rule[e.get("ticker")] = e["rule"]
        elif e.get("event") == "settle" and e.get("ticker") in rule:
            a = out.setdefault(rule[e["ticker"]], [0, 0.0])
            a[0] += 1
            a[1] += float(e.get("pnl") or 0)
    return out


def cut_losers(apply=False, log=print):
    """Remove live rules that lost (or broke even) over 25+ real bets. -> list of removed ids."""
    cfg = json.loads(CFG.read_text())
    rec = real_record()
    cut = [r["id"] for r in cfg["golden_rules"]
           if rec.get(r["id"], [0, 0])[0] >= CUT_MIN_BETS and rec[r["id"]][1] <= CUT_MAX_PNL]
    if not cut:
        return []
    keep = [r for r in cfg["golden_rules"] if r["id"] not in cut]
    desc = ", ".join(f"{i} (${rec[i][1]:+.2f} on {rec[i][0]} bets)" for i in cut)
    if not keep:
        log(f"  rotate: every live rule is unprofitable after {CUT_MIN_BETS}+ bets ({desc}); left as is, tell the account holder")
        return []
    if not apply:
        log(f"  rotate: WOULD remove {desc} (dry run)")
        return []
    backup = CFG.read_text()
    new = dict(cfg)
    new["golden_rules"] = keep
    new["series"] = sorted({r["scope"] for r in keep})
    new["_note"] = cfg["_note"] + (f" {time.strftime('%b %d %H:%M UTC', time.gmtime())}: removed {desc}: unprofitable "
                                   f"after {CUT_MIN_BETS}+ real bets (account holder's rule, Nov 20).")
    CFG.write_text(json.dumps(new, indent=1) + "\n")
    chk = subprocess.run([sys.executable, "-c", "import sys; from kalshi15m import real; real.load_config(sys.argv[1])", str(CFG)],
                         cwd=ROOT, capture_output=True, text=True)
    if chk.returncode != 0:
        CFG.write_text(backup)
        log("  rotate: removal reverted, config failed to load")
        return []
    gone = json.loads(REMOVED.read_text()) if REMOVED.exists() else {"rules": [], "why": {}}
    for i in cut:
        if i not in gone["rules"]:
            gone["rules"].append(i)
        gone["why"][i] = {"ts": int(time.time()), "real_bets": rec[i][0], "real_pnl": round(rec[i][1], 4)}
    REMOVED.write_text(json.dumps(gone, indent=1))
    with open(ROT_LOG, "a") as f:
        f.write(json.dumps({"ts": int(time.time()), "applied": True, "removed": cut, "reason": f"unprofitable after {CUT_MIN_BETS}+ real bets",
                            "live_before": [r["id"] for r in cfg["golden_rules"]], "live_after": [r["id"] for r in keep]}) + "\n")
    log(f"  rotate: REMOVED {desc}")
    return cut


def _live_fams():
    from . import golden_live as GL
    return {r["family"] for r in GL.GOLDEN + GL.SINGLE + GL.EXTRA} - {"ens_fixed"}


def _load():
    """All batches once: [(gen, fwd_start, candidate, {day: [pnl, n, sq]})]."""
    from . import evolve as E
    out = []
    for g in E.gens():
        C = json.loads(E.cands_path(g).read_text())
        dp = E.daily_path(g)
        D = json.loads(dp.read_text())["days"] if dp.exists() else {}
        for c in C["candidates"]:
            out.append((g, int(C.get("fwd_start") or 0), c, {int(d): v for d, v in D.get(c["id"], {}).items()}))
    return out


def _stats(daily, before):
    n = s = q = 0.0
    up = nd = 0
    for d, x in daily.items():
        if d < before:
            s += x[0]; n += x[1]; q += x[2]; nd += 1; up += x[0] > 0
    t = 0.0
    if n >= 3:
        var = (q - s * s / n) / (n - 1)
        t = s / n / math.sqrt(var / n) if var > 0 else 0.0
    return n, s, t, up, nd


def rid(g, c):
    return c["id"] if g == 1 else f"{c['id']}@g{g}"


CLONE_CORR = 0.8          # same strategy type and coin as a removed rule, daily P&L this correlated: blocked too


def _corr(a, b):
    ds = sorted(set(a) | set(b))
    if len(ds) < 5:
        return 0.0
    x = [a.get(d, [0])[0] for d in ds]
    y = [b.get(d, [0])[0] for d in ds]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((u - mx) * (v - my) for u, v in zip(x, y))
    sxx, syy = sum((u - mx) ** 2 for u in x), sum((v - my) ** 2 for v in y)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0


def eligible(ALL, before, fams, gone=None):
    rows = []
    gone = removed_ids() if gone is None else gone
    gone_daily = {(c["family"], c["scope"]): [] for g, _, c, _ in ALL if rid(g, c) in gone}
    for g, _, c, daily in ALL:
        if rid(g, c) in gone:
            gone_daily[(c["family"], c["scope"])].append(daily)
    for g, start, c, daily in ALL:
        if rid(g, c) in gone:
            continue
        if any(_corr(daily, gd) >= CLONE_CORR for gd in gone_daily.get((c["family"], c["scope"]), [])):
            continue                          # a near-copy of a rule removed for losing real money
        if c["scope"] == "ALL" or c["family"] not in fams or (c.get("kind") == "sized" and not c.get("norms")):
            continue
        if (before * 86400 - start) / 86400 < MIN_DAYS:
            continue
        n, s, t, up, nd = _stats(daily, before)
        if n < MIN_FILLS or s <= 0:
            continue
        rows.append({"rid": rid(g, c), "gen": g, "c": c, "daily": daily, "filled": n, "pnl": s, "t": t,
                     "up": up / max(nd, 1), "strength": t * math.sqrt(min(n, 30) / 30),
                     "per_day": s / max((before * 86400 - start) / 86400, 1)})
    return rows


def _one_per_coin(rows, key):
    out, coins = [], set()
    for r in sorted(rows, key=key):
        if r["c"]["scope"] not in coins:
            coins.add(r["c"]["scope"])
            out.append(r)
        if len(out) >= MAX_RULES:
            break
    return out


def p_strength(rows):
    return _one_per_coin(rows, lambda r: -r["strength"])


def p_consistency(rows):          # how the Nov 12 live set was chosen: share of days up, then t
    return _one_per_coin(rows, lambda r: (-r["up"], -r["t"]))


def p_family(rows):               # rank ideas (strategy type x coin) by their members' average forward $/day
    ideas = {}
    for r in rows:
        ideas.setdefault((r["c"]["family"], r["c"]["scope"]), []).append(r)
    score = {k: sum(r["per_day"] for r in v) / len(v) for k, v in ideas.items()}
    best = [max(v, key=lambda r: r["strength"]) for k, v in sorted(ideas.items(), key=lambda kv: -score[kv[0]])]
    return _one_per_coin(best, lambda r: 0)


def p_pnl_per_day(rows):
    return _one_per_coin(rows, lambda r: -r["per_day"])


POLICIES = {"strength": p_strength, "consistency": p_consistency, "family": p_family, "pnl_per_day": p_pnl_per_day}


def walk(ALL, live_ids, fams, log=print):
    """Walk-forward test of every policy and of the current live set -> {name: {per_day, days, days_up}}."""
    days = sorted({d for _, _, _, daily in ALL for d in daily})
    by_rid = {rid(g, c): daily for g, _, c, daily in ALL}
    res = {k: [] for k in list(POLICIES) + ["current"]}
    for d in days:
        rows = eligible(ALL, d, fams)
        if not rows:
            continue
        for k, fn in POLICIES.items():
            res[k].append(sum(r["daily"].get(d, [0])[0] for r in fn(rows)))
        res["current"].append(sum(by_rid.get(i, {}).get(d, [0])[0] for i in live_ids))
    out = {k: {"per_day": round(sum(v) / len(v), 3) if v else None, "days": len(v), "days_up": sum(x > 0 for x in v)}
           for k, v in res.items()}
    return out


def _runner_pid():
    p = subprocess.run(["ps", "-eo", "pid,etimes,args"], capture_output=True, text=True).stdout.splitlines()
    for ln in p[1:]:
        pid, et, args = ln.strip().split(None, 2)
        if args.startswith(RUNNER_ARGS):
            return int(pid), int(et)
    return None, None


def _open_positions():
    """Open bets on the account (real check: reads only, places nothing). None if it cannot tell."""
    if not os.environ.get("KALSHI_KEY_ID"):
        return None
    try:
        p = subprocess.run([sys.executable, "-m", "kalshi15m", "real", "check", "--live", "--config", str(CFG)],
                           cwd=ROOT, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return None
    for ln in (p.stdout + p.stderr).splitlines():
        if ln.startswith("open positions:"):
            return int(ln.split(":")[1])
    return None


def restart_if_flat(log=print):
    """The runner reads its config at start: restart it (by PID; the watchdog restarts it within ~60 s) once the
    config is newer than the runner and no bet is open."""
    pid, et = _runner_pid()
    if pid is None or time.time() - et >= CFG.stat().st_mtime:
        return False
    n = _open_positions()
    if n != 0:
        log(f"  rotate: new rule set waits for the runner restart ({'open bets: ' + str(n) if n else 'cannot check open bets'})")
        return False
    os.kill(pid, signal.SIGTERM)
    log(f"  rotate: runner {pid} restarted on the new rule set (no bets open)")
    return True


def _rule_entry(r):
    c = r["c"]
    e = {"id": r["rid"], "family": c["family"], "scope": c["scope"], "t": round(r["t"], 2), "params": c["params"]}
    if c.get("kind") == "sized":
        e["norm"] = float(list(c["norms"].values())[0])
    return e


def run(apply=False, log=print):
    from . import golden_live as GL
    cut_losers(apply, log)
    ALL = _load()
    fams = _live_fams()
    cfg = json.loads(CFG.read_text())
    live = [r["id"] for r in cfg["golden_rules"]]
    W = walk(ALL, live, fams, log)
    today = int(time.time() // 86400) + 1
    rows = eligible(ALL, today, fams)
    cur = W["current"]
    ranked = sorted(POLICIES, key=lambda k: -(W[k]["per_day"] if W[k]["per_day"] is not None else -9e9))
    best = ranked[0]
    log("  rotate walk-forward ($/day, all chosen rules together, forward-lab bets): "
        + ", ".join(f"{k} {W[k]['per_day']:+.2f} ({W[k]['days_up']}/{W[k]['days']} up)" for k in ranked if W[k]["per_day"] is not None)
        + (f"; current live set {cur['per_day']:+.2f} ({cur['days_up']}/{cur['days']} up)" if cur["per_day"] is not None else ""))
    rec = {"ts": int(time.time()), "walk": W, "best_policy": best, "live_before": live, "applied": False}
    trusted = (W[best]["days"] >= MIN_TEST_DAYS and W[best]["per_day"] > 0
               and (cur["per_day"] is None or W[best]["per_day"] > cur["per_day"]))
    picks = POLICIES[best](rows) if rows else []
    rec["picks"] = [r["rid"] for r in picks]
    if not trusted:
        rec["reason"] = f"no policy beat the current live set walk-forward (best: {best})"
        log(f"  rotate: keep the current rules ({rec['reason']})")
    else:
        # hysteresis: keep an incumbent unless its coin's challenger is clearly stronger
        info = {r["rid"]: r for r in eligible(ALL, today, fams | {GL.RULES[i]["family"] for i in live if i in GL.RULES})}
        # real money outranks the lab: a live rule that is profitable over CUT_MIN_BETS+ real bets is never swapped out
        real = real_record()
        proven = {i for i in live if real.get(i, [0, 0])[0] >= CUT_MIN_BETS and real[i][1] > 0}
        new, coins = [("keep", i) for i in live if i in proven], {GL.RULES[i]["scope"] for i in live if i in proven}
        for p in picks:
            if p["c"]["scope"] in coins:
                continue
            inc = [i for i in live if GL.RULES.get(i, {}).get("scope") == p["c"]["scope"]]
            if inc and inc[0] != p["rid"]:
                ir = info.get(inc[0])
                if ir is not None and p["strength"] < ir["strength"] + HYSTERESIS:
                    new.append(("keep", inc[0])); coins.add(p["c"]["scope"]); continue
            new.append(("pick", p)); coins.add(p["c"]["scope"])
        for i in live:                                 # incumbents on coins no policy pick covers: kept if still good
            sc = GL.RULES.get(i, {}).get("scope")
            ir = info.get(i)
            if sc not in coins and ir is not None and len(new) < MAX_RULES:
                new.append(("keep", i)); coins.add(sc)
        new = new[:MAX_RULES]
        new_ids = [x[1] if x[0] == "keep" else x[1]["rid"] for x in new]
        rec["live_after"] = new_ids
        last = [json.loads(ln) for ln in ROT_LOG.read_text().splitlines()] if ROT_LOG.exists() else []
        last_applied = max((x["ts"] for x in last if x.get("applied")), default=0)
        if set(new_ids) == set(live):
            rec["reason"] = "the best policy keeps the current rules"
            log("  rotate: no change (the tested policy keeps the current rules)")
        elif time.time() - last_applied < MIN_GAP_S:
            rec["reason"] = "rotated less than 20 hours ago"
            log(f"  rotate: would change to {new_ids}, waiting (last rotation < 20 h ago)")
        elif not apply:
            rec["reason"] = "dry run"
            log(f"  rotate: WOULD change {live} -> {new_ids} (dry run)")
        else:
            entries = []
            reg = json.loads(REG.read_text()) if REG.exists() else {"rules": []}
            for kind, x in new:
                if kind == "keep":
                    entries.append(next(r for r in cfg["golden_rules"] if r["id"] == x))
                    continue
                e = _rule_entry(x)
                old = GL.RULES.get(e["id"])
                if old is not None and old["params"] == e["params"]:
                    e["t"] = old["t"]
                    if "norm" in old and old.get("norm") is not None:
                        e["norm"] = old["norm"]
                elif not any(r["id"] == e["id"] for r in reg["rules"]):
                    reg["rules"].append({**e, "added": int(time.time()), "policy": best})
                entries.append({k: e[k] for k in ("id", "family", "scope", "t", "params", "norm") if k in e})
            backup = CFG.read_text()
            REG.write_text(json.dumps(reg, indent=1))
            new_cfg = dict(cfg)
            new_cfg["golden_rules"] = entries
            new_cfg["series"] = sorted({e["scope"] for e in entries})
            new_cfg["_note"] = cfg["_note"].split(" Auto-rotation")[0] + (
                f" Auto-rotation (account holder, Nov 19: keep the most profitable strategies in, the bad ones out): "
                f"last change {time.strftime('%b %d %H:%M UTC', time.gmtime())} by the '{best}' policy, which beat the "
                f"previous set walk-forward ({W[best]['per_day']:+.2f} vs {cur['per_day'] if cur['per_day'] is not None else 'n/a'} $/day). "
                f"Log: data/lab/rotation_log.jsonl.")
            CFG.write_text(json.dumps(new_cfg, indent=1) + "\n")
            chk = subprocess.run([sys.executable, "-c", "import sys; from kalshi15m import real; real.load_config(sys.argv[1])", str(CFG)],
                                 cwd=ROOT, capture_output=True, text=True)
            if chk.returncode != 0:
                CFG.write_text(backup)
                rec["reason"] = "new config failed to load, reverted: " + (chk.stderr.strip().splitlines() or ["?"])[-1]
                log(f"  rotate: {rec['reason']}")
            else:
                rec["applied"] = True
                rec["reason"] = f"policy '{best}' beat the current set walk-forward"
                log(f"  rotate: CHANGED {live} -> {new_ids}")
    with open(ROT_LOG, "a") as f:
        f.write(json.dumps(rec, default=float) + "\n")
    restart_if_flat(log)
    return rec


def tracking(hours=24, log=print):
    """Cold strategy or broken bot? For each live rule over the last `hours`: real bets and P&L vs the forward lab's
    replay of the same rule (data/lab/fwd_live_bets.json, Kalshi's own trades deciding fills). Both losing = the
    strategy is cold; real losing while the lab wins = an execution problem worth looking at."""
    since = time.time() - hours * 3600
    cfg = json.loads(CFG.read_text())
    lab_path = LABDIR / "fwd_live_bets.json"
    lab = json.loads(lab_path.read_text()) if lab_path.exists() else {"rules": {}, "generated": 0}
    upto = min(time.time(), lab.get("generated", 0))
    rule, real = {}, {}
    for ln in open(REAL_LOG) if REAL_LOG.exists() else []:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if e.get("event") == "order_intent":
            rule[e.get("ticker")] = (e.get("rule"), e.get("ts", 0))
        elif e.get("event") == "settle" and e.get("ticker") in rule:
            rid_, t = rule[e["ticker"]]
            if since <= t <= upto:
                a = real.setdefault(rid_, [0, 0.0])
                a[0] += 1
                a[1] += float(e.get("pnl") or 0)
    out = {}
    log(f"  real vs lab, last {hours} h (to {time.strftime('%H:%M UTC', time.gmtime(upto))}):")
    for r in cfg["golden_rules"]:
        i = r["id"]
        lb = [b for b in lab["rules"].get(i, []) if b.get("filled") and since <= b["ts"] <= upto]
        rn, rp = real.get(i, [0, 0.0])
        lp = sum(b["pnl"] for b in lb)
        verdict = ("no bets" if not rn and not lb else "cold strategy (lab lost too)" if rp < 0 and lp < 0
                   else "CHECK EXECUTION (lab made money)" if rp < 0 <= lp and rn >= 3 else "ok")
        out[i] = {"real_bets": rn, "real_pnl": round(rp, 2), "lab_bets": len(lb), "lab_pnl": round(lp, 2), "verdict": verdict}
        log(f"    {i:26s} real {rn:3d} bets ${rp:+6.2f} | lab {len(lb):3d} bets ${lp:+6.2f} | {verdict}")
    return out


def main(args=None):
    args = list(args or [])
    if "tracking" in args:
        tracking()
        return
    run(apply="apply" in args)
    tracking()
