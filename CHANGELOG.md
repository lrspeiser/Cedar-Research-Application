# Changelog

All notable changes to this project will be documented in this file.

## 2025-09-20 — CI stabilization and macOS DMG packaging fixes

Summary: Stabilized the CI pipeline by splitting workflows, fixing artifact collisions, hardening the packaged-app smoke test, and resolving PyInstaller/Qt framework issues. Result: full CI green including the “Tests — Packaged Qt DMG (macOS)” job and a downloadable DMG artifact.

Key commits
- CI (tests_qt_dmg): fix DMG mount script, guard when no app found — f555921
- Packaging (macOS DMG): ensure PySide6 in bundle, add hooks contrib — f299c18
- Workflows: split macOS DMG branch vs release; fix tags placement; exclude Qt3D — 13ced77
- Packaging (macOS): avoid Qt3D symlink collisions; spec-only excludes/filter — 941ae1b, 5152318
- CI: checkout+setup-python before Playwright tests; guard summary on missing pytest-stdout — b7e75f4
- CI: fix upload-artifact 409 by unique artifact names per job — e665f39

CI and workflow changes
- Split macOS DMG workflows (Option C best practice):
  - .github/workflows/macos-dmg.yml — branch-only with paths filter.
  - .github/workflows/macos-dmg-release.yml — tag-only (push.tags: [ 'v*' ]).
  - Why: tags must be nested under push; paths filters can suppress tag runs; splitting avoids surprises.
- Artifact name conflicts (409 Conflict) with actions/upload-artifact@v4:
  - Gave each job a unique artifact name (test-artifacts-playwright-linux, test-artifacts-playwright-macos).
  - Removed unsupported merge-multiple input.
- Tests — Packaged Qt DMG job:
  - Added checkout and setup-python before running tests to ensure requirements.txt exists and Python 3.11 is used.
  - Guarded summary parsing when pytest-stdout.txt is missing to avoid awk failures.
- Packaged app headless smoke test (mounts DMG and launches app):
  - Fixed ls option order (use `ls -d mnt/*.app`), added a guard to print mnt contents and hdiutil info if no .app found.

PyInstaller and Qt frameworks
- Initial packaged run failed: ModuleNotFoundError: PySide6.
  - Added pyinstaller-hooks-contrib so Qt hooks run.
  - Ensured top-level PySide6 hidden import is present.
- macOS frameworks collision: FileExistsError on Qt3D*.framework/Resources during COLLECT.
  - Added excludes for PySide6.Qt3D* in the spec and a defensive filter to drop any Qt3D entries from datas/binaries.
  - Important: do not pass makespec-only options like --exclude-module when building from a .spec (PyInstaller errors: "makespec options not valid when a .spec file is given"). All excludes live in the spec.

Embedded Qt headless test (CI)
- Original failure: UI-driven file chooser blocked in headless mode. Switched test to backend HTTP upload flow and increased httpx timeout from 10s to 120s to accommodate backend processing/LLM latency.
- Headless flags in CI: CEDARPY_QT_HEADLESS=1, CEDARPY_OPEN_BROWSER=0, QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu", QTWEBENGINE_DISABLE_SANDBOX=1.

OpenAI/LLM in CI
- Real API usage: tests set CEDARPY_TEST_LLM_READY=1 and use GitHub secrets OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY. Never print keys; logs mask them. See README “LLM classification on file upload” for setup.

Troubleshooting guide (quick)
- Packaged app fails to start, no logs:
  - Check app.log uploaded by the DMG test and ~/Library/Logs/CedarPy/cedarqt_*.log.
- DMG mount step fails to find app:
  - Ensure ls uses `-d` before pattern; print `ls -la mnt` and `hdiutil info` for context.
- PyInstaller error: "makespec options not valid when a .spec file is given":
  - Remove CLI options like --exclude-module when invoking with a .spec. Put excludes in the spec.
- PySide6 missing:
  - Ensure pyinstaller-hooks-contrib is installed and at least PySide6 is in hiddenimports.
- Qt3D symlink collision:
  - Exclude Qt3D modules in spec and filter any collected Qt3D entries from datas/binaries.
- Artifact upload 409:
  - Use unique artifact names per job with upload-artifact v4.
- Tests failing to install requirements (requirements.txt missing):
  - Add actions/checkout and actions/setup-python before installing.

Verification
- CI run 17882249523 completed successfully across all jobs (lint, compile, backend core, websocket non-LLM, LLM backend, Playwright UI, Embedded Qt, Build DMG, Tests — Packaged Qt DMG).
- DMG artifact produced: CedarPy-qt.dmg (~238 MB) and validated by launching headlessly in CI.

Notes for future changes
- When editing packaging/cedarpy.spec, keep Qt3D excludes and the PySide6 hidden import.
- When changing packaged launch script or environment variables, update the README sections and cross-referenced code comments.
- Any additional Playwright result uploads must use unique artifact names to avoid conflicts.
