# STIXX teaser ads (1080x1920, 30 fps, with sound)

Vertical teasers in the app's ASCII style. Nothing in them is a screen recording: every frame is worked out from the clock in
`ad.html`, pushed through a pixel pass (tear, RGB split, grain, scanlines, bloom, shake) and handed to ffmpeg. The soundtrack is
synthesised by `audio.py` from the same timeline, so every hit lands on its picture.

## "Up": `stixx-collection.mp4`, 1080x1920 phone screen, 26.6 s, with sound (`ad3.html`, `render_dom.js`, `audio3.py`, `make_ad3.sh`)
A screen recording of one collection going up. It is the app's own stylesheet and card pictures in a 540x960 page, with the prices scripted (the app's
market can't be told what to do): ten cards, each on a path with pullbacks and noise, and every winner stays under the ceiling the app gives it (Reaper 5x,
Grimm 10x, Ronin 16x, Shogun 12x, Liftoff 14x, Null 16x, Stitch and Brick 40x). Phantom and Ignition fall, as cards do. The profit starts at +$7.04 and
ends at +$752.38, solved exactly in the page. Rows glide past each other as the order changes, every market step plays a note that climbs with the profit,
milestones ($50, $100, $250, $500, the last) ring, and a breath of silence comes before the numbers lock. The film says it is an illustration of one lucky
collection in the simulated market, play money, 18+, and that a pack sells back for about 89% of its price on average. `make_ad3.sh <outdir>` makes it again
(about two minutes); `render_dom.js` renders any web-page film frame by frame.

## "Letters": `stixx-cinematic.mp4`, 1920x1080 landscape, 33.7 s, with a synthesised score (`ad2.html`, `audio2.py`, `make_ad2.sh`)
A second film from a new engine, built to be watched with the sound on and hard to scroll past. Letterboxed to 2.35:1 with a lens (bloom,
anamorphic streaks, colour fringing, a teal-and-amber grade, vignette, grain). The retention shape:
1. 0-5 s, the hook: the camera pulls back out of the 1,578,000 letters of the Umbra card until the picture appears (a question the viewer wants answered)
2. 5-10 s, one pack, a breath of near-silence, the tear in slow motion
3. 10-19 s, five pulls, each louder than the last, rising notes, a Mythic last; a running total keeps counting
4. 19-27 s, a card from that pack runs in the simulated market, the sell, the profit after the 10% fee (illustrative, and under the card's real 12x ceiling)
5. 27-34 s, "first pack free", then a dive into the letters that lands on the first frame, so the film loops
Captions sit in the letterbox for muted viewing, and "play money · simulated market · 18+" stays on screen throughout. `render.js` takes `AD_FILE`,
`AD_W` and `AD_H` to render it. `make_ad2.sh <outdir>` makes the whole thing again (about two minutes).

## Take four (current vertical film, for the public beta): `stixx-teaser-4.mp4`, 48.9 s
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
