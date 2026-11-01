# launchscope

Measures how new Solana memecoin launches perform in the 30 minutes after they appear.

1. `collect` polls GeckoTerminal's Solana new-pools feed and records each new pool the first time it is seen
   (liquidity, market cap, first-five-minute buys and sells).
2. `analyze track` waits until each SOL-paired launch is 30 minutes past first sight, then pulls one-minute
   candles and records peak, end-of-window price, time to peak and an outcome group.
3. `analyze build` writes `data/launches/outcomes.json` (one row per launch) and `data/launches/paths.json`
   (median and middle-half price path by minute), which feed the dashboard.

```bash
pip install requests
python -m launchscope.collect --minutes 20 --pages 2
python -m launchscope.analyze track --max 300
python -m launchscope.analyze build
```

Run `collect` and `analyze track` at the same time. The free GeckoTerminal API allows only a few calls per
minute; set `GECKO_MIN_INTERVAL` (seconds between calls, default 6.5) if you get rate-limited.

Prices are measured against the close of the minute each launch was first seen. Fees, slippage and failed
transactions are not modelled, so these figures describe the market, not a strategy's returns.
