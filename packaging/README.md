# Packaging CedarPy for macOS (DMG)

This builds a distributable DMG for macOS that contains:
- cedarpy (self-contained binary via PyInstaller)
- CedarPy.app (wrapper that opens Terminal and runs the server)
- Run CedarPy.command (double-click to run in Terminal)
- README-FIRST.txt

Build:
```bash
bash packaging/build_dmg.sh
```
Output: CedarPy-macOS.dmg at the repo root.

Notes:
- The app is unsigned; macOS Gatekeeper may require right-click  Open.
- The app defaults to SQLite at ~/CedarPyData/cedarpy.db if no DB URL is set. For MySQL, set CEDARPY_DATABASE_URL or CEDARPY_MYSQL_URL.
- The launcher defaults CEDARPY_UPLOAD_DIR to ~/CedarPyUploads to avoid DMG read-only issues.
- To avoid macOS mounting some DMGs with noexec, the launcher copies the binary to $HOME/CedarPyApp/bin and runs it from there.
- Shell API is ENABLED by default in the DMG launcher (sets CEDARPY_SHELL_API_ENABLED=1). Optionally set CEDARPY_SHELL_API_TOKEN for API access; if unset, API is local-only.

.env usage (API keys):
- If a .env file exists in the repo root when building, the build script will source it for the build and copy it into CedarPy.app/Contents/Resources/.env.
- At runtime, the app will load .env from (in order):
  1) current working directory
  2) ~/CedarPyData/.env (DATA_DIR)
  3) the app’s Resources/.env (inside the .app bundle)
- Place CEDARPY_OPENAI_API_KEY or OPENAI_API_KEY in .env to enable LLM features. See README for setup. Do not print secrets to the console.
