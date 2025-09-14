import os
import threading
import time
import webbrowser

import uvicorn
from main import app


def main():
    host = os.getenv("CEDARPY_HOST", "127.0.0.1")
    port = int(os.getenv("CEDARPY_PORT", "8000"))

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