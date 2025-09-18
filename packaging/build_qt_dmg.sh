#!/usr/bin/env bash
set -euo pipefail

# Build the official macOS DMG for CedarPy with a Dock icon and standard Quit behavior.
# WHY: The Qt build shows a Dock icon (no LSUIElement), provides a normal app menu, and supports Cmd-Q/quit from Dock.
# This is the REQUIRED build for user-facing distribution so the app can be exited cleanly.

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
# Optionally enable default tracing for diagnostics in this build
if [ "${CEDARPY_TRACE_DEFAULT:-}" = "1" ]; then
  echo "CEDARPY_TRACE=1" >> "$RES_DIR/.env"
  echo "[build] Enabled default trace logging (CEDARPY_TRACE=1) in app Resources/.env for this build"
fi
# Add a DEBUG-FIRST guide inside the app Resources
cat > "$RES_DIR/DEBUG-FIRST.txt" <<'EOF'
CedarPy – Debugging First Steps

This build includes enhanced tracing and diagnostics.

Tracing (imports + actions)
- Tracing is controlled by the environment variable CEDARPY_TRACE.
- In this build, tracing may be enabled by default if the packager set CEDARPY_TRACE_DEFAULT=1.
- You can toggle it by editing CedarPy.app/Contents/Resources/.env and setting:
    CEDARPY_TRACE=1   # enable
    # or remove/comment the line to disable

Where to find logs
- Qt shell logs:    ~/Library/Logs/CedarPy/cedarqt_*.log
- Server logs:      ~/Library/Logs/CedarPy/cedarpy_*.log
- Shell API logs:   ~/CedarPyData/logs/shell/*.log

Common recovery steps
- If the server fails to start:
  1) tail the latest cedarqt_*.log and cedarpy_*.log to see errors
  2) remove stale lock if present: rm -f ~/Library/Logs/CedarPy/cedarqt.lock
  3) ensure port 8000 is free or change CEDARPY_PORT

Quiting the app
- This build shows a Dock icon and supports Cmd-Q / Quit from the Dock.

EOF

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
