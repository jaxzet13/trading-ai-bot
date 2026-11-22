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

* `dist/` holds the game, the card pictures (`cards/`, about 29 MB) and `server.js`. There is nothing to install: no packages.
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

## Before you announce it

1. Keep the 18+ gate. The cards contain explicit language and violence, and packs are a game of chance, so STIXX is for adults. Do not advertise it to children or in places that mostly reach them.
2. Keep "play money" in every ad and caption. Every number in the app that is simulated says so; keep it that way in clips and posts (the clip's end card already says it).
3. Read the fine print window (footer: "fine print") and change it to match your company name and contact details.
4. No real money: nothing in this build charges, pays out, or lets cards be cashed out. If that ever changes, get legal advice for every country you sell in before you do it.
5. Run the server behind HTTPS and keep `ADMIN_TOKEN` secret.
