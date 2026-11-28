# La Liga and Premier League focus (Nov 28 2026)

Request: "do way more backtesting on La Liga and Premier League ... they were the most profitable in the backtests".

What was found:
* Kalshi lists soccer winner markets only since Oct 9: La Liga 63 games, EPL 61. No older history exists.
* The "most profitable" results are tiny samples: La Liga's walk-forward made +3.4c on 26 bets (t 0.5; the first, coarser
  study had +11c on 114 bets, t 1.9, and it changes with the strategy grid, which is what noise looks like); EPL +4.6c on 8 bets.
* Every other La Liga / EPL market type (spreads, totals, both teams to score, corners, scorers) over 34 days: walk-forward
  -2.5c to -3.6c a bet; best in-sample t 0.8 where luck alone gives 3.1.
* All six soccer leagues pooled (17,535 strategies): walk-forward -1.3c a bet, t -0.3.

So there is nothing to scale. The one honest test left is games played after the freeze: `forward_soccer.py` (baseline
`search_frozen_nov28.json`) reports the extra bets and money since. Real money only if that is clearly positive over >= 100 new bets.
