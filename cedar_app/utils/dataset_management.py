"""
Dataset management utilities for Cedar app.
Handles dataset CRUD operations and data management.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import HTTPException, Request, Form, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from ..db_utils import _get_project_engine, ensure_project_initialized
from main_models import Dataset, Project, Branch
from main_helpers import current_branch, add_version, ensure_main_branch, branch_filter_ids
from ..changelog_utils import record_changelog


def create_dataset(app, project_id: int, name: str, description: Optional[str], 
                  request: Request, db: Session) -> Dict[str, Any]:
    """Create a new dataset."""
    ensure_project_initialized(project_id)
    
    # Derive branch from query params
    branch_id = request.query_params.get("branch_id")
    try:
        branch_id = int(branch_id) if branch_id is not None else None
    except Exception:
        branch_id = None
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    branch = current_branch(db, project.id, branch_id)
    
    # Clean input
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Dataset name is required")
    
    description = (description or "").strip()
    
    # Check for duplicate name in branch
    existing = db.query(Dataset).filter(
        Dataset.project_id == project_id,
        Dataset.branch_id == branch.id,
        Dataset.name == name
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"Dataset '{name}' already exists in this branch")
    
    # Create dataset
    dataset = Dataset(
        project_id=project.id,
        branch_id=branch.id,
        name=name,
        description=description,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    
    # Add version tracking
    add_version(db, "dataset", dataset.id, {
        "project_id": project.id,
        "branch_id": branch.id,
        "name": name,
        "description": description
    })
    
    # Record in changelog
    try:
        record_changelog(
            db, project.id, branch.id, "dataset.create",
            {"name": name, "description": description},
            {"dataset_id": dataset.id}
        )
    except Exception:
        pass
    
    return {
        "ok": True,
        "dataset_id": dataset.id,
        "name": dataset.name,
        "redirect": f"/project/{project.id}?branch_id={branch.id}&dataset_id={dataset.id}&msg=Dataset+created"
    }


def update_dataset(app, project_id: int, dataset_id: int, 
                  name: Optional[str], description: Optional[str], 
                  db: Session) -> Dict[str, Any]:
    """Update an existing dataset."""
    ensure_project_initialized(project_id)
    
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.project_id == project_id
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Update fields if provided
    updated = False
    old_values = {
        "name": dataset.name,
        "description": dataset.description
    }
    
    if name is not None:
        name = name.strip()
        if name and name != dataset.name:
            # Check for duplicate
            existing = db.query(Dataset).filter(
                Dataset.project_id == project_id,
                Dataset.branch_id == dataset.branch_id,
                Dataset.name == name,
                Dataset.id != dataset_id
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"Dataset '{name}' already exists")
            dataset.name = name
            updated = True
    
    if description is not None:
        description = description.strip()
        if description != dataset.description:
            dataset.description = description
            updated = True
    
    if updated:
        dataset.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(dataset)
        
        # Add version tracking
        add_version(db, "dataset", dataset.id, {
            "project_id": project_id,
            "branch_id": dataset.branch_id,
            "name": dataset.name,
            "description": dataset.description,
            "old_values": old_values
        })
        
        # Record in changelog
        try:
            record_changelog(
                db, project_id, dataset.branch_id, "dataset.update",
                {"dataset_id": dataset_id, "old_values": old_values},
                {"name": dataset.name, "description": dataset.description}
            )
        except Exception:
            pass
    
    return {
        "ok": True,
        "dataset_id": dataset.id,
        "name": dataset.name,
        "description": dataset.description,
        "updated": updated
    }


def delete_dataset(app, project_id: int, dataset_id: int, db: Session) -> Dict[str, Any]:
    """Delete a dataset."""
    ensure_project_initialized(project_id)
    
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.project_id == project_id
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    dataset_name = dataset.name
    branch_id = dataset.branch_id
    
    # Delete the dataset
    db.delete(dataset)
    db.commit()
    
    # Record in changelog
    try:
        record_changelog(
            db, project_id, branch_id, "dataset.delete",
            {"dataset_id": dataset_id, "name": dataset_name},
            {}
        )
    except Exception:
        pass
    
    return {
        "ok": True,
        "message": f"Dataset '{dataset_name}' deleted",
        "redirect": f"/project/{project_id}?branch_id={branch_id}&msg=Dataset+deleted"
    }


def get_dataset(app, project_id: int, dataset_id: int, db: Session) -> Dict[str, Any]:
    """Get dataset details."""
    ensure_project_initialized(project_id)
    
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.project_id == project_id
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    return {
        "id": dataset.id,
        "project_id": dataset.project_id,
        "branch_id": dataset.branch_id,
        "name": dataset.name,
        "description": dataset.description,
        "created_at": dataset.created_at.isoformat() + "Z" if dataset.created_at else None,
        "updated_at": dataset.updated_at.isoformat() + "Z" if dataset.updated_at else None
    }


def list_datasets(app, project_id: int, branch_id: Optional[int], 
                 db: Session) -> List[Dict[str, Any]]:
    """List datasets for a project/branch."""
    ensure_project_initialized(project_id)
    
    # Get branch filter IDs (roll-up logic)
    if branch_id:
        show_branch_ids = branch_filter_ids(db, project_id, branch_id)
    else:
        # Default to main branch if not specified
        main_b = ensure_main_branch(db, project_id)
        show_branch_ids = branch_filter_ids(db, project_id, main_b.id)
    
    datasets = db.query(Dataset).filter(
        Dataset.project_id == project_id,
        Dataset.branch_id.in_(show_branch_ids)
    ).order_by(Dataset.created_at.desc()).all()
    
    result = []
    for d in datasets:
        result.append({
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "branch_id": d.branch_id,
            "created_at": d.created_at.isoformat() + "Z" if d.created_at else None,
            "updated_at": d.updated_at.isoformat() + "Z" if d.updated_at else None
        })
    
    return result


def search_datasets(app, project_id: int, query: str, 
                   branch_id: Optional[int], db: Session) -> List[Dict[str, Any]]:
    """Search datasets by name or description."""
    ensure_project_initialized(project_id)
    
    # Get branch filter IDs
    if branch_id:
        show_branch_ids = branch_filter_ids(db, project_id, branch_id)
    else:
        main_b = ensure_main_branch(db, project_id)
        show_branch_ids = branch_filter_ids(db, project_id, main_b.id)
    
    # Search pattern
    search_pattern = f"%{query}%"
    
    datasets = db.query(Dataset).filter(
        Dataset.project_id == project_id,
        Dataset.branch_id.in_(show_branch_ids),
        db.or_(
            Dataset.name.ilike(search_pattern),
            Dataset.description.ilike(search_pattern)
        )
    ).order_by(Dataset.created_at.desc()).limit(50).all()
    
    result = []
    for d in datasets:
        result.append({
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "branch_id": d.branch_id,
            "created_at": d.created_at.isoformat() + "Z" if d.created_at else None
        })
    
    return result


def clone_dataset(app, project_id: int, dataset_id: int, 
                 new_name: str, target_branch_id: Optional[int], 
                 db: Session) -> Dict[str, Any]:
    """Clone a dataset to a new branch or with a new name."""
    ensure_project_initialized(project_id)
    
    # Get source dataset
    source = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.project_id == project_id
    ).first()
    
    if not source:
        raise HTTPException(status_code=404, detail="Source dataset not found")
    
    # Determine target branch
    if target_branch_id:
        target_branch = db.query(Branch).filter(
            Branch.id == target_branch_id,
            Branch.project_id == project_id
        ).first()
        if not target_branch:
            raise HTTPException(status_code=404, detail="Target branch not found")
    else:
        target_branch = db.query(Branch).filter(
            Branch.id == source.branch_id
        ).first()
    
    # Clean new name
    new_name = (new_name or f"{source.name}_copy").strip()
    
    # Check for duplicate
    existing = db.query(Dataset).filter(
        Dataset.project_id == project_id,
        Dataset.branch_id == target_branch.id,
        Dataset.name == new_name
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"Dataset '{new_name}' already exists in target branch")
    
    # Create clone
    clone = Dataset(
        project_id=project_id,
        branch_id=target_branch.id,
        name=new_name,
        description=f"{source.description or ''} (cloned from {source.name})".strip(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    
    # Add version tracking
    add_version(db, "dataset", clone.id, {
        "project_id": project_id,
        "branch_id": target_branch.id,
        "name": new_name,
        "cloned_from": dataset_id,
        "source_name": source.name
    })
    
    # Record in changelog
    try:
        record_changelog(
            db, project_id, target_branch.id, "dataset.clone",
            {"source_id": dataset_id, "source_name": source.name},
            {"clone_id": clone.id, "clone_name": clone.name}
        )
    except Exception:
        pass
    
    return {
        "ok": True,
        "dataset_id": clone.id,
        "name": clone.name,
        "redirect": f"/project/{project_id}?branch_id={target_branch.id}&dataset_id={clone.id}&msg=Dataset+cloned"
    }