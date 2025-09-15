#!/usr/bin/env python3
import os
import sys
import signal
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime
from threading import Thread

# Initialize logging similar to run_cedarpy
LOG_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), "Library", "Logs", "CedarPy")
LOCK_PATH = os.path.join(LOG_DIR_DEFAULT, "cedarqt.lock")


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
    return log_path

_log_path = _init_logging()

# Single-instance guard using a lock file
_single_lock_fh = None
try:
    os.makedirs(LOG_DIR_DEFAULT, exist_ok=True)
    # Use O_CREAT|O_EXCL to create a PID file atomically
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    _single_lock_fh = os.open(LOCK_PATH, flags, 0o644)
    os.write(_single_lock_fh, str(os.getpid()).encode("utf-8"))
except FileExistsError:
    # Another instance is likely running; bail out safely
    print(f"[cedarqt] another instance detected via {LOCK_PATH}; exiting")
    sys.exit(0)
except Exception as e:
    # Non-fatal; continue but log
    print(f"[cedarqt] lock warning: {e}")

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