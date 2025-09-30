"""
Resource Indexer Module

Builds indexes of project resources (files, code, databases, notes, images)
for use by the Chief Agent in decision-making.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ResourceIndexer:
    """Builds resource indexes from database"""
    
    @staticmethod
    def build_resource_index(
        db_session,
        project_id: Optional[int],
        branch_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """
        Build a comprehensive index of project resources.
        
        Returns:
            Dictionary with keys: files, code, databases, notes, images
            Returns None if db_session, project_id, or branch_id are missing
        """
        if not (db_session and project_id and branch_id):
            return None
        
        try:
            resources_index = {
                "files": [],
                "code": [],
                "databases": [],
                "notes": [],
                "images": []
            }
            
            # Index files and images
            ResourceIndexer._index_files(
                resources_index, db_session, project_id, branch_id
            )
            
            # Index saved code snippets
            ResourceIndexer._index_code(
                resources_index, db_session, project_id, branch_id
            )
            
            # Index databases/datasets
            ResourceIndexer._index_databases(
                resources_index, db_session, project_id, branch_id
            )
            
            # Index notes
            ResourceIndexer._index_notes(
                resources_index, db_session, project_id, branch_id
            )
            
            logger.info(f"[ResourceIndexer] Built index: "
                       f"{len(resources_index['files'])} files, "
                       f"{len(resources_index['code'])} code snippets, "
                       f"{len(resources_index['databases'])} databases, "
                       f"{len(resources_index['notes'])} notes, "
                       f"{len(resources_index['images'])} images")
            
            return resources_index
            
        except Exception as e:
            logger.warning(f"[ResourceIndexer] Failed to build resource index: {e}")
            return None
    
    @staticmethod
    def _index_files(
        resources_index: Dict[str, List],
        db_session,
        project_id: int,
        branch_id: int
    ):
        """Index files and images from FileEntry"""
        try:
            from main_models import FileEntry
            
            files = db_session.query(FileEntry).filter(
                FileEntry.project_id == int(project_id),
                FileEntry.branch_id == int(branch_id)
            ).order_by(FileEntry.created_at.desc()).limit(1000).all()
            
            for f in files:
                title = (getattr(f, 'ai_title', None) or f.display_name or '').strip() or f.filename
                rec = {
                    "id": f.id,
                    "name": title,
                    "structure": f.structure,
                    "file_type": f.file_type
                }
                resources_index["files"].append(rec)
                
                # Check if it's an image
                ft = (f.file_type or '').lower()
                if (f.structure or '').lower() == 'images' or ft in {
                    "jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff"
                }:
                    resources_index["images"].append({
                        "id": f.id,
                        "name": title
                    })
        except Exception as e:
            logger.warning(f"[ResourceIndexer] Failed to index files: {e}")
    
    @staticmethod
    def _index_code(
        resources_index: Dict[str, List],
        db_session,
        project_id: int,
        branch_id: int
    ):
        """Index saved code snippets"""
        try:
            from main_models import SavedCode
            
            codes = db_session.query(SavedCode).filter(
                SavedCode.project_id == int(project_id),
                SavedCode.branch_id == int(branch_id)
            ).order_by(SavedCode.created_at.desc()).limit(1000).all()
            
            for sc in codes:
                resources_index["code"].append({
                    "id": sc.id,
                    "name": (sc.name or '').strip() or f"Code {sc.id}",
                    "language": getattr(sc, 'language', None)
                })
        except Exception as e:
            logger.warning(f"[ResourceIndexer] Failed to index code: {e}")
    
    @staticmethod
    def _index_databases(
        resources_index: Dict[str, List],
        db_session,
        project_id: int,
        branch_id: int
    ):
        """Index databases/datasets"""
        try:
            from main_models import Dataset
            
            datasets = db_session.query(Dataset).filter(
                Dataset.project_id == int(project_id),
                Dataset.branch_id == int(branch_id)
            ).order_by(Dataset.created_at.desc()).limit(1000).all()
            
            for d in datasets:
                resources_index["databases"].append({
                    "id": d.id,
                    "name": d.name
                })
        except Exception as e:
            logger.warning(f"[ResourceIndexer] Failed to index databases: {e}")
    
    @staticmethod
    def _index_notes(
        resources_index: Dict[str, List],
        db_session,
        project_id: int,
        branch_id: int
    ):
        """Index notes/documentation"""
        try:
            from main_models import ChiefAgentNote
            
            notes = db_session.query(ChiefAgentNote).filter(
                ChiefAgentNote.project_id == int(project_id),
                ChiefAgentNote.branch_id == int(branch_id)
            ).order_by(ChiefAgentNote.created_at.desc()).limit(500).all()
            
            for note in notes:
                resources_index["notes"].append({
                    "id": note.id,
                    "summary": (note.summary or '')[:100],
                    "thread_id": getattr(note, 'thread_id', None)
                })
        except Exception as e:
            logger.warning(f"[ResourceIndexer] Failed to index notes: {e}")
