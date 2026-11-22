# STIXX public beta: how to put it online and how to read the numbers

STIXX is a static page plus one small Node server. The page works on its own (open `index.html`), but **invites, free-pack rewards and provably fair seeds need the server**, because a page can't be trusted to count its own rewards. Without the server the page says so and gives nothing out.

## Put it online (about 10 minutes)

You need somewhere that runs Node 18 or newer **with HTTPS** (sharing, clipboard and video recording only work on secure pages) **and a disk that survives restarts** (invites and fair-play seeds live in one JSON file; if it is wiped, everyone's invite counts reset).

```bash
cd stickfist
python3 build.py --release --url https://your-domain.example      # writes dist/
cd dist
PORT=8080 DATA_FILE=/data/stixx.json TRUST_PROXY=1 ADMIN_TOKEN=pick-a-long-random-string node server.js
```

* **On a host that runs containers** (Fly.io, Render, Railway and similar), use the `Dockerfile` in this folder instead: it runs the build above and starts the server. Give it the build argument `PUBLIC_URL=https://your-domain.example`, mount a persistent volume at `/data`, and put the secrets (`ADMIN_TOKEN`, and the Stripe ones in `STRIPE.md`) in the host's secret settings, not in the repository. The server listens on `PORT` (8080 by default). With no `SHOP_OPEN`/`REQUIEM_OPEN` set, nothing can be bought: `/api/shop/orders?token=...` lists exactly what is still missing.
* `dist/` holds the game, the card pictures (`cards/`, about 34 MB, including small copies in `cards/s/` that the lists and grids use), the home-screen icons and manifest (players on a phone can "add to home screen" and get it full-screen like an app, over HTTPS) and `server.js`. There is nothing to install: no packages. If you change a card picture, run `python3 make_thumbs.py` to refresh its small copy.
* `TRUST_PROXY=1` when you sit behind a proxy or CDN (Render, Fly, Railway, Cloudflare, nginx...), so the server reads the visitor's address from `X-Forwarded-For`. Leave it off when the server faces the internet directly.
* `DATA_FILE` must be on a persistent volume. Back it up by copying the file.
* Hosting the page somewhere else (a static host) and the server elsewhere? Build with `--api https://api.your-domain.example`. The server answers cross-origin calls (`CORS_ORIGIN` narrows who may).
* `og.png` (the picture shown when a link is shared) should sit next to `index.html`. Drop a 1200x630 image there.

## What the server stores

A random id per browser, the invite code, who invited them, counters, the days they visited, a **hash** of their network address (never the address), and their fair-play seed. No names, emails or payment details exist anywhere. Cards and play money stay in the player's browser.

## Free packs and invites: the rules (all in `server.js`, top of the file)

| Rule | Value |
| --- | --- |
| First pack | free, on arrival |
| Daily pack | 1 free pack a day, plus extra on streak days 3, 7, 14 and 30 |
| Friend joins through your link | the friend gets 1 free pack immediately |
| Friend opens their first pack | you get 1 free pack |
| Bonus | +2 packs at 5 friends, +3 at 10, +5 at 25 |
| Cap | 30 rewarded friends per player (`MAX_FRIENDS`) |
| Same network | at most 2 rewarded friends per network per inviter (`SAME_NET_MAX`) |
| New players per network | 40 an hour (`HELLOS_PER_HOUR`) |
| Creator codes | 3 to 16 letters or numbers, after the first pack, one change a day; reserved and offensive words refused (add more with `BLOCKED_CODES=A,B`) |

Honest limits: someone with several phones on different networks can still farm the cap of 30. The prize is play-money cards, so that costs you nothing but is worth knowing. If you ever make packs worth real value, none of this is enough: you would need accounts, ID checks and a legal review first.

## Provably fair packs

The server holds a secret seed per player and shows its SHA-256 hash **before** any pack. The player picks a client seed. Pack number `n` is:

```
digest = HMAC-SHA256(key = server seed as hex text, message = "clientSeed:n")
```

Slot `i` of the pack uses hex characters `8i..8i+7` of the digest as a number in `[0,1)` and walks down that slot's odds (the table on the Odds page). When the player taps "reveal the seed", the server sends the old seed and starts a new one; the page re-does every draw, checks `SHA-256(seed)` equals what was shown before, and marks each pack checked. The "check a draw by hand" box does the same for anyone who pastes a seed. Without a server the page uses a seed on the device and says it can only prove the odds were applied, not that nobody else could pick the seed. The style a copy comes out in is fixed by its copy id (a public formula), not by the draw.

## The numbers to watch

`GET /api/stats?token=<ADMIN_TOKEN>` returns:

| Field | What it means | Good beta signal |
| --- | --- | --- |
| `joined` / `active` | players seen / players who opened a pack | `activation` (active/joined) above 0.7 |
| `referred` / `refActive` | players who arrived by a link / who then opened a pack | |
| `kFactor` | new players who opened a pack through an invite, per player who opened a pack | above 0.3 is strong; above 1 means invites alone grow it |
| `retention.d1`, `retention.d7` | share of players who came back the next day / a week later | d1 above 0.3, d7 above 0.12 |
| `shareRate` | clips shared + invite links copied or shared, per active player | above 0.15 |
| `events` | counts of `clip`, `clipSave`, `clipShare`, `inviteCopy`, `inviteShare` | clip made to clip shared is the fun-to-brag ratio |
| `days` | per day: new, referred, active, referred-and-active, daily users, events | |

Those thresholds are rules of thumb, not promises. Change one thing at a time and watch two weeks.

## Requiem, the limited drop (a preview in the beta)

`#/limited` shows **Requiem**: six premium cards, three to a pack, $65 for a physical pack, each card with its own rarity and far more characters than any other card here. It is a preview. It cannot be bought or opened, takes no payment, and its cards are not in anyone's collection or in the market. A banner on the pack page links to it.

- The cards, odds and page text come from `src/js/01b-limited.js` and `08b-limited.js`; the pictures are in `cards/rq/`. `design-concepts/requiem/README.md` explains how the cards are made and checked, and what selling the pack for real would take (payments, printing and shipping, provable draws, a real limit, rules for paid random packs, a real age check).
- **A limit must be real.** Until you set `RQ.run` (how many packs you will print) and `RQ.closes` (the date orders close) the page says it has no limit to count down to, and shows no countdown and no "N left". Do not add either unless the number is true. Print exactly `run` packs.
- The odds on the page are exact and are worked out live from the slot tables. About 28% of packs sell back for at least $65, the average sell-back is about 89%, and the rarest card (Seraph) is about 1 pack in 2,500. If you change a card's worth or a slot, the page changes with it.
- **Nothing pops up on its own.** There are no rank-up toasts, price alert banners, "while you were away" summaries, reward toasts or badge dots. What you ask for still answers you (a sale with Undo, a purchase, copying your link), and the half-hourly "take a break" reminder stays, because it protects the player. Your rank and your price history still update; they just don't announce themselves.
- **Digital packs for real money are built but off** (`SHOP_OPEN=1`; see `STRIPE.md`): real money buys pack openings only, the cards keep no cash value, and nothing is cashable. It has a daily spending limit, an 18+ confirmation, and wording that stays true while it is on.
- **Selling it for real is built but off.** `STRIPE.md` is the setup guide: Stripe Checkout (Apple Pay, Google Pay, cards), a signed webhook, and a pre-shuffled, fingerprinted run of packs so the odds are the real counts. Nothing is sold until you set the keys, your terms page and the run; `node test-pay.js` tests it against a pretend Stripe.
- Check the image-model terms and take legal advice before selling: see "Where the paintings came from" and "What it takes to sell it for real" in the Requiem README.

## Before you announce it

1. Keep the 18+ gate. The cards contain explicit language and violence, and packs are a game of chance, so STIXX is for adults. Do not advertise it to children or in places that mostly reach them.
2. Keep "play money" in every ad and caption. Every number in the app that is simulated says so; keep it that way in clips and posts (the clip's end card already says it).
3. Read the fine print window (footer: "fine print") and change it to match your company name and contact details.
4. No real money: nothing in this build charges, pays out, or lets cards be cashed out. The "cash out" button is a notice only: it says cashing out and buying cards with real money through Stripe arrive with the public release, and that the beta's balance is play money. Building that release means payments, ID and age checks, and a legal review for every country you sell in (random packs and a payout can count as gambling or as a financial product depending on the place). Do that before you take a payment, and keep the notice's wording true to what you have actually shipped.
5. Run the server behind HTTPS and keep `ADMIN_TOKEN` secret.
