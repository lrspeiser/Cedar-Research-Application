import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.e2e
@pytest.mark.timeout(60)
@pytest.mark.skipif(os.getenv("CI", "").lower() == "true", reason="Skip stale lock test on CI without Qt runtime")
def test_qt_stale_lock_recovery(tmp_path: Path):
    # Use a temporary log dir for isolation
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    lock_path = log_dir / "cedarqt.lock"

    # Create a stale lock with a non-existent PID
    lock_path.write_text("999999\n", encoding="utf-8")

    env = os.environ.copy()
    env["CEDARPY_LOG_DIR"] = str(log_dir)
    env["CEDARPY_QT_HEADLESS"] = "1"
    env["CEDARPY_OPEN_BROWSER"] = "0"
    env["CEDARPY_ALLOW_MULTI"] = "0"  # enable lock logic

    # Launch cedarqt and give it a moment to start
    proc = subprocess.Popen([sys.executable, "cedarqt.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    try:
        # Wait up to 20s for log file creation
        deadline = time.time() + 20
        log_file = None
        while time.time() < deadline and log_file is None:
            candidates = sorted(log_dir.glob("cedarqt_*.log"))
            if candidates:
                log_file = candidates[-1]
                break
            time.sleep(0.2)
        assert log_file is not None, "cedarqt log not created"

        # Read log and look for stale lock removal message
        content = log_file.read_text(encoding="utf-8", errors="ignore")
        assert "removed stale lock" in content, f"Expected stale lock removal; log was:\n{content}"
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
