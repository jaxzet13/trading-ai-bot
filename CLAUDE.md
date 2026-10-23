# trading-ai-bot

Two independent pieces live here:

* `nyopen/` – the NAS100 "NY open first-candle vs 12 EMA" strategy, its backtester, optimiser and dashboard exporter. Read `nyopen/README.md` first. The dashboard is `dashboard/index.html` and reads `dashboard/data.js`.
* `src/`, `server.py` – an older, unrelated toy model and an X posting template.

## Working on the strategy
- Data: `python -m nyopen.run download` fills `data/cache/` and writes `data/nas100_m1.csv.gz`. The cache is resumable; rerun to extend it.
- Every backtest must go through `python -m nyopen.run backtest --name <name>` so it lands in `experiments/experiments.jsonl` and the dashboard.
- Judge changes on out-of-sample metrics (after `OOS_START` in `nyopen/optimize.py`). Do not move that date later.
- `python -m nyopen.run improve --name <name>` is the structured search. Add new levers as `Params` fields and new candidates to `STAGES` in `nyopen/improve.py`.
- Keep `Params` defaults equal to the best configuration that survived out of sample; document the reason in the commit and in the table in `nyopen/README.md`.
- A change needs a reason a trader would recognise, not just a better number. Reject calendar tricks (skip a weekday, skip a month) unless there is an event-driven explanation.
- `VIDEO_RULE` in `nyopen/strategy.py` must keep reproducing the plain video rule; the dashboard overlays it as the baseline.
- `dashboard/data.js` is generated. Rebuild it with `python -m nyopen.run export` instead of editing it.
