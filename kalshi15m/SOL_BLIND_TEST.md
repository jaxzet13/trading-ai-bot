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
