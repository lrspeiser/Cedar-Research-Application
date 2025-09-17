import re
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure repo root on sys.path for importing 'main'
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from main import projects_list_html


def test_projects_list_html_formats_datetime():
    class P:
        def __init__(self, id, title, dt):
            self.id = id
            self.title = title
            self.created_at = dt
    # Two sample projects
    now = datetime.now(timezone.utc)
    projects = [P(1, "Alpha", now), P(2, "Beta", now)]
    html = projects_list_html(projects)
    # Expect a UTC timestamp with our format
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC", html)
    # Expect titles to be present, safely escaped
    assert "Alpha" in html and "Beta" in html
