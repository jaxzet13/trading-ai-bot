# Edge model tuning sweep (Nov 27 2026): lower the entry bar to 4c; nothing else beats the current model

Account holder: "just do anything you can to improve it ... we've been on a plateau". `sweep.py`, output in
`results.txt` / `results.json`. All numbers are on unseen days (walk-forward), 1 contract, Kalshi fee, live coins.

**A. Model settings (full walk-forward refit each):** none beat the current one ($2.67/day at 5c).
roll 21 $2.73 (deeper drawdown), roll 49 $2.21, LAM_COIN 100 $2.80 (maxDD 9.9), LAM_COIN 1000 $2.06,
LAM_POOL 5 $2.68, LAM_POOL 80 $2.65, daily refit $2.66.

**B. Entry rules chosen walk-forward** (120 rules: bar 3-8c x 6 minute windows x 4 price bands; each test day uses
the rule with the best record on earlier days): $3.20/day vs $2.64 for the current rule on the same 45 days, same
max drawdown (7.8). It chose 4c most often, then 3c.

**C. Per-coin bars chosen walk-forward:** $3.36/day (maxDD 10.9); chose 3-4c for every coin.

**D. Fixed 4c vs 5c, current model, same 45 days:** $3.74 vs $2.64/day, t 4.8 vs 4.9, 34 vs 33 days up, both halves
better (3.39/4.07 vs 2.48/2.79), max drawdown 14.0 vs 7.8. Full 59 days: 69.5 bets/day, +5.5c a bet, $3.81/day.

**Done:** `kalshi15m/edge.py` THR 0.05 -> 0.04, model retrained (same 5 live coins). The cost is a deeper drawdown
and a lower average edge per bet; the live record (159 model bets, about -1.7c per contract against +6.4c in the
backtest) is still too short to judge either way.
