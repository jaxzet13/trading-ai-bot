#!/usr/bin/env python3
"""Assemble a Requiem run: the exact list of sealed packs, shuffled, with a fingerprint you publish before the first sale.

A physical run is finite, so the odds on the page have to be the real counts. This turns the slot tables in src/js/01b-limited.js into whole cards:
for each slot, N packs x each card's share, rounded to whole cards by largest remainder, so every slot has exactly N cards. Then every slot is shuffled on its own and
the three slots are zipped into N packs. A card that rounds to zero is still printed once (--allow-missing turns that off), so every card exists in the run; the true counts
are in the output and are what the page shows.

    python requiem_run.py --packs 2500                  # writes ../../data/requiem-run.json (SECRET until the run sells out) and requiem-run.public.json
    python requiem_run.py --packs 2500 --out some/dir
    python requiem_run.py --packs 2500 --seed test      # a repeatable shuffle, for tests only: a real run must use the default, an unpredictable shuffle

What to do with the output:
  1. Print exactly the counts in requiem-run.public.json (that is how many of each card to order).
  2. Publish the "commit" (the SHA-256 of requiem-run.json) before the sale opens. The server refuses to sell if the file changes after the first sale.
  3. Keep requiem-run.json private while packs are being sold: it says what is in pack 1, pack 2 and so on. Pack the real packs in this order and number them.
  4. When the run is sold out, publish requiem-run.json. Anyone can check its SHA-256 against the commit, and see what was in their pack number.
Nobody involved in selling should buy packs to chase a rare card: you know the order, so anyone who can see the file can cherry-pick. Have the file held by someone who isn't buying, or
accept that the commit proves the list wasn't changed but not that the seller never peeked.
"""
import argparse, datetime, hashlib, json, os, random, re, secrets

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))


def read_slots():
    src = open(os.path.join(ROOT, 'src', 'js', '01b-limited.js'), encoding='utf-8').read()
    m = re.search(r'slots:\s*(\[\s*\[\[.*?\]\s*\]\s*\])\s*,\s*slotNames', src, re.S)
    assert m, 'could not find the slot tables in 01b-limited.js'
    return json.loads(re.sub(r'(?<![\d])\.(\d)', r'0.\1', m.group(1)))


def largest_remainder(weights, total):
    s = sum(w for _, w in weights); raw = [(c, total * w / s, w) for c, w in weights]
    out = {c: int(x) for c, x, _ in raw}; short = total - sum(out.values())
    for c, x, w in sorted(raw, key=lambda r: (-(r[1] - int(r[1])), -r[2]))[:short]: out[c] += 1
    return out


def assemble(n, rng, allow_missing=False):
    slots = read_slots(); per_slot = [largest_remainder(sl, n) for sl in slots]
    if not allow_missing:                                               # every card exists at least once
        every = {c for sl in slots for c, _ in sl}
        for c in sorted(every):
            if sum(p.get(c, 0) for p in per_slot) == 0:
                k = max(i for i, sl in enumerate(slots) if any(x == c for x, _ in sl))          # the richest slot that can hold it
                take = max((x for x in per_slot[k] if x != c), key=lambda x: per_slot[k][x]); per_slot[k][take] -= 1; per_slot[k][c] = per_slot[k].get(c, 0) + 1
    lists = []
    for p in per_slot:
        cards = [c for c, k in sorted(p.items()) for _ in range(k)]; rng.shuffle(cards); lists.append(cards)
    assert all(len(x) == n for x in lists)
    return [list(t) for t in zip(*lists)], per_slot


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--packs', type=int, required=True, help='how many packs are in the run')
    ap.add_argument('--out', default=os.path.join(ROOT, 'data')); ap.add_argument('--seed', default='', help='a repeatable shuffle, for tests only')
    ap.add_argument('--allow-missing', action='store_true', help='let a card that rounds to zero stay out of the run')
    a = ap.parse_args(); assert a.packs >= 1
    rng = random.Random(a.seed) if a.seed else random.SystemRandom()
    packs, per_slot = assemble(a.packs, rng, a.allow_missing)
    run = dict(v=1, made=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), n=a.packs, salt=secrets.token_hex(16) if not a.seed else 'test', packs=packs)
    raw = json.dumps(run, separators=(',', ':')).encode(); commit = hashlib.sha256(raw).hexdigest()
    totals = {}
    for p in packs:
        for c in p: totals[c] = totals.get(c, 0) + 1
    os.makedirs(a.out, exist_ok=True)
    open(os.path.join(a.out, 'requiem-run.json'), 'wb').write(raw)
    pub = dict(n=a.packs, commit=commit, made=run['made'], counts=totals, per_slot=per_slot)
    open(os.path.join(a.out, 'requiem-run.public.json'), 'w').write(json.dumps(pub, indent=1))
    print(f"{a.packs} packs, {3 * a.packs} cards. SHA-256 commit: {commit}")
    for c, k in sorted(totals.items(), key=lambda x: x[1]): print(f"  {c:<11} {k:>6}   (1 in {a.packs / k:,.0f} packs on average)")
    print(f"wrote {os.path.join(a.out, 'requiem-run.json')} (keep private) and requiem-run.public.json")


if __name__ == '__main__':
    main()
