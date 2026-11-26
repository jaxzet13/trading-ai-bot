"""The packs after the clean-up: the 35 first cards (stick figures, the ones that look right) plus the few new paintings that read well as text.
Packs share the twelve commons as fillers; each pack's rare slot is a window on the ladder of rare cards, higher up in the dearer packs.
    python3 pool.py   # roster_full.json (everything that was made) -> roster.json (what ships)"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); full = json.load(open(os.path.join(HERE, 'roster_full.json')))
by = {c['id']: c for p in full for c in p['fill'] + p['rare']}
# the glyph cards: scenes that live as text (src/js/06c-glyph.js). Each one is rare, and each has its own animation.
import importlib.util
_sp = importlib.util.spec_from_file_location('roster', os.path.join(HERE, 'roster.py')); RR = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(RR)
NEWG = [('candle', '160', 'Last Candle', 12, 'ms', 'it burns for whoever is looking.', '#ffb866'), ('bouquet', '161', 'Bouquet', 30, 'ec', 'for no one in particular. for everyone.', '#ff7ad0'), ('heartword', '162', 'Heartword', 70, 'td', 'every word in it is you.', '#ff6b8f'),
        ('morpho', '163', 'Morpho', 140, 'sg', 'it only shows its blue when it flies.', '#4fd0ff'), ('phoenix', '164', 'Phoenix', 400, 'sg', 'burns out. comes back rarer.', '#ff7a1f')]
for _id, _no, _nm, _v, _set, _cap, _tint in NEWG:
    _r = RR.rarity(_v); by[_id] = dict(no=_no, id=_id, name=_nm, sub='glyph scene', rar=_r, chars=RR.CHARS[_r], val=round(_v * 500), tint=_tint, cap=_cap, styles=False, set=_set, pack=_set, kind='rare')
COMMONS = ['stitch', 'brick', 'orbit', 'rook', 'mop', 'pan', 'cone', 'fuse', 'countdown', 'spark', 'flare', 'bubble']
FILL = dict(fp=[], ms=['ms062', 'ms068', 'ms069'], ec=['ec081', 'ec085'], td=[], sg=[])
RARE0 = dict(fp=['tempest', 'surge', 'ignition', 'console', 'phantom', 'kraken', 'suit', 'colossus', 'gantry', 'leviathan'],
            ms=['suit', 'ms074', 'colossus', 'gantry', 'leviathan', 'liftoff', 'null', 'booster', 'shogun'],
            ec=['leviathan', 'liftoff', 'null', 'booster', 'shogun', 'apogee', 'ronin', 'luna'],
            td=['booster', 'shogun', 'apogee', 'ronin', 'luna', 'titan', 'grimm', 'reaper'],
            sg=['ronin', 'luna', 'titan', 'grimm', 'reaper', 'mars', 'umbra', 'horizon'])
RARE = {k: v + dict(fp=[], ms=['candle'], ec=['candle', 'bouquet'], td=['bouquet', 'heartword'], sg=['heartword', 'morpho', 'phoenix'])[k] for k, v in RARE0.items()}
out = []
for pk in ['fp', 'ms', 'ec', 'td', 'sg']:
    fill = [dict(by[i], kind='common' if by[i].get('kind') == 'common' else by[i].get('kind', 'common')) for i in COMMONS + FILL[pk]]
    rare = [dict(by[i], kind='rare') for i in RARE[pk]]
    for c in fill + rare: c['pack'] = pk
    out.append(dict(pack=pk, fill=fill, rare=sorted(rare, key=lambda c: c['val'])))
json.dump(out, open(os.path.join(HERE, 'roster.json'), 'w'), indent=1)
keep = {c['id'] for p in out for c in p['fill'] + p['rare']}; allid = set(by)
print(len(keep), 'cards ship;', len(allid - keep), 'dropped'); print(sorted(allid - keep)[:5], '...')
json.dump(sorted(allid - keep), open(os.path.join(HERE, 'dropped.json'), 'w'))
