#!/usr/bin/env python3
import os
import sys
import signal
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime

# Initialize logging similar to run_cedarpy
LOG_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), "Library", "Logs", "CedarPy")

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

# Qt imports (PySide6 + QtWebEngine)
from PySide6.QtCore import Qt, QUrl, QObject
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEnginePage
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


def _launch_server(host: str, port: int):
    env = os.environ.copy()
    env.setdefault("CEDARPY_OPEN_BROWSER", "0")  # prevent run_cedarpy from opening a system browser
    # Prefer uvicorn CLI; avoid reload inside packaged app
    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", host, "--port", str(port), "--log-level", "info"]
    print(f"[cedarqt] launching server: {' '.join(cmd)}")
    log_dir = os.getenv("CEDARPY_LOG_DIR", LOG_DIR_DEFAULT)
    os.makedirs(log_dir, exist_ok=True)
    server_log_path = os.path.join(log_dir, "uvicorn_from_qt.log")
    server_log = open(server_log_path, "a", buffering=1)
    proc = subprocess.Popen(cmd, stdout=server_log, stderr=server_log, env=env)
    return proc


def main():
    host = os.getenv("CEDARPY_HOST", "127.0.0.1")
    port = int(os.getenv("CEDARPY_PORT", "8000"))
    url = f"http://{host}:{port}/"

    # Start server
    proc = _launch_server(host, port)

    # Prepare Qt app and view
    app = QApplication(sys.argv)

    # Interceptor must be installed on a profile; default profile is fine for now
    try:
        from PySide6.QtWebEngineCore import QWebEngineProfile
        QWebEngineProfile.defaultProfile().setRequestInterceptor(RequestLogger())
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

    # Poll server before showing; otherwise we just load and let it spin
    _wait_for_server(url, timeout_sec=25.0)

    win.show()

    # Ensure child server is terminated on exit
    def _shutdown():
        try:
            if proc.poll() is None:
                print("[cedarqt] terminating server ...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
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