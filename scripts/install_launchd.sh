#!/usr/bin/env bash
# Installs `tradelab run` as a macOS launchd agent so it runs continuously
# in the background, starting on login and restarting itself if it ever
# crashes or the Mac reboots — this is what keeps the 7-minute trading
# cycle actually running instead of depending on a terminal staying open.
#
# Usage (from the repo root, with your venv already created + .env filled in):
#   ./scripts/install_launchd.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${REPO_DIR}/.venv/bin/python"
PLIST_SRC="${REPO_DIR}/scripts/com.tradelab.run.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/com.tradelab.run.plist"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "No venv found at ${PYTHON_BIN}."
    echo "Create one first:  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

if [[ ! -f "${REPO_DIR}/.env" ]]; then
    echo "Warning: no .env found at ${REPO_DIR}/.env — tradelab needs your Alpaca paper keys there."
fi

mkdir -p "${HOME}/Library/LaunchAgents"
sed -e "s|__PYTHON__|${PYTHON_BIN}|g" -e "s|__REPO_DIR__|${REPO_DIR}|g" \
    "$PLIST_SRC" > "$PLIST_DST"

launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "Installed and started com.tradelab.run"
echo "  Logs:   ${REPO_DIR}/tradelab_run.log  /  ${REPO_DIR}/tradelab_run.err.log"
echo "  Status: launchctl list | grep tradelab"
echo "  Stop:   launchctl unload ${PLIST_DST}"
echo "  Start:  launchctl load ${PLIST_DST}"
