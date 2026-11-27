"""Triumph's ladder: five packs at $1 / $5 / $10 / $25 / $50, each with its own Min Value and Max Pull and six value bins on the rare slot (card 5).
The bins and their percentages are Triumph's, for Normal and High (read off its pack-style sheet); Max is the same shape pushed further.
Card values are set so each bin really holds a card of that value, and the rare slot's weights are solved (solve2.js) so every style of every pack returns 94.7%.
    python3 pool2.py && node solve2.js && python3 apply_roster.py"""
import json, os, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__)); full = json.load(open(os.path.join(HERE, 'roster_full.json')))
by = {c['id']: c for p in full for c in p['fill'] + p['rare']}
_sp = importlib.util.spec_from_file_location('roster', os.path.join(HERE, 'roster.py')); RR = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(RR)
for _id, _no, _nm, _set, _cap, _tint in [('vigil', '160', 'Vigil', 'ms', 'it holds the light so you can see.', '#ffb866'), ('lightwriter', '161', 'Light Writer', 'ec', 'writes in the air. gone in a second.', '#ff7ad0'), ('heartstring', '162', 'Heartstring', 'td', 'it floats as long as you hold on.', '#ff6b8f'), ('morpho', '163', 'Morpho', 'sg', 'grew wings. forgot how to land.', '#4fd0ff'), ('phoenix', '164', 'Phoenix', 'sg', 'burns out. comes back rarer.', '#ff7a1f')]:
    by[_id] = dict(no=_no, id=_id, name=_nm, sub='glyph scene', rar='rare', chars=0, val=0, tint=_tint, cap=_cap, styles=False, set=_set, pack=_set, kind='rare')
PACKS = ['fp', 'ms', 'ec', 'td', 'sg']; PRICE = dict(fp=1, ms=5, ec=10, td=25, sg=50); MIN = dict(fp=.10, ms=1, ec=3, td=8, sg=15); MAX = dict(fp=20, ms=100, ec=200, td=500, sg=1000)
MULT = [1, 2, 5, 6, 8, 10]; F = .02
PCT = dict(normal=[.313, .187, .192, .19, .07, .048], high=[.398, .402, .026, .04, .028, .107], max=[.46, .36, .015, .025, .015, .125])
COMMONS = ['stitch', 'brick', 'orbit', 'rook', 'mop', 'pan', 'cone', 'fuse', 'countdown', 'spark', 'flare', 'bubble']
# weakest to strongest: the cards that carry the five packs' rare slot
RANK = ['tempest', 'surge', 'ignition', 'vigil', 'console', 'phantom', 'kraken', 'ms069', 'colossus', 'lightwriter', 'ec081', 'suit', 'leviathan', 'gantry', 'ec085', 'liftoff', 'heartstring', 'null', 'booster', 'shogun', 'ms074', 'morpho', 'apogee', 'ronin', 'luna', 'titan', 'phoenix', 'grimm', 'reaper', 'mars', 'umbra', 'horizon']
EDGES = {}
slots = {}   # pack -> list of (bin, value in dollars, key)
A = {}       # the cheap card of each pack's top bin (the dearest card, the Max Pull, is the other one)
for i, pk in enumerate(PACKS):
    g = dict(fp=1, ms=1, ec=.5, td=.45, sg=.5)[pk]; e = [round(MIN[pk] * (1 + g * (m - 1)), 2) for m in MULT] + [MAX[pk]]
    EDGES[pk] = e; cards = []
    for b in range(5):
        prev = A.get(PACKS[i - 1]) if i else None      # the cheap top-bin card of the pack below fits one of this pack's bins: it plays that bin here
        if prev and e[b] <= prev[0] < e[b + 1]: cards.append((b, prev[0], prev[1]))
        else: cards.append((b, e[b] + F * (e[b + 1] - e[b]), pk + str(b)))
    av = 1.5 * e[5] if False else (1.5 if i == 0 else e[5]); A[pk] = (av, pk + 'A')
    cards.append((5, av, pk + 'A')); cards.append((5, MAX[pk], pk + 'B'))
    slots[pk] = cards
keys = {}
for pk in PACKS:
    for b, v, k in slots[pk]: keys[k] = v
order = sorted(keys, key=lambda k: keys[k]); assert len(order) <= len(RANK), (len(order), len(RANK))
who = {k: RANK[i] for i, k in enumerate(order)}
out = []
for pk in PACKS:
    fill = [dict(by[i], kind='common', pack=pk) for i in COMMONS] + ([dict(by[i], kind='uncommon', pack=pk) for i in ('ms062', 'ms068')] if pk == 'ms' else [])
    rare = []
    for b, v, k in slots[pk]:
        c = dict(by[who[k]], pack=pk, kind='rare'); r = RR.rarity(v); c.update(val=round(v * 500), rar=r, chars=RR.CHARS[r], bin=b, top=(b == 5 and v == MAX[pk])); rare.append(c)
    out.append(dict(pack=pk, fill=fill, rare=rare, price=PRICE[pk], pct=PCT, edges=EDGES[pk]))
json.dump(out, open(os.path.join(HERE, 'roster.json'), 'w'), indent=1)
for p in out: print(p['pack'], '$%g' % p['price'], [(c['id'], c['val'] / 500) for c in p['rare']])
print(len(set(c['id'] for p in out for c in p['rare'])), 'rare cards')
