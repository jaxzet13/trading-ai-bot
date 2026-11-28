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

## La Liga deep dive (laliga_deep.py, Nov 28)
The +11c is 114 bets on only 20 games (5.7 near-duplicate bets per game: "back the 20-30c underdog" at ten different minutes).
84% of the profit comes from the best 3 games (three upsets); without the best 5 games it is -5.4c. Bootstrap over games, 90% interval:
-3.9c to +26.5c. The same strategies on the other five soccer leagues (2,846 bets on games that never influenced the choice):
-5.0c a bet (EPL -5.2, Champions League -13.2, Bundesliga -1.8, MLS -6.8, Liga MX -0.3). Verdict: three underdog upsets, not an edge.
