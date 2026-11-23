"""Data files for the Tennis Arb Lab dashboard (python -m tennis report -> data/tennis/report/*.json).

Each file is a JSON array of rows (the dashboard attaches them as its datasets):
  summary.json   one row: what the recorder has seen so far and the arbs it found
  closest.json   per match, the cheapest moment to buy both sides (YES+YES or NO+NO) and how far from an arb it was
  arbs.json      every arb the live order books confirmed (collect.confirm_arbs), with its locked-in profit after fees
  tours.json     per tour: open matches now, settled matches, how they settled (normal / fair-price)
"""
from __future__ import annotations

import json
import time
from collections import defaultdict

from . import api, arb
from .collect import BOOKS, CHECKS, DATA, RESULTS

OUT = DATA / "report"
TOUR = {"KXATPMATCH": "ATP", "KXWTAMATCH": "WTA", "KXATPCHALLENGERMATCH": "ATP Challenger",
        "KXWTACHALLENGERMATCH": "WTA Challenger", "KXITFMATCH": "ITF Men", "KXITFWMATCH": "ITF Women"}


def _cost_with_fees(p1, p2):
    """Cost of one contract on each side incl. fees for a 10-contract order (fees are per order, ceil to the cent)."""
    return round(p1 + p2 + (api.fee(p1, 10) + api.fee(p2, 10)) / 10, 4)


def build(log=print):
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(BOOKS.glob("*.jsonl"))
    book, by_event, best, first_ts, last_ts, n_rows = {}, defaultdict(set), {}, None, None, 0
    for p in paths:
        for ln in open(p):
            r = json.loads(ln)
            n_rows += 1
            first_ts = first_ts or r["ts"]
            last_ts = r["ts"]
            book[r["ticker"]] = r
            by_event[r["event"]].add(r["ticker"])
            ts = by_event[r["event"]]
            if len(ts) != 2:
                continue
            a, b = (book[t] for t in sorted(ts))
            for kind, p1, p2 in (("YES+YES", a.get("yes_ask"), b.get("yes_ask")),
                                 ("NO+NO", 1 - a["yes_bid"] if a.get("yes_bid") else None,
                                  1 - b["yes_bid"] if b.get("yes_bid") else None)):
                if not p1 or not p2:
                    continue
                c = _cost_with_fees(p1, p2)
                cur = best.get(r["event"])
                if cur is None or c < cur["cost_with_fees"]:
                    best[r["event"]] = {"match": f"{a.get('player')} vs {b.get('player')}", "tour": TOUR.get(r.get("series"), r.get("series")),
                                        "side": kind, "price_a": round(p1, 2), "price_b": round(p2, 2),
                                        "cost_with_fees": c, "gap_cents": round((c - 1) * 100, 1),
                                        "seen": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(r["ts"]))}
    found = arb.scan(paths, log=lambda m: None) if paths else []
    closest = sorted(best.values(), key=lambda x: x["cost_with_fees"])[:25]
    arbs = [{"match": x["event"], "tour": TOUR.get(x.get("series"), x.get("series")), "side": x["kind"].upper(),
             "contracts": x["n"], "cost": x["cost"], "profit": x["profit"],
             "opened": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(x["ts"]))} for x in found]
    # open matches now: the latest row per market, two markets per match
    open_now = defaultdict(int)
    for e, ts in by_event.items():
        rows = [book[t] for t in ts]
        if len(rows) == 2 and last_ts and all(last_ts - r["ts"] < 6 * 3600 for r in rows):
            open_now[TOUR.get(rows[0].get("series"), rows[0].get("series"))] += 1
    settled = defaultdict(lambda: [0, 0])
    ev = defaultdict(list)
    if RESULTS.exists():
        for ln in open(RESULTS):
            r = json.loads(ln)
            ev[(r["series"], r["event"])].append(r["result"])
    for (s, e), rs in ev.items():
        t = TOUR.get(s, s)
        settled[t][0] += 1
        settled[t][1] += all(x == "scalar" for x in rs)
    tours = [{"tour": t, "open_now": open_now.get(t, 0), "settled": settled[t][0],
              "fair_price_settled": settled[t][1],
              "fair_price_pct": round(100 * settled[t][1] / settled[t][0], 1) if settled[t][0] else None}
             for t in TOUR.values()]
    # arbs seen in the market list, re-checked at once against the live order books
    listed = confirmed = 0
    conf_profit = 0.0
    confirmed_rows = []
    if CHECKS.exists():
        for ln in open(CHECKS):
            c = json.loads(ln)
            listed += 1
            if c.get("live"):
                confirmed += 1
                best_live = max(c["live"], key=lambda x: x["profit"])
                conf_profit += best_live["profit"]
                confirmed_rows.append({"match": c["event"], "tour": TOUR.get(c.get("series"), c.get("series")),
                                       "side": best_live["kind"].upper(), "contracts": best_live["n"],
                                       "cost": best_live["cost"], "profit": best_live["profit"],
                                       "opened": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(c["ts"]))})
    hours = round((last_ts - first_ts) / 3600, 1) if first_ts else 0.0
    summary = [{"hours_recorded": hours, "price_updates": n_rows, "matches_seen": len(by_event),
                "open_matches_now": sum(open_now.values()), "arbs_listed": len(arbs),
                "arbs_checked": listed, "arbs_confirmed": confirmed, "confirmed_profit": round(conf_profit, 2),
                "closest_gap_cents": closest[0]["gap_cents"] if closest else None,
                "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}]
    arbs = confirmed_rows                         # the dashboard lists only arbs the live books confirmed
    for name, rows in (("summary", summary), ("closest", closest), ("arbs", arbs), ("tours", tours)):
        (OUT / f"{name}.json").write_text(json.dumps(rows, indent=0))
    log(f"report: {hours} h recorded, {len(by_event)} matches, {summary[0]['arbs_listed']} arbs in the market list, "
        f"{confirmed}/{listed} confirmed in the live books")
    return summary[0]
