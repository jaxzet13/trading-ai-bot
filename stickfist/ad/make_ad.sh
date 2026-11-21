#!/bin/bash
# Re-makes the teaser from source:  ./make_ad.sh <outdir> [@handle]
# Needs node + playwright (chromium), python3 with numpy and scipy, ffmpeg, and JetBrains Mono installed.
# With a handle the end card shows it under "follow this account."; without one it says only "follow this account.".
set -e
OUT=${1:-out}; HANDLE=${2:--}; cd "$(dirname "$0")"
node render.js video "$OUT" "$HANDLE" 4
python3 audio.py "$OUT/timeline.json" "$OUT/audio.wav"
ffmpeg -v error -y -framerate 30 -i "$OUT/frames/f%05d.jpg" -i "$OUT/audio.wav" -c:v libx264 -preset medium -crf 25 -maxrate 5.6M -bufsize 11M -pix_fmt yuv420p -r 30 -c:a aac -b:a 160k -movflags +faststart -shortest "$OUT/stixx-teaser-3.mp4"
echo "wrote $OUT/stixx-teaser-3.mp4"
