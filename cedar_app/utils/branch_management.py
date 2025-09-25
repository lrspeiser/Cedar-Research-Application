"""
Branch management utilities for Cedar app.
Handles branch creation, switching, deletion, and management.
"""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import HTTPException, Request, Form, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from ..db_utils import _get_project_engine, ensure_project_initialized
from main_models import Branch, Project, FileEntry, Thread, Dataset, Note, ChangelogEntry
from main_helpers import add_version, ensure_main_branch, current_branch
from ..changelog_utils import record_changelog


def create_branch(app, project_id: int, name: str, db: Session) -> Dict[str, Any]:
    """Create a new branch."""
    ensure_project_initialized(project_id)
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    name = name.strip()
    if not name or name.lower() == "main":
        # Prevent duplicate/invalid
        main = ensure_main_branch(db, project.id)
        raise HTTPException(status_code=400, detail="Invalid branch name. Cannot create 'main' branch.")
    
    # Check for duplicate
    existing = db.query(Branch).filter(
        Branch.project_id == project.id,
        Branch.name == name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Branch '{name}' already exists")
    
    # Create branch
    branch = Branch(
        project_id=project.id,
        name=name,
        is_default=False,
        created_at=datetime.utcnow()
    )
    db.add(branch)
    
    try:
        db.commit()
        db.refresh(branch)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Failed to create branch")
    
    # Add version tracking
    add_version(db, "branch", branch.id, {
        "project_id": project.id,
        "name": branch.name,
        "is_default": False
    })
    
    # Record in changelog
    try:
        record_changelog(
            db, project.id, branch.id, "branch.create",
            {"name": name},
            {"branch_id": branch.id}
        )
    except Exception:
        pass
    
    return {
        "ok": True,
        "branch_id": branch.id,
        "name": branch.name,
        "redirect": f"/project/{project.id}?branch_id={branch.id}&msg=Branch+created"
    }


def delete_branch(app, project_id: int, branch_id: int, db: Session) -> Dict[str, Any]:
    """Delete a branch and all its associated data."""
    ensure_project_initialized(project_id)
    
    branch = db.query(Branch).filter(
        Branch.id == branch_id,
        Branch.project_id == project_id
    ).first()
    
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    if branch.name.lower() == "main" or branch.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete main branch")
    
    branch_name = branch.name
    
    # Delete all associated data
    try:
        # Delete files (and physical files)
        files = db.query(FileEntry).filter(
            FileEntry.project_id == project_id,
            FileEntry.branch_id == branch_id
        ).all()
        for f in files:
            try:
                if f.storage_path and os.path.exists(f.storage_path):
                    os.remove(f.storage_path)
            except:
                pass
            db.delete(f)
        
        # Delete threads and messages
        threads = db.query(Thread).filter(
            Thread.project_id == project_id,
            Thread.branch_id == branch_id
        ).all()
        for t in threads:
            # Messages are cascade deleted due to foreign key
            db.delete(t)
        
        # Delete datasets
        datasets = db.query(Dataset).filter(
            Dataset.project_id == project_id,
            Dataset.branch_id == branch_id
        ).all()
        for d in datasets:
            db.delete(d)
        
        # Delete notes
        notes = db.query(Note).filter(
            Note.project_id == project_id,
            Note.branch_id == branch_id
        ).all()
        for n in notes:
            db.delete(n)
        
        # Delete changelog entries
        changelog = db.query(ChangelogEntry).filter(
            ChangelogEntry.project_id == project_id,
            ChangelogEntry.branch_id == branch_id
        ).all()
        for c in changelog:
            db.delete(c)
        
        # Finally delete the branch itself
        db.delete(branch)
        db.commit()
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete branch: {str(e)}")
    
    # Get main branch for redirect
    main = ensure_main_branch(db, project_id)
    
    return {
        "ok": True,
        "message": f"Branch '{branch_name}' and all associated data deleted",
        "redirect": f"/project/{project_id}?branch_id={main.id}&msg=Branch+deleted"
    }


def list_branches(app, project_id: int, db: Session) -> List[Dict[str, Any]]:
    """List all branches for a project."""
    ensure_project_initialized(project_id)
    
    branches = db.query(Branch).filter(
        Branch.project_id == project_id
    ).order_by(Branch.created_at.asc()).all()
    
    if not branches:
        # Ensure at least main branch exists
        main = ensure_main_branch(db, project_id)
        branches = [main]
    
    result = []
    for b in branches:
        # Count items in branch
        file_count = db.query(FileEntry).filter(
            FileEntry.project_id == project_id,
            FileEntry.branch_id == b.id
        ).count()
        
        thread_count = db.query(Thread).filter(
            Thread.project_id == project_id,
            Thread.branch_id == b.id
        ).count()
        
        dataset_count = db.query(Dataset).filter(
            Dataset.project_id == project_id,
            Dataset.branch_id == b.id
        ).count()
        
        result.append({
            "id": b.id,
            "name": b.name,
            "is_default": b.is_default,
            "file_count": file_count,
            "thread_count": thread_count,
            "dataset_count": dataset_count,
            "created_at": b.created_at.isoformat() + "Z" if b.created_at else None
        })
    
    return result


def get_branch_info(app, project_id: int, branch_id: int, db: Session) -> Dict[str, Any]:
    """Get detailed information about a branch."""
    ensure_project_initialized(project_id)
    
    branch = db.query(Branch).filter(
        Branch.id == branch_id,
        Branch.project_id == project_id
    ).first()
    
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    # Get counts
    file_count = db.query(FileEntry).filter(
        FileEntry.project_id == project_id,
        FileEntry.branch_id == branch_id
    ).count()
    
    thread_count = db.query(Thread).filter(
        Thread.project_id == project_id,
        Thread.branch_id == branch_id
    ).count()
    
    dataset_count = db.query(Dataset).filter(
        Dataset.project_id == project_id,
        Dataset.branch_id == branch_id
    ).count()
    
    note_count = db.query(Note).filter(
        Note.project_id == project_id,
        Note.branch_id == branch_id
    ).count()
    
    changelog_count = db.query(ChangelogEntry).filter(
        ChangelogEntry.project_id == project_id,
        ChangelogEntry.branch_id == branch_id
    ).count()
    
    return {
        "id": branch.id,
        "project_id": branch.project_id,
        "name": branch.name,
        "is_default": branch.is_default,
        "statistics": {
            "files": file_count,
            "threads": thread_count,
            "datasets": dataset_count,
            "notes": note_count,
            "changelog_entries": changelog_count
        },
        "created_at": branch.created_at.isoformat() + "Z" if branch.created_at else None
    }


def switch_branch(app, project_id: int, branch_id: int, db: Session) -> Dict[str, Any]:
    """Switch to a different branch."""
    ensure_project_initialized(project_id)
    
    branch = db.query(Branch).filter(
        Branch.id == branch_id,
        Branch.project_id == project_id
    ).first()
    
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    # Record the switch in changelog
    try:
        record_changelog(
            db, project_id, branch_id, "branch.switch",
            {"previous_branch": current_branch(db, project_id).name},
            {"new_branch": branch.name}
        )
    except Exception:
        pass
    
    return {
        "ok": True,
        "branch_id": branch.id,
        "name": branch.name,
        "redirect": f"/project/{project_id}?branch_id={branch.id}&msg=Switched+to+{branch.name}"
    }


def rename_branch(app, project_id: int, branch_id: int, 
                 new_name: str, db: Session) -> Dict[str, Any]:
    """Rename a branch."""
    ensure_project_initialized(project_id)
    
    branch = db.query(Branch).filter(
        Branch.id == branch_id,
        Branch.project_id == project_id
    ).first()
    
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    if branch.name.lower() == "main" or branch.is_default:
        raise HTTPException(status_code=400, detail="Cannot rename main branch")
    
    new_name = new_name.strip()
    if not new_name or new_name.lower() == "main":
        raise HTTPException(status_code=400, detail="Invalid branch name")
    
    # Check for duplicate
    existing = db.query(Branch).filter(
        Branch.project_id == project_id,
        Branch.name == new_name,
        Branch.id != branch_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Branch '{new_name}' already exists")
    
    old_name = branch.name
    branch.name = new_name
    
    try:
        db.commit()
        db.refresh(branch)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to rename branch")
    
    # Add version tracking
    add_version(db, "branch", branch.id, {
        "project_id": project_id,
        "old_name": old_name,
        "new_name": new_name
    })
    
    # Record in changelog
    try:
        record_changelog(
            db, project_id, branch_id, "branch.rename",
            {"old_name": old_name},
            {"new_name": new_name}
        )
    except Exception:
        pass
    
    return {
        "ok": True,
        "branch_id": branch.id,
        "name": branch.name,
        "redirect": f"/project/{project_id}?branch_id={branch_id}&msg=Branch+renamed"
    }


def compare_branches(app, project_id: int, branch1_id: int, 
                    branch2_id: int, db: Session) -> Dict[str, Any]:
    """Compare two branches to show differences."""
    ensure_project_initialized(project_id)
    
    branch1 = db.query(Branch).filter(
        Branch.id == branch1_id,
        Branch.project_id == project_id
    ).first()
    
    branch2 = db.query(Branch).filter(
        Branch.id == branch2_id,
        Branch.project_id == project_id
    ).first()
    
    if not branch1 or not branch2:
        raise HTTPException(status_code=404, detail="One or both branches not found")
    
    # Compare files
    files1 = set(db.query(FileEntry.display_name).filter(
        FileEntry.project_id == project_id,
        FileEntry.branch_id == branch1_id
    ).all())
    
    files2 = set(db.query(FileEntry.display_name).filter(
        FileEntry.project_id == project_id,
        FileEntry.branch_id == branch2_id
    ).all())
    
    files_only_in_1 = files1 - files2
    files_only_in_2 = files2 - files1
    files_in_both = files1 & files2
    
    # Compare datasets
    datasets1 = set(db.query(Dataset.name).filter(
        Dataset.project_id == project_id,
        Dataset.branch_id == branch1_id
    ).all())
    
    datasets2 = set(db.query(Dataset.name).filter(
        Dataset.project_id == project_id,
        Dataset.branch_id == branch2_id
    ).all())
    
    datasets_only_in_1 = datasets1 - datasets2
    datasets_only_in_2 = datasets2 - datasets1
    datasets_in_both = datasets1 & datasets2
    
    return {
        "branch1": {
            "id": branch1.id,
            "name": branch1.name
        },
        "branch2": {
            "id": branch2.id,
            "name": branch2.name
        },
        "comparison": {
            "files": {
                "only_in_branch1": [f[0] for f in files_only_in_1],
                "only_in_branch2": [f[0] for f in files_only_in_2],
                "in_both": [f[0] for f in files_in_both]
            },
            "datasets": {
                "only_in_branch1": [d[0] for d in datasets_only_in_1],
                "only_in_branch2": [d[0] for d in datasets_only_in_2],
                "in_both": [d[0] for d in datasets_in_both]
            }
        }
    }


