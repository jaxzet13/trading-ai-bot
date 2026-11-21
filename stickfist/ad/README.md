# STIXX teaser ads (1080x1920, 30 fps, with sound)

Vertical teasers in the app's ASCII style. Nothing in them is a screen recording: every frame is worked out from the clock in
`ad.html`, pushed through a pixel pass (tear, RGB split, grain, scanlines, bloom, shake) and handed to ffmpeg. The soundtrack is
synthesised by `audio.py` from the same timeline, so every hit lands on its picture.

## Take two (current): `stixx-teaser-2.mp4`, `cover-2.jpg`, 33.3 s
Six steps, then a cliffhanger. The cards are the app's own pictures, drawn the way the app draws them (rounded, glowing, name and
character count on the card); ASCII is the language around them: captions, charts, the way a card decodes out of text.
1. buy a pack  2. get cards (five, each decoding into its art)  3. watch the value go up (like stocks, like memecoins)
4. sell at the peak  5. watch your profit fly  6. collect your favorites (hoping they skyrocket)
Then the pack alone in the dark with a heartbeat, the rip, the Umbra card decoding out of text, and a hard cut to silence
before it finishes. End card: STIXX, "beta drops soon.", "follow this account."

## Take one: `stixx-teaser.mp4` (`ad_v1.html`)
The abstract version: you've seen cards, you've seen charts, you've never seen both. Everything drawn in ASCII, with the AI bots.

## Files
- `ad.html`: the film. `?handle=@name` puts an account name on the end card
- `render.js`: `shots <t,t,...> <dir>` for stills, `video <dir> [@handle]` for every frame. `AD_FILE=ad_v1.html` renders take one
- `audio.py`: pulse, clicks, chimes, coins, heartbeat, riser, rip, the cut to silence (take two). Needs numpy and scipy
- `make_ad.sh <outdir> [@handle]`: renders it all again (needs node + playwright, ffmpeg, JetBrains Mono)

## Honesty
Everything shown is the demo. The bots, trades, prices and money are simulated, and the film says so on screen
("demo mode · simulated market", "demo money · simulated market · beta coming soon"). The story card is Orbit, bought for 12 cents
and sold at its peak; that run is an illustration of how these markets move, not a record of one. No account name is baked in.
