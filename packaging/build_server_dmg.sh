#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")"/.. && pwd)
cd "$ROOT_DIR"

# Ensure PyInstaller installed
python3 -m pip install -U pyinstaller >/dev/null

# Clean old
rm -rf build dist 2>/dev/null || true

# Build server-only app
pyinstaller --clean packaging/cedarpy_server.spec

# Copy .env if present
if [ -f .env ] && [ -d dist/CedarPyServer.app/Contents/Resources ]; then
  cp .env dist/CedarPyServer.app/Contents/Resources/.env
fi

# Create DMG
mkdir -p dist
DMG_PATH="dist/CedarPyServer.dmg"
rm -f "$DMG_PATH"
hdiutil create -volname "CedarPyServer" -srcfolder dist/CedarPyServer.app -ov -format UDZO "$DMG_PATH"

echo "DMG created: $DMG_PATH"