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

# Optional CI gating
# - Set CEDARPY_SKIP_CI_CHECK=1 to skip gating
# - Set CEDARPY_REQUIRE_CI=1 to fail if gating cannot be performed
# - Set CEDARPY_CI_BRANCH to override branch (default: main)
# - Set CEDARPY_GITHUB_REPO (owner/repo) to override repo autodetection
ci_gate() {
  if [ "${CEDARPY_SKIP_CI_CHECK:-}" = "1" ]; then
    echo "[ci] Skipping CI gating via CEDARPY_SKIP_CI_CHECK=1"
    return 0
  fi
  BRANCH="${CEDARPY_CI_BRANCH:-main}"
  WFLOW_NAME="${CEDARPY_CI_WORKFLOW:-CI}"
  # Derive repo from git remote if not provided
  ORIGIN_URL=$(git -C "$ROOT_DIR" remote get-url origin 2>/dev/null || true)
  REPO_GUESS=$(printf "%s" "$ORIGIN_URL" | sed -E 's#.*github.com[:/]+([^/]+)/([^/]+)(\.git)?$#\1/\2#')
  REPO="${CEDARPY_GITHUB_REPO:-$REPO_GUESS}"
  if [ -z "$REPO" ]; then
    if [ "${CEDARPY_REQUIRE_CI:-}" = "1" ]; then
      echo "[ci] ERROR: Could not determine GitHub repo and CEDARPY_REQUIRE_CI=1 set; aborting" >&2
      exit 3
    else
      echo "[ci] WARNING: Could not determine GitHub repo; proceeding without CI gating" >&2
      return 0
    fi
  fi
  echo "[ci] Gating on latest run for $REPO (branch=$BRANCH, workflow=$WFLOW_NAME)"
  if command -v gh >/dev/null 2>&1; then
    # Use GitHub CLI, constrain by workflow name
    RUN_ID=$(gh run list --repo "$REPO" --workflow "$WFLOW_NAME" --branch "$BRANCH" --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)
    if [ -z "$RUN_ID" ]; then
      if [ "${CEDARPY_REQUIRE_CI:-}" = "1" ]; then
        echo "[ci] ERROR: No recent runs found for $REPO#$BRANCH; aborting" >&2
        exit 3
      else
        echo "[ci] WARNING: No recent runs found for $REPO#$BRANCH; proceeding"
        return 0
      fi
    fi
    echo "[ci] Waiting for run $RUN_ID to complete..."
    if ! gh run watch "$RUN_ID" --repo "$REPO" --exit-status; then
      echo "[ci] ERROR: GitHub run failed (run_id=$RUN_ID)" >&2
      exit 3
    fi
    echo "[ci] Run $RUN_ID succeeded. Proceeding with build."
  else
    # Fallback to REST API via curl; requires GITHUB_TOKEN
    if [ -z "${GITHUB_TOKEN:-}" ]; then
      if [ "${CEDARPY_REQUIRE_CI:-}" = "1" ]; then
        echo "[ci] ERROR: gh not found and GITHUB_TOKEN not set; aborting due to CEDARPY_REQUIRE_CI=1" >&2
        exit 3
      else
        echo "[ci] WARNING: gh not found and GITHUB_TOKEN not set; proceeding without CI gating" >&2
        return 0
      fi
    fi
    echo "[ci] Using GitHub REST API for $REPO (branch=$BRANCH, workflow=$WFLOW_NAME)"
    # Resolve workflow id by name
    WF_RESP=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" "https://api.github.com/repos/$REPO/actions/workflows")
    WF_ID=$(printf "%s" "$WF_RESP" | python3 - <<'PY'
import sys,json
w=json.load(sys.stdin).get('workflows') or []
name = __import__('os').environ.get('WFLOW_NAME')
for wf in w:
    if wf.get('name')==name or wf.get('path','').endswith(name):
        print(wf.get('id'))
        break
PY
)
    if [ -z "$WF_ID" ]; then
      echo "[ci] ERROR: Could not resolve workflow id for '$WFLOW_NAME'" >&2
      exit 3
    fi
    # Poll until status=completed, then require conclusion=success
    ATTEMPTS=0
    MAX_ATTEMPTS=120 # ~10 minutes at 5s intervals
    while :; do
      RESP=$(curl -s \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/$REPO/actions/workflows/$WF_ID/runs?branch=$BRANCH&per_page=1")
      STATUS=$(printf "%s" "$RESP" | python3 -c 'import sys,json; d=json.load(sys.stdin); r=d.get("workflow_runs",[{"status":"","conclusion":"","id":None}])[0]; print(r.get("status",""))' 2>/dev/null || true)
      CONCL=$(printf "%s" "$RESP" | python3 -c 'import sys,json; d=json.load(sys.stdin); r=d.get("workflow_runs",[{"status":"","conclusion":"","id":None}])[0]; print(r.get("conclusion",""))' 2>/dev/null || true)
      if [ "$STATUS" = "completed" ]; then
        if [ "$CONCL" = "success" ]; then
          echo "[ci] Latest run succeeded. Proceeding with build."
          break
        else
          echo "[ci] ERROR: Latest run concluded '$CONCL'" >&2
          exit 3
        fi
      fi
      ATTEMPTS=$((ATTEMPTS+1))
      if [ $ATTEMPTS -ge $MAX_ATTEMPTS ]; then
        echo "[ci] ERROR: Timed out waiting for run completion" >&2
        exit 3
      fi
      sleep 5
    done
  fi
}

mkdir -p "$OUT_DIR"

# Gate on CI before doing heavy work
ci_gate

# Clean old outputs
rm -rf "$DIST_DIR/$APP_NAME" "$DMG_PATH" "$ROOT_DIR/build" "$DIST_DIR" 2>/dev/null || true

# Ensure PyInstaller and app dependencies are available
python3 -m pip install -q --upgrade pip wheel
# Install application requirements (PySide6, FastAPI, etc.) if present
if [ -f "$ROOT_DIR/requirements.txt" ]; then
  python3 -m pip install -q -r "$ROOT_DIR/requirements.txt"
fi
if [ -f "$PKG_DIR/requirements-macos.txt" ]; then
  python3 -m pip install -q -r "$PKG_DIR/requirements-macos.txt"
fi
python3 -m pip install -q pyinstaller pyinstaller-hooks-contrib

# Build the Qt app from the PyInstaller spec that launches cedarqt.py
# Important: run from repo root so spec's repo_root points here.
(
  cd "$ROOT_DIR" && \
  pyinstaller --noconfirm --clean \
    --exclude-module PySide6.Qt3DCore \
    --exclude-module PySide6.Qt3DAnimation \
    --exclude-module PySide6.Qt3DRender \
    --exclude-module PySide6.Qt3DInput \
    --exclude-module PySide6.Qt3DExtras \
    "$PKG_DIR/cedarpy.spec"
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
