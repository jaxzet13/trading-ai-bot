# X Growth Automation API (Compliant Template)

This app automates **scheduled posting workflows** and **engagement analytics** for X in a safe, policy-aware way.

## Why this exists
- Batch-generate and schedule posts from campaign hooks.
- Publish due posts via one automation endpoint.
- Track event metrics (`impression`, `like`, `reply`, `repost`, `follow`).
- Measure engagement rate and follower gains.

## Run
```bash
cd src
pip install -r requirements.txt
python x_growth_app.py
```

## Environment
- `X_GROWTH_DB` (default: `x_growth.db`)
- `X_DRY_RUN` (default: `true`) — keeps publishing simulated.

## Key Endpoints
- `GET /health`
- `POST /campaigns`
- `POST /automation/run`
- `POST /events`
- `GET /analytics/summary`
- `GET /posts`

## Example: create campaign
```bash
curl -X POST localhost:5000/campaigns \
  -H 'content-type: application/json' \
  -d '{
    "name": "ai trader growth",
    "persona": "Quant founder",
    "audience": "retail traders",
    "hooks": [
      "Most traders lose because they ignore risk.",
      "A simple checklist beats emotional entries every time."
    ],
    "hashtags": ["Trading", "RiskManagement", "AI"],
    "start_at": "2026-01-01T12:00:00+00:00",
    "cadence_minutes": 180
  }'
```

> Keep content truthful, useful, and compliant with X platform policies.
