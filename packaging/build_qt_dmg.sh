#!/usr/bin/env bash
set -euo pipefail

# Build a Qt-embedded CedarPy.app (PyInstaller spec) and wrap it into a DMG.
# This build shows a Dock icon (no LSUIElement), launches cedarqt.py, and embeds the browser.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
PKG_DIR="$ROOT_DIR/packaging"
OUT_DIR="$PKG_DIR/dist-qt"
APP_NAME="CedarPy.app"
DMG_PATH="$OUT_DIR/CedarPy-qt.dmg"

mkdir -p "$OUT_DIR"

# Clean old outputs
rm -rf "$DIST_DIR/$APP_NAME" "$DMG_PATH" "$ROOT_DIR/build" "$DIST_DIR" 2>/dev/null || true

# Ensure PyInstaller is available
python3 -m pip install -q --upgrade pip wheel
python3 -m pip install -q pyinstaller

# Build the Qt app from the PyInstaller spec that launches cedarqt.py
# Important: run from repo root so spec's repo_root points here.
(
  cd "$ROOT_DIR" && \
  pyinstaller --noconfirm --clean "$PKG_DIR/cedarpy.spec"
)

if [ ! -d "$DIST_DIR/$APP_NAME" ]; then
  echo "ERROR: Build failed; $DIST_DIR/$APP_NAME not found" >&2
  exit 2
fi

# Bundle user's .env into app Resources so first-run seeding works
RES_DIR="$DIST_DIR/$APP_NAME/Contents/Resources"
mkdir -p "$RES_DIR"
if [ -f "$HOME/CedarPyData/.env" ]; then
  cp -f "$HOME/CedarPyData/.env" "$RES_DIR/.env"
  echo "[build] Bundled ~/CedarPyData/.env into app Resources (keys masked):"
  { grep -E '^(OPENAI_API_KEY|CEDARPY_OPENAI_API_KEY)=' "$RES_DIR/.env" || echo "  (no OpenAI keys found)"; } | sed -E 's/(OPENAI_API_KEY|CEDARPY_OPENAI_API_KEY)=.*/\1=***MASKED***/'
else
  echo "[build] WARNING: ~/CedarPyData/.env not found; creating an empty one in app Resources" >&2
  touch "$RES_DIR/.env"
fi

# Stage and create DMG
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
cp -R "$DIST_DIR/$APP_NAME" "$TMP_DIR/"
ln -s /Applications "$TMP_DIR/Applications"

hdiutil create -volname "CedarPy" -srcfolder "$TMP_DIR" -ov -format UDZO "$DMG_PATH"

SZ=$(du -h "$DMG_PATH" | cut -f1)
echo "========================================="
echo "Qt app build completed"
echo "DMG: $DMG_PATH"
echo "Size: $SZ"
echo "Install: open \"$DMG_PATH\" and drag CedarPy.app to Applications"
echo "========================================="
