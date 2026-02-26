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

echo ""
echo "═══════════════════════════════════════"
echo "  Setup complete!"
echo "═══════════════════════════════════════"
echo ""
echo "To run:"
echo "  source venv/bin/activate"
echo "  python main.py"
echo ""
echo "To test connection first:"
echo "  python test_client.py"
echo "  python test_client.py --address YOUR_SS58_ADDRESS"
echo ""
