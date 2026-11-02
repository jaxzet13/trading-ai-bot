#!/usr/bin/env bash
# REAL-MONEY runner for KXNEAR15M fair_value (see REAL_MONEY.md).
#   bash scripts/run_real.sh                 # DEMO exchange (fake money)  <- default
#   bash scripts/run_real.sh --dry-run       # signals only, no key, no orders
#   bash scripts/run_real.sh --live          # REAL MONEY: asks you to type a phrase
# Stop: press Ctrl+C, or create a file named STOP in the repo root (touch STOP).
#
# Needs env vars KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH (not needed for --dry-run).
# Restarts the runner if it crashes. Does NOT restart after a clean stop
# (STOP file, Ctrl+C, balance below min_balance_usd, bad config / missing key).
set -u
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}

if [ ! -d .venv ]; then
  echo "First run: creating .venv and installing packages ..."
  $PY -m venv .venv || { echo "Python 3.10+ is required"; exit 1; }
  .venv/bin/pip install -q -r kalshi15m/requirements.txt
fi
PY=.venv/bin/python
.venv/bin/python -c "import cryptography" 2>/dev/null || .venv/bin/pip install -q "cryptography>=42"
mkdir -p data/kalshi15m

ARGS=("$@")
case " ${ARGS[*]-} " in
  *" --live "*|*" --demo "*) ;;
  *) ARGS+=("--demo") ;;
esac

# keep a Mac awake while this runs
if command -v caffeinate >/dev/null 2>&1; then caffeinate -dimsw $$ & fi

trap 'echo; echo "stopped"; exit 0' INT TERM
echo "Real runner starting $(date) with: ${ARGS[*]}   Log: data/kalshi15m/real_log.jsonl"
while true; do
  if [ -e STOP ]; then echo "STOP file present: not starting. Delete it to run again."; exit 0; fi
  $PY -u -m kalshi15m real "${ARGS[@]}" 2>&1 | tee -i -a data/kalshi15m/real_console.log
  code=${PIPESTATUS[0]}
  if [ "$code" -eq 0 ]; then echo "runner stopped cleanly (exit 0); not restarting."; exit 0; fi
  if [ "$code" -eq 2 ]; then echo "configuration / key / confirmation problem (exit 2); not restarting."; exit 2; fi
  if [ "$code" -ge 128 ]; then echo "runner was interrupted (exit $code); not restarting."; exit "$code"; fi
  echo "runner crashed (exit $code); restarting in 15 s ... (create a STOP file to prevent this)"
  sleep 15
done
