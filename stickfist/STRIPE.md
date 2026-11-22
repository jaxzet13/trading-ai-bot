# Selling the Requiem pack with Stripe (Apple Pay included)

This is how to turn on real payments for the physical Requiem pack. It is **off** until you do every step below: the page shows the preview and the server refuses to take an order.

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
