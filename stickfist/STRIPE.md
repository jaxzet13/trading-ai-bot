# Taking real payments with Stripe (Apple Pay included)

There are two things you can sell, each with its own switch, both **off** until you set them up:

- **Digital packs** (`SHOP_OPEN=1`): real money buys pack openings in the game. See "Digital packs" at the end of this file.
- **The physical Requiem pack** (`REQUIEM_OPEN=1`): described first, below.

They share the same Stripe account, keys, webhook, public address and terms page. The sections below on the account, Apple Pay, the server and the webhook apply to both.

## The physical Requiem pack

It is **off** until you do every step below: the page shows the preview and the server refuses to take an order.

## How it works

1. A buyer opens `#/limited`, ticks "I'm 18 or older", picks 1 to 3 packs and presses **Pay**.
2. The server asks Stripe for a **Checkout** page and sends the buyer there. It is Stripe's page, so **Apple Pay, Google Pay and cards appear on their own** on devices that support them, and a card number never touches STIXX. Stripe collects the shipping address (United States only) and a phone number.
3. When Stripe says the payment is complete (a signed webhook), the server gives the buyer the next pack(s) of a **pre-shuffled run** and keeps: the Stripe session id, the pack numbers and the amount. Names, emails and addresses stay in Stripe: read them there to ship.
4. Stripe sends the buyer back to the page, which shows their pack numbers ("number 7 of 2,500").

Packs are finite and sealed in a fixed order, so the odds on the page are the real counts: the server never sells a pack twice, holds the packs of a buyer who is paying, and releases them if the payment page expires.

## Setup, in order

**1. A Stripe account.** Create one at stripe.com and finish business verification. Start in **test mode** (a `sk_test_…` key, and test card `4242 4242 4242 4242`). Switch to live only after you have tried everything.

**2. Apple Pay.** With Stripe's hosted Checkout there is **no domain registration and no Apple developer account to set up**: Stripe's docs say Apple Pay works on hosted Checkout with no extra configuration. Check **Settings → Payment methods** in the Stripe Dashboard and make sure Apple Pay and Google Pay are on. Do not add a list of allowed payment methods in code (this code doesn't, on purpose: a method that isn't in such a list can't appear). Apple Pay shows on Safari on an iPhone or Mac that has a card in Wallet. (Domain registration is only needed if you later move to an embedded payment form on your own page.)

**3. A server on the web.** The checkout needs `server.js` running on a real HTTPS address (see `BETA.md`). It can't run in the claude.ai preview or from a file, because those have no server.

**4. Assemble the run.** Decide how many packs you will print. Then:

```bash
python3 design-concepts/requiem/requiem_run.py --packs 2500
```

This writes `data/requiem-run.json` (the shuffled list of sealed packs; **keep it private**) and `data/requiem-run.public.json` (the counts and a SHA-256 **fingerprint**). **Print exactly those counts**, **publish the fingerprint before the sale opens**, pack the physical packs in the file's order and number them. Put `requiem-run.json` in the server's `data/` folder (or point `REQUIEM_RUN_FILE` at it). Everyone who can see the file knows what is in each pack number, so the person holding it shouldn't be buying packs. When the run sells out, publish `requiem-run.json` so anyone can check it against the fingerprint.

**5. Your terms.** Publish a page with your terms, shipping times, and returns and refund policy. The sale will not open without its address in `REQUIEM_TERMS_URL`. I haven't written terms for you: that is a legal document for your business.

**6. The webhook.** In the Stripe Dashboard go to **Developers → Webhooks → Add endpoint**:
- URL: `https://YOUR-SITE/api/stripe/webhook`
- Events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired`
- Copy the **signing secret** (`whsec_…`).

**7. Settings.** Set these environment variables where `server.js` runs. Keys are secrets: put them in the host's secret settings, never in the repository or a chat.

| Variable | Value |
|---|---|
| `REQUIEM_OPEN` | `1` (the switch; remove it to close the sale instantly) |
| `STRIPE_SECRET_KEY` | `sk_test_…` first, then `sk_live_…` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` from step 6 |
| `PUBLIC_URL` | `https://YOUR-SITE` (https is required with a live key) |
| `REQUIEM_TERMS_URL` | the address of your terms page |
| `REQUIEM_PRICE_CENTS` | `6500` (the price of one pack, shipping included; default 6500) |
| `REQUIEM_UNIT_COST_CENTS` | **required.** What one pack costs you to print, pack and ship, in cents, e.g. `1200`. The sale won't open without it: the server uses it to check you make a profit. |
| `REQUIEM_MIN_MARGIN_PCT` | the least you must keep of each pack's price after Stripe's fee and your cost; default `20`. The sale stays closed below it. |
| `REQUIEM_MAX_PER_ORDER` | `3` (default 3) |
| `REQUIEM_CLOSES` | optional, `2027-02-14`: orders close at the end of that day (UTC-5) |
| `STRIPE_TAX` | optional, `1` to let Stripe Tax work out sales tax (set Stripe Tax up in the Dashboard first) |
| `ADMIN_TOKEN` | any long secret: lets you read the order list |

Also build the page for your server: `python3 build.py --release --url https://YOUR-SITE`. The `dist/` folder it writes holds everything the server needs, `pay.js` included.

**8. Try it.** With test keys: open the page, pay with the test card, check the webhook shows as delivered in Stripe, and that the page shows your pack number. Then open `https://YOUR-SITE/api/requiem/orders?token=YOUR_ADMIN_TOKEN` to see each order and **exactly which cards are in the packs to send**. Read the address in the Stripe Dashboard (Payments) to ship it. Try Apple Pay on a real iPhone once you are on a live key.

## What it checks for you

- Nothing is sold unless every setting is present, the run file is valid, and the terms address is set. `…/api/requiem/orders?token=…` lists what's missing.
- Signed webhooks only (HMAC-SHA256, within 5 minutes). A repeated event changes nothing.
- A pack is given out once. If a payment ever arrives after the last pack, the order is marked `short`: refund it in Stripe.
- If the run file changes after the first sale, the sale shuts.
- Orders are saved to disk the moment a payment is confirmed.
- The page never shows how many packs are left (no "only 3 left" pressure). It shows the run size and says "Sold out" when it is.
- `node test-pay.js` runs all of this against a pretend Stripe, with no network.

## What I could not do, and what is still on you

- **I can't create your Stripe account, hold your keys, or take a real payment.** I tested everything against a pretend Stripe. Do the test-mode run in step 8 yourself before going live.
- **Law and tax.** Selling random sealed packs for real money is regulated differently in different places, and some places treat paid random packs as gambling or require odds disclosure, age verification and refund rights. Get advice for each place you ship to. The "I'm 18" box is a tick box, not an age check. Sales tax is yours to set up (Stripe Tax can calculate it).
- **A real limit.** The page says "a run of N packs, printed once" from your run file. Print exactly that many and never reprint.
- **Refunds, shipping and fulfilment** are manual: the admin list tells you what goes in each pack, and Stripe has the addresses.
- **The beta's play-money wording.** While the sale is open the footer, the cash-out notice and the age gate each name the Requiem pack as the one real-money exception. Close the sale (`REQUIEM_OPEN` unset) and they go back to "play money only".

## Digital packs

**What real money buys:** pack openings, and nothing else. Each pack has one flat real price (`SHOP_PRICES`: First Print **$1.00**, Moonshot **$3.00**; no bundles, no discounts). The player's balance, their cards and every price in the game stay play-money items with **no cash value**, and nothing can be cashed out. I built it this way on purpose: if real money bought play money at 1:1, or if cards could be sold for real money, the game would look and behave like gambling, and that is a different legal world.

**How it works**
1. On the pack page a **Buy packs** button appears only while the server says digital packs are on. It opens a window that says what real money buys, that the packs are random, that the cards have no cash value, the daily limit and a link to your terms and refunds page. The player ticks "I'm 18 or older, I understand the packs are random, and I'm spending real money", picks 1 to 10 packs and presses Pay.
2. The server asks Stripe for a Checkout page (no shipping address: it is digital) and sends the player there. Apple Pay, Google Pay and cards appear on Stripe's page; STIXX never sees a card.
3. When Stripe confirms the payment (the same signed webhook as the Requiem pack), the server adds the packs to that player's **running total** of bought packs, kept separately for each pack (a bought Moonshot pack opens as Moonshot). The page compares that total with how many it has already added, and adds the difference. Because it is a running total, a purchase can never be added twice, even if a message is lost or the player reloads. A pack you bought is shown as "a pack you bought", never "free", and opening it spends no play money.
4. Packs the player has paid for survive "start over".

**Settings** (in addition to the Stripe ones above: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `PUBLIC_URL`, `REQUIEM_TERMS_URL`, which is your terms and refund policy)

| Variable | Value |
|---|---|
| `SHOP_OPEN` | `1` to turn digital packs on (remove it to turn them off at once) |
| `SHOP_PRICES` | the real price of each pack in cents, as JSON; default `{"fp":100,"ms":300}` ($1.00 and $3.00). Stripe's minimum charge is 50 cents. A pack left out of the list can't be bought. |
| `SHOP_MAX_PER_ORDER` | default `10` |
| `SHOP_MIN_NET_PCT` | the least of each digital pack's price that must be left after Stripe's fee; default `60`. A pack cheaper than that isn't offered (a 50 cent pack would lose 62% to the fee). |
| `STRIPE_FEE_PCT`, `STRIPE_FEE_FIXED_CENTS` | Stripe's card fee, used only for these checks; defaults `2.9` and `30` (the usual US card rate: check yours) |
| `SHOP_DAILY_CAP_CENTS` | the most one player can spend in a day (UTC); default `2500`. A spending limit for the player's own protection, counting payments still open. Lower it if you like. |

Webhook events needed are the same four listed in step 6 above. Try it in test mode first: pay with `4242 4242 4242 4242`, and check the packs arrive once.

**Seeing orders:** `https://YOUR-SITE/api/shop/orders?token=YOUR_ADMIN_TOKEN` lists paid orders (a short player id, packs, amount) with no personal details; the Stripe Dashboard has the buyer's payment details and handles refunds. A paid order that couldn't be matched to a player is marked `short`: refund it in Stripe.

**What changes in the game's wording while digital packs are on.** The footer, the age gate, the cash-out notice and the fine print all say that real money buys packs only and the cards have no cash value, and the cash-out window stops saying "coming at public release". That line would promise buyers a payout, so it isn't shown while real money is taken. If you ever mean to let people cash out real money, that is regulated gambling in most places: get legal advice first, and note that nothing here supports it.

**Things that are on you**
- **Law.** Selling random packs for real money ("loot boxes") is restricted or regulated in some places, and you need real age verification, refund handling and sales tax for digital goods (Stripe Tax can calculate it). The 18+ tick box is not an age check. Get legal advice before you switch it on for the public.
- **Marketing.** Anything that shows profits ("$7 to $752") has to say clearly that it is play money, and must not suggest real returns.
- **iPhone and Android app stores.** This is a web app, so Stripe is fine in the browser. If you wrap it in an app for the App Store or Google Play, those stores require their own in-app purchase system for digital goods.
- **Children.** Random-pack purchases must not be aimed at minors. Keep the 18+ gate and don't advertise where children are.

## Connecting your Stripe account to Claude (optional)

This is separate from the server's key. Claude can't take payments or hold your key; a connector only lets Claude see and configure things in your Stripe account when you ask, for example to check that Apple Pay is on, to see account status, or to add the webhook endpoint once your server has an address. Connect it from the card Claude shows you (it asks you to log in to Stripe and choose the account). Use test mode while you build. Your server still needs `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` set as environment variables where it runs.

## How the packs are priced (and why the break-even rate didn't change)

First Print is $1.00 and Moonshot is $3.00. To get there without touching the odds, the game's play money was **redenominated**: one dollar is now 500 units (it was 100 cents), so a unit is a fifth of a cent, and Moonshot's card values were scaled by the same factor as its price. Every pack has the same cards at the same odds, worth the same share of the price, so the return and the chance of selling back at least what a pack cost are unchanged. Measured from the app's own maths at base prices:

| Pack | Price before | Price now | Returns on average | Chance of selling back at least the price | Middle pack |
|---|---|---|---|---|---|
| First Print | $4.99 | $1.00 | 89.5% to 89.3% | 44.5% to 44.5% | 62.9% to 62.8% of the price |
| Moonshot | $5.79 | $3.00 | 90.2% to 90.4% | 43.1% to 43.1% | 20.4% to 20.5% of the price |

**A later change to the odds (published on the odds page).** After the repricing the packs were re-tuned so that real wins are a little more common and the very top prizes a little rarer, with the average return left where it was (the 95% ceiling is untouched). The middle cards (Shogun and Liftoff) sell for a modest amount above the pack price and turn up more often; the jackpot cards (Ronin, Grimm, Reaper, Umbra, Apogee, Luna) are rarer by about a quarter.

| Pack | Returns on average | Sells back at least the price | 2× the price or more | Under half the price |
|---|---|---|---|---|
| First Print, before | 89.3% | 44.5% | 4.8% | 49.8% |
| First Print, now | 89.1% | 50.7% | 5.4% | 43.8% |
| Moonshot, before | 90.4% | 43.1% | 13.5% | 56.5% |
| Moonshot, now | 90.8% | 49.3% | 13.5% | 50.3% |

This is not a way to make players better off over time: the return is still under 100%, so the more packs someone opens the more likely they are to be behind, and the daily pack limit, the break and the half-hourly reminder stay as they are. What it changes is how an individual pack feels, not who wins in the long run. The result screen says the same plain thing after every pack ("You paid $1.00 and got $0.62 of cards"), whether that is a win or a loss.

Two things to know:
- **The in-game price still floats with the market**, as it always has (that is what keeps the return near 90% whatever the cards are doing), so you will see First Print at about $1 and Moonshot at about $3, not exactly. The **real** price is fixed at $1.00 and $3.00.
- **The starting balance is $2.00** (it was $10.00): two First Print packs, as before. Everything else that was in cents is scaled the same way, and the Requiem pack and the real-money shop are always in real dollars.

## Are you always ahead of what players can make?

Short answer: yes for the digital packs, by design, and for the physical Requiem pack as far as the numbers you control go. "Always" has limits, listed at the end.

**Digital packs: players can't make real money at all.** Real money only buys pack openings. The cards, the balance and every price are play items with no cash value, and **no code in this project can pay anyone**: `node test-pay.js` reads the server's source and fails if it ever contains a payout, transfer, refund or any call to Stripe other than starting a Checkout session. Inside the game, a pack returns about 89% to 90% when you sell, measured at every market state over 90 days, and the game now refuses to let it pass 95% even if a price cap binds. So you take in the whole price, less Stripe's fee:

| Pack | Price | Stripe's fee (2.9% + 30 cents) | You keep |
|---|---|---|---|
| First Print | $1.00 | $0.33 | $0.67 (67%) |
| Moonshot | $3.00 | $0.39 | $2.61 (87%) |

The fixed 30 cents is why very cheap packs are a bad deal for you: that is a third of a $1 pack. The server drops any price that leaves less than `SHOP_MIN_NET_PCT` (60%) after the fee, so it can't be set to lose money by mistake. Hosting, refunds and Stripe's dispute fees come out of what you keep.

**The physical Requiem pack: you set the cost, the server checks the margin.** The sale won't open until you say what a pack costs you (`REQUIEM_UNIT_COST_CENTS`), and it refuses to open if you'd keep less than `REQUIEM_MIN_MARGIN_PCT` (20%) after Stripe's fee. At a $12.00 cost you keep $50.81 of each $65.00 pack (78.2%); over a 2,500-pack run that is $127,025. `python requiem_run.py --packs 2500 --unit-cost 1200` prints this, and the admin views (`/api/requiem/orders?token=…`, `/api/shop/orders?token=…`) show the live economics and why a sale is closed.

**What "always" can't mean.**
- Buyers of the physical pack can resell cards, and resale prices are set by buyers, not by you. At the planned worths in `01b-limited.js` the cards in a run add up to about 98.6% of what buyers pay for it. So if the market values the cards at those numbers, buyers *as a group* hold about what they paid, and a lucky buyer can come out well ahead on resale while you still keep your margin on every pack. If you want buyers as a group to hold clearly less than they paid, lower the planned worths and tell me; I haven't changed them without asking.
- Fixed costs (design, the print run, shipping, hosting, a Stripe account) and refunds, chargebacks and unsold stock all come out of what you keep. A run you don't sell out of can lose money even though every pack sold made one.
- None of this is tax or legal advice.
