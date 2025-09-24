"""
Main routes for Cedar app.
Handles home page, about, and general endpoints.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

from cedar_app.database import get_registry_db
from cedar_app.utils.html import layout, projects_list_html

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Home page - redirects to projects list."""
    return RedirectResponse("/projects", status_code=303)

@router.get("/projects", response_class=HTMLResponse)
def projects_list(db=Depends(get_registry_db)):
    """Display list of all projects."""
    from main_models import Project
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    body = projects_list_html(projects)
    return layout("Projects", body)

@router.get("/about", response_class=HTMLResponse)
def about():
    """About page."""
    body = """
    <h1>About Cedar</h1>
    <div class='card'>
        <p>Cedar is a powerful data management and analysis platform.</p>
        <p>Version: 2.0.0</p>
    </div>
    """
    return layout("About", body)
