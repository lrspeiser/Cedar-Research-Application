#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")"/.. && pwd)
cd "$ROOT_DIR"

# Install build deps (PyInstaller)
python3 -m pip install -U -r packaging/requirements-macos.txt

# Clean old artifacts
rm -rf build dist

# Load .env if present (export variables) without printing values
set +x
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Build the app bundle
python3 -m PyInstaller --clean packaging/cedarpy.spec

# If an .env exists, copy it into the app Resources so the app can load it at runtime
if [ -f .env ] && [ -d dist/CedarPy.app/Contents/Resources ]; then
  cp .env dist/CedarPy.app/Contents/Resources/.env
fi

# Create a DMG with the .app bundle at root
mkdir -p dist
DMG_PATH="dist/CedarPy.dmg"
hdiutil create -volname "CedarPy" -srcfolder dist/CedarPy.app -ov -format UDZO "$DMG_PATH"

echo "DMG created: $DMG_PATH"
