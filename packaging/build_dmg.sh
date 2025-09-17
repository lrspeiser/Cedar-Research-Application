#!/usr/bin/env bash
set -euo pipefail

# Build a macOS DMG containing a self-contained cedarpy server binary and a wrapper app/command.
# Requirements: python3, virtualenv, pyinstaller, osacompile (built-in), hdiutil (built-in)

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT_DIR/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"
DIST="$ROOT_DIR/dist"
BUILD="$ROOT_DIR/build"
APP_NAME="CedarPy"
BINARY_NAME="cedarpy"
DMG_NAME="${APP_NAME}-macOS.dmg"

mkdir -p "$DIST" "$BUILD"

if [ ! -x "$PY" ]; then
  echo "Creating venv at $VENV"
  python3 -m venv "$VENV"
fi

"$PIP" install --upgrade pip >/dev/null
"$PIP" install -r "$ROOT_DIR/requirements.txt" >/dev/null
"$PIP" install pyinstaller >/dev/null

# 1) Build a macOS .app bundle (single item)
rm -rf "$DIST" "$BUILD"
pushd "$ROOT_DIR" >/dev/null
"$VENV/bin/pyinstaller" \
  --clean \
--onefile \
  --windowed \
  --name "$APP_NAME" \
  --distpath "$ROOT_DIR/dist" \
  --workpath "$BUILD" \
  --specpath "$BUILD" \
  --hidden-import main \
  --hidden-import main_mini \
  --add-data "$ROOT_DIR/main.py:." \
  --add-data "$ROOT_DIR/main_mini.py:." \
  run_cedarpy.py
popd >/dev/null

# 2) Stage only the .app into the DMG content
STAGE="$ROOT_DIR/.dmg_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$ROOT_DIR/dist/${APP_NAME}.app" "$STAGE/${APP_NAME}.app"

# 3) Build the DMG with just the .app
DMG_PATH="$ROOT_DIR/$DMG_NAME"
rm -f "$DMG_PATH"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG_PATH"

echo "Built DMG: $DMG_PATH"
exit 0

# Legacy code below (kept for reference, no longer used)

# 2) Create a .command that opens Terminal and runs the server
cat > "$STAGE/Run ${APP_NAME}.command" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Stop any existing running instance
if command -v pkill >/dev/null 2>&1; then
  pkill -f "$HOME/CedarPyApp/bin/cedarpy" || pkill -x cedarpy || true
else
  pids=$(pgrep -f "$HOME/CedarPyApp/bin/cedarpy" || true)
  if [ -n "$pids" ]; then kill $pids || true; fi
fi
sleep 0.5
# Use a writable uploads directory outside the read-only DMG by default
export CEDARPY_UPLOAD_DIR="${CEDARPY_UPLOAD_DIR:-$HOME/CedarPyUploads}"
# Default-on Shell API in DMG build; override by unsetting or setting to 0 before launch
export CEDARPY_SHELL_API_ENABLED="${CEDARPY_SHELL_API_ENABLED:-1}"
mkdir -p "$CEDARPY_UPLOAD_DIR"
# Copy the binary off the (possibly noexec) DMG and run from user directory
DEST="$HOME/CedarPyApp/bin"
mkdir -p "$DEST"
cp -f ./cedarpy "$DEST/cedarpy"
chmod +x "$DEST/cedarpy"
exec "$DEST/cedarpy"
EOS
chmod +x "$STAGE/Run ${APP_NAME}.command"

# 3) Create a minimal .app that opens Terminal and runs the server next to it
#    This is a convenience wrapper so users can double-click the app icon.
OSA_SRC="$BUILD/${APP_NAME}.applescript"
cat > "$OSA_SRC" <<'EOF'
on run
  set appPath to (path to me as alias)
  set dirPath to do shell script "dirname " & quoted form of POSIX path of appPath
  tell application "Terminal"
    do script "export CEDARPY_SHELL_API_ENABLED=\"1\"; export CEDARPY_UPLOAD_DIR=\"$HOME/CedarPyUploads\"; mkdir -p \"$HOME/CedarPyUploads\"; pkill -f \"$HOME/CedarPyApp/bin/cedarpy\" || pkill -x cedarpy || true; sleep 0.5; cd " & quoted form of dirPath & " && DEST=\"$HOME/CedarPyApp/bin\"; mkdir -p \"$HOME/CedarPyApp/bin\"; cp -f ./cedarpy \"$HOME/CedarPyApp/bin/cedarpy\"; chmod +x \"$HOME/CedarPyApp/bin/cedarpy\"; \"$HOME/CedarPyApp/bin/cedarpy\""
    activate
  end tell
end run
EOF

osacompile -o "$STAGE/${APP_NAME}.app" "$OSA_SRC"

# 4) Add a short README for end users
cat > "$STAGE/README-FIRST.txt" <<'EOF'
CedarPy – FastAPI + MySQL prototype

How to run:
1) Double-click "CedarPy.app" (or "Run CedarPy.command"). A Terminal window will open and start the server.
2) Your browser should open to http://127.0.0.1:8000 automatically. If not, open it manually.

Environment variables (optional):
- CEDARPY_MYSQL_URL: SQLAlchemy DSN, e.g. mysql+pymysql://user:pass@host/cedarpython
- CEDARPY_UPLOAD_DIR: Directory for uploaded files (defaults to ./user_uploads next to the running process)

Note: You must have access to a MySQL instance and database. See the repository README for the schema quickstart.
EOF

# 5) Build the DMG
DMG_PATH="$ROOT_DIR/$DMG_NAME"
rm -f "$DMG_PATH"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG_PATH"

echo "Built DMG: $DMG_PATH"