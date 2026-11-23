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
  4b. Empty slots (fewer than MAX_RULES live rules, e.g. after losers were cut): each policy's picks on the coins the
     live set does not trade are scored walk-forward ON THEIR OWN (walk_fill). They are added to the live set only if
     that add-on made money over >= MIN_TEST_DAYS days, with at least half the days up. (Nov 22 check: every policy's
     add-on LOST money, -0.17 to -0.96 $/day over 11 days, so the slots stay empty until that changes.)
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
    rsz = {k: [] for k in res}            # the same picks at the runner's dollar stakes (4th daily field, when scored)
    sz = lambda x: x[3] if len(x) > 3 else None
    for d in days:
        rows = eligible(ALL, d, fams)
        if not rows:
            continue
        for k, fn in POLICIES.items():
            pk = fn(rows)
            res[k].append(sum(r["daily"].get(d, [0])[0] for r in pk))
            v = [sz(r["daily"][d]) for r in pk if d in r["daily"]]
            rsz[k].append(None if None in v else sum(v))
        res["current"].append(sum(by_rid.get(i, {}).get(d, [0])[0] for i in live_ids))
        v = [sz(by_rid[i][d]) for i in live_ids if d in by_rid.get(i, {})]
        rsz["current"].append(None if None in v else sum(v))
    out = {}
    for k, v in res.items():
        s_ = [x for x in rsz[k] if x is not None]
        out[k] = {"per_day": round(sum(v) / len(v), 3) if v else None, "days": len(v), "days_up": sum(x > 0 for x in v),
                  "per_day_sized": round(sum(s_) / len(s_), 3) if s_ else None, "days_sized": len(s_)}
    return out


def walk_fill(ALL, live_ids, fams, scope_of):
    """Walk-forward test of filling the empty slots: on each day, each policy picks from coins the live set does not
    trade (using only earlier days), at most MAX_RULES - len(live) rules, scored on that day alone."""
    free = MAX_RULES - len(live_ids)
    taken = {scope_of(i) for i in live_ids}
    days = sorted({d for _, _, _, daily in ALL for d in daily})
    res = {k: [] for k in POLICIES}
    if free <= 0:
        return {k: {"per_day": None, "days": 0, "days_up": 0} for k in POLICIES}
    for d in days:
        rows = [r for r in eligible(ALL, d, fams) if r["c"]["scope"] not in taken]
        if not rows:
            continue
        for k, fn in POLICIES.items():
            res[k].append(sum(r["daily"].get(d, [0])[0] for r in fn(rows)[:free]))
    return {k: {"per_day": round(sum(v) / len(v), 3) if v else None, "days": len(v), "days_up": sum(x > 0 for x in v)}
            for k, v in res.items()}


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
    if any(W[k].get("per_day_sized") is not None for k in W):
        log("  rotate walk-forward at $1 stakes (dollar-staked like the runner; information only for now): "
            + ", ".join(f"{k} {W[k]['per_day_sized']:+.2f} ({W[k]['days_sized']} d)" for k in list(ranked) + ["current"]
                        if W[k].get("per_day_sized") is not None))
    rec = {"ts": int(time.time()), "walk": W, "best_policy": best, "live_before": live, "applied": False}
    trusted = (W[best]["days"] >= MIN_TEST_DAYS and W[best]["per_day"] > 0
               and (cur["per_day"] is None or W[best]["per_day"] > cur["per_day"]))
    picks = POLICIES[best](rows) if rows else []
    rec["picks"] = [r["rid"] for r in picks]
    new = None
    if not trusted:
        rec["reason"] = f"no policy beat the current live set walk-forward (best: {best})"
        log(f"  rotate: keep the current rules ({rec['reason']})")
        # empty slots: add rules on untraded coins only if that add-on made money walk-forward on its own
        free = MAX_RULES - len(live)
        if free > 0:
            scope_of = lambda i: GL.RULES.get(i, {}).get("scope")
            F = walk_fill(ALL, live, fams, scope_of)
            rec["fill_walk"] = F
            fr = sorted((k for k in F if F[k]["per_day"] is not None), key=lambda k: -F[k]["per_day"])
            if fr:
                log(f"  rotate fill test ({free} empty slots, add-on rules alone, $/day): "
                    + ", ".join(f"{k} {F[k]['per_day']:+.2f} ({F[k]['days_up']}/{F[k]['days']} up)" for k in fr))
                fb = fr[0]
                if F[fb]["days"] >= MIN_TEST_DAYS and F[fb]["per_day"] > 0 and 2 * F[fb]["days_up"] >= F[fb]["days"]:
                    taken = {scope_of(i) for i in live}
                    fill = POLICIES[fb]([r for r in rows if r["c"]["scope"] not in taken])[:free]
                    if fill:
                        new = [("keep", i) for i in live] + [("pick", r) for r in fill]
                        best = fb
                        why = (f"fill test: the '{fb}' policy's add-on rules made {F[fb]['per_day']:+.2f} $/day "
                               f"walk-forward ({F[fb]['days_up']}/{F[fb]['days']} days up)")
                else:
                    log("  rotate: empty slots stay empty (no add-on made money walk-forward)")
    else:
        why = (f"policy '{best}' beat the current set walk-forward ({W[best]['per_day']:+.2f} vs "
               f"{cur['per_day'] if cur['per_day'] is not None else 'n/a'} $/day)")
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
    if new is not None:
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
                f"last change {time.strftime('%b %d %H:%M UTC', time.gmtime())}: {why}. "
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
                rec["reason"] = why
                log(f"  rotate: CHANGED {live} -> {new_ids}")
    with open(ROT_LOG, "a") as f:
        f.write(json.dumps(rec, default=float) + "\n")
    restart_if_flat(log)
    return rec


def guards(log=print):
    """The runner's own brakes, read from its log the way it applies them: per live rule, the last
    limits.rule_pause_last_n real bets against limits.rule_pause_loss_usd (PAUSED once they lost that much), and the
    drawdown brake (bets halved while equity is more than limits.drawdown_brake_usd below its high-water mark).
    Halving never shows up as a skipped signal, only as smaller bets, so it is reported here."""
    cfg = json.loads(CFG.read_text())
    L = cfg["limits"]
    n, lim = L.get("rule_pause_last_n"), L.get("rule_pause_loss_usd")
    since = L.get("rule_pause_ignore_before_ts") or 0
    rule_of, pnl, order, bal = {}, {}, {}, None
    for ln in open(REAL_LOG) if REAL_LOG.exists() else []:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        tk, k = e.get("ticker"), e.get("event")
        if k == "order_intent" and tk:
            rule_of[tk] = e.get("rule")
            bal = e.get("balance_crypto", bal)
        elif k in ("settle", "exit") and tk and e.get("ts", 0) >= since and isinstance(e.get("pnl"), (int, float)):
            r = rule_of.get(tk)
            if tk not in pnl:
                order.setdefault(r, []).append(tk)
            pnl[tk] = pnl.get(tk, 0.0) + e["pnl"]
    out = {"rules": {}}
    for r in cfg["golden_rules"]:
        last = order.get(r["id"], [])[-int(n or 0):]
        tot = sum(pnl[t] for t in last)
        st = ("PAUSED" if n and len(last) >= n and tot <= -lim else "ok") if n and lim else "no auto-pause"
        out["rules"][r["id"]] = {"last_n_bets": len(last), "last_n_pnl": round(tot, 2), "state": st}
        log(f"    {r['id']:26s} last {len(last):2d} real bets ${tot:+6.2f} (pause at -${lim:.2f} over {n}): {st}")
    peak_f = REAL_LOG.with_name(REAL_LOG.stem + "_peak.json")
    brake = L.get("drawdown_brake_usd")
    if brake and peak_f.exists() and bal is not None:
        peak = json.loads(peak_f.read_text())["peak"]
        on = bal < peak - brake
        out["brake"] = {"peak": peak, "below": round(peak - brake, 2), "balance": bal, "halving": on}
        log(f"    drawdown brake: high ${peak:.2f}, bets halve below ${peak - brake:.2f}; last balance ${bal:.2f} "
            f"(excl. open bets) -> {'BETS HALVED' if on else 'full size'}")
    return out


def lab_sizing(stake=None, log=print):
    """The lab replays each live rule at 1 contract per bet; the runner stakes dollars (3% of balance), so it buys
    more contracts when the price is cheap. Lab P&L of each live rule both ways, all forward days. (Nov 23: on the
    live rules' 620 filled lab bets, entries at 15-25c returned +115% per dollar, 25-60c +13-16%, 60c+ about 0, so
    dollar staking earns more than 1 contract; real bets agree: +0.115 vs +0.069 per dollar over 415 bets.)"""
    cfg = json.loads(CFG.read_text())
    L = cfg["limits"]
    lab_path = LABDIR / "fwd_live_bets.json"
    lab = json.loads(lab_path.read_text()) if lab_path.exists() else {"rules": {}}
    if stake is None:
        bal = None
        for ln in open(REAL_LOG) if REAL_LOG.exists() else []:
            if '"order_intent"' in ln:
                try:
                    bal = json.loads(ln).get("balance_crypto", bal)
                except ValueError:
                    pass
        pct = L.get("stake_pct_of_balance")
        stake = max(L.get("stake_usd_min", L["stake_usd"]), pct * bal) if pct and bal else L["stake_usd"]
    out = {}
    log(f"  lab replay of the live rules, 1 contract vs the runner's ${stake:.2f} stakes:")
    for r in cfg["golden_rules"]:
        bets = [b for b in lab["rules"].get(r["id"], []) if b.get("filled") and b.get("limit")]
        one = sum(b["pnl"] for b in bets)
        sized = sum(b["pnl"] * max(1, int(stake // b["limit"])) for b in bets)
        cost = sum(b["limit"] * max(1, int(stake // b["limit"])) for b in bets)
        out[r["id"]] = {"bets": len(bets), "pnl_1c": round(one, 2), "pnl_sized": round(sized, 2),
                        "return_per_dollar": round(sized / cost, 3) if cost else None}
        log(f"    {r['id']:26s} {len(bets):4d} bets  1 contract ${one:+7.2f}  sized ${sized:+7.2f}"
            + (f"  ({sized / cost:+.3f} per $)" if cost else ""))
    return out


def hours(log=print):
    """Is night still better? Real bets and the lab's replay of the live rules by 4-hour UTC block, return per dollar
    staked. Since Nov 23 the runner bets x2 from 04 to 12 UTC and x0.5 otherwise (limits.stake_hour_mult) because the
    live rules made +0.37/$ real and +0.35/$ in the lab there vs +0.03 and +0.09 the rest of the day. Over the 60-day
    history (search window, 2,590 trades of the three live rules) that night edge does NOT hold: 04-12 +0.151/$ vs
    +0.137/$ otherwise (p=0.41, night ahead in 4 of 10 weeks). What does hold in all three data sets is a weak
    20-24 UTC block: history +0.007/$ vs +0.169/$ (p=0.016, worse in 8 of 10 weeks, all three rules), lab -0.08,
    real -0.06."""
    real, out = {}, {"real": {}, "lab": {}}
    for ln in open(REAL_LOG) if REAL_LOG.exists() else []:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        tk, k = e.get("ticker"), e.get("event")
        if k == "order_intent" and tk:
            real[tk] = {"ts": e.get("ts", 0), "cost": 0.0}
        elif k == "fill" and tk in real:
            real[tk]["cost"] += float(e.get("cost") or 0)
        elif k == "settle" and tk in real:
            real[tk]["pnl"] = float(e.get("pnl_kalshi", e.get("pnl")) or 0)
    lab_path = LABDIR / "fwd_live_bets.json"
    lab = json.loads(lab_path.read_text()) if lab_path.exists() else {"rules": {}}
    rows = {"real": [(v["ts"], v["pnl"], v["cost"]) for v in real.values() if "pnl" in v and v["cost"] > 0],
            "lab": [(b["ts"], b["pnl"], b["limit"]) for bs in lab["rules"].values() for b in bs if b.get("filled") and b.get("limit")]}
    blk = lambda ts: int(ts % 86400 // 3600) // 4
    for name, xs in rows.items():
        cells = []
        for b in range(6):
            sel = [x for x in xs if blk(x[0]) == b]
            c = sum(x[2] for x in sel)
            r = round(sum(x[1] for x in sel) / c, 3) if c else None
            out[name][f"{4 * b:02d}-{4 * b + 4:02d}"] = {"bets": len(sel), "per_dollar": r}
            cells.append(f"{4 * b:02d}-{4 * b + 4:02d} {r:+.2f}/$ ({len(sel)})" if r is not None else f"{4 * b:02d}-{4 * b + 4:02d} -")
        night = [x for x in xs if 4 <= int(x[0] % 86400 // 3600) < 12]
        day = [x for x in xs if not 4 <= int(x[0] % 86400 // 3600) < 12]
        f = lambda s: sum(x[1] for x in s) / sum(x[2] for x in s) if s and sum(x[2] for x in s) else 0.0
        out[name]["night_vs_day"] = [round(f(night), 3), round(f(day), 3)]
        log(f"  {name} by UTC hour, return per $: " + "  ".join(cells)
            + f"  | night 04-12 {f(night):+.2f}/$ vs day {f(day):+.2f}/$")
    return out


def tracking(hours=24, log=print):
    """Cold strategy or broken bot? For each live rule over the last `hours`: real bets and P&L vs the forward lab's
    replay of the same rule (data/lab/fwd_live_bets.json, Kalshi's own trades deciding fills). Both losing = the
    strategy is cold; real losing while the lab wins = an execution problem worth looking at. The lab bets 1 contract
    while the runner stakes dollars (more contracts at cheap prices), so the verdict compares real P&L per contract
    (Nov 22: NEAR real -$6.33 vs lab -$2.49 on the same 24 bets, same outcomes 24/24 and better fill prices; the gap
    was only that sizing)."""
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
                a = real.setdefault(rid_, [0, 0.0, 0.0])
                a[0] += 1
                a[1] += float(e.get("pnl") or 0)
                a[2] += float(e.get("pnl") or 0) / max(float(e.get("n") or 1), 1.0)   # per contract, as the lab bets
    out = {}
    log(f"  real vs lab, last {hours} h (to {time.strftime('%H:%M UTC', time.gmtime(upto))}):")
    for r in cfg["golden_rules"]:
        i = r["id"]
        lb = [b for b in lab["rules"].get(i, []) if b.get("filled") and since <= b["ts"] <= upto]
        rn, rp, r1 = real.get(i, [0, 0.0, 0.0])
        lp = sum(b["pnl"] for b in lb)
        verdict = ("no bets" if not rn and not lb else "cold strategy (lab lost too)" if r1 < 0 and lp < 0
                   else "CHECK EXECUTION (lab made money)" if r1 < 0 <= lp and rn >= 3 else "ok")
        out[i] = {"real_bets": rn, "real_pnl": round(rp, 2), "real_pnl_1c": round(r1, 2), "lab_bets": len(lb),
                  "lab_pnl": round(lp, 2), "verdict": verdict}
        log(f"    {i:26s} real {rn:3d} bets ${rp:+6.2f} (${r1:+6.2f} at 1 contract) | lab {len(lb):3d} bets ${lp:+6.2f} | {verdict}")
    return out


def main(args=None):
    args = list(args or [])
    if "hours" in args:
        hours()
        return
    if "tracking" in args or "guards" in args:
        if "tracking" in args:
            tracking()
            lab_sizing()
            hours()
        guards()
        return
    run(apply="apply" in args)
    tracking()
    lab_sizing()
    hours()
    guards()
