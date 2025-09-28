"""
Table components for Cedar app
"""

from typing import List, Dict, Any, Optional
from main_helpers import escape


def data_table(headers: List[str], rows: List[List[str]], css_class: str = "table") -> str:
    """
    Generate a data table HTML component.
    
    Args:
        headers: List of column headers
        rows: List of row data (each row is a list of cell values)
        css_class: CSS class for the table
    """
    header_html = "".join(f"<th>{escape(h)}</th>" for h in headers)
    
    rows_html = []
    for row in rows:
        cells = "".join(f"<td>{cell}</td>" for cell in row)  # Cells may contain HTML
        rows_html.append(f"<tr>{cells}</tr>")
    
    tbody_content = "\n".join(rows_html) if rows_html else f'<tr><td colspan="{len(headers)}" class="muted">No data available.</td></tr>'
    
    return f"""
        <table class="{css_class}">
            <thead>
                <tr>{header_html}</tr>
            </thead>
            <tbody>
                {tbody_content}
            </tbody>
        </table>
    """


def projects_table(projects: List[Any]) -> str:
    """Generate projects table specifically."""
    headers = ["Title", "Created", "Actions"]
    rows = []
    
    for p in projects:
        row = [
            f'<a href="/project/{p.id}">{escape(p.title)}</a>',
            f'<span class="small muted">{p.created_at:%Y-%m-%d %H:%M:%S} UTC</span>',
            f'''
                <form method="post" action="/project/{p.id}/delete" class="inline" 
                      onsubmit="return confirm('Delete project {escape(p.title)} and all its data?');">
                    <button type="submit" class="secondary">Delete</button>
                </form>
            '''
        ]
        rows.append(row)
    
    return data_table(headers, rows)


def files_table(files: List[Any], project_id: int) -> str:
    """Generate files table for a project."""
    import os
    from cedar_app.db_utils import _project_dirs
    
    headers = ["Name", "Type", "Structure", "Branch", "Size", "Created"]
    rows = []
    
    for f in files:
        # Generate file URL if possible
        storage_path = f.storage_path or ""
        url = None
        try:
            abs_path = os.path.abspath(storage_path)
            base_root = _project_dirs(project_id)["files_root"]
            if abs_path.startswith(base_root):
                rel = abs_path[len(base_root):].lstrip(os.sep).replace(os.sep, "/")
                url = f"/uploads/{project_id}/{rel}"
        except Exception:
            url = None
            
        link_html = f'<a href="{url}" target="_blank">{escape(f.display_name)}</a>' if url else escape(f.display_name)
        
        row = [
            link_html,
            escape(f.file_type or ''),
            escape(f.structure or ''),
            escape(f.branch.name if f.branch else ''),
            f'<span class="small muted">{f.size_bytes or 0}</span>',
            f'<span class="small muted">{f.created_at:%Y-%m-%d %H:%M:%S} UTC</span>'
        ]
        rows.append(row)
    
    return data_table(headers, rows)


def datasets_table(datasets: List[Any]) -> str:
    """Generate datasets/databases table."""
    headers = ["Name", "Branch", "Created"]
    rows = []
    
    for d in datasets:
        row = [
            escape(d.name),
            escape(d.branch.name if d.branch else ''),
            f'<span class="small muted">{d.created_at:%Y-%m-%d %H:%M:%S} UTC</span>'
        ]
        rows.append(row)
    
    return data_table(headers, rows)