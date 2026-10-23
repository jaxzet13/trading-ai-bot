# fastfund: the two-to-four-week route

Three engines, run together:

1. **Sportsbook sign-up promos, hedged** (`promos.py`). Bonus bets placed on a longshot and hedged with cash on the
   other side at a second book or exchange keep ~67% of the bonus whatever the result. October 2026 offers
   (DraftKings, FanDuel, bet365, Fanatics, Caesars, BetMGM), ordered by the cash each needs at once, snowball
   $100 into roughly $1,170 in about three weeks. State-dependent; 21+, own identity, one account per person, taxable.
2. **Fast-lane prop tickets bought one after another** (`tickets.py`). Lucid Pro 50k at 2% risk, replayed from
   every historical start: one ticket is funded within 14 days 32% of the time; with up to 8 tickets bought as each
   one fails, 53% within 14 days, 77% within 30, 94% within 60, at an average of 2.9 tickets ($343).
   Odds flatten past ~6 tickets because a failed ticket hands the next the same bad week.
3. **Free prop-firm competitions** (listed in `nyopen/playbook.py`). Free entries, top of the leaderboard wins,
   so trade at the maximum size allowed.

The page is the top of `playbook/index.html`. `python -m nyopen.playbook` regenerates its data.
