# Strategy Lab

Mass search for day-trading rules, scored on real prop-firm rule sets, judged on data the search never saw.
App: `lab_app/index.html` (reads the generated `lab_app/data.js`).

## Run it

    python -m lab.data download      # HistData.com 1-minute zips into data/histdata/ (gitignored)
    python -m lab.data build         # day x minute matrices in data/lab/ (gitignored)
    python -m lab.search             # about 20 minutes; writes experiments/lab/raw.npy (gitignored)
    python -m lab.report             # writes experiments/lab/results.json and lab_app/data.js

## How it works

* `data.py`: instruments, costs, downloader. HistData stamps are New York wall-clock time, not fixed EST as documented; `detect_clock()` checks this per instrument.
* `signals.py`: entry families (open candle, opening range, time-of-day momentum and fade, gap, previous-day levels, mean deviation, Donchian, RSI, Asia range) plus coin-flip "null" entries.
* `kernel.py`: 1-minute exit simulation for 78 exit shapes. Stop fills before target inside a minute. Costs plus extra slippage on stops.
* `firms.py`: evaluation, funded phase and payouts for 13 rule sets (collected November 2026; verify before paying).
* `search.py`: TRAIN 2016-2021 filters (t >= 2, PF >= 1.05), VALID 2022-2023 must stay positive, TEST 2024-Nov 2026 is only reported. Do not move these dates later and never select on TEST.
* `report.py`: zero-edge baseline per firm, leaderboard, and family portfolios.

## Results of the November 2026 run

| Step | Count |
| --- | --- |
| Strategies tested | 5,698,992 |
| Passed training filter | 3,957 |
| Still positive in validation | 2,717 (478 distinct) |
| Positive on test | 78% of the 478, average +0.10R (was +0.18R in validation) |

* Only two families held up on test with many survivors: NAS100 NY time-of-day momentum (+0.09R) and NAS100 NY open candle (+0.18R). USDJPY London momentum held with only 5 survivors. GBPUSD, EURUSD, SPX500 families did not hold.
* Picking the single best strategy on validation value is mostly luck: validation value of 40k per attempt became about zero on test. Use family portfolios instead.
* Futures 50k accounts (Lucid, Apex, Topstep, MFFU, Tradeify, TakeProfit) are about break-even per attempt on test, with or without the edge.
* CFD 100k two-step accounts (FTMO, FundedNext, FundingPips) were worth about 5k to 6k per attempt on test with the three-family portfolio: pass 41 to 45%, median 46 to 69 days. FTMO 1-step with two NAS100 time-of-day strategies: pass 64%, median 32 days.
* The zero-edge value of the CFD 100k accounts is about 600 to 800 per attempt, so part of the value is the rules, not the strategy.

## Rules for extending it

* New ideas go in `signals.py` as a family; rerun search and report.
* Judge on the family table and the portfolio test column, not on one strategy's validation value.
* The test window is one 2.9-year period with overlapping attempts. Treat the dollar figures as rough.
