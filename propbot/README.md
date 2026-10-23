# propbot: the search for a second, lower-variance strategy

Built after the question "can the NY open strategy pass a prop-firm challenge?". The goal was a strategy
family with a high win rate, fixed targets and a daily loss cap, so that losing streaks stay short.

## What is here
| File | Purpose |
|---|---|
| `engine.py` | Generic intraday engine: market / stop / limit orders, targets, trailing and breakeven stops, N trades a day, daily loss cap in R, conservative fills. |
| `features.py` | Session VWAP, 15-minute opening range, previous-day high/low/close, EMAs, ATR, per session. |
| `strategies.py` | Five candidates: opening-range breakout, VWAP pullback, EMA pullback, opening-range fade, previous-day break. |
| `run.py` | Evaluate candidates (IS/OOS, challenge odds). `python -m propbot.run --export` writes `experiments/alternatives.json` for the dashboard. |

## Result (October 2026)
None of the five candidates has an edge after a 1-point cost. Across 220 configurations the best in-sample
profit factor was 1.07 and nothing cleared 1.08 both in and out of sample. The open-candle rule at other
session opens (Frankfurt, London, 08:30 data, 10:00) has no edge either. The NY open is special in this data;
the other candidates are kept so the next idea can be tested in minutes rather than built from scratch.

## What actually makes the challenge passable
Risk management, not a new signal. With the NY open strategy and the sizing policy "cut risk in drawdown"
(halve the risk once 30% of the max-loss allowance is used, quarter it at 60%):

| Risk per trade | Two-step pass | Median days | Funded after 12 months |
|---|---|---|---|
| 0.5% | 100% of historical starts | 287 | 100% |
| 0.75% | 100% of historical starts | 194 | 100% |
| 1.0% | 89% | 174 | 81% |

Rules that cannot be passed with this edge: any 30-day phase limit, and futures-style trailing drawdowns.
