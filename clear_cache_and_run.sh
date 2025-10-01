#!/bin/bash
#
# Clear Python bytecode cache and start CedarPy backend
# This prevents stale .pyc files from causing issues during development
#

echo "🧹 Clearing Python bytecode cache..."

# Clear __pycache__ directories
find /Users/leonardspeiser/Projects/cedarpy -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Clear .pyc files
find /Users/leonardspeiser/Projects/cedarpy -type f -name "*.pyc" -delete 2>/dev/null || true

echo "✅ Cache cleared"
echo ""
echo "🚀 Starting CedarPy backend..."
echo ""

# Set environment variable to prevent writing .pyc files in dev mode
export PYTHONDONTWRITEBYTECODE=1

# Run the backend
cd /Users/leonardspeiser/Projects/cedarpy
python main.py
