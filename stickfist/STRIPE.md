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

Two things to know:
- **The in-game price still floats with the market**, as it always has (that is what keeps the return near 89% whatever the cards are doing), so you will see First Print at about $1 and Moonshot at about $3, not exactly. The **real** price is fixed at $1.00 and $3.00.
- **The starting balance is $2.00** (it was $10.00): two First Print packs, as before. Everything else that was in cents is scaled the same way, and the Requiem pack and the real-money shop are always in real dollars.
