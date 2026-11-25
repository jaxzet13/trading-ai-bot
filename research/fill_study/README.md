# Why some orders did not fill, and the fix (Nov 25 2026)

## What happened to the real orders

43 orders by the edge model up to Nov 25 14:00 UTC:

* The first 23 carried a fixed limit = the ask seen at the minute boundary: 14 filled (61%).
* From Nov 25 06:00 the limit was that ask + up to 2c: 17 of 20 filled (85%).
  With the book logged at send time: ask still within the limit -> 16 of 16 filled; ask beyond it -> 1 of 4.
* The order reaches Kalshi about 1.35 s after the minute boundary: wake-up 0.5 s, spot data 0.45 s, and
  0.34 s for the order itself, because it went out on a cold connection (a warm one takes 0.04 s).
* When two coins signal in the same minute the second order waits another ~0.5 s for the first to finish.

So an order misses when the ask moves up by more than its allowance in that second. It also fills at whatever
lower price is there when the ask has dropped. Fills when the price falls, misses when it rises.

## What the trade tape says (`tape.py`, `sim.py`)

Every walk-forward taker signal of the last 14 days on the 5 live coins (706 signals) replayed against Kalshi's
trade tape: the ask an order meets `delay` seconds after the minute is read off the next trade.

| rule (order lands 1.35 s late) | fills | profit per signal |
|---|---|---|
| scorecard's assumption: fills at the ask at the minute | 100% | +3.6c |
| fixed limit, ask + 0c | 52% | +2.4c |
| ask + 2c (the rule until now) | 74% | +2.8c |
| ask + 5c | 79% | +3.2c |
| skip when the ask has dropped more than 2c | 54% | +1.7c |
| re-priced at the new mid, edge after fee >= 4c | 100% | +3.6c |

* Price moves in that second are not against us on average: buying at whatever the ask is when the order lands
  earns what the scorecard assumes. The loss came from the one-sided limit.
* The signals the old rule missed earn +2.9c each at the price they would have paid (182 signals, standard error
  3.5c). Re-pricing instead of the old rule: +0.8 to +1.4c per signal at every delay tested and in both halves of
  the sample, t about 1 to 1.7. Suggestive, not proven; there is no sign that it costs anything.
* Moves of more than 10c in a second (9 cases) lost money: those are dropped.
* Skipping when the price has dropped is clearly worse. Not done.
* With re-pricing, a faster order earns the same in this sample (0.3 s vs 1.35 s). Speed only matters for the
  fixed-limit rule.

## What changed in the live bot

* `real.reprice`: an edge order is re-priced on the live book at the moment it goes out. The model's probability
  is the market mid plus a correction, so it moves with the mid (same correction in log-odds). The order buys at
  the new ask (+1c slack) while the edge after the fee is >= 4c (`limits.edge_exec_min_edge`); it is dropped when
  the ask moved more than 10c (`edge_exec_max_move`) or the edge is gone, and the market stays open for the
  next minute. The entry rule is unchanged: the model needs >= 5c at the minute boundary.
* `KalshiAPI.warm`: three connections are kept open from 2 s before each minute, so the order takes ~0.04 s
  instead of ~0.34 s.
* Without the order-book stream the old ask + 2c limit is used.

Not done: deciding earlier than 0.5 s after the minute. The spot bar is already final 0.03 s after the minute
(225 of 225 product-minutes measured), so it is possible, but with re-pricing the tape shows no gain from it.
