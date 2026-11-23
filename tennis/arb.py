"""Risk-free arbs in the recorded tennis books (python -m tennis arbs).

A match event has two markets, one per player, and exactly one settles YES when the match is played out. So:
  * YES on both players pays exactly $1: an arb when yes_ask(A) + yes_ask(B) + both fees < $1.
  * NO on both players also pays exactly $1: an arb when no_ask(A) + no_ask(B) + both fees < $1
    (no_ask = 1 - yes_bid; the size is the yes-bid size).
Fees are Kalshi's taker fee per order (api.fee), computed on the contracts that are actually available, so a
'profit' here is what a taker could really have locked in at that moment. Matches that are not played out:
checked on 3,000 settled matches (Oct 2 - Nov 23), 97% settled one YES / one NO; the other 3% ('scalar': injury,
walkover, cancellation before a ball is played) settle both markets at a fair price that adds up to exactly $1
(e.g. 0.34 + 0.66), so YES+YES and NO+NO still pay exactly $1. A retirement after play starts settles normally.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from . import api
from .collect import BOOKS

MAX_CONTRACTS = 100


def legs_profit(p1, s1, p2, s2, cap=MAX_CONTRACTS):
    """Best locked-in profit buying n of each leg at prices p1, p2 (sizes s1, s2) -> (profit $, n) or None."""
    if None in (p1, p2, s1, s2) or p1 <= 0 or p2 <= 0:
        return None
    best = None
    for n in range(1, int(min(s1, s2, cap)) + 1):
        prof = n * (1 - p1 - p2) - api.fee(p1, n) - api.fee(p2, n)
        if prof > 0 and (best is None or prof > best[0]):
            best = (round(prof, 4), n)
    return best


def check(a, b):
    """Arbs between the two players' markets a, b (top_of_book rows) -> list of dicts."""
    out = []
    y = legs_profit(a["yes_ask"], a["yes_ask_size"], b["yes_ask"], b["yes_ask_size"])
    if y:
        out.append({"kind": "yes+yes", "profit": y[0], "n": y[1], "cost": round(a["yes_ask"] + b["yes_ask"], 4)})
    nA = 1 - a["yes_bid"] if a.get("yes_bid") else None
    nB = 1 - b["yes_bid"] if b.get("yes_bid") else None
    n = legs_profit(nA, a.get("yes_bid_size"), nB, b.get("yes_bid_size"))
    if n:
        out.append({"kind": "no+no", "profit": n[0], "n": n[1], "cost": round(nA + nB, 4)})
    return out


def scan(paths=None, log=print):
    """Replay the recorded books in time order, keep the latest row per market, check each match when it changes.
    An arb that stays open across snapshots is counted once (when it opens)."""
    paths = paths or sorted(BOOKS.glob("*.jsonl"))
    book, by_event, live, found = {}, defaultdict(set), set(), []
    for p in paths:
        for ln in open(p):
            r = json.loads(ln)
            book[r["ticker"]] = r
            by_event[r["event"]].add(r["ticker"])
            ts = by_event[r["event"]]
            if len(ts) != 2:
                continue
            a, b = (book[t] for t in sorted(ts))
            arbs = check(a, b)
            for x in arbs:
                key = (r["event"], x["kind"])
                if key not in live:
                    found.append({**x, "event": r["event"], "series": r.get("series"), "ts": r["ts"]})
                live.add(key)
            for kind in ("yes+yes", "no+no"):
                if not any(x["kind"] == kind for x in arbs):
                    live.discard((r["event"], kind))
    tot = sum(x["profit"] for x in found)
    log(f"arbs: {len(found)} opened in {len(paths)} day(s) of books, locked-in profit if all taken ${tot:.2f}")
    for x in found[-15:]:
        log(f"  {x['event']:40s} {x['kind']:8s} {x['n']:3d} contracts at {x['cost']:.2f}  profit ${x['profit']:.2f}")
    return found
