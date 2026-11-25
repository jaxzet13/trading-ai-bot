# Edge model: can it learn what the restored ZEC rule sees? (Nov 25 2026)

The old rule fv_tau:KXZEC15M:10 bets when the vol model's probability is 11c or more from Kalshi's price. Next to
the edge model its extra ZEC bets made about +9c each on unseen days, so the model under-reacts to big gaps there.

`gap_test.py`: same walk-forward, same 5c threshold, live coins (57 unseen days).

| variant | bets a day | per bet | a day | t | max drawdown |
|---|---|---|---|---|---|
| live model | 41.1 | +6.7c | $2.75 | 5.9 | $7.84 |
| + gap in probability units | 40.9 | +6.5c | $2.64 | 5.8 | $8.64 |
| + the part of the gap beyond 8c | 39.8 | +6.2c | $2.47 | 5.2 | $12.15 |
| + gap, + gap late in the window | 41.0 | +6.6c | $2.70 | 6.0 | $6.88 |
| weaker pull of each coin toward the pooled fit (300 -> 30) | 53.7 | +6.0c | $3.22 | 5.8 | $10.45 |

None of the gap features helps. Weaker shrinkage gives more bets at a slightly lower edge (more dollars a day, the
same t, a bigger drawdown): it acts like a lower threshold and was tuned on the test days themselves, so it is not
adopted. The ZEC rule stays as a separate rule next to the model.
