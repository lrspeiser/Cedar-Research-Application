"""
Refactored page rendering utilities for Cedar app.
This is a transitional module that imports from the new component structure.
"""

from typing import List, Optional, Dict, Any
from main_models import Project, Branch, Thread, ThreadMessage, FileEntry, Dataset, Note
from main_helpers import escape

# Import components
from cedar_app.templates.components.alerts import message_alert
from cedar_app.templates.components.tables import projects_table, files_table, datasets_table


def projects_list_html(projects: List[Project], msg: Optional[str] = None) -> str:
    """Generate HTML for the projects list page using components."""
    
    # Use alert component for messages
    message_html = message_alert(msg)
    
    if not projects:
        return f"""
        <h1>Projects</h1>
        {message_html}
        <p class="muted">No projects yet. Create one:</p>
        <form method="post" action="/projects/create" class="card" style="max-width:520px">
            <label>Project title</label>
            <input type="text" name="title" placeholder="My First Project" required />
            <div style="height:10px"></div>
            <button type="submit">Create Project</button>
        </form>
        """
    
    # Use table component for projects list
    table_html = projects_table(projects)
    
    return f"""
        <h1>Projects</h1>
        {message_html}
        <div class="row">
          <div class="card" style="flex:2">
            {table_html}
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


# Keep the original project_page_html for now as it's too complex to refactor all at once
# We'll gradually extract more components
from cedar_app.utils.page_rendering import project_page_html