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
python -m kalshi15m bot --series KXBTC15M KXETH15M KXSOL15M   # PAPER: each coin runs its own pick
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

## Results so far (17,640 markets, Aug 31 - Nov 1 2026, walk-forward)

Tested with one parameter set across BTC, ETH and SOL, re-tuned on past data only, 6 time folds,
both as taker (buy at the ask) and maker (rest a limit order at the bid).

* **No strategy cleared the bar** (t-stat >= 2, profit in 60% of folds, profit on 2+ coins).
* Best maker results: `closing_value` +$761 over 4,135 trades (t=0.41, 4 of 5 folds up) and
  `reversal` +$126 (t=0.18). Both are well within luck.
* **Maker orders work but don't create an edge:** about 90% fill, each fill saves ~1c vs the ask,
  but filled orders win ~2-3 points less often than the signals overall (adverse selection).
  Spreads are usually 1c, so there is little room to improve on the bid.
* Market prices are well calibrated at every minute of the window.

`python -m kalshi15m download` also pulls Kalshi's archive (from `--since`, every `--every`-th market)
for a longer test; it takes a few hours because the archive serves one market per request.

## Each coin, its own strategy

`backtest` also picks a strategy per coin, walk-forward: before each period it takes the strategy,
order type and settings with the best t-stat on that coin's earlier data (sitting out if none reaches
2), then trades the period untouched. `bot --strategy auto` (the default) runs each coin's latest pick.
On Aug 31 - Nov 1: BTC picked spot lag (+$12), ETH mostly sat out (+$41), SOL picked the fair-value
family (+$610). Combined +$663, t = 0.80: not yet distinguishable from luck.

## Live paper trading (current setup)

`kalshi15m/live.json` holds the two strategies being paper-traded on live markets:
ETH reversal after a big move (maker) and SOL fair value (maker). Start and refresh:

```bash
python -m kalshi15m bot --config kalshi15m/live.json     # runs both, paper mode
python -m kalshi15m live-report                          # update dashboard/index.html
```

The bot only runs while its machine is on. For a long paper run, start it on a computer or
server that stays up.

## Going live (read this first)

* Paper mode is the default. `--demo --live` trades on Kalshi's demo exchange (fake money).
* `--live` sends real orders and needs `KALSHI_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` (RSA key from
  Kalshi account settings). Order fields follow Kalshi's v2 API; verify on demo first.
* Built-in limits: `--stake` per trade, `--max-daily-loss`, one trade per market, max 40 trades/day.
* Do not go live with a strategy that didn't pass the out-of-sample test.
