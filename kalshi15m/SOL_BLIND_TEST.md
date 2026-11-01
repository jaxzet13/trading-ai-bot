# SOL fair-value blind test (written before looking at the archive)

Why: on Aug 31 - Nov 1 data, `fair_value` on SOL alone with maker orders made +$878 out of sample
(t = 1.03, 4 of 5 folds up). SOL was picked *after* seeing that it did best of three coins, so that
number is biased upward. The Apr - Aug 2026 SOL archive has never been used for any test or tuning.

Frozen rule (the parameters the walk-forward picked most recently, fold F6):

    strategy   fair_value
    params     start=2 end=13 edge=0.12 vol_mult=1.0  (min_price 0.05, max_price 0.95)
    execution  maker: rest at the bid (+1c if the spread allows) for 2 minutes
    stake      $10 per trade; also reported as a flat 10 contracts per trade

Pass if, on the archive only: total P&L > 0 AND t-stat >= 2 (flat 10 contracts) AND at least
3 of the 5 months are profitable. Anything else is a fail. No re-tuning on the archive.

## Result (run Nov 1 2026, 7,309 SOL markets, Apr 1 - Sep 1 2026, every 2nd archive market)

**FAIL.**

| Execution | P&L ($10/trade) | Trades | t-stat | Flat 10 contracts | Months profitable |
|---|---|---|---|---|---|
| maker (the frozen rule) | -$280 | 1,913 | -0.27 | -$77, t = -0.45 | 2 of 5 (Apr, Jun) |
| taker (for reference) | -$1,165 | 2,088 | -1.19 | -$146, t = -0.79 | 2 of 5 |

Monthly maker P&L: Apr +$177, May -$89, Jun +$686, Jul -$906, Aug -$118.
Maker diagnostics: 92% fill rate, 1.8c saved per fill, but filled orders won 22.6% vs 26.0% for all
signals (adverse selection). The +$878 seen on Aug 31 - Nov 1 does not hold up on older data; it is
most likely luck plus picking SOL after the fact.
