#!/bin/bash
# Re-makes the "made of code" film from source:  ./make_ad5.sh <outdir>
# Needs node + playwright (chromium), python3 with numpy and scipy, ffmpeg, and the card pictures in ../cards.
set -e
OUT=${1:-out5}; cd "$(dirname "$0")"
AD_FILE=ad5.html node render_dom.js video "$OUT" 4
python3 audio5.py "$OUT/audio.wav"
ffmpeg -v error -y -framerate 30 -i "$OUT/frames/f%05d.jpg" -i "$OUT/audio.wav" -c:v libx264 -preset slow -crf 21 -maxrate 9M -bufsize 18M -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -movflags +faststart -shortest "$OUT/stixx-code.mp4"
echo "wrote $OUT/stixx-code.mp4"
