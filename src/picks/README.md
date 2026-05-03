# Sports Picks Aggregator

Scans every in-season sport on [The Odds API](https://the-odds-api.com), line-shops across US books, strips the vig to build a consensus fair price per market, and ranks today's top **+EV singles**. Also suggests uncorrelated 2–3 leg **parlays** from the top singles.

> Reality check: there is no system that reliably beats Vegas long-term. This finds pricing edges (a book priced differently from the rest of the market). It does not model sharp money or injuries. Use responsibly and never bet more than you can lose.

## Setup

```bash
pip install -r src/requirements.txt
export ODDS_API_KEY=your_key_here   # free tier at the-odds-api.com
```

## Usage

### Web UI (recommended)

```bash
ODDS_API_KEY=your_key python -m src.picks.web
# then open http://localhost:5050 in a browser
```

Filters (sports, min-edge, today-only, props) are controls on the page itself. Results are cached for 90 s so refreshing doesn't burn API quota.

### CLI

```bash
# Top 15 +EV picks across every sport
python -m src.picks

# Include player props (costs more API credits)
python -m src.picks --props --top 20

# Only today's games, NBA + MLB only, emit JSON
python -m src.picks --today --sports basketball_nba baseball_mlb --json

# Raise the edge threshold to "only show me meaningful edges"
python -m src.picks --min-edge 0.03 --min-books 4
```

## How it works

For each market at each book we have `(my_price, opposite_price)`. We strip the vig by normalizing implied probabilities to sum to 1, giving a fair probability *at that book*. Averaging across all books that quoted the market gives a **consensus fair probability**. The single best price across all books is the one you'd actually bet. Edge = `fair_prob * best_decimal - 1`.

- `math.py` — odds conversion, no-vig, edge, fractional Kelly
- `odds.py` — Odds API client
- `scanner.py` — flattens events → picks, computes fair / edge
- `parlays.py` — combines uncorrelated legs into +EV parlays
- `__main__.py` — CLI

## Limits

- Free-tier Odds API has a monthly request quota. Each sport = 1 request for game markets; each event = 1 request if `--props` is on. Start without `--props` to stay under quota.
- Consensus fair uses book averaging. If one book is very sharp (e.g. Pinnacle), its line is better than consensus — but Pinnacle is often absent from US regions.
- Parlay "uncorrelated" check only rules out same-game and same-player combos. Cross-game correlation (weather, travel) is not modeled.
