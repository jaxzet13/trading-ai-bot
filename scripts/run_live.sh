#!/usr/bin/env bash
# Paper-trade the strategies in kalshi15m/live.json on live Kalshi markets.
# Mac / Linux:  bash scripts/run_live.sh        (stop with Ctrl+C)
#
# - installs the Python packages it needs (first run only)
# - restarts the bot if it crashes or loses the network
# - serves a live dashboard at http://localhost:8050 that updates every 15 seconds
#   (trade data is refreshed every 20 seconds)
set -u
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}

if [ ! -d .venv ]; then
  echo "First run: creating .venv and installing packages ..."
  $PY -m venv .venv || { echo "Python 3.10+ is required"; exit 1; }
  .venv/bin/pip install -q -r kalshi15m/requirements.txt
fi
PY=.venv/bin/python
mkdir -p data/kalshi15m

# keep the computer awake on a Mac while this runs
if command -v caffeinate >/dev/null 2>&1; then caffeinate -dimsw $$ & fi

( while true; do sleep 20; $PY -m kalshi15m live-report >/dev/null 2>&1; done ) &
( $PY -m kalshi15m serve >/dev/null 2>&1 ) &
SERVER=$!
echo "Live dashboard: http://localhost:8050  (updates every 15 s)"
REPORT=$!
trap 'kill $REPORT $SERVER 2>/dev/null; $PY -m kalshi15m live-report; echo "stopped"; exit 0' INT TERM

echo "Paper trading started $(date). Log: data/kalshi15m/bot_log.jsonl"
while true; do
  $PY -u -m kalshi15m bot --config kalshi15m/live.json 2>&1 | tee -a data/kalshi15m/bot_console.log
  echo "bot exited, restarting in 10 s ..."
  sleep 10
done
