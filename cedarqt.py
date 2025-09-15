#!/usr/bin/env python3
import os
import sys
import signal
import subprocess
import time
import urllib.request
import urllib.error
import errno
from datetime import datetime
from threading import Thread

# Initialize logging similar to run_cedarpy
LOG_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), "Library", "Logs", "CedarPy")
# Lock path now respects CEDARPY_LOG_DIR for consistency with logs.
# See README.md section "Single-instance lock and stale lock recovery" for details.
LOCK_PATH = os.path.join(os.getenv("CEDARPY_LOG_DIR", LOG_DIR_DEFAULT), "cedarqt.lock")


def _init_logging() -> str:
    log_dir = os.getenv("CEDARPY_LOG_DIR", LOG_DIR_DEFAULT)
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_path = os.path.join(log_dir, f"cedarqt_{ts}.log")
    f = open(log_path, "a", buffering=1)
    sys.stdout = f
    sys.stderr = f
    print(f"[cedarqt] log_path={log_path}")
    print(f"[cedarqt] sys.executable={sys.executable}")
    print(f"[cedarqt] cwd={os.getcwd()}")
    print(f"[cedarqt] lock_path={LOCK_PATH} pid={os.getpid()}")
    return log_path

_log_path = _init_logging()

# Single-instance guard using a lock file, with stale-lock recovery (single retry to avoid loops)
# See README.md for rationale and troubleshooting steps.

def _pid_is_running(pid: int) -> bool:
    try:
        # Signal 0 checks for existence without sending a signal
        os.kill(pid, 0)
        return True
    except OSError as e:
        # ESRCH -> no such process; EPERM -> exists but no permission (still running)
        return e.errno == errno.EPERM


def _acquire_single_instance_lock(lock_path: str):
    """Attempt to acquire a single-instance lock.

    Strategy:
    - Try O_EXCL create; if it exists, check PID liveness from the file.
    - If PID not running or file unreadable/unparsable, remove and retry ONCE.
    - If still failing after one retry, exit gracefully.
    """
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY

    def _try_create():
        fh = os.open(lock_path, flags, 0o644)
        os.write(fh, str(os.getpid()).encode("utf-8"))
        print(f"[cedarqt] acquired single-instance lock: {lock_path}")
        return fh

    try:
        return _try_create()
    except FileExistsError:
        # Read existing PID (best-effort)
        existing_pid = None
        try:
            with open(lock_path, "r") as f:
                content = f.read().strip()
                # Extract leading integer if file has noise
                digits = "".join(ch for ch in content if ch.isdigit())
                if digits:
                    existing_pid = int(digits)
        except Exception as e:
            print(f"[cedarqt] lock read error, treating as stale: {e}")

        # If PID appears alive, exit; otherwise treat as stale
        if existing_pid is not None and _pid_is_running(existing_pid):
            print(f"[cedarqt] another instance detected via {lock_path} (pid={existing_pid}); exiting")
            sys.exit(0)
        else:
            try:
                os.remove(lock_path)
                print(f"[cedarqt] removed stale lock: {lock_path} (pid={existing_pid})")
            except Exception as e:
                print(f"[cedarqt] failed to remove stale lock {lock_path}: {e}; exiting")
                sys.exit(0)
            # One retry only to avoid any chance of loops
            try:
                return _try_create()
            except FileExistsError:
                print(f"[cedarqt] lock re-created concurrently; another instance likely started; exiting")
                sys.exit(0)
            except Exception as e:
                print(f"[cedarqt] unexpected error after stale-lock cleanup: {e}; exiting")
                sys.exit(0)
    except Exception as e:
        print(f"[cedarqt] lock warning: {e}")
        return None


_single_lock_fh = _acquire_single_instance_lock(LOCK_PATH)

# Qt imports (PySide6 + QtWebEngine)
from PySide6.QtCore import Qt, QUrl, QObject
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

class RequestLogger(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):  # type: ignore[override]
        try:
            method = bytes(info.requestMethod()).decode("ascii", "ignore")
            url = info.requestUrl().toString()
            rtype = int(info.resourceType()) if hasattr(info, 'resourceType') else -1
            print(f"[qt-request] {method} {url} type={rtype}")
        except Exception:
            pass

class LoggingWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):  # type: ignore[override]
        # Map Qt levels to text
        try:
            lvl_map = {
                QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel: 'INFO',
                QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: 'WARN',
                QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: 'ERROR',
            }
            lvl = lvl_map.get(level, str(int(level)))
        except Exception:
            lvl = str(level)
        try:
            print(f"[qt-console] {lvl} {sourceID}:{lineNumber} :: {message}")
        except Exception:
            pass
        # Don't call super(); default implementation prints to stderr.


def _wait_for_server(url: str, timeout_sec: float = 20.0) -> bool:
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    print(f"[cedarqt] server ready: {url} status={resp.status}")
                    return True
        except urllib.error.URLError as e:
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    print(f"[cedarqt] server NOT ready after {timeout_sec}s: {url}")
    return False


def _launch_server_inprocess(host: str, port: int):
    # Run uvicorn in-process so PyInstaller bundles work without relying on -m
    os.environ.setdefault("CEDARPY_OPEN_BROWSER", "0")
    try:
        from main import app as fastapi_app
        from uvicorn import Config, Server
    except Exception as e:
        print(f"[cedarqt] failed to import server app: {e}")
        return None, None
    log_dir = os.getenv("CEDARPY_LOG_DIR", LOG_DIR_DEFAULT)
    os.makedirs(log_dir, exist_ok=True)
    server_log_path = os.path.join(log_dir, "uvicorn_from_qt.log")
    # uvicorn logs will go to stdout/stderr; they are captured by our redirected f in _init_logging
    config = Config(app=fastapi_app, host=host, port=port, log_level="info")
    server = Server(config)
    t = Thread(target=server.run, daemon=True)
    print(f"[cedarqt] starting uvicorn in-process on http://{host}:{port}")
    t.start()
    return server, t


def main():
    host = os.getenv("CEDARPY_HOST", "127.0.0.1")
    port = int(os.getenv("CEDARPY_PORT", "8000"))
    url = f"http://{host}:{port}/"

    # Start server (in-process)
    server, server_thread = _launch_server_inprocess(host, port)

    # Prepare Qt app and view
    app = QApplication(sys.argv)

    # Interceptor must be installed on a profile; default profile is fine for now
    try:
        QWebEngineProfile.defaultProfile().setUrlRequestInterceptor(RequestLogger())
    except Exception as e:
        print(f"[cedarqt] failed to install request interceptor: {e}")

    view = QWebEngineView()
    page = LoggingWebPage(view)
    view.setPage(page)
    view.setUrl(QUrl(url))

    win = QMainWindow()
    win.setWindowTitle("CedarPy")
    win.setCentralWidget(view)
    win.resize(1200, 800)

    # Poll server before showing; otherwise quit with a helpful dialog
    if not _wait_for_server(url, timeout_sec=25.0):
        try:
            QMessageBox.critical(None, "CedarPy", "Server failed to start on 127.0.0.1:" + str(port) + "\nCheck logs in ~/Library/Logs/CedarPy.")
        except Exception:
            pass
        # Clean up lock and exit
        try:
            if _single_lock_fh is not None:
                os.close(_single_lock_fh)
                os.remove(LOCK_PATH)
        except Exception:
            pass
        sys.exit(1)

    win.show()
    try:
        win.raise_()
        win.activateWindow()
        app.setActiveWindow(win)
    except Exception:
        pass

    # Ensure child server is terminated on exit
    def _shutdown():
        try:
            if server is not None:
                print("[cedarqt] stopping server ...")
                try:
                    # signal graceful shutdown
                    server.should_exit = True  # type: ignore[attr-defined]
                except Exception:
                    pass
                # Wait briefly for thread to finish
                try:
                    if server_thread and server_thread.is_alive():
                        server_thread.join(timeout=5)
                except Exception:
                    pass
        except Exception:
            pass
        # Release single-instance lock
        try:
            if _single_lock_fh is not None:
                os.close(_single_lock_fh)
                os.remove(LOCK_PATH)
        except Exception:
            pass

    app.aboutToQuit.connect(_shutdown)  # type: ignore

    # Handle Unix signals to close the app cleanly
    try:
        import signal
        def _sig_handler(signum, frame):
            print(f"[cedarqt] signal {signum} -> quitting")
            app.quit()
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass

    rc = app.exec()
    sys.exit(rc)


if __name__ == '__main__':
    main()