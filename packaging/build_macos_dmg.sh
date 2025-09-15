#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")"/.. && pwd)
cd "$ROOT_DIR"

# Install build deps (PyInstaller)
python3 -m pip install -U -r packaging/requirements-macos.txt

# Clean old artifacts
rm -rf build dist

# Build the app bundle
python3 -m PyInstaller --clean packaging/cedarpy.spec

# Create a DMG with the .app bundle at root
mkdir -p dist
DMG_PATH="dist/CedarPy.dmg"
hdiutil create -volname "CedarPy" -srcfolder dist/CedarPy.app -ov -format UDZO "$DMG_PATH"

echo "DMG created: $DMG_PATH"
