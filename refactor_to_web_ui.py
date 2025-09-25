#!/usr/bin/env python3
"""
Script to refactor main_impl_full.py into web_ui.py
Extracts business logic into modules and keeps only UI/routing code.
"""

import re

def refactor_to_web_ui():
    with open('/Users/leonardspeiser/Projects/cedarpy/cedar_app/main_impl_full.py', 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    i = 0
    
    # Keep everything up to line 420 (imports and initial setup)
    while i < 420 and i < len(lines):
        new_lines.append(lines[i])
        i += 1
    
    # Add imports for extracted modules
    new_lines.extend([
        "\n# ====== Extracted Modules ======\n",
        "# Code collection utilities\n",
        "from cedar_app.utils.code_collection import collect_code_items as _collect_code_items\n",
        "\n# UI view rendering\n",
        "from cedar_app.utils.ui_views import (\n",
        "    view_logs as view_logs_impl,\n",
        "    view_changelog as view_changelog_impl,\n",
        "    render_project_view\n",
        ")\n",
        "\n# Project and thread management\n",
        "from cedar_app.routes.project_thread_routes import (\n",
        "    create_project as create_project_impl,\n",
        "    create_thread as create_thread_impl\n",
        ")\n\n",
    ])
    
    # Process the rest of the file
    while i < len(lines):
        line = lines[i]
        
        # Handle @app.get("/log") - view_logs
        if i == 1168 and '@app.get("/log"' in line:
            new_lines.append(line)
            new_lines.append("def view_logs(project_id: Optional[int] = None, branch_id: Optional[int] = None):\n")
            new_lines.append('    """View application logs."""\n')
            new_lines.append("    return view_logs_impl(project_id, branch_id)\n\n")
            i = 1232  # Skip to end of original function
            
        # Handle @app.get("/changelog") - view_changelog
        elif i == 1231 and '@app.get("/changelog"' in line:
            new_lines.append(line)
            new_lines.append("def view_changelog(request: Request, project_id: Optional[int] = None, branch_id: Optional[int] = None):\n")
            new_lines.append('    """View changelog entries."""\n')
            new_lines.append("    return view_changelog_impl(request, project_id, branch_id)\n\n")
            i = 1343  # Skip to end
            
        # Handle @app.post("/projects/create") - create_project
        elif i == 1509 and '@app.post("/projects/create"' in line:
            new_lines.append(line)
            new_lines.append("def create_project(title: str = Form(...), db: Session = Depends(get_registry_db)):\n")
            new_lines.append('    """Create a new project."""\n')
            new_lines.append("    return create_project_impl(title, db)\n\n")
            i = 1552  # Skip to end
            
        # Skip _collect_code_items (internal function)
        elif i == 1609 and 'def _collect_code_items' in line:
            i = 1743  # Skip entire function
            
        # Handle @app.get("/project/{project_id}") - view_project
        elif i == 1743 and '@app.get("/project/{project_id}"' in line:
            new_lines.append(line)
            new_lines.extend([
                "def view_project(project_id: int, branch_id: Optional[int] = None, msg: Optional[str] = None,\n",
                "                file_id: Optional[int] = None, dataset_id: Optional[int] = None,\n",
                "                thread_id: Optional[int] = None, code_mid: Optional[int] = None,\n",
                "                code_idx: Optional[int] = None, db: Session = Depends(get_project_db)):\n",
                '    """Main project view."""\n',
                "    from main_models import FileEntry, Dataset, Thread, Note\n",
                "    from main_helpers import branch_filter_ids\n",
                "    \n",
                "    ensure_project_initialized(project_id)\n",
                "    project = db.query(Project).filter(Project.id == project_id).first()\n",
                "    if not project:\n",
                "        return RedirectResponse('/', status_code=303)\n",
                "    \n",
                "    branch = current_branch(db, project.id, branch_id)\n",
                "    ids = branch_filter_ids(db, project.id, branch.id)\n",
                "    \n",
                "    # Query all needed data\n",
                "    files = db.query(FileEntry).filter(\n",
                "        FileEntry.project_id == project.id,\n",
                "        FileEntry.branch_id.in_(ids)\n",
                "    ).order_by(FileEntry.created_at.desc()).all()\n",
                "    \n",
                "    datasets = db.query(Dataset).filter(\n",
                "        Dataset.project_id == project.id,\n",
                "        Dataset.branch_id.in_(ids)\n",
                "    ).order_by(Dataset.created_at.desc()).all()\n",
                "    \n",
                "    threads = db.query(Thread).filter(\n",
                "        Thread.project_id == project.id,\n",
                "        Thread.branch_id.in_(ids)\n",
                "    ).order_by(Thread.created_at.desc()).all()\n",
                "    \n",
                "    notes = db.query(Note).filter(\n",
                "        Note.project_id == project.id,\n",
                "        Note.branch_id.in_(ids)\n",
                "    ).order_by(Note.created_at.desc()).all()\n",
                "    \n",
                "    # Collect code items\n",
                "    code_items = _collect_code_items(db, project.id, threads)\n",
                "    \n",
                "    # Render HTML\n",
                "    html = render_project_view(\n",
                "        project, branch, threads, files, datasets, notes, code_items,\n",
                "        msg, file_id, dataset_id, thread_id, code_mid, code_idx\n",
                "    )\n",
                "    return HTMLResponse(html)\n\n",
            ])
            i = 1878  # Skip to end
            
        # Handle @app.post and @app.get for create_thread
        elif (i == 1879 and '@app.post("/project/{project_id}/threads/create"' in line) or \
             (i == 1904 and '@app.get("/project/{project_id}/threads/new"' in line):
            new_lines.append(line)
            i += 1
            if i == 1880 or i == 1905:  # Both decorators point to same function
                pass  # Keep moving
            
        elif i == 1907 and 'def create_thread' in line:
            new_lines.append("def create_thread(project_id: int, request: Request, title: Optional[str] = Form(None), db: Session = Depends(get_project_db)):\n")
            new_lines.append('    """Create a new thread."""\n')
            new_lines.append("    return create_thread_impl(project_id, request, title, db)\n\n")
            i = 1966  # Skip to end
            
        else:
            new_lines.append(line)
            i += 1
    
    # Write the new web_ui.py file
    with open('/Users/leonardspeiser/Projects/cedarpy/cedar_app/web_ui.py', 'w') as f:
        f.writelines(new_lines)
    
    print(f"Original file: {len(lines)} lines")
    print(f"New web_ui.py: {len(new_lines)} lines")
    print(f"Reduction: {len(lines) - len(new_lines)} lines")
    print("\nRefactoring complete! Created web_ui.py")

if __name__ == "__main__":
    refactor_to_web_ui()