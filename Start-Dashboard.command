#!/usr/bin/env bash
# TradeLab one-click launcher for Mac.
# Double-click this file in Finder to set everything up and open the
# dashboard in your browser — no terminal typing required.
#
# First time you double-click it, macOS may warn "unidentified developer" —
# right-click the file instead and choose "Open" to bypass that once.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python is not installed."
    echo "Install it from https://www.python.org/downloads/ then run this again."
    read -rp "Press Enter to close..." _
    exit 1
fi

if [[ ! -d .venv ]]; then
    echo "Setting up TradeLab (first run only, takes a minute)..."
    python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

echo "Installing/updating dependencies (first run may take a few minutes)..."
pip install -q -r requirements.txt

if [[ ! -f .env ]]; then
    echo ""
    echo "First-time setup: paste your Alpaca PAPER trading keys below."
    echo "(Get them from https://app.alpaca.markets/paper/dashboard/overview)"
    read -rp "Alpaca API Key: " api_key
    read -rsp "Alpaca Secret Key: " secret_key
    echo ""
    cat > .env <<ENV_EOF
ALPACA_API_KEY=${api_key}
ALPACA_SECRET_KEY=${secret_key}
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets
DATABASE_URL=sqlite:///tradelab.db
ENV_EOF
    echo "Saved .env"
fi

echo ""
echo "Starting TradeLab dashboard — your browser will open automatically."
echo "Close this window or press Ctrl+C to stop."
echo ""
python -m tradelab.main web

read -rp "Press Enter to close..." _
