#!/bin/bash
# Re-makes the "ascii player" film from source:  ./make_ad7.sh <outdir>
# Needs node + playwright (chromium), python3 with numpy and scipy, ffmpeg, and the card pictures in ../cards.
set -e
OUT=${1:-out7}; cd "$(dirname "$0")"
AD_FILE=ad7.html node render_dom.js video "$OUT" 4
python3 audio7.py "$OUT/audio.wav"
ffmpeg -v error -y -framerate 30 -i "$OUT/frames/f%05d.jpg" -i "$OUT/audio.wav" -c:v libx264 -preset slow -crf 21 -maxrate 9M -bufsize 18M -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -movflags +faststart -shortest "$OUT/stixx-idle.mp4"
echo "wrote $OUT/stixx-idle.mp4"
