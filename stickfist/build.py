"""Build index.html from the parts in src/. The app ships as one file; the source lives in pieces.

    python3 build.py            write index.html
    python3 build.py --check    also syntax-check the script with node
    python3 build.py --release [--url https://your.site/]
                                write dist/: the game, the card pictures, server.js and pay.js, ready to host.
                                The page is wired to the beta server on the same address (invites, free-pack
                                rewards and provably fair seeds); --api http://other.host sets another address.

src/style.css        all styles
src/body.html        the page structure
src/js/NN-name.js    the script, in order: data, utilities, copy codes, state and economy, text effects,
                     the animation engines, card/pack markup, pages, the opening, events, start
cards/*.jpg          the card pictures (the ASCII cards), referenced by relative path; cards/s/ holds small copies for lists and
                     grids (python3 make_thumbs.py makes them); icons/ holds the home-screen icons (node icons/make_icons.js)
"""
import glob, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
read = lambda p: open(os.path.join(ROOT, p), encoding='utf-8').read()

def arg(name, default=''):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else default

RELEASE = '--release' in sys.argv
API = arg('--api', '/' if RELEASE else '')          # '' = no server: the page runs alone and says invites are off
URL = arg('--url', '').rstrip('/')
TITLE = 'STIXX: ASCII card packs'
DESC = 'Collectible trading cards drawn entirely in text. Open a free pack every day, collect all 33 cards and trade them with the AI buyers. Free to play, play money only. 18+.'
ICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 28 28'%3E%3Crect width='28' height='28' rx='7.5' fill='%23000'/%3E%3Ccircle cx='14' cy='5.9' r='1.7' fill='%23fff'/%3E%3Cpath d='M8.2 9.8 19.8 21.4M19.8 9.8 8.2 21.4' fill='none' stroke='%23fff' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E"
OG_IMG = (URL + '/' if URL else '') + 'og.png'

PWA = '''<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icons/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="STIXX">''' if RELEASE else ''

HEAD = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{TITLE}</title>
<meta name="description" content="{DESC}">
<meta name="theme-color" content="#07080a">
<meta name="stixx-api" content="{API}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="STIXX">
<meta property="og:title" content="{TITLE}">
<meta property="og:description" content="{DESC}">
<meta property="og:image" content="{OG_IMG}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{ICON}">
{PWA}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap">
<style>
'''

parts = sorted(glob.glob(os.path.join(ROOT, 'src', 'js', '*.js')))
script = '(() => {\n"use strict";\n\n' + '\n'.join(open(p, encoding='utf-8').read() for p in parts) + '\n})();\n'
out = HEAD + read('src/style.css') + '</style>\n</head>\n<body>\n' + read('src/body.html').rstrip('\n') + '\n\n<script>\n' + script + '</script>\n</body>\n</html>\n'
if RELEASE:
    import shutil
    dist = os.path.join(ROOT, 'dist'); shutil.rmtree(dist, ignore_errors=True); os.makedirs(dist)
    open(os.path.join(dist, 'index.html'), 'w', encoding='utf-8').write(out)
    shutil.copytree(os.path.join(ROOT, 'cards'), os.path.join(dist, 'cards'))
    shutil.copytree(os.path.join(ROOT, 'icons'), os.path.join(dist, 'icons'), ignore=shutil.ignore_patterns('*.js'))
    open(os.path.join(dist, 'manifest.webmanifest'), 'w').write('{"name":"STIXX","short_name":"STIXX","description":"ASCII trading cards. Play money only. 18+.","start_url":"/","scope":"/","display":"standalone","orientation":"portrait","background_color":"#050506","theme_color":"#050506","icons":[{"src":"icons/icon-192.png","sizes":"192x192","type":"image/png"},{"src":"icons/icon-512.png","sizes":"512x512","type":"image/png"},{"src":"icons/icon-maskable-512.png","sizes":"512x512","type":"image/png","purpose":"maskable"}]}\n')
    for f in ('server.js', 'pay.js', 'terms.html', 'og.png', 'BETA.md', 'STRIPE.md'):
        if os.path.exists(os.path.join(ROOT, f)): shutil.copy(os.path.join(ROOT, f), dist)
    open(os.path.join(dist, 'package.json'), 'w').write('{"name":"stixx-beta","private":true,"version":"0.1.0","scripts":{"start":"node server.js"},"engines":{"node":">=18"}}\n')
    print(f'dist/: index.html {len(out):,} bytes, cards, server.js + pay.js (api = {API!r})')
else:
    open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8').write(out)
    print(f'index.html: {len(out):,} bytes from {len(parts)} script parts')

if '--check' in sys.argv:
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
        f.write(script); name = f.name
    r = subprocess.run(['node', '--check', name], capture_output=True, text=True)
    print('syntax ok' if r.returncode == 0 else r.stderr)
    if r.returncode: sys.exit(1)
