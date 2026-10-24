# desk: multi-market day-trading search

Tests standard day-trading setups on several markets with one honest rule: choose parameters on 2019-2023 (2021-2023
for EURUSD and US30), then keep a setup only if it also has a profit factor of 1.10+ on the 2024-2026 hold-out, at
least 150 trades, and a positive result in most in-sample years.

| File | Purpose |
|---|---|
| `instruments.py` | NAS100, US30, US500, XAUUSD, EURUSD, GBPUSD: Dukascopy symbol, round-trip cost, minimum stop, sessions. |
| `features.py` | Per-session context: session VWAP, 15-minute opening range, Asian range (19:00-03:00 NY), previous session levels. |
| `strategies.py` | Opening-range breakout, Asian-range breakout, VWAP pullback (the open-candle rule comes from `nyopen`). |
| `search.py` | `python -m desk.search XAUUSD EURUSD ...` writes `experiments/desk/<market>.json` and the trade lists of accepted setups. |
| `portfolio.py` | Combines accepted setups into one desk and runs it through `nyopen/propfirm.py`. |

Data: `python -m nyopen.data 2019-01-01 2026-10-23 XAUUSD` (any Dukascopy symbol; caches under `data/cache_<SYMBOL>/`).

## Result (October 2026)
236 configurations across NAS100, gold (2019-2026), EURUSD and US30 (2021-2026), in the London and New York sessions.

| Market | Best setup | In-sample PF | Out-of-sample PF | Verdict |
|---|---|---|---|---|
| NAS100 | New York open-candle rule | 1.37 | 1.27 | on the desk |
| US30 | New York 15-minute opening-range breakout | 1.05 | 0.89 | rejected |
| EURUSD | London open-candle (video rule) | 1.02 | 0.74 | rejected |
| Gold | London Asian-range breakout | 0.97 | 0.73 | rejected; no setup clears 1.1 even at zero cost |

Only the NAS100 New York open survives. It trades identically on NQ / MNQ futures.
GBPUSD and US500 were not downloaded (they track EURUSD and NAS100 closely).
