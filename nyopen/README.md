# NY Open Candle strategy (NAS100, 5-minute)

Reproduction and research harness for the "first 5-minute candle after the New York open vs the 12 EMA" strategy.

## The rule
1. Build 5-minute bars in New York time. Compute a 12-period EMA on closes (pre-market bars included, so the EMA is live at the open).
2. Take the 09:30 candle. If it closes above the EMA, go long at its close. Below, go short. One trade per day.
3. Initial stop at the signal candle's low (long) or high (short). That distance is 1R.
4. After each later bar closes, raise (lower for shorts) the stop to the EMA if that is tighter. The stop never loosens.
5. Exit when a bar trades through the stop, or at the open of the 15:55 bar.
6. Position size risks `risk_pct` of equity per trade; `cost_points` of spread and slippage is charged on every trade.

Everything in steps 1 to 6 is a field on `Params` in `strategy.py`, so a change is one flag away.
`VIDEO_RULE` in `strategy.py` holds the overrides that reproduce the plain video rule.

## Current defaults (promoted from the `improve v3` and `v4` searches, October 2026)
| Lever | Video | Now | Why |
|---|---|---|---|
| Trend filter | none | price vs 300 EMA (5-min, about a day of bars) | only take the open candle in the direction of the wider trend; biggest single gain in and out of sample |
| Trailing stop | 12 EMA | chandelier, 3.5 x ATR(14) from the trade's extreme, active once the trade is +1R | gives winners room and does not choke a trade that is still near entry; lower drawdown than the EMA trail |
| Breakeven | none | stop to entry at +1R | a trade that reached 1R should not turn into a full loss |
| Time exit | 15:55 | 15:30 | the last half hour is closing-auction noise with little follow-through |
| Signal EMA | 12 | 8 | small, consistent improvement in both halves |
| Weak-signal filter | off | skip if the close is within 0.1R of the EMA | removes coin-flip candles sitting on the EMA |
| Flat-candle filter | off | skip signal candles under 5 points | holiday sessions print 0.1-point candles that are not tradeable |

Each search also wanted to skip a weekday (v3: Wednesday, v4: Thursday). Different day each time is the signature of noise, so both were rejected even though they lift the numbers.

Result on 2019-01 to 2026-10 (1% risk, 1 point cost): video rule +275%, profit factor 1.13, max drawdown 35%. Current defaults +1,085%, profit factor 1.31, max drawdown 24%, every calendar year positive. Out of sample (2024 on) the profit factor goes from 1.10 to 1.27.

## Prop-firm simulation
`propfirm.py` replays the trade stream against typical challenge rules (two-step 10/5 with 10% max loss, one-step 10/6, 30-day-limited phases, futures-style trailing drawdown), starting an evaluation on every historical day and at several fixed risk sizes. The dashboard shows pass rate, blow-up rate, days to pass, and the odds of still being funded a year later. Read it before deciding on risk per trade.

## Layout
| File | Purpose |
|---|---|
| `data.py` | Downloads Dukascopy `USATECHIDXUSD` 1-minute candles (one `.bi5` per day into `data/cache/`), decodes them, writes `data/nas100_m1.csv.gz`, resamples. |
| `strategy.py` | `Params` and `run_day()`: the simulation of a single session. |
| `backtest.py` | Runs every session, computes metrics, appends the run to `experiments/experiments.jsonl`. |
| `metrics.py` | Return, CAGR, win rate, profit factor, drawdown, Sharpe, Sortino, streaks, yearly and monthly tables. |
| `optimize.py` | `evaluate()` runs once and splits the trades at `OOS_START` into in-sample / out-of-sample metrics; grid sweeps; walk-forward by year. |
| `improve.py` | Staged search over lever groups. Selects in-sample, refuses any stage that lowers the out-of-sample profit factor, logs everything, writes `experiments/improve_<name>.json` for the dashboard. |
| `propfirm.py` | Prop-firm challenge simulator (pass / blow-up rates, time to pass, funded survival) across rule sets and risk sizes. |
| `export.py` | Writes `dashboard/data.js` and `dashboard/data.json` for the dashboard. |
| `run.py` | CLI. |

## Commands
```bash
pip install -r requirements.txt
python -m nyopen.run download                    # first run takes a while: Dukascopy rate-limits to a few files a second
python -m nyopen.run backtest --name base        # backtest with the defaults, log it, rebuild dashboard/data.js
python -m nyopen.run backtest --name test --set trail_mode=swing swing_len=2 exit_time=12:00
python -m nyopen.run sweep --name grid1          # IS/OOS grid; every row is logged
python -m nyopen.run improve --name v4           # staged search from the current defaults
python -m nyopen.run improve --name v4 --from-video-rule   # ... or from the plain video rule
```
Then open `dashboard/index.html` in a browser.

## The improvement loop (for an AI agent or a human)
1. Form a hypothesis (for example "the short side after a gap up is the weak part").
2. Add a `Params` field or edit `run_day()` to express it. Keep the default behaviour unchanged.
3. Run `python -m nyopen.run backtest --name <hypothesis> --set <field>=<value>`.
4. Compare the new row in the dashboard's experiment log. The decision metric is the **out-of-sample** profit factor and average R, not the full-period return.
5. If it holds up, make it the default in `Params` and note why in the commit message.
6. Never judge a change on fewer than ~100 trades, and never move `OOS_START` later to make a result look better.
