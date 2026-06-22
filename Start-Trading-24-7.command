#!/usr/bin/env bash
# TradeLab one-click background trading setup for Mac.
# Double-click this file ONCE in Finder. It sets everything up (if needed)
# and installs the trading loop as a background service that keeps running
# even after you close this window, log out, or restart your Mac.
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
./scripts/install_launchd.sh

echo ""
echo "All set — TradeLab now trades in the background automatically."
echo "Double-click Start-Dashboard.command anytime to see the leaderboard and your account."
read -rp "Press Enter to close..." _
