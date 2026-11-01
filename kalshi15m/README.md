# Kalshi 15-minute up/down: backtester, dashboard and bot

Kalshi lists a new market every 15 minutes for BTC, ETH and SOL (`KXBTC15M`, `KXETH15M`, `KXSOL15M`):
*will the price at :15 be at or above the price at :00?* This package downloads every settled
market with its real minute-by-minute order book, backtests strategies against it with Kalshi's fees,
shows the results in a dashboard, and can run a strategy live (paper trading by default).

## Quick start

```bash
pip install -r kalshi15m/requirements.txt
python -m kalshi15m download --days 45     # ~10 min, public APIs, no key needed
python -m kalshi15m backtest               # sweeps + train/test split, writes dashboard/
python -m kalshi15m serve                  # open http://localhost:8050
python -m kalshi15m bot --strategy fair_value            # PAPER trading, prints decisions
```

## What's tested

| Strategy | Idea |
|---|---|
| `baseline_yes` | Always buy YES at minute 1 (the control: shows what fees + spread cost) |
| `momentum` / `reversal` | Bet the previous 15 minutes continue / reverse |
| `late_favorite` | Buy the 70-98c favourite in the last minutes |
| `longshot` | Buy the side priced under 25c |
| `spot_lag` | Spot already moved far from the strike but the book hasn't caught up |
| `fair_value` | Lognormal model (spot vs strike, trailing vol) vs. the order book |

Every strategy is tuned on the first 70% of markets and judged on the last 30%.
Fills are at the ask (taker), fee = `ceil(0.07 * C * P * (1-P))`.

## Results so far (45 days, Sep 17 - Nov 1 2026)

**No strategy showed a reliable edge.** Out-of-sample, none cleared a t-stat of 2. Market prices
are well calibrated (a 25c contract wins about 25% of the time), and taker fees + spread cost
~4-5% per trade on coin-flip prices. Things that looked great in-sample (e.g. `fair_value`, +$245 on
BTC) lost on the test period. See the dashboard's "Does tuning carry over?" chart.

Ideas not yet tested: resting maker limit orders (earn the spread instead of paying it), a faster
spot feed than Coinbase 1-minute bars, and order-flow / book-imbalance signals. These need tick-level
data, which you can collect by running the bot in paper mode.

## Going live (read this first)

* Paper mode is the default. `--demo --live` trades on Kalshi's demo exchange (fake money).
* `--live` sends real orders and needs `KALSHI_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` (RSA key from
  Kalshi account settings). Order fields follow Kalshi's v2 API; verify on demo first.
* Built-in limits: `--stake` per trade, `--max-daily-loss`, one trade per market, max 40 trades/day.
* Do not go live with a strategy that didn't pass the out-of-sample test.
