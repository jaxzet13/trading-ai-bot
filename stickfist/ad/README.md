# STIXX teaser (33.5 s, 1080x1920, 30 fps)

A vertical teaser ad made entirely of text, in the app's own ASCII style. Nothing in it is a screen recording: every frame is
worked out from the clock in `ad.html`, pushed through a pixel pass (tear, RGB split, grain, scanlines, bloom, shake) and
handed to ffmpeg. The soundtrack is synthesised by `audio.py` from the same timeline, so every hit lands on its picture.

- `stixx-teaser.mp4` and `cover.jpg`: the finished film and a poster frame
- `ad.html`: the film (timeline, scenes, effects). `?handle=@name` puts an account name on the end card
- `render.js`: `shots <t,t,...> <dir>` for stills, `video <dir> [@handle]` for every frame
- `audio.py`: drone, heartbeat, static, typing, glitches, riser, rip, the cut to silence
- `make_ad.sh <outdir> [@handle]`: renders it all again

Story: you've seen cards / you've seen charts / you've never seen both. A pack, five cards, a price that runs and drops and runs,
AI bots, a sell. Then the pack alone in the dark with the heartbeat speeding up, the rip, a card resolving out of big blocks into
an eclipse, and a hard cut to silence before it finishes. The end card: STIXX, "beta drops soon.", "follow this account."

Honesty: everything shown is the demo. The bots, the trades, the volume and the money are simulated, and the film says so on
screen ("demo mode · simulated market"). The +1,740% and $1.66 are the same demo numbers the in-app intro uses.
No account name is baked in: pass `@handle` to `make_ad.sh` to add yours.
