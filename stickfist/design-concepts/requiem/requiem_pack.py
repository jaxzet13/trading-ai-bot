#!/usr/bin/env python3
"""Requiem pack maths. The same numbers the app works out in 04-state.js (evOf / packDist), in Python, so the odds printed on the page can be checked.

A pack is a list of slots; a slot is a list of (card id, weight). A card sells back for 90% of its value (SELLBACK, the same rule every pack uses).
  ev   = what a pack sells back for on average
  rtp  = ev / price
  hit  = the chance a pack sells back for at least what it cost
  median = the middle outcome

    python requiem_pack.py            # print the table for the pack that ships in src/js/01b-limited.js (kept in sync by hand: see PACK below)
    python requiem_pack.py --json     # the PACK as JSON
"""
import json, sys
import numpy as np

SELLBACK = 0.9
CARDS = {  # value in cents: what the card is worth at launch (a guide, not a promise; real prices will be set by whoever buys and sells them)
    'pallbearer': 900, 'vigil': 1800, 'halation': 5500, 'witness': 16000, 'orrery': 52000, 'seraph': 360000,
}
PRICE = 6500
PACK = dict(price=PRICE, slots=[
    [('pallbearer', 72), ('vigil', 28)],
    [('pallbearer', 36), ('vigil', 56.5), ('halation', 6.6), ('witness', 0.9)],
    [('pallbearer', 14), ('vigil', 63.3), ('halation', 17.6), ('witness', 4.4), ('orrery', 0.64), ('seraph', 0.04)],
])


def sell(v): return int(np.floor(v * SELLBACK))


def stats(pack, values=CARDS):
    price = pack['price']; cap = price * 4
    dist = np.zeros(cap + 1); dist[0] = 1.0; ev = 0.0
    for slot in pack['slots']:
        t = sum(w for _, w in slot)
        outs = {}
        for cid, w in slot: outs[sell(values[cid])] = outs.get(sell(values[cid]), 0) + w / t
        ev += sum(v * p for v, p in outs.items())
        nxt = np.zeros(cap + 1)
        for v, p in outs.items():
            if v >= cap: nxt[cap] += p * dist.sum(); continue
            nxt[v:cap] += p * dist[:cap - v]; nxt[cap] += p * dist[cap - v:].sum()
        dist = nxt
    hit = dist[price:].sum(); acc = np.cumsum(dist); med = int(np.searchsorted(acc, 0.5))
    return dict(ev=ev, rtp=ev / price, hit=hit, median=med, dist=dist)


def card_chance(pack, cid):
    q = 1.0
    for slot in pack['slots']:
        t = sum(w for _, w in slot); q *= 1 - sum(w for c, w in slot if c == cid) / t
    return 1 - q


if __name__ == '__main__':
    if '--json' in sys.argv:
        print(json.dumps(PACK)); sys.exit()
    s = stats(PACK)
    print(f"price ${PRICE / 100:.2f}  cards per pack {len(PACK['slots'])}")
    print(f"average card value ${sum(sum(w*CARDS[c] for c,w in sl)/sum(w for _,w in sl) for sl in PACK['slots'])/100:.2f}")
    print(f"average sell-back ${s['ev'] / 100:.2f} = {s['rtp'] * 100:.1f}% of the price   chance of selling back at least the price {s['hit'] * 100:.1f}%   middle pack ${s['median'] / 100:.2f}")
    floor = sum(min(sell(CARDS[c]) for c, _ in sl) for sl in PACK['slots'])
    print(f"the worst possible pack sells back for ${floor / 100:.2f} ({floor / PRICE * 100:.0f}% of the price)")
    for c in CARDS:
        p = card_chance(PACK, c); print(f"  {c:<11} value ${CARDS[c] / 100:>9,.2f}   in {p * 100:6.2f}% of packs   (1 in {1 / p:,.0f})")
