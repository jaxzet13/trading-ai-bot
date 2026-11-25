# Kalshi stock-index markets (S&P 500, Nasdaq-100): first backtest. No edge for a taker.

Nov 25 2026. Question: is there anything to earn by buying at the ask (fee 0.07 p (1 - p)) in Kalshi's index
markets, tested the same way as the crypto and tennis markets?

**Verdict: no edge.** Kalshi's prices are well calibrated; buying either side costs 3 to 5c a contract in spread and
fee, with day-clustered t between -2 and -8 and both halves negative. A normal fair-value model is worse than Kalshi's
own price and adds nothing to it out of sample. Momentum adds nothing measurable. The bracket ladders never sum to
an arbitrage. The only positive number in the study is a bet on the direction of the index (it fell intraday on
most of these days), not a mispricing. 43 trading days (28 of them out of sample for the models): enough to see
the cost of the spread clearly, too few to prove or rule out a small model edge.

## What these markets are (differs from the brief)

| series | what | events a day | contracts a day (mean / median) |
|---|---|---|---|
| KXINX | S&P 500 range: 28 brackets of 25 points + 2 tails, settles on the 16:00 close | 1 | 50,000 / 22,000 |
| KXNASDAQ100 | Nasdaq-100 range: 28 brackets of 100 points + 2 tails | 1 | 40,000 / 5,400 |
| KXINXU | S&P 500 "X or above", strikes every 5 points | 7 (10:00 ... 16:00) | 16:00 event 690,000 / 480,000; each hourly event 220,000 / 170,000 |
| KXNASDAQ100U | Nasdaq-100 "X or above", strikes every 10 points | 7 | 16:00 event 700,000 / 235,000; each hourly event 166,000 / 104,000 |

* The range series (KXINX, KXNASDAQ100) have **no** ladder of "or above" contracts: one "top tail or above" market,
  the rest are brackets. The threshold ladder is the **U series, and it is not dead**: it trades 10 to 40 times
  more than the range series (about 2 million contracts a day for the S&P across the 7 events). So it was
  included: the 16:00 events and the six hourly events.
* Fee: all four series are `quadratic`, multiplier 1 (0.07 p (1 - p) for takers).

## Data (`download.py`, stored in `data/index/`, 173 MB, not in git)

* 43 trading days, Sep 28 - Nov 25 2026 (42 for the three series whose Nov 25 event had not settled yet),
  15,175 markets with their 1-minute quotes (Kalshi candlesticks: yes bid / ask close, volume):
  range 1,368 markets; "or above" 16:00 events 5,604; hourly events 8,203.
* Kalshi returns a bar only for minutes in which the book or the tape changed; the last quote is carried forward.
* Index level: **Yahoo chart API, 5-minute bars of ^GSPC and ^NDX** (reachable with a browser User-Agent via
  query2; 60 days of 5-minute bars, which is exactly this sample). 1-minute bars (30 days) are stored but not
  used. As a cross-check the level implied by Kalshi's own 16:00 ladder (strike where the mid crosses 50c,
  interpolated) is within 1.5 bp (S&P) / 2.4 bp (Nasdaq) of Yahoo at the median, 7 / 10 bp at the 95th
  percentile. Model (b) was run with both.
* Not downloaded: the 21 trading days Aug 27 - Sep 25. They exist (`/historical/markets`, back to at least
  Aug 10) but cost one request per market and Yahoo has no 5-minute bars that far back.
  `python3 research/index_study/download.py 90` fetches them (about 2,300 requests, an hour or more).
* Full range ladders (all 30 markets, needed for the bracket sums) only for the last 11 days; before that only
  the brackets that traded.
* Rate limit, learned the hard way: every candlestick request costs 50 tokens of a 600-token bucket (200 a second
  come back) that this machine's other programs share (the live bot reads candlesticks at each minute boundary,
  the tennis learner in between). The first attempt at 2.5 requests a second drew HTTP 429 at once. The
  downloader now uses the batch endpoint (`/markets/candlesticks`, up to 40 tickers a request), stays silent
  from 6 s before to 6 s after every minute boundary, and backs off when the bucket runs low. The live bot's
  log shows no rate-limit error during the download (22:00-23:45 UTC).

## How it was scored (`study.py`, full output in `results.txt`)

* One row per market and decision time: 10:00, 11:00, 12:00, 13:00, 14:00, 15:00, 15:30, 15:50 New York for the
  16:00 events; 60, 30 and 10 minutes before the close for the hourly events. 27,259 rows.
* A row needs a two-sided quote **and volume traded before the decision time** (range >= 1, 16:00 "or above"
  >= 50, hourly >= 300 contracts). This matters, see "A trap" below.
* Taker only: buy YES at the ask or buy NO at 1 - bid, plus the fee; settles at 0 or 1.
* t statistics with days as the independent unit (every contract of a day rides on one index path).
  Halves = first / second half of the days.
* Quotes are minute closes. Sizes at the ask are unknown (candles carry no depth), so the losses below are for
  one contract at the quoted price; a real order would do no better.

## a. Calibration

Range brackets (direction-neutral by construction; S&P + Nasdaq, 3,055 rows, 42 days):

| mid | n | settles minus mid | buy YES after fee (t) [halves] | buy NO after fee (t) [halves] |
|---|---|---|---|---|
| 3-10c | 1,154 | -1.4c | -3.7c (-3.8) [-4.4 / -3.0] | -0.6c (-0.7) [+0.4 / -1.6] |
| 10-25c | 1,072 | +0.6c | -2.8c (-2.5) [-4.0 / -2.0] | -3.9c (-3.3) [-2.6 / -4.7] |
| 25-40c | 469 | -0.2c | -4.1c (-1.5) [-3.9 / -4.2] | -3.6c (-1.4) [-4.0 / -3.1] |
| 40-60c | 241 | -0.5c | -4.6c (-1.4) | -3.6c (-1.1) |
| all | 3,055 | -0.2c (t -0.5) | **-3.3c (-7.9) [-3.3 / -3.3]** | **-2.7c (-6.7) [-2.8 / -2.7]** |

Same picture at every time of day (YES -2.7 to -4.2c, NO -1.0 to -3.1c in the 3-25c band from 10:00 to 15:50).

"Or above" contracts, by side of the favourite (this removes the direction of the index: a favourite is YES below
the level and NO above it):

| favourite's mid | 16:00 events: favourite wins minus mid | buy favourite (t) | buy longshot (t) | hourly events: favourite wins minus mid | buy favourite (t) | buy longshot (t) |
|---|---|---|---|---|---|---|
| 50-60c | -0.1c | -4.8c (-5.0) | -4.6c (-4.3) | -1.0c | -8.0c (-6.4) | -6.1c (-4.7) |
| 60-75c | -1.3c | -5.4c (-3.0) | -3.0c (-1.6) | +0.4c | -5.5c (-4.1) | -6.6c (-4.5) |
| 75-90c | -0.0c | -3.1c (-1.5) | -3.2c (-1.6) | -1.0c | -4.6c (-4.8) | -2.8c (-3.0) |
| 90-97c | +1.2c | -0.9c (-0.6) | -3.5c (-2.4) | -0.6c | -2.6c (-3.0) | -1.6c (-1.8) |
| all | **+0.0c (t 0.0)** | **-3.2c (-2.2) [-2.6 / -3.7]** | **-3.4c (-2.3) [-4.2 / -2.8]** | **-0.5c (t -0.7)** | **-4.9c (-6.2) [-3.8 / -5.7]** | **-4.0c (-5.0) [-5.5 / -2.7]** |

12,869 rows (16:00 events) and 7,884 rows (hourly), 43 days. Spreads: 3-7c on S&P strikes, 4-15c on Nasdaq
strikes (widest near the money).

By YES price, the 16:00 "or above" contracts look badly miscalibrated: YES settles 7.3c below its mid (t -2.4),
buying NO earns +4.0c after the fee (t +1.3; in the 3-10c band +2.2c, t +4.3, both halves positive). **This is the
index, not Kalshi**: in these 42 days the S&P closed below its 10:00 level on 64% of days (mean -33 bp, t -2.3) and
below its 12:00 level on 62% (-19 bp, t -2.4); the Nasdaq the same (-39 bp, -20 bp). Every "or above" contract is a
bet on that one direction. Split by favourite / longshot the bias is 0.0c. In the hourly events, whose direction
was balanced, the same cell (buy NO at 3-10c) loses 2.9c (t -2.4). The high t of the 3-10c band comes from a
payoff that wins a few cents on most days and loses 90c on a rare one that this sample did not contain.

By time of day (16:00 "or above", three bands): YES after fee -3 to -19c at every hour (the falling index),
NO after fee +9 to +11c at 10:00-13:00 in the middle band (t 1.4 to 1.8) fading to 0-3c from 15:00 on. Hourly events:
both sides negative at 60 and 30 minutes; at 10 minutes YES is about 0 (+0.8c / -1.1c / -1.9c) and NO -5 to -15c.
Nothing positive on both sides of the split anywhere.

## b. Fair-value model

P(finish at or above the strike) = Phi(ln(S / K) / (sigma sqrt(minutes left))), S = Yahoo level at the decision
time, sigma = root mean square of 5-minute returns over the last 5 sessions and today so far. Brackets: difference
of two such terms. No tuning.

* Raw model vs Kalshi's mid, all 43 days: the model's log-loss is worse than the mid's in every family
  (16:00 "or above" -0.021, t -2.9; hourly -0.011, t -1.7; range -0.019, t -2.6). The model differs from the mid
  by 5-6c on average and the mid is right.
* Betting the raw model when its edge after the fee is >= 3c / 5c (one bet per market, the first signal):

| family | rule | bets | a day | c per bet | t | halves |
|---|---|---|---|---|---|---|
| 16:00 "or above" | >= 3c | 2,047 | 48 | -2.7c | -1.4 | -0.0 / -4.6 |
| | >= 5c | 1,567 | 36 | -3.8c | -1.9 | -1.4 / -5.6 |
| hourly "or above" | >= 3c | 1,436 | 33 | -0.7c | -0.5 | -0.4 / -0.9 |
| | >= 5c | 1,047 | 24 | -1.5c | -0.9 | -3.8 / +0.4 |
| range | >= 3c | 284 | 7 | -5.2c | -2.4 | -1.9 / -8.4 |
| | >= 5c | 204 | 5 | -8.9c | -3.5 | -6.8 / -10.7 |

  With the level implied by Kalshi's own ladder instead of Yahoo (16:00 "or above"): -4.1c (t -2.6) and
  -5.2c (t -2.9).
* Walk-forward logistic regression, offset logit(mid), fitted on earlier days only, first 15 days for training,
  28 test days. For "or above" contracts without an intercept (an intercept is the direction bet), terms:
  logit(mid) (favourite-longshot) and the model's gap logit(model) - logit(mid).

| family | model | log-loss gain over the mid (t) | bets >= 3c: n, a day, c per bet (t) [halves] | bets >= 5c |
|---|---|---|---|---|
| 16:00 | logit(mid) | -0.0008 (-0.6) | 0 bets | 0 bets |
| 16:00 | + model gap | -0.0032 (-1.0) | 124, 4.4, -4.9c (-0.6) [-4.1 / -21.6] | 49, -1.9c (-0.2) |
| hourly | logit(mid) | -0.0016 (-1.7) | 0 bets | 0 bets |
| hourly | + model gap | -0.0018 (-0.5) | 185, 6.6, -4.0c (-1.3) [+0.1 / -16.2] | 49, +3.8c (+0.4) [+9.3 / -44.3] |
| range | intercept + logit(mid) + gap | -0.0032 (-1.6) | 14, 0.5, -29.0c (-2.2) | 2 bets |

  The gap does not predict the outcome beyond Kalshi's price: negative out of sample everywhere.

## c. Momentum

Index move over the last 5, 15 and 60 minutes divided by sigma sqrt(minutes), added to the same walk-forward model.

| family | model | log-loss gain over the mid (t) [halves] | bets >= 3c: n, a day, c per bet (t) [halves] | bets >= 5c |
|---|---|---|---|---|
| 16:00 | logit(mid) + gap + momentum | -0.0003 (-0.1) [-0.005 / +0.004] | 738, 26, +1.7c (+0.3) [+1.5 / +1.8] | 486, 17, +4.4c (+0.5) [+11.3 / +1.4] |
| 16:00 | momentum only | +0.0035 (+0.5) [+0.002 / +0.005] | 583, 21, +4.1c (+0.4) [+5.3 / +3.8] | 393, 14, +4.7c (+0.4) [+11.1 / +3.4] |
| hourly | logit(mid) + gap + momentum | +0.0005 (+0.1) | 319, 11, +1.0c (+0.3) [-0.4 / +2.8] | 135, 4.8, -4.3c (-0.7) |
| hourly | momentum only | -0.0006 (-0.3) | 125, 4.5, -1.7c (-0.3) [-2.2 / -1.3] | 53, 1.9, +6.9c (+0.7) |

Fitted coefficients (16:00): +0.06 on 5 minutes, -0.25 on 15 minutes, +0.36 on 60 minutes (continuation of the
last hour). Positive cents per bet on the 16:00 events, but t 0.3 to 0.5 on 28 test days with 20 bets a day that
all point the same way: indistinguishable from zero, and it does not repeat in the hourly events.

For the record, the direction bet (intercept only: buy NO on everything because YES kept losing): 1,388 bets,
50 a day, +9.5c a bet, t +1.6, halves +13.4 / +7.1. That is being short the index every afternoon in a stretch
when it fell every afternoon. Not an edge in Kalshi's prices; the futures do the same bet without a 4c spread.

## d. Bracket sums and ladder consistency

| check | S&P | Nasdaq |
|---|---|---|
| minutes with all 30 bracket quotes (11 days) | 3,826 | 3,828 |
| sum of the 30 asks, mean (5%..95%) | 1.48 (1.36..1.63) | 1.54 (1.39..1.70) |
| cheapest full set with fees | $1.30 | $1.37 |
| sum of the 30 bids, mean (5%..95%) | 0.87 (0.78..0.97) | 0.84 (0.71..0.98) |
| best sell-everything proceeds after fees | $0.997 | $0.989 |
| minutes with an arbitrage (either way, even before fees) | 0 | 0 |
| "or above" ladder: higher strike bid above lower strike ask, after fees (5-minute snapshots, 43 days) | 0 of 83,147 pairs | 0 of 164,608 |
| bracket vs the same range built from two "or above" strikes: locked gain after fees | 26 of 13,085 snapshots on 14 days, best 5.2c | 9 of 13,489 on 3 days, best 3.8c |

The last row is three legs priced from minute-close snapshots that are not simultaneous, about 0.2% of
snapshots, size unknown. Not a strategy; it only says the two families are priced consistently (mid gap 0.3c,
standard deviation 1.5c).

## A trap this study fell into first

The download kept only markets with enough total volume. Scored on that sample, hourly longshots looked
profitable: buying the 3-10c side earned +3.5c after the fee, t +3.2, both halves positive. It is a look-ahead:
a far strike gets its volume when the index moves towards it, so selecting on the day's volume selects the
longshots that came in. With the filter "volume before the decision time" the same bet loses 1.6c (t -1.8).
`python3 research/index_study/study.py --no-prevol` reproduces the biased version.

## Verdict

* **Taker, any simple rule: no edge.** Cost of crossing the spread and paying the fee: 3c a contract in the range
  brackets (t -7 to -8), 3c in the 16:00 "or above" strikes (t -2.2), 4 to 5c in the hourly strikes (t -5 to -6);
  both halves negative in all of them. Calibration error after removing the index direction: 0.0 to 0.5c.
* **Fair-value model (level, time, realised volatility): worse than Kalshi's price**, -3 to -9c a bet where it
  disagrees by 3c or more, and no information beyond the price out of sample.
* **Momentum: nothing proven.** +2 to +4c a bet on about 20 bets a day in the 16:00 events, t under 0.5, not
  repeated in the hourly events. 28 out-of-sample days is too little to call this either way; it is not a reason
  to trade.
* **Arbitrage: none.** A full set of brackets costs $1.30 or more.
* Not tested: resting orders (rejected on crypto and tennis), the trade tape (how much size is at the ask),
  the days before Sep 28.

## Files

* `download.py`: settled markets + 1-minute quotes of the four series, Yahoo bars. Run for this study as
  `download.py 90 --live-only --minvol=50 --range-minvol=1` (about the last 11 days with `--minvol=10` and all range
  brackets), then the same with `--hourly --hourly-minvol=300`.
* `common.py`: loading, quote grid, implied level, day-clustered t.
* `study.py`: every table above. `results.txt`: its full output.
