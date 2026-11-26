"""The roster: 30 different cards in each of the five packs (150 in all).
  - 18 fillers a pack (12 commons and 6 uncommons): the cards in slots 1 to 4, 6 and 7
  - 12 rare-slot cards a pack, dearest last: the cards you open a pack for
The 35 cards that already existed (their art is illustrated) keep their pictures and are placed in the pack that fits their value; the other 115
are drawn in code (draw.py), then turned into text (../ascii_cards.py).

    python3 roster.py            # writes roster.json (and nothing else)
    python3 roster.py --draw     # also draws every new card into sources/ and converts them to cards/ (900 wide) and cards/s/ (360 wide)
"""
import json, os, random, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))

PACKS = ['fp', 'ms', 'ec', 'td', 'sg']
# values in dollars; the ones named are the existing illustrated cards
COMMON_VALS = [.02, .025, .03, .03, .035, .04, .04, .045, .05, .05, .055, .06]
EXIST_COMMONS = ['stitch', 'brick', 'orbit', 'rook', 'mop', 'pan', 'cone', 'fuse', 'countdown', 'spark', 'flare', 'bubble']
EXIST_VALS = [.03, .03, .04, .03, .03, .04, .04, .04, .05, .05, .05, .06]
UNC_VALS = [.08, .10, .12, .14, .17, .20]
RARE = {   # dearest last; None = a new card is drawn, a name = an existing illustrated card
    'fp': [(.25, None), (.30, 'tempest'), (.35, 'surge'), (.40, 'ignition'), (.45, 'console'), (.55, None), (.70, 'phantom'), (.90, 'kraken'), (1.2, 'suit'), (1.6, 'colossus'), (2.2, 'gantry'), (3.0, None)],
    'ms': [(.6, None), (.8, None), (1.1, None), (1.5, None), (2.0, None), (2.8, None), (3.2, 'leviathan'), (4.4, 'liftoff'), (6.5, 'null'), (8, 'booster'), (11, 'shogun'), (15, None)],
    'ec': [(1.5, None), (2.2, None), (3.0, None), (4.0, None), (5.5, None), (7.5, None), (10, None), (13, 'apogee'), (17, 'ronin'), (22, 'luna'), (28, None), (34, None)],
    'td': [(4, None), (5.5, None), (7.5, None), (10, None), (14, None), (19, None), (26, None), (32, None), (38, 'titan'), (60, 'grimm'), (85, None), (110, 'reaper')],
    'sg': [(9, None), (12, None), (16, None), (22, None), (30, None), (42, None), (58, None), (80, None), (150, 'mars'), (220, 'umbra'), (300, None), (450, 'horizon')],
}
def rarity(v):
    for lim, name in ((.07, 'common'), (.25, 'uncommon'), (.65, 'rare'), (1.5, 'epic'), (4.5, 'legendary'), (9, 'mythic'), (14, 'exotic'), (25, 'divine'), (45, 'celestial'), (75, 'cosmic'), (130, 'eternal'), (260, 'ascended')):
        if v < lim: return name
    return 'secret'
CHARS = dict(common=6432, uncommon=7260, rare=9800, epic=15750, legendary=29400, mythic=40320, exotic=52000, divine=72000, celestial=100000, cosmic=150000, eternal=220000, ascended=380000, secret=700000)

HATS = ['crown', 'cone', 'tophat', 'pot', 'flower', 'antenna', 'halo', 'helmet', 'party', 'beanie', 'frog', 'horns', 'wizard', 'chef', 'phones']
HAT_WORD = dict(crown='Royal', cone='Cone', tophat='Fancy', pot='Pot', flower='Bloom', antenna='Signal', halo='Holy', helmet='Hard Hat', party='Party', beanie='Cozy', frog='Froggy', horns='Devil', wizard='Wizard', chef='Chef', phones='DJ', none='')
PROPS = {   # noun, caption
    'umbrella': ('Umbrella', 'forecast: dry.'), 'balloon': ('Balloon', 'held on a little too tight.'), 'sword': ('Sword', 'it is mostly for pointing.'), 'flag': ('Flag', 'claimed it. no one asked.'),
    'lantern': ('Lantern', 'walks home the long way.'), 'cup': ('Cup', 'refills are a lifestyle.'), 'fish': ('Fish', 'caught it. kept it. named it.'), 'book': ('Book', 'on page one. forever.'),
    'bat': ('Bat', 'swings first, thinks later.'), 'trophy': ('Trophy', 'participation, officially.'), 'scope': ('Scope', 'sees everything. says little.'), 'kite': ('Kite', 'wind is a team sport.'),
    'guitar': ('Guitar', 'knows three chords. uses two.'), 'wrench': ('Wrench', 'it was already broken.'), 'torch': ('Torch', 'light it. regret nothing.'), 'shield': ('Shield', 'blocks mostly feelings.'),
    'magnet': ('Magnet', 'attracts the wrong crowd.'), 'ladder': ('Ladder', 'up is a direction.'), 'cake': ('Cake', 'for later. (it is now.)'), 'plant': ('Plant', 'watered twice. thriving.'),
    'boombox': ('Boombox', 'volume is a personality.'), 'oar': ('Oar', 'no boat. all commitment.'), 'anchor': ('Anchor', 'going nowhere, heavily.'), 'key': ('Key', 'fits nothing yet.'),
    'clock': ('Clock', 'always about to be late.'), 'camera': ('Camera', 'lens cap is on.'), 'bone': ('Bone', 'a good find.'), 'rocket': ('Rocket', 'a toy. for now.'), 'brush': ('Brush', 'one more coat.'), 'net': ('Net', 'has never caught anything.'),
}
POSES = ['stand', 'wave', 'cheer', 'run', 'jump', 'flex', 'point', 'dance', 'hold', 'lunge', 'shrug']
SCENE_WORD = dict(plain='Studio', night='Night', dunes='Dune', sea='Harbour', city='City', mountains='Summit', aurora='Aurora', cave='Crystal', forest='Firefly', snow='Frost', storm='Storm', sunset='Sunset', lighthouse='Lighthouse', nebula='Nebula', volcano='Volcano', canyon='Canyon')
EASY = ['plain', 'night', 'dunes', 'sea', 'mountains', 'snow', 'sunset']
BIG = ['aurora', 'cave', 'forest', 'storm', 'volcano', 'lighthouse', 'nebula', 'city', 'canyon', 'sunset', 'mountains', 'night']
TINT = lambda hue: '#%02x%02x%02x' % tuple(int(c * 255) for c in __import__('colorsys').hsv_to_rgb((hue % 360) / 360, .35, 1))

def build():
    rnd = random.Random(7); cards = []; used = set(); n = [44]
    def uniq(hat, prop, scene=None):
        k = (hat, prop, scene); return k not in used
    FIGN = dict(robed='Pilgrim', angel='Seraph', knight='Warden', horned='Horned One', crowned='Hollow King', lone='Wanderer', idol='Idol', monk='Monk', twin='Twins', gate='Gate', tower='Spire', spire='Teeth', orb='Orb', mourner='Mourner')
    COMPN = dict(eclipse='of the Eclipse', moon='at Moonrise', rift='in the Rift', rings='of the Rings', halo='in Halo', sunburst='at Sunburst', storm='in the Storm', void='in the Void')
    CAPS = dict(eclipse='it went dark at noon. it stayed.', moon='the only lamp for a hundred miles.', rift='something is leaving through the crack.', rings='each ring is a year it waited.', halo='no one asked it to be holy.', sunburst='looks straight at it. does not blink.', storm='the weather answers to it.', void='the quiet got bigger, not emptier.')
    PAL = dict(fp=['bone', 'rust', 'ice'], ms=['blue', 'teal', 'green', 'ice'], ec=['amber', 'violet', 'teal', 'green'], td=['crimson', 'magenta', 'violet', 'rust'], sg=['bone', 'ice', 'crimson', 'magenta', 'amber'])
    FIGS = ['robed', 'angel', 'knight', 'horned', 'crowned', 'lone', 'idol', 'monk', 'twin', 'gate', 'tower', 'spire', 'mourner']
    COMPS = ['eclipse', 'moon', 'rift', 'rings', 'halo', 'sunburst', 'storm', 'void']
    def new_card(pack, val, kind):
        n[0] += 1; r = random.Random(zlib.crc32(('%s%d' % (pack, n[0])).encode())); big = kind == 'rare'
        while True:
            fig = r.choice(FIGS); comp = r.choice(COMPS); pal = r.choice(PAL[pack])
            if (fig, comp, pal) not in used: used.add((fig, comp, pal)); break
        power = min(1, .25 + .15 * PACKS.index(pack) + (.2 if big else 0) + r.random() * .15)
        name = '%s %s' % (FIGN[fig], COMPN[comp]); hue = {'bone': 40, 'blue': 215, 'amber': 35, 'crimson': 355, 'violet': 270, 'teal': 175, 'green': 130, 'magenta': 320, 'ice': 200, 'rust': 18}[pal]
        rar = rarity(val)
        return dict(no='%03d' % n[0], id=('%s%03d' % (pack, n[0])), name=name, sub='%s, %s' % (fig, comp), rar=rar, chars=CHARS[rar], val=round(val * 500), tint=TINT(hue), cap=CAPS[comp], styles=False, set=pack, pack=pack, kind=kind,
                    spec=dict(fig=fig, comp=comp, pal=pal, seed=r.randrange(10 ** 6), power=power, grain=r.choice(('film', 'film', 'speckle')), dx=r.choice((-.08, 0, 0, .08)), chroma=big and r.random() < .3))
    # names must be unique too
    seen_names = set()
    def fix_name(c):
        base = c['name']; k = 2
        while c['name'] in seen_names: c['name'] = '%s %d' % (base, k); k += 1
        seen_names.add(c['name'])
    for pk in PACKS:
        fill, rare = [], []
        if pk == 'fp':
            for cid, v in zip(EXIST_COMMONS, EXIST_VALS): fill.append(dict(id=cid, val=round(v * 500), existing=True, kind='common'))
        else:
            for v in COMMON_VALS: fill.append(new_card(pk, v, 'common'))
        for v in UNC_VALS: fill.append(new_card(pk, v, 'uncommon'))
        for v, ex in RARE[pk]:
            rare.append(dict(id=ex, val=round(v * 500), existing=True, kind='rare') if ex else new_card(pk, v, 'rare'))
        for c in fill + rare:
            if not c.get('existing'): fix_name(c)
        cards.append(dict(pack=pk, fill=fill, rare=rare))
    # cards that have a painting take its name, caption and subject
    sys.path.insert(0, os.path.join(HERE, '..', 'paint')); import cards_data as CD
    for p in cards:
        for c in p['fill'] + p['rare']:
            if c.get('existing') or c['id'] not in CD.C or not os.path.exists(os.path.join(HERE, '..', 'paint', 'sources', c['id'] + '.png')): continue
            nm, cap, subj, look = CD.C[c['id']]; c.update(name=nm, cap=cap, sub=look + ' painting', painted=True); c.pop('spec', None)
            from PIL import Image as _I; px = _I.open(os.path.join(HERE, '..', 'paint', 'sources', c['id'] + '.png')).convert('RGB').resize((24, 30)); r_, g_, b_ = [sum(p[i] for p in px.getdata()) / 720 for i in range(3)]; m_ = max(r_, g_, b_, 1); c['tint'] = '#%02x%02x%02x' % tuple(min(255, int(v * 255 / m_ * .6 + 100)) for v in (r_, g_, b_))
    return cards

if __name__ == '__main__':
    packs = build(); allc = [c for p in packs for c in p['fill'] + p['rare']]
    assert len({c['id'] for c in allc}) == len(allc) == 150, (len(allc), len({c['id'] for c in allc}))
    json.dump(packs, open(os.path.join(HERE, 'roster.json'), 'w'), indent=1); print(len(allc), 'cards;', sum(1 for c in allc if not c.get('existing')), 'new')
    if '--draw' in sys.argv:
        sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..')); from aura import card; import ascii_cards; from PIL import Image
        os.makedirs(os.path.join(HERE, 'sources'), exist_ok=True); k = 0
        for c in allc:
            if c.get('existing') or c.get('painted'): continue
            src = os.path.join(HERE, 'sources', c['id'] + '.png'); card(c['spec']).save(src); ascii_cards.convert(src, os.path.join(ROOT, 'cards', c['id'] + '.jpg'), 80)
            Image.open(src).resize((360, 437), Image.LANCZOS).save('/tmp/_t.png'); ascii_cards.convert('/tmp/_t.png', os.path.join(ROOT, 'cards', 's', c['id'] + '.jpg'), 30); k += 1
        print('drew', k)
