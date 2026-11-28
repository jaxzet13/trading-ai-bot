# Other Kalshi markets like the 15-minute crypto ones (Nov 28 2026)

Account holder: "What can we do to add a variety of profitability to Kalshi, are there any other prediction markets like the 15m
that we can profit from since sportsbetting doesn't work".

* `fifteen_min.json`: Kalshi lists 54 fifteen-minute series. Beyond our 9 crypto coins the busy ones are gold (74M contracts in 3
  days), WTI oil, silver, natural gas, copper, Brent, platinum, palladium, 5 currency pairs and the S&P 500 / Treasury yields.
  Same question as the crypto ones ("price up in the next 15 minutes", strike = price at the window start), settled on Pyth Network prices.
* Pyth's price endpoints need an API key from this container (401), so the exact settlement price series is not available yet.
* `gold_probe.py`: first look at gold with Coinbase's PAXG token as a stand-in price (957 usable windows over 48 days): the
  market's own mid predicts better than the PAXG model (log loss 0.512 vs 0.576) and betting the model made -0.7c to +2.2c a bet
  (t <= 1.4). Inconclusive, not promising: PAXG is illiquid (many missing minutes) and trades at a premium to spot gold.
* `survey.py` / `survey.json`: every non-sports series, settled markets and contracts in the last 14 days (slow, still running).
