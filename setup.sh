#!/bin/bash
# BTManager-v2 Quick Setup
# Run: bash setup.sh

set -e

echo "═══════════════════════════════════════"
echo "  BTManager-v2 Setup"
echo "═══════════════════════════════════════"

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating venv..."
source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

