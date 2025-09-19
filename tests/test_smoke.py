from fastapi.testclient import TestClient
import time
import re

import main

client = TestClient(main.app, follow_redirects=True)


def test_home_ok():
    r = client.get("/")
    assert r.status_code == 200
    assert re.search(r"Cedar", r.text)


def test_create_and_open_project():
    title = f"Smoke {int(time.time())}"
    r = client.post("/projects/create", data={"title": title})
    # With follow_redirects=True, we expect a 200 and the project page in the response
    assert r.status_code == 200
    r2 = r

    assert r2.status_code == 200
    # Project page should contain a heading and right pane sections
    assert re.search(r"<h1>", r2.text)
    assert "Files" in r2.text
    # Assert production layout CSS (two-column grid) is present
    assert re.search(r"\.two-col\s*\{[\s\S]*grid-template-columns", r2.text)
    # Assert client logging hook exists so Console Logs can capture
    assert "/api/client-log" in r2.text
