"""
Page rendering utilities for Cedar app.
Functions to generate HTML for various pages and components.
"""

from typing import List, Optional, Dict, Any
from main_models import Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Note
from main_helpers import escape
import html


def projects_list_html(projects: List[Project]) -> str:
    """Generate HTML for the projects list page."""
    if not projects:
        return f"""
        <h1>Projects</h1>
        <p class="muted">No projects yet. Create one:</p>
        <form method="post" action="/projects/create" class="card" style="max-width:520px">
            <label>Project title</label>
            <input type="text" name="title" placeholder="My First Project" required />
            <div style="height:10px"></div>
            <button type="submit">Create Project</button>
        </form>
        """
    rows = []
    for p in projects:
        rows.append(f"""
            <tr>
              <td><a href="/project/{p.id}">{escape(p.title)}</a></td>
              <td class="small muted">{p.created_at:%Y-%m-%d %H:%M:%S} UTC</td>
              <td>
                <form method="post" action="/project/{p.id}/delete" class="inline" onsubmit="return confirm('Delete project {escape(p.title)} and all its data?');">
                  <button type="submit" class="secondary">Delete</button>
                </form>
              </td>
            </tr>
        """)
    return f"""
        <h1>Projects</h1>
        <div class="row">
          <div class="card" style="flex:2">
            <table class="table">
              <thead><tr><th>Title</th><th>Created</th><th>Actions</th></tr></thead>
              <tbody>
                {''.join(rows)}
              </tbody>
            </table>
          </div>
          <div class="card" style="flex:1">
            <h3>Create a new project</h3>
            <form method="post" action="/projects/create">
              <input type="text" name="title" placeholder="Project title" required />
              <div style="height:10px"></div>
              <button type="submit">Create</button>
            </form>
          </div>
        </div>
    """