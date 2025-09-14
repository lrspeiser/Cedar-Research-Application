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
- The app is unsigned; macOS Gatekeeper may require right-click → Open.
- The server needs a reachable MySQL database. Set CEDARPY_MYSQL_URL appropriately before running.