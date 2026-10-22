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

## Layout
| File | Purpose |
|---|---|
| `data.py` | Downloads Dukascopy `USATECHIDXUSD` 1-minute candles (one `.bi5` per day into `data/cache/`), decodes them, writes `data/nas100_m1.csv.gz`, resamples. |
| `strategy.py` | `Params` and `run_day()`: the simulation of a single session. |
| `backtest.py` | Runs every session, computes metrics, appends the run to `experiments/experiments.jsonl`. |
| `metrics.py` | Return, CAGR, win rate, profit factor, drawdown, Sharpe, Sortino, streaks, yearly and monthly tables. |
| `optimize.py` | Grid sweeps scored in-sample (before `OOS_START`) and out-of-sample, plus walk-forward by year. |
| `export.py` | Writes `dashboard/data.js` and `dashboard/data.json` for the dashboard. |
| `run.py` | CLI. |

## Commands
```bash
pip install -r requirements.txt
python -m nyopen.run download                    # first run takes a while: Dukascopy rate-limits to a few files a second
python -m nyopen.run backtest --name base        # backtest with the defaults, log it, rebuild dashboard/data.js
python -m nyopen.run backtest --name test --set trail_mode=swing swing_len=2 exit_time=12:00
python -m nyopen.run sweep --name grid1          # IS/OOS grid; every row is logged
```
Then open `dashboard/index.html` in a browser.

## The improvement loop (for an AI agent or a human)
1. Form a hypothesis (for example "the short side after a gap up is the weak part").
2. Add a `Params` field or edit `run_day()` to express it. Keep the default behaviour unchanged.
3. Run `python -m nyopen.run backtest --name <hypothesis> --set <field>=<value>`.
4. Compare the new row in the dashboard's experiment log. The decision metric is the **out-of-sample** profit factor and average R, not the full-period return.
5. If it holds up, make it the default in `Params` and note why in the commit message.
6. Never judge a change on fewer than ~100 trades, and never move `OOS_START` later to make a result look better.
