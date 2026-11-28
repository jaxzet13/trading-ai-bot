# 15-minute markets (Nov 28 2026)
download.py -> data/m15 (gitignored); search.py = 4.96M strategies, no edge; render.py -> dashboard/m15_markets.html.

## Forward test: silver and USD/CAD (no real money)
`forward.py freeze` (done Nov 28) saved 5 strategies per group in frozen.json, picked on history only (>= 60 bets, positive in both halves).
`forward.py score` scores only days after the freeze -> forward.json. Promotion bar, fixed before any forward data:
>= 100 forward bets, t by day >= 2.5, positive in both halves. Nothing is tuned after the freeze.
