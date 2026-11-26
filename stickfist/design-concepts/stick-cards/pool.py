"""The packs after the clean-up: the 35 first cards (stick figures, the ones that look right) plus the few new paintings that read well as text.
Packs share the twelve commons as fillers; each pack's rare slot is a window on the ladder of rare cards, higher up in the dearer packs.
    python3 pool.py   # roster_full.json (everything that was made) -> roster.json (what ships)"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); full = json.load(open(os.path.join(HERE, 'roster_full.json')))
by = {c['id']: c for p in full for c in p['fill'] + p['rare']}
COMMONS = ['stitch', 'brick', 'orbit', 'rook', 'mop', 'pan', 'cone', 'fuse', 'countdown', 'spark', 'flare', 'bubble']
FILL = dict(fp=[], ms=['ms062', 'ms068', 'ms069'], ec=['ec081', 'ec085'], td=[], sg=[])
RARE = dict(fp=['tempest', 'surge', 'ignition', 'console', 'phantom', 'kraken', 'suit', 'colossus', 'gantry', 'leviathan'],
            ms=['suit', 'ms074', 'colossus', 'gantry', 'leviathan', 'liftoff', 'null', 'booster', 'shogun'],
            ec=['leviathan', 'liftoff', 'null', 'booster', 'shogun', 'apogee', 'ronin', 'luna'],
            td=['booster', 'shogun', 'apogee', 'ronin', 'luna', 'titan', 'grimm', 'reaper'],
            sg=['ronin', 'luna', 'titan', 'grimm', 'reaper', 'mars', 'umbra', 'horizon'])
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
