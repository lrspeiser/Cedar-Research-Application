from fastapi.testclient import TestClient
import time
import re

import main

client = TestClient(main.app)


def test_home_ok():
    r = client.get("/")
    assert r.status_code == 200
    assert re.search(r"Cedar", r.text)


def test_create_and_open_project():
    title = f"Smoke {int(time.time())}"
    r = client.post("/projects/create", data={"title": title})
    # Allow 303 redirect
    assert r.status_code in (200, 303)

    # Follow redirect if present
    url = r.headers.get("location") or "/"
    r2 = client.get(url)
    assert r2.status_code == 200
    # Project page should contain a heading and right pane sections
    assert re.search(r"<h1>", r2.text)
    assert "Files" in r2.text
