# Nov 24 review: why the leaderboard rules plateaued, and the pooled edge model

One-off analysis scripts (scratch paths inside them point at the session scratchpad; the production code is
`kalshi15m/edge.py`). Order: build.py / rows.py (pool every stored market) -> an1.py (calibration of Kalshi's
prices and of the old fair-value "edge") -> an2.py (which signals predict beyond the price) -> wf.py / wf2.py
(walk-forward logistic model) -> sim.py / robust.py / final.py (bets, stress tests, final spec) -> gbm.py
(a gradient-boosted model did worse out of sample) -> real_vs.py (real fills vs the candle ask) ->
ten1.py / ten2.py (the same test on tennis: no taker edge).

Headline numbers are in the commit message of the edge-model commit and in data/lab/edge_walk.json.
