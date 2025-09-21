import time
import re
from fastapi.testclient import TestClient

import main

client = TestClient(main.app, follow_redirects=True)

def test_project_page_renders_with_percent_signs():
    # Create a unique project and follow redirect to the project page
    title = f"Percent Render {int(time.time()*1000000)}"
    r = client.post("/projects/create", data={"title": title})
    assert r.status_code == 200
    html = r.text
    # The inline JS/CSS includes percent signs (e.g., 80%, -50%). Ensure they render and do not break formatting.
    assert "var PROJECT_ID = " in html
    assert "%" in html  # Basic sanity: page contains percent signs
    # Specific sequences from the project page UI
    assert "translateX(-50%)" in html
    assert "width='80%'" in html or "width=\"80%\"" in html or "width:80%" in html
    # Page contains core sections
    assert re.search(r"<h1>.*</h1>", html)
