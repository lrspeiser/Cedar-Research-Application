#!/usr/bin/env python3
import os
import sys
import signal
import subprocess
import time
import urllib.request
import urllib.error
import errno
from datetime import datetime, timezone
from threading import Thread

# Enable DevTools for QtWebEngine so tests can drive the embedded browser via CDP.
# Use CEDARPY_QT_DEVTOOLS_PORT to choose the port (default 9222).
# For CI, you can set CEDARPY_QT_HEADLESS=1 to run Qt offscreen.
# See README ("Embedded UI testing via Playwright + CDP") for details.
if os.getenv("QTWEBENGINE_REMOTE_DEBUGGING") is None:
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = os.getenv("CEDARPY_QT_DEVTOOLS_PORT", "9222")
if os.getenv("CEDARPY_QT_HEADLESS", "").strip().lower() in {"1", "true", "yes"}:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Initialize logging similar to run_cedarpy
LOG_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), "Library", "Logs", "CedarPy")
# Lock path now respects CEDARPY_LOG_DIR for consistency with logs.
# See README.md section "Single-instance lock and stale lock recovery" for details.
LOCK_PATH = os.path.join(os.getenv("CEDARPY_LOG_DIR", LOG_DIR_DEFAULT), "cedarqt.lock")


def _init_logging() -> str:
    log_dir = os.getenv("CEDARPY_LOG_DIR", LOG_DIR_DEFAULT)
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
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


# Allow tests/CI to run multiple instances without fighting over a global lock
if os.getenv("CEDARPY_ALLOW_MULTI", "").strip().lower() in {"1", "true", "yes"}:
    _single_lock_fh = None
    print("[cedarqt] single-instance lock disabled via CEDARPY_ALLOW_MULTI=1")
else:
    _single_lock_fh = _acquire_single_instance_lock(LOCK_PATH)

# Qt imports (PySide6 + QtWebEngine)
from PySide6.QtCore import Qt, QUrl, QObject
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtGui import QDesktopServices

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

    # Allow tests to provide a file selection path without a native dialog.
    def chooseFiles(self, mode, oldFiles, acceptedMimeTypes):  # type: ignore[override]
        try:
            test_mode = os.getenv("CEDARPY_QT_HARNESS", "").strip().lower() in {"1", "true", "yes"}
            test_file = os.getenv("CEDARPY_QT_TEST_FILE")
            if test_mode and test_file and os.path.isfile(test_file):
                print(f"[qt-page] chooseFiles intercepted, returning: {test_file}")
                return [test_file]
        except Exception as e:
            try:
                print(f"[qt-page] chooseFiles error: {e}")
            except Exception:
                pass
        return super().chooseFiles(mode, oldFiles, acceptedMimeTypes)


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
    fastapi_app = None
    try:
        from main import app as fastapi_app  # type: ignore
        print("[cedarqt] imported main.app via normal import")
    except Exception as e1:
        print(f"[cedarqt] import main failed: {e1}; trying fallback loader")
        try:
            import importlib.util as _util, sys as _sys, os as _os
            base_dir = _os.path.dirname(_sys.executable) if getattr(_sys, 'frozen', False) else _os.path.dirname(__file__)
            resources_dir = _os.path.abspath(_os.path.join(base_dir, '..', 'Resources'))
            candidates = [
                _os.path.join(base_dir, 'main.py'),
                _os.path.join(resources_dir, 'main.py'),
                _os.path.abspath(_os.path.join(_os.path.dirname(__file__), 'main.py')),
            ]
            loaded = False
            for cand in candidates:
                try:
                    if _os.path.isfile(cand):
                        spec = _util.spec_from_file_location('main', cand)
                        if spec and spec.loader:
                            mod = _util.module_from_spec(spec)  # type: ignore
                            spec.loader.exec_module(mod)  # type: ignore
                            fastapi_app = getattr(mod, 'app', None)
                            if fastapi_app is not None:
                                print(f"[cedarqt] loaded main.app from {cand}")
                                loaded = True
                                break
                except Exception as e2:
                    print(f"[cedarqt] fallback load error from {cand}: {e2}")
            if not loaded:
                print("[cedarqt] failed to locate main.py in fallback paths")
                return None, None
            from uvicorn import Config, Server  # type: ignore
        except Exception as e3:
            print(f"[cedarqt] failed to import server app via fallback: {e3}")
            return None, None
    from uvicorn import Config, Server
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


def _open_full_disk_access_settings():
    try:
        url = QUrl("x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
        if not QDesktopServices.openUrl(url):
            # Fallback to shell 'open'
            try:
                subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"])  # nosec - opens System Settings
            except Exception:
                pass
    except Exception:
        try:
            subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"])  # nosec
        except Exception:
            pass


def _maybe_prompt_full_disk_access_once():
    try:
        show = os.getenv("CEDARPY_SHOW_FDA_PROMPT", "1").strip().lower() not in {"0", "false", "no", "off"}
        if not show:
            return
        stamp_dir = os.getenv("CEDARPY_LOG_DIR", LOG_DIR_DEFAULT)
        os.makedirs(stamp_dir, exist_ok=True)
        stamp = os.path.join(stamp_dir, "fda_prompt_seen")
        if os.path.exists(stamp):
            return
        msg = (
            "To let CedarPy search across your files without interruptions, please grant Full Disk Access.\n\n"
            "Steps: System Settings → Privacy & Security → Full Disk Access → add CedarPy and toggle it on.\n\n"
            "After enabling, quit and reopen CedarPy to ensure permissions take effect."
        )
        box = QMessageBox()
        box.setWindowTitle("CedarPy – Permissions")
        box.setText(msg)
        open_btn = box.addButton("Open Settings", QMessageBox.AcceptRole)
        skip_btn = box.addButton("Skip", QMessageBox.RejectRole)
        box.setDefaultButton(open_btn)
        box.exec()
        if box.clickedButton() == open_btn:
            _open_full_disk_access_settings()
        try:
            with open(stamp, "w") as f:
                f.write("seen\n")
        except Exception:
            pass
    except Exception:
        pass


def _choose_listen_port(host: str, desired: int) -> int:
    try:
        import socket as _s
        # Try desired
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
        # Find free
        s2 = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        s2.bind((host, 0))
        port = s2.getsockname()[1]
        s2.close()
        return int(port)
    except Exception:
        return desired


def main():
    host = os.getenv("CEDARPY_HOST", "127.0.0.1")
    port_env = os.getenv("CEDARPY_PORT", "8000")
    try:
        desired = int(port_env)
    except Exception:
        desired = 8000
    port = _choose_listen_port(host, desired)
    # Propagate the effective port to child pieces that might read env again
    os.environ["CEDARPY_PORT"] = str(port)
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
    # Only attempt to raise/activate when not in headless/offscreen mode
    if os.getenv("QT_QPA_PLATFORM", "") != "offscreen":
        try:
            win.raise_()
            win.activateWindow()
            app.setActiveWindow(win)
        except Exception:
            pass

    # Optional in-process UI harness for end-to-end testing of the embedded browser.
    # Set CEDARPY_QT_HARNESS=1 to enable. Provide CEDARPY_QT_TEST_FILE for the file to upload.
    if os.getenv("CEDARPY_QT_HARNESS", "").strip().lower() in {"1", "true", "yes"}:
        try:
            from PySide6.QtCore import QTimer
            def run_harness():
                print("[qt-harness] starting")
                def js(script):
                    try:
                        page.runJavaScript(script)
                    except Exception as e:
                        print(f"[qt-harness] js error: {e}")
                # Step 1: create a project
                title = f"Harness {int(time.time()*1000)}"
                js(
                    "(function(){\n"
                    "var el=document.querySelector(\"input[name=title]\"); if(el){ el.value=%s; el.dispatchEvent(new Event('input',{bubbles:true})); }\n"
                    "var btn=document.querySelector(\"form[action='/projects/create'] button[type=submit]\");\n"
                    "if(!btn){ var all=[].slice.call(document.querySelectorAll('button,a')); btn=all.find(e=>e.textContent.trim()==='Create Project'); }\n"
                    "if(btn){ btn.click(); }\n"
                    "})();" % (repr(title))
                )
                # Fallback uploader (programmatic) if the GUI flow stalls
                def fallback_upload():
                    try:
                        import urllib.request as _ur
                        from urllib.parse import urlparse as _urlparse, parse_qs as _parse_qs
                        import re as _re, time as _time, uuid as _uuid
                        test_file = os.getenv("CEDARPY_QT_TEST_FILE")
                        if not test_file or not os.path.isfile(test_file):
                            print("[qt-harness] fallback skipped: no test file")
                            return
                        # Resolve or create a project id
                        proj_id = None
                        branch_id = 1
                        try:
                            # Try current page first
                            here = page.url().toString()
                            u = _urlparse(here)
                            if u.path.startswith('/project/'):
                                proj_id = int(u.path.split('/')[-1] or '0')
                                qs = _parse_qs(u.query)
                                try:
                                    branch_id = int((qs.get('branch_id') or ['1'])[0])
                                except Exception:
                                    branch_id = 1
                        except Exception:
                            proj_id = None
                        # If we still don't have a project, create one programmatically
                        if not proj_id:
                            try:
                                home_url = f"http://{host}:{port}/"
                                home_html = _ur.urlopen(home_url, timeout=5).read().decode('utf-8', 'ignore')
                                m = _re.search(r"/project/(\\d+)", home_html)
                                if m:
                                    proj_id = int(m.group(1))
                                else:
                                    title = f"Harness Programmatic {_int(_time.time()*1000) if ' _int' in dir() else str(int(_time.time()*1000))}"
                                    data = f"title={_ur.quote(title)}".encode('utf-8')
                                    req = _ur.Request(f"http://{host}:{port}/projects/create", data=data, method='POST')
                                    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
                                    try:
                                        _ur.urlopen(req, timeout=5)
                                    except Exception:
                                        pass
                                    home_html = _ur.urlopen(home_url, timeout=5).read().decode('utf-8', 'ignore')
                                    m = _re.search(r"/project/(\\d+)", home_html)
                                    if m:
                                        proj_id = int(m.group(1))
                                    else:
                                        print("[qt-harness] fallback could not find project after create")
                                        return
                            except Exception as e:
                                print(f"[qt-harness] fallback project resolution error: {e}")
                                return
                        # Build multipart and upload
                        boundary = '----CedarHarness' + _uuid.uuid4().hex
                        with open(test_file, 'rb') as f:
                            data = f.read()
                        filename = os.path.basename(test_file)
                        body = (
                            f"--{boundary}\r\n"
                            f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                            f"Content-Type: application/octet-stream\r\n\r\n".encode('utf-8') + data +
                            f"\r\n--{boundary}--\r\n".encode('utf-8')
                        )
                        target = f"http://{host}:{port}/project/{proj_id}/files/upload?branch_id={branch_id}"
                        req = _ur.Request(target, data=body, method='POST')
                        req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                        req.add_header('Content-Length', str(len(body)))
                        try:
                            with _ur.urlopen(req, timeout=10) as resp:
                                print(f"[qt-harness] fallback upload status={resp.status}")
                        except Exception as e:
                            print(f"[qt-harness] fallback upload error: {e}")
                    except Exception as e:
                        print(f"[qt-harness] fallback exception: {e}")
                # Poll for project page then upload
                attempts = {"count": 0}
                def wait_project_and_upload():
                    try:
                        cur = page.url().toString()
                        if "/project/" in cur:
                            print(f"[qt-harness] on project page: {cur}")
                            # Click the file input to trigger chooseFiles (avoid nested quotes in selector)
                            js("(function(){ var i=document.querySelector('[data-testid=upload-input]'); if(i){ i.click(); } })();")
                            # Small delay then click submit
                            def click_submit():
                                js("(function(){ var b=document.querySelector('[data-testid=\"upload-submit\"]'); if(b){ b.click(); } })();")
                                # Wait for msg=File+uploaded in URL, with fallback
                                def wait_uploaded():
                                    try:
                                        here = page.url().toString()
                                        if 'msg=File+uploaded' in here:
                                            print(f"[qt-harness] success url={here}")
                                            return
                                    except Exception:
                                        pass
                                    attempts["count"] += 1
                                    # After ~10 attempts (~3s), try programmatic upload as a fallback
                                    if attempts["count"] == 10:
                                        print("[qt-harness] GUI upload stalled; attempting fallback upload")
                                        fallback_upload()
                                    QTimer.singleShot(300, wait_uploaded)
                                QTimer.singleShot(500, wait_uploaded)
                            QTimer.singleShot(500, click_submit)
                            return
                    except Exception:
                        pass
                    QTimer.singleShot(300, wait_project_and_upload)
                QTimer.singleShot(500, wait_project_and_upload)
            # Grab page from view
            page = view.page()
            QTimer.singleShot(800, run_harness)
        except Exception as e:
            print(f"[qt-harness] init error: {e}")

    # Prompt for Full Disk Access on first launch to reduce later interruptions
    try:
        _maybe_prompt_full_disk_access_once()
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