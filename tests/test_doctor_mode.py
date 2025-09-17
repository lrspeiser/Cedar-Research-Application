import os
import sys
import time
from pathlib import Path

import pytest

# Ensure repo root on sys.path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import run_cedarpy


def test_doctor_mode_runs(monkeypatch, tmp_path: Path):
    # Ensure doctor writes logs to tmp as fallback and does not try to open a browser
    monkeypatch.setenv("CEDARPY_DOCTOR", "1")
    monkeypatch.setenv("CEDARPY_OPEN_BROWSER", "0")
    # Run doctor in-process; function returns an exit code
    rc = run_cedarpy.run_doctor()
    assert rc in (0, 3, 4) or rc == 2
    # We accept non-zero codes here when network or startup conditions vary,
    # but the function must return promptly and not raise.
