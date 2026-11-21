"""Build index.html from the parts in src/. The app ships as one file; the source lives in pieces.

    python3 build.py            write index.html
    python3 build.py --check    also syntax-check the script with node

src/style.css        all styles
src/body.html        the page structure
src/js/NN-name.js    the script, in order: data, utilities, copy codes, state and economy, text effects,
                     the animation engines, card/pack markup, pages, the opening, events, start
cards/*.jpg          the card pictures (the ASCII cards), referenced by relative path
"""
import glob, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
read = lambda p: open(os.path.join(ROOT, p), encoding='utf-8').read()

HEAD = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>STIXX First Print</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap">
<style>
'''

parts = sorted(glob.glob(os.path.join(ROOT, 'src', 'js', '*.js')))
script = '(() => {\n"use strict";\n\n' + '\n'.join(open(p, encoding='utf-8').read() for p in parts) + '\n})();\n'
out = HEAD + read('src/style.css') + '</style>\n</head>\n<body>\n' + read('src/body.html').rstrip('\n') + '\n\n<script>\n' + script + '</script>\n</body>\n</html>\n'
open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8').write(out)
print(f'index.html: {len(out):,} bytes from {len(parts)} script parts')

if '--check' in sys.argv:
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
        f.write(script); name = f.name
    r = subprocess.run(['node', '--check', name], capture_output=True, text=True)
    print('syntax ok' if r.returncode == 0 else r.stderr)
    if r.returncode: sys.exit(1)
