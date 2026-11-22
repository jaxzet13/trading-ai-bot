# STIXX teaser ads (1080x1920, 30 fps, with sound)

Vertical teasers in the app's ASCII style. Nothing in them is a screen recording: every frame is worked out from the clock in
`ad.html`, pushed through a pixel pass (tear, RGB split, grain, scanlines, bloom, shake) and handed to ffmpeg. The soundtrack is
synthesised by `audio.py` from the same timeline, so every hit lands on its picture.

## Take four (current, for the public beta): `stixx-teaser-4.mp4`, 48.9 s
Take three with the words changed for launch: "first pack free. tap the link." on the end card (and "nothing to pay. it's play money."),
"play money · simulated market" under the action instead of "demo mode", and `?url=` (or `url:stixx.example` as the render argument) to put the
game's address on the end card. Same pictures, same sound. `make_variants.py` cuts it into three hook variants for testing
(`hook-zoom`, `hook-profit`, `hook-rip`); they differ only in how the first three seconds open.

## Take three: `stixx-teaser-3.mp4`, `cover-3.jpg`, 48.9 s
Slower, so every caption stays up for at least a second and a half after it is typed, and with a new shot: the camera dives into one
card (Ronin, 71,680 characters) until every individual letter it is made of fills the screen, with a focus frame, a zoom readout and
the letter under the frame, then pulls back out. All pacing comes from one table at the top of `ad.html` (`D`), so any act can be
lengthened or shortened and the captions, hits, effects and audio follow.
1. buy a pack  2. get cards  (the zoom: "every card is made of text")  3. watch the value go up  4. sell at the peak
5. watch your profit fly  6. collect your favorites, then the cliffhanger and the end card as before.

## Take two: `stixx-teaser-2.mp4`, 33 s
The same six steps, faster, without the zoom.

## Take one: `stixx-teaser.mp4` (`ad_v1.html`)
The abstract version: you've seen cards, you've seen charts, you've never seen both. Everything drawn in ASCII, with the AI bots.

## Files
- `ad.html`: the film. `?handle=@name` puts an account name on the end card
- `render.js`: `shots <t,t,...> <dir>` for stills, `video <dir> [@handle]` for every frame. `AD_FILE=ad_v1.html` renders take one
- `audio.py`: pulse, clicks, chimes, coins, the zoom, heartbeat, riser, rip, the cut to silence. Needs numpy and scipy
- `make_ad.sh <outdir> [@handle]`: renders it all again (needs node + playwright, ffmpeg, JetBrains Mono)

## Honesty
The bots, trades, prices and money are simulated, and the film says so on screen ("play money · simulated market", and "play money · simulated market · 18+"
on the end card; takes one to three say "demo"). The story card is Orbit, bought for 12 cents
and sold at its peak; that run is an illustration of how these markets move, not a record of one. No account name is baked in.
