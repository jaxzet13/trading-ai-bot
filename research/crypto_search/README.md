# Crypto 15m: the big strategy search (Nov 27 2026). Nothing robustly beats the live edge model.

Account holder: "backtest 100,000 different strategies", then "research 1 million strategies for crypto 15m charts
... keep trying until you find better strategies". Every result below is on unseen days: strategies used on a day
were chosen on earlier days only (walk-forward), plus a held-back last third. Benchmark: the live model (ridge on
21 features, 4c bar) on the same 45 days: $3.67/day, t 4.66, 5.2c a bet, max drawdown $14.02.

| search | size | best honest result | verdict |
|---|---|---|---|
| `search.py` feature-decile, model-edge, model+feature, model+hour rules | ~95,000 tried, 54,722 scored | top-5 picked walk-forward: +2.3c a bet alone; model + them $3.87/day but t 3.91 | no |
| `search2.py` + every pair of features x deciles (5-95c prices) | ~1,775,000 tried, 507,320 scored | model + top-20: $3.87/day, t 4.72, both halves higher; the strategies alone +0.6c a bet; top-5 on the hold-out +1.7c | +5%, inside the noise; not deployed |
| `gbm.py` LightGBM (4 settings), alone and blended with the live model | 4 models x 3 bars | best: deeper GBM + live model at 3c $3.71/day t 3.98 | no |
| `features2.py` new inputs: market move 1m / 3m, gap closing, spread, all four | 5 variants | gap closing $3.83/day (research version); paired t 0.87; built into the model properly $3.72 (45 d) and $3.69 vs $3.76 (59 d) | reverted, not robust |
| `filters` (research/edge_tune) time of day, spread, side | 84 rules | walk-forward choice = take everything | no |

Earlier the same day (research/edge_tune): model settings (window, shrinkage, refit) unchanged; entry bar 5c -> 4c
adopted. The live model is unchanged by this search.

Why brute force finds nothing: with 500,000 strategies the best in-sample t from luck alone is ~5.1 and the
in-sample leaders (t up to 32 before the price-band fix) are noise or near-certain 95-99c contracts; the live model
already combines all 21 inputs, so single rules built from the same inputs rarely add information.
