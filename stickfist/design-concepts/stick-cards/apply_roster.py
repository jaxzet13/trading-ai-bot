"""Writes roster.json and slots.json into src/js/01-data.js: the card list (existing cards get their new value and rarity, the new ones are added) and the five packs."""
import json, os, re
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.normpath(os.path.join(HERE, '..', '..', 'src', 'js', '01-data.js'))
roster = json.load(open(os.path.join(HERE, 'roster.json'))); slots = json.load(open(os.path.join(HERE, 'slots.json')))
import importlib.util; spec = importlib.util.spec_from_file_location('roster', os.path.join(HERE, 'roster.py')); R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
s = open(P).read()
cards = [c for pk in roster for c in pk['fill'] + pk['rare']]
for c in cards:
    if not c.get('existing'): continue
    s, n = re.subn(r'(id: "%s",[^\n]*?rar: )"\w+"([^\n]*?val:\s*)\d+' % c['id'], lambda m: m.group(1) + '"%s"' % R.rarity(c['val'] / 500) + m.group(2) + str(c['val']), s, count=1); assert n == 1, c['id']
seen = set(); new = []
for c in cards:
    if not c.get('existing') and c['id'] not in seen: seen.add(c['id']); new.append(c)
lines = ''.join('  { no: "%s", set: "%s", id: "%s", name: "%s", sub: "%s", rar: "%s", chars: %d, val: %d, tint: "%s", cap: "%s", styles: false },\n' % (c['no'], c['set'], c['id'], c['name'], c['sub'], c['rar'], c['chars'], c['val'], c['tint'], c['cap'].replace('"', "'")) for c in new)
s = re.sub(r'\n  // generated cards.*?\n(?=\];)', '\n', s, flags=re.S) if '// generated cards' in s else s
i = s.index('const CARDS = ['); j = s.index('\n];', i)
k = s.rindex('\n', 0, j); s = s[:k] + (',' if not s[:k].rstrip().endswith(',') else '') + s[k:]; j = s.index('\n];', i)
s = s[:j + 1] + '  // generated cards: drawn in code (design-concepts/stick-cards), the new paintings that read well as text\n' + lines + s[j + 1:]
s = s.replace('const SETS = { fp: { code: "IS", name: "First Print" }, ms: { code: "MS", name: "Moonshot" } };', 'const SETS = { fp: { code: "IS", name: "First Print" }, ms: { code: "MS", name: "Moonshot" }, ec: { code: "EC", name: "Eclipse" }, td: { code: "TD", name: "Tidal" }, sg: { code: "SG", name: "Singularity" } };')
META = {'fp': ('First Print', 'Stick figures made of text. Seven cards a pack, and the fifth is the one you open it for. Cards from $0.10 to $20.', '#3be477', 'print', 500),
        'ms': ('Moonshot', 'A launch: lit fuses, rockets, mission control and the Moon. Cards from $1 to $100.', '#ffa046', 'launch', 2500),
        'ec': ('Eclipse', 'Cards from under a black sun. Cards from $3 to $200.', '#ffc24a', 'eclipse', 5000),
        'td': ('Tidal', 'The big names. Cards from $8 to $500.', '#46d2ff', 'tidal', 12500),
        'sg': ('Singularity', 'The edge of the dark. Cards from $15 to $1,000.', '#b78cff', 'void', 25000)}
rows = []; RP = {p['pack']: p['rare'] for p in roster}; EG = {p['pack']: p['edges'] for p in roster}
for pid in ['fp', 'ms', 'ec', 'td', 'sg']:
    name, blurb, col, scene, price = META[pid]
    sl = ',\n      '.join(name_ + ': [' + ',\n        '.join('[' + ', '.join('["%s", %s]' % (c, '%g' % w) for c, w in x) + ']' for x in slots[pid][name_]) + ']' for name_ in ('normal', 'high', 'max'))
    rows.append('  { id: "%s", name: "%s", blurb: "%s", price: %d, min: %d, max: %d, edges: %s, n: 7, col: "%s", scene: "%s",\n    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of %d cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],\n    slotsBy: {\n      %s\n    },\n    get slots() { return this.slotsBy[packStyleOf(this.id)]; } }' % (pid, name, blurb, price, price, price, json.dumps(EG[pid]), col, scene, len(RP[pid]), sl))
a = s.index('const PACKS = ['); b = s.index('const RARE_SLOT')
s = s[:a] + 'const PACKS = [\n  // Five packs that share the twelve commons as fillers (cards 1 to 4, 6 and 7); card 5 is the rare slot, a window on the ladder of rare cards\n  // that starts higher up in the dearer packs. A dearer pack\'s rare slot starts higher up the ladder. Every pack returns 94.7% on average.\n' + ',\n'.join(rows) + '\n];\n' + s[b:]
open(P, 'w').write(s); print(len(new), 'cards added')
