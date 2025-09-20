# CI and Packaging Guide

This guide documents the CI layout, the macOS DMG packaging process, the pitfalls we hit, and the durable fixes. Keep it close when editing workflows or packaging.

Last updated: 2025-09-20

## CI layout (parallel jobs)
- Lint (ruff) → Compile (syntax) → Parallel tests:
  - Backend core (fast, no WS/UI)
  - Websocket (non‑LLM)
  - LLM backend (real API)
  - Playwright (browser UI)
  - Embedded Qt UI (macOS headless)
- Build DMG (macOS)
- Tests — Packaged Qt DMG (macOS): mount, launch, verify HTTP, then Playwright smoke

## Workflow files
- Branch builds (with paths filter): `.github/workflows/macos-dmg.yml`
- Tag builds (v*): `.github/workflows/macos-dmg-release.yml`
  - Note: tags must be nested under `on.push.tags`. Paths filters can suppress tag runs; splitting avoids surprises.

## Environment for UI/Qt tests
- Common
  - `PYTHONUNBUFFERED=1`
  - For LLM tests: `OPENAI_API_KEY` and/or `CEDARPY_OPENAI_API_KEY` via GitHub Secrets
  - `CEDARPY_TEST_LLM_READY=1` (real LLM in CI; no stubs)
- Embedded Qt
  - `CEDARPY_QT_HEADLESS=1`
  - `CEDARPY_OPEN_BROWSER=0`
  - `QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"`
  - `QTWEBENGINE_DISABLE_SANDBOX=1`
- Packaged Qt DMG smoke
  - `CEDARPY_ALLOW_MULTI=1` to skip single-instance locking in CI

## Packaged-app smoke (DMG)
- Mount the DMG, find the .app, launch its binary, and curl the root until ready.
- Critical details
  - Use `ls -d mnt/*.app` (flags before operands on macOS/BSD).
  - If not found: print `ls -la mnt` and `hdiutil info` to aid debugging.
  - Wait loop 60s: curl `http://127.0.0.1:$PORT/`.
  - Always tail `app.log` on failure; upload it as an artifact.

## PyInstaller (macOS Qt)
- Use `pyinstaller-hooks-contrib` to ensure Qt hooks run.
- PySide6 handling
  - Include `PySide6` as a hidden import so `import PySide6` works.
  - Avoid collecting the entire package with `collect_all('PySide6')` as it can drag in frameworks that collide in COLLECT.
- Qt3D collisions
  - Error observed: `FileExistsError: [Errno 17] ... Qt3DAnimation.framework/Resources` during COLLECT.
  - Fix: add excludes for `PySide6.Qt3D*` in the spec and filter any `Qt3D` entries from `datas`/`binaries` before `Analysis`.
- Spec vs CLI
  - When building with a `.spec`, do not pass makespec-only CLI options like `--exclude-module`. PyInstaller will fail with: "makespec options not valid when a .spec file is given".
  - Put all excludes and collection policy in the `.spec`.

## Playwright artifacts (v4 uploader)
- Do not upload into the same artifact name from multiple jobs; actions/upload-artifact@v4 will 409 conflict.
- Use unique names per job, e.g., `test-artifacts-playwright-linux` and `test-artifacts-playwright-macos`.

## Common failures and fixes
- requirements.txt missing in packaged DMG job
  - Cause: running tests without `actions/checkout` and `actions/setup-python`.
  - Fix: add checkout + Python 3.11 setup before pip install & tests.
- awk failure on missing `pytest-stdout.txt`
  - Fix: guard the summary step; if the file is missing, default counts to 0 / `n/a`.
- LLM chat/test timeouts
  - Ensure API keys are present; keep verbose logs. If needed, temporarily increase `httpx` timeouts in tests.

## API keys (OpenAI)
- CI uses GitHub Secrets `OPENAI_API_KEY` or `CEDARPY_OPENAI_API_KEY`.
- Never print secrets; logs must mask them.
- Packaged apps: place keys in `~/CedarPyData/.env` as `OPENAI_API_KEY` or `CEDARPY_OPENAI_API_KEY`. See README “LLM classification on file upload”.

## Verification checklist before shipping DMG
- CI green on: backend core, websocket (non‑LLM), LLM backend, Playwright UI, Embedded Qt.
- DMG job mounts, launches, responds to HTTP.
- App log artifact present and clean of startup errors.
- DMG artifact named `CedarPy-qt.dmg` attached (or downloadable via GH CLI).

## References
- CI run that validated these fixes: 17882249523 (all jobs success; DMG produced ~238 MB)
- See `CHANGELOG.md` entry 2025-09-20 for a narrative of issues and exact fixes.
