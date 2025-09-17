#!/bin/bash

# Build a self-contained CedarPy.app by embedding a Python venv and sources (no PyInstaller), then pack a DMG.
# This avoids PyInstaller bootloader and signing complexities.
# The app binary is a tiny launcher that runs the embedded Python.

set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="CedarPy"
BUILD_DIR="$PROJ_ROOT/packaging/build-embedded"
APP_DIR="$BUILD_DIR/$APP_NAME.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"
FRAMEWORKS="$CONTENTS/Frameworks"
VENV_DIR="$FRAMEWORKS/venv"
PY="$VENV_DIR/bin/python3"

rm -rf "$BUILD_DIR"
mkdir -p "$MACOS" "$RES" "$FRAMEWORKS"

# 1) Create embedded venv and install runtime deps
python3 -m venv "$VENV_DIR"
"$PY" -m pip install --upgrade pip wheel
"$PY" -m pip install -r "$PROJ_ROOT/packaging/requirements-app.txt"

# 2) Copy application sources into Resources
cp "$PROJ_ROOT/main.py" "$RES/main.py"
# IMPORTANT: Do not remove this copy; mini module is required for minimal launches and fallback.
# See README postmortem for rationale.
cp "$PROJ_ROOT/main_mini.py" "$RES/main_mini.py"
cp "$PROJ_ROOT/run_cedarpy.py" "$RES/run_cedarpy.py"
cp "$PROJ_ROOT/PROJECT_SEPARATION_README.md" "$RES/PROJECT_SEPARATION_README.md" || true
cp "$PROJ_ROOT/BRANCH_SQL_POLICY.md" "$RES/BRANCH_SQL_POLICY.md" || true
# Include .env into Resources preferring project .env, then user data .env (keys masked)
PROJ_ENV="$PROJ_ROOT/.env"
USER_ENV="$HOME/CedarPyData/.env"
if [ -f "$PROJ_ENV" ]; then
  cp -f "$PROJ_ENV" "$RES/.env"
  echo "[build] Bundled project .env into embedded app Resources (keys masked):"
  { grep -E '^(OPENAI_API_KEY|CEDARPY_OPENAI_API_KEY)=' "$RES/.env" || echo "  (no OpenAI keys found)"; } | sed -E 's/(OPENAI_API_KEY|CEDARPY_OPENAI_API_KEY)=.*/\1=***MASKED***/'
elif [ -f "$USER_ENV" ]; then
  cp -f "$USER_ENV" "$RES/.env"
  echo "[build] Bundled user data .env into embedded app Resources (keys masked):"
  { grep -E '^(OPENAI_API_KEY|CEDARPY_OPENAI_API_KEY)=' "$RES/.env" || echo "  (no OpenAI keys found)"; } | sed -E 's/(OPENAI_API_KEY|CEDARPY_OPENAI_API_KEY)=.*/\1=***MASKED***/'
else
  echo "[build] WARNING: No .env found in project or user data; creating empty Resources/.env" >&2
  : > "$RES/.env"
fi

# 3) Create launcher that runs the embedded python
cat > "$MACOS/$APP_NAME" << 'SH'
#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HERE/../Frameworks/venv"
PY="$VENV/bin/python3"
# Redirect stdout/stderr to user logs dir like before
LOG_DIR="$HOME/Library/Logs/CedarPy"
mkdir -p "$LOG_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG_FILE="$LOG_DIR/cedarpy_${TS}.log"
exec >>"$LOG_FILE" 2>&1

# Make sure we default data dir to a writable location
export CEDARPY_DATA_DIR="$HOME/CedarPyData"
# Default host to 127.0.0.1 and port 8000 unless overridden
export CEDARPY_HOST="0.0.0.0"
export CEDARPY_PORT="8000"
export CEDARPY_OPEN_BROWSER="1"

# Run the launcher script using embedded python
exec "$PY" "$HERE/../Resources/run_cedarpy.py"
SH
chmod +x "$MACOS/$APP_NAME"

# 4) Info.plist
cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>CedarPy</string>
    <key>CFBundleDisplayName</key><string>CedarPy</string>
    <key>CFBundleIdentifier</key><string>is.grue.cedarpy</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundleShortVersionString</key><string>1.0.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSUIElement</key><true/>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>CFBundleExecutable</key><string>CedarPy</string>
</dict>
</plist>
PLIST

# 5) Create DMG
DMG_DIR="$PROJ_ROOT/packaging/dist-embedded"
DMG_PATH="$DMG_DIR/$APP_NAME-embedded.dmg"
rm -rf "$DMG_DIR"
mkdir -p "$DMG_DIR"

TEMP_DIR="$(mktemp -d)"
trap "rm -rf $TEMP_DIR" EXIT
cp -R "$APP_DIR" "$TEMP_DIR/"
ln -s /Applications "$TEMP_DIR/Applications"

hdiutil create -volname "$APP_NAME" -srcfolder "$TEMP_DIR" -ov -format UDZO "$DMG_PATH"

SZ=$(du -h "$DMG_PATH" | cut -f1)
cat <<MSG
=========================================
Embedded app build completed
DMG: $DMG_PATH
Size: $SZ
To install: open "$DMG_PATH" and drag $APP_NAME.app to Applications
Then open $APP_NAME.app and visit http://127.0.0.1:8000/
Logs: ~/Library/Logs/CedarPy
=========================================
MSG
