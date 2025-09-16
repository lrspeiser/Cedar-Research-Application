import os
import sys
import importlib.util
import threading
import time
import webbrowser
import traceback
import re
from datetime import datetime

import uvicorn
import subprocess
import signal

LOG_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), "Library", "Logs", "CedarPy")

def _init_logging() -> str:
    log_dir = os.getenv("CEDARPY_LOG_DIR", LOG_DIR_DEFAULT)
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_path = os.path.join(log_dir, f"cedarpy_{ts}.log")
    # Redirect stdout/stderr to the log
    f = open(log_path, "a", buffering=1)
    sys.stdout = f
    sys.stderr = f
    print(f"[cedarpy] log_path={log_path}")
    return log_path


def _mask_dsn(url: str) -> str:
    try:
        return re.sub(r"(mysql\+pymysql://[^:@]+):([^@]*)@", r"\1:***@", url)
    except Exception:
        return url


# Initialize logging ASAP so import failures are captured
_log_path = _init_logging()
print(f"[cedarpy] sys.executable={sys.executable}")
print(f"[cedarpy] sys.frozen={getattr(sys, 'frozen', False)}")
print(f"[cedarpy] cwd={os.getcwd()}")
print(f"[cedarpy] _MEIPASS={getattr(sys, '_MEIPASS', None)}")

# Try to import the FastAPI app from main, with a fallback loader for PyInstaller bundles.
try:
    from main import app  # type: ignore
    print("[cedarpy] imported app from main")
except Exception:
    print("[cedarpy] direct import failed, attempting fallback load for main.py")
    base_dir = getattr(sys, "_MEIPASS", None)
    if not base_dir:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(__file__)
    resources_dir = os.path.abspath(os.path.join(os.path.dirname(base_dir), "Resources")) if base_dir else None
    # Try known locations
    candidates = [
        os.path.join(base_dir, "main.py") if base_dir else None,
        os.path.join(resources_dir, "main.py") if resources_dir and os.path.isdir(resources_dir) else None,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py")),
    ]
    candidates = [c for c in candidates if c]
    print("[cedarpy] search candidates:")
    for c in candidates:
        print(f"  - {c} exists={os.path.exists(c)}")
    app = None  # type: ignore
    last_err = None
    for candidate in candidates:
        try:
            if os.path.exists(candidate):
                spec = importlib.util.spec_from_file_location("main", candidate)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)  # type: ignore
                    spec.loader.exec_module(mod)  # type: ignore
                    app = getattr(mod, "app", None)  # type: ignore
                    if app is not None:
                        print(f"[cedarpy] loaded app from {candidate}")
                        break
        except Exception as e:
            last_err = e
            print("[cedarpy] load error:\n" + traceback.format_exc())
    if app is None:
        raise ModuleNotFoundError(f"Could not locate main.app in packaged bundle; last_err={last_err}")


def _kill_other_instances():
    try:
        own = os.getpid()
        out = subprocess.run(["/bin/ps", "-ax", "-o", "pid=,command="], capture_output=True, text=True)
        lines = out.stdout.strip().splitlines()
        patterns = ["CedarPy.app/Contents/MacOS/CedarPy", "/CedarPyApp/bin/cedarpy", "run_cedarpy.py"]
        for line in lines:
            parts = line.strip().split(None, 1)
            if not parts:
                continue
            try:
                pid = int(parts[0])
            except Exception:
                continue
            cmd = parts[1] if len(parts) > 1 else ""
            if pid == own:
                continue
            if any(pat in cmd for pat in patterns):
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
    except Exception:
        pass


def _choose_listen_port(host: str, desired: int) -> int:
    try:
        import socket as _s
        s = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        try:
            s.bind((host, desired))
            s.close()
            return desired
        except Exception:
            try:
                s.close()
            except Exception:
                pass
        s2 = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        s2.bind((host, 0))
        port = s2.getsockname()[1]
        s2.close()
        return int(port)
    except Exception:
        return desired


def main():
    log_path = _init_logging()
    print("[cedarpy] starting CedarPy ...")

    host = os.getenv("CEDARPY_HOST", "127.0.0.1")
    try:
        desired = int(os.getenv("CEDARPY_PORT", "8000"))
    except Exception:
        desired = 8000
    port = _choose_listen_port(host, desired)
    os.environ["CEDARPY_PORT"] = str(port)

    # Ensure single instance
    _kill_other_instances()

    # Default to SQLite in ~/CedarPyData if no DB URL is set, so the app runs offline.
    if not os.getenv("CEDARPY_DATABASE_URL") and not os.getenv("CEDARPY_MYSQL_URL"):
        home = os.path.expanduser("~")
        data_dir = os.environ.get("CEDARPY_DATA_DIR", os.path.join(home, "CedarPyData"))
        os.makedirs(data_dir, exist_ok=True)
        os.environ["CEDARPY_DATABASE_URL"] = f"sqlite:///{os.path.join(data_dir, 'cedarpy.db')}"
    print(f"[cedarpy] DB_URL={_mask_dsn(os.getenv('CEDARPY_DATABASE_URL') or os.getenv('CEDARPY_MYSQL_URL') or 'sqlite default')}")

    def open_browser():
        time.sleep(1.5)
        try:
            browse_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
            eff_port = os.getenv("CEDARPY_PORT", str(port))
            print(f"[cedarpy] opening browser at http://{browse_host}:{eff_port} (bound on {host})")
            webbrowser.open(f"http://{browse_host}:{eff_port}")
        except Exception:
            pass

    if os.getenv("CEDARPY_OPEN_BROWSER", "1") == "1":
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        print(f"[cedarpy] uvicorn starting on http://{host}:{port}")
        uvicorn.run(app, host=host, port=port, reload=False)
        print("[cedarpy] uvicorn stopped")
    except Exception:
        print("[cedarpy] FATAL exception:\n" + traceback.format_exc())
        # Keep the log around long enough to inspect if launched via GUI
        time.sleep(2)
        raise


if __name__ == "__main__":
    main()
