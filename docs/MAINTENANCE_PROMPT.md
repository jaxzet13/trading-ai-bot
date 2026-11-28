# Maintenance prompt (paste this to Claude any time)

```
Run a full maintenance and improvement pass on my Kalshi trading system. Repo: jaxzet13/trading-ai-bot, branch
claude/determined-mayer-o254q7. Read docs/MAINTENANCE_PROMPT.md and the notes file (TRANSFORM_NOTES.md in the scratchpad, if
present) first. Work through all of this without asking me questions, then give me a short plain-English report.

1. HEALTH. Check every process is running (real-money 15m crypto bot and its edge loop, Discord feed, the three tennis
   processes, tennis auto-better, tennis parlay runner, sports recorder, keep-alive) and restart anything missing from its
   watchdog script. If keys or watchdog scripts are missing, tell me immediately. Respect STOP_* files.

2. MONEY CHECK. Balance of each shard (crypto, combos, tennis), real bets and profit/loss per strategy since it started, and
   compare live results with the backtest scorecard. Say plainly if live is far below the backtest or a strategy is losing.

3. REVIEW EVERY STRATEGY that has real or practice money (crypto edge model, the two restored rules, tennis auto-better,
   tennis parlays, anything else running). For each: keep, change, or replace. Decide ONLY from results on days the strategy
   never saw (walk-forward, hold-out, forward tests). Never from in-sample numbers.

4. RESEARCH. Do more data testing and backtesting to find better or additional strategies: new inputs for the crypto model,
   the other Kalshi 15-minute markets (gold, oil, metals, currencies, S&P), weather and other daily markets, anything promising.
   Every test must be honest: pick on earlier days only, score on later days, count how many strategies were tried and compare
   with what luck alone would give, freeze promising candidates and forward-test them on new games/days. Report negative
   results too. Never rig a test, loosen it, or cherry-pick a window to make something look good.

5. IMPROVE. Fix bugs and tooling freely. Change a real-money setting (entry bar, sizing, limits, which coins are live) only when
   it clearly beats the current one on unseen days, and tell me what and why in the same reply. A new strategy gets real money
   only after it passes walk-forward with t >= 2.5, is positive in both halves AND passes a forward test, then small size, and
   only after I say yes.

6. STANDING RULES. Do not change bet size (currently 2x), add money, or move money between shards without my word. Never commit
   Kalshi credentials. Keep the $4 balance floor. Do not re-add daily caps, drawdown brakes, night/day multipliers or per-rule
   auto-pause. Do not re-add the NEAR drift rule. No resting (maker) orders. Do not restart the retired evolution loop,
   rotation or live-report. Real money only on my own account. No pull requests unless I ask. Commit and push to the branch
   after each change.

7. REPORT. Short, plain English, numbers first: is it running, how much did we make or lose and how does that compare with the
   backtest, what you changed and why, what you tested and what it showed, what you recommend next, and anything you need from
   me. "Nothing needed changing" is a fine answer. If an edge is fading, say so. No promises about income: tell me the truth.
```

Notes
* A prompt cannot guarantee steady income. Every edge found so far is small and can fade; the point of the pass is to catch fading
  edges early and keep the testing honest.
* Claude already runs hourly and 3-hourly checks inside an active session. This prompt is for a fresh session or a deeper pass.

## Autonomy policy (Nov 28 2026, account holder: "go, use it every 3 hours")
The 3-hourly scheduled check (trigger trig_01Duk1XNvxPYKXyvd3WvVWEN, 51 */3 * * * UTC) now runs with full autonomy over every live
strategy: it may change entry bar, bet size (1x-3x, max 40% of a shard at risk), order pricing, which coins are live, retire/add
strategies and move up to $10 a pass between the account holder's own shards, WITHOUT asking, reporting afterwards.
Guardrails: changes must beat the current setting on unseen days in both halves (never loosen tests), one at a time, logged with
a rollback, re-checked after >= 100 bets (roll back if clearly worse), size up only when live is within the backtest's normal
range, $4 floor kept, no deposits/withdrawals, no credentials committed. Previously forbidden items (daily caps, drawdown brake,
night/day multipliers, per-rule auto-pause, NEAR drift rule, resting orders, retired loops) stay forbidden.
