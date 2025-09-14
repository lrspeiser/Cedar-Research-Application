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

# 1) Build a one-file CLI binary that runs the server
rm -rf "$DIST" "$BUILD"
pyinstaller \
  --clean \
  --onefile \
  --name "$BINARY_NAME" \
  "$ROOT_DIR/run_cedarpy.py"

# Copy artifacts into a staging dir for the DMG
STAGE="$ROOT_DIR/.dmg_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp "$ROOT_DIR/dist/$BINARY_NAME" "$STAGE/$BINARY_NAME"

# 2) Create a .command that opens Terminal and runs the server
cat > "$STAGE/Run ${APP_NAME}.command" <<'EOS'
#!/usr/bin/env bash
cd "$(dirname "$0")"
chmod +x ./cedarpy
./cedarpy
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
    do script "cd " & quoted form of dirPath & " && chmod +x ./cedarpy && ./cedarpy"
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