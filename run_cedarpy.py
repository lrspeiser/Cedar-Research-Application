import os
import threading
import time
import webbrowser

import uvicorn
from main import app


def main():
    host = os.getenv("CEDARPY_HOST", "127.0.0.1")
    port = int(os.getenv("CEDARPY_PORT", "8000"))

    # Default to SQLite in ~/CedarPyData if no DB URL is set, so the app runs offline.
    if not os.getenv("CEDARPY_DATABASE_URL") and not os.getenv("CEDARPY_MYSQL_URL"):
        home = os.path.expanduser("~")
        data_dir = os.environ.get("CEDARPY_DATA_DIR", os.path.join(home, "CedarPyData"))
        os.makedirs(data_dir, exist_ok=True)
        os.environ["CEDARPY_DATABASE_URL"] = f"sqlite:///{os.path.join(data_dir, 'cedarpy.db')}"

    def open_browser():
        # Open the app in the default browser shortly after startup
        time.sleep(1.5)
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            pass

    if os.getenv("CEDARPY_OPEN_BROWSER", "1") == "1":
        threading.Thread(target=open_browser, daemon=True).start()

    # Run without reload in packaged mode
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()