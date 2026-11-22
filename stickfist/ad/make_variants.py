#!/usr/bin/env python3
"""Cuts the teaser into hook variants for testing which first three seconds stop a scroll.

    python3 make_variants.py stixx-teaser-4.mp4 out/

Every variant opens on a different moment from the film, runs part of the loop, and ends on the same end card, so the only thing that
changes between them is the hook. Run one against another (same budget, same audience, one week) and keep the winner. The cuts use the
film's own timeline (the table `D` at the top of ad.html): cold open 0-4.2, buy 4.2-7.6, cards 7.6-12.9, zoom 12.9-19.1, rise 19.1-23.9,
sell 23.9-27.7, profit 27.7-30.9, collect 30.9-35.5, build 35.5-38.9, rip 38.9-39.6, reveal 39.6-42.6, black 42.6-43.5, end 43.5-48.9.
"""
import subprocess, sys, os

SRC = sys.argv[1] if len(sys.argv) > 1 else "stixx-teaser-4.mp4"
OUT = sys.argv[2] if len(sys.argv) > 2 else "variants"
ACT = dict(cold=(0, 4.2), buy=(4.2, 7.6), cards=(7.6, 12.9), zoom=(12.9, 19.1), rise=(19.1, 23.9), sell=(23.9, 27.7), profit=(27.7, 30.9),
           collect=(30.9, 35.5), build=(35.5, 38.9), rip=(38.9, 39.6), reveal=(39.6, 42.6), end=(43.5, 48.9))
VARIANTS = {
    "hook-zoom":   ["zoom", "rise", "profit", "end"],                    # opens by diving into the letters of one card
    "hook-profit": ["profit", "buy", "cards", "sell", "end"],            # opens on the money moment, then shows how
    "hook-rip":    [("rip", "reveal"), "cards", "zoom", "end"],          # opens on the rip and the rarest pull
}

def span(x):
    if isinstance(x, tuple): return ACT[x[0]][0], ACT[x[1]][1]
    return ACT[x]

os.makedirs(OUT, exist_ok=True)
for name, acts in VARIANTS.items():
    parts, labels = [], []
    for i, a in enumerate(acts):
        s, e = span(a); d = e - s
        parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}];"
                     f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,afade=t=in:d=0.06,afade=t=out:st={d - 0.06:.2f}:d=0.06[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(acts)}:v=1:a=1[v][a]"
    out = os.path.join(OUT, name + ".mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", SRC, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "25",
                    "-maxrate", "5.6M", "-bufsize", "11M", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out], check=True)
    print("wrote", out)
