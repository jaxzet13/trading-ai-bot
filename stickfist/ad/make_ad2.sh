#!/bin/bash
# Re-makes the landscape film "Letters" from source:  ./make_ad2.sh <outdir>
# Needs node + playwright (chromium), python3 with numpy and scipy, ffmpeg, and JetBrains Mono installed.
set -e
OUT=${1:-out2}; cd "$(dirname "$0")"
AD_FILE=ad2.html AD_W=1920 AD_H=1080 node render.js video "$OUT" - 4
python3 audio2.py "$OUT/timeline.json" "$OUT/audio.wav"
ffmpeg -v error -y -framerate 30 -i "$OUT/frames/f%05d.jpg" -i "$OUT/audio.wav" -c:v libx264 -preset slow -crf 22 -maxrate 8M -bufsize 16M -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -movflags +faststart -shortest "$OUT/stixx-cinematic.mp4"
echo "wrote $OUT/stixx-cinematic.mp4"
