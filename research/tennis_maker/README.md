# Tennis: can the auto-better earn more? (Nov 25 2026)

Asked after 12 real wins out of 12 (favourites at 85-96c, +$1.16): bets at those prices win about 9 times in 10
with no edge at all, a win makes ~10c and a loss costs ~90c, so the streak is not evidence by itself.

## What 62 days of settled matches say (`study.py`, 20,939 markets)

Challenger matches, decision 60-240 minutes before the scheduled start, backing the player whose mid price is:

| mid | wins minus mid | buy at the ask (after the fee) |
|---|---|---|
| 0.80-0.90 | +1.7 to +2.0c | +0.2 to +0.5c (t < 0.5) |
| 0.90-0.96 | +3.0 to +3.6c | +1.9 to +2.6c (t 1.6 to 1.9) |

A small edge on the heaviest favourites, not statistically solid. ITF, ATP and WTA show nothing consistent.
The scheduled start is not the real start: many Challenger matches are already in play before it.

## Resting bids (`tape.py`, `sim.py`: 1,629 markets replayed against Kalshi's trade tape)

A bid resting at the best bid from 120 minutes before the start until the start, mid 0.80-0.96 (840 signals):

| | share | earns |
|---|---|---|
| if every bid were filled | 100% | +3.1c |
| filled for certain (a sale printed below the bid) | 74% | +1.1c |
| filled, best case (first in the queue) | 81% | +1.4c |
| never filled | 19-26% | +8.6 to +10.1c |
| buying at the ask instead | 100% | +1.0c |

Per signal, a resting bid makes +0.8 to +1.1c against +1.0c for buying at the ask: the same. As in the crypto
markets, the bids that do not fill are the winners. Same picture in the 0.90-0.96 band (+1.7 to +2.1c a signal
resting, +2.1c buying) and at 60 or 30 minutes before the start. Candle bid lows cannot be used to detect fills
(quotes are pulled and replaced without a trade): only the tape can.

## Decision

No change to how the auto-better trades. The only lever that changes its profit is the stake, which is a risk
decision: at 1 contract the expected profit is 10-20c a day; one loss costs ~90c. The account holder was given
the numbers and asked for a stake and stop-loss if they want it larger.
