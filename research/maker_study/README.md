# Resting bids (maker orders) on the 15-minute crypto markets: tested, not worth it

Nov 25 2026. Question: a resting bid pays no Kalshi fee (about 1.7c at mid prices) and does not pay the spread
(about 1.3c). Would the edge model earn more by resting bids instead of buying at the ask?

## How it was tested

* `build.py`: the walk-forward model's out-of-sample P(YES) for every market x minute (same code as the scorecard).
* `tape.py`: Kalshi's public trade tape for every market where the model saw a possible resting-bid bet
  (DOGE, NEAR, SOL, XRP, ZEC; 1,000 markets, Nov 22-25, about 2,000 trades a market).
* `sim.py`: replay. A 1-contract bid rests from 1.2 s after the minute boundary; it is filled if the tape shows
  a sale below its price (certain fill) or at its price (best case: first in the queue). No fee on fills.
  The taker rule in the same replay reproduces the scorecard's bets and P&L for those days exactly.

## Result

Every posted bid, model edge at the bid of 3c or more (3,952 posted minutes):

| | share | earns per contract |
|---|---|---|
| if every bid were filled | 100% | +1.8c |
| filled within 58 s (certain fills) | 82% | -1.2c |
| filled within 58 s (best case) | 87% | -0.2c |
| never filled | 13-18% | +14.6c |

The bids that fill are the losing ones: somebody sells to a resting bid mostly when the price is about to fall
through it. What that costs (2 to 3c a contract) is what the missing fee and spread save, so nothing is gained.
Resting for a shorter time is worse, not better (3 s: -2.9c on certain fills; 10 s: -2.0c), because the first
seconds are when the informed selling happens. Improving the bid by a cent, or asking for a bigger model edge
(5c: -2.2c on certain fills), does not change the picture. One bet per market, the best resting-bid variant made
+1.5c a bet in the best case and about 0 in the certain-fill case, on days when the taker rule made -1.8c: no
variant is distinguishable from zero.

## Decision

Not built into the live bot. These markets move several cents within seconds, and a bot that reacts in about a
second cannot keep a resting bid out of the way of faster traders. The bot keeps buying at the ask only when the
model's edge after the fee is 5c or more.

The same data says where not to look: any order that waits to be hit is selected against. Gains have to come from
the model (better probabilities) and from getting taker orders in faster, not from resting orders.
