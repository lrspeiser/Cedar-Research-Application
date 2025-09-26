"""
Chat persistence system for managing numbered chats with background processing.
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from pathlib import Path
import threading
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

class ChatManager:
    """Manages persistent numbered chats that continue processing in the background."""
    
    def __init__(self, data_dir: str = "/tmp/cedar_chats"):
        """Initialize the chat manager with a data directory."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.active_chats = {}  # Maps chat_id to processing status
        self.chat_locks = defaultdict(threading.Lock)
        
    def get_next_chat_number(self, project_id: int, branch_id: int) -> int:
        """Get the next sequential chat number for a project/branch."""
        chat_meta_file = self.data_dir / f"project_{project_id}_branch_{branch_id}_meta.json"
        
        with self.chat_locks[f"{project_id}_{branch_id}"]:
            if chat_meta_file.exists():
                with open(chat_meta_file, 'r') as f:
                    meta = json.load(f)
                    next_num = meta.get('next_chat_number', 1)
            else:
                next_num = 1
            
            # Update metadata
            meta = {'next_chat_number': next_num + 1, 'last_updated': datetime.now(timezone.utc).isoformat()}
            with open(chat_meta_file, 'w') as f:
                json.dump(meta, f, indent=2)
                
            return next_num
    
    def get_chat_file_path(self, project_id: int, branch_id: int, chat_number: int) -> Path:
        """Get the file path for a specific chat."""
        return self.data_dir / f"chat_p{project_id}_b{branch_id}_n{chat_number}.json"
    
    def create_chat(self, project_id: int, branch_id: int, thread_id: Optional[int] = None, 
                    title: Optional[str] = None) -> Dict[str, Any]:
        """Create a new numbered chat."""
        chat_number = self.get_next_chat_number(project_id, branch_id)
        
        if not title:
            title = f"Chat {chat_number}"
        
        chat_data = {
            'chat_number': chat_number,
            'project_id': project_id,
            'branch_id': branch_id,
            'thread_id': thread_id,
            'title': title,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'status': 'active',  # active, processing, complete, error
            'messages': [],
            'agent_results': [],
            'metadata': {}
        }
        
        # Save to file
        chat_file = self.get_chat_file_path(project_id, branch_id, chat_number)
        with open(chat_file, 'w') as f:
            json.dump(chat_data, f, indent=2)
        
        # Track as active
        chat_key = f"{project_id}_{branch_id}_{chat_number}"
        self.active_chats[chat_key] = {'status': 'active', 'file': str(chat_file)}
        
        return chat_data
    
    def get_chat(self, project_id: int, branch_id: int, chat_number: int) -> Optional[Dict[str, Any]]:
        """Retrieve a chat by its number."""
        chat_file = self.get_chat_file_path(project_id, branch_id, chat_number)
        
        if not chat_file.exists():
            return None
            
        with self.chat_locks[f"{project_id}_{branch_id}_{chat_number}"]:
            with open(chat_file, 'r') as f:
                return json.load(f)
    
    def update_chat(self, project_id: int, branch_id: int, chat_number: int, 
                    updates: Dict[str, Any]) -> bool:
        """Update a chat with new data."""
        chat_file = self.get_chat_file_path(project_id, branch_id, chat_number)
        
        if not chat_file.exists():
            return False
        
        with self.chat_locks[f"{project_id}_{branch_id}_{chat_number}"]:
            # Load existing data
            with open(chat_file, 'r') as f:
                chat_data = json.load(f)
            
            # Apply updates
            for key, value in updates.items():
                if key == 'messages' and isinstance(value, list):
                    # Append messages rather than replacing
                    chat_data['messages'].extend(value)
                elif key == 'agent_results' and isinstance(value, list):
                    # Append agent results
                    chat_data['agent_results'].extend(value)
                else:
                    chat_data[key] = value
            
            chat_data['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Save back to file
            with open(chat_file, 'w') as f:
                json.dump(chat_data, f, indent=2)
                
        return True
    
    def add_message(self, project_id: int, branch_id: int, chat_number: int, 
                    role: str, content: str, metadata: Optional[Dict] = None) -> bool:
        """Add a single message to a chat."""
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metadata': metadata or {}
        }
        
        return self.update_chat(project_id, branch_id, chat_number, {'messages': [message]})
    
    def list_chats(self, project_id: int, branch_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """List all chats for a project/branch in reverse chronological order."""
        chats = []
        pattern = f"chat_p{project_id}_b{branch_id}_n*.json"
        
        # Find all matching chat files
        for chat_file in sorted(self.data_dir.glob(pattern), reverse=True):
            if len(chats) >= limit:
                break
                
            try:
                with open(chat_file, 'r') as f:
                    chat_data = json.load(f)
                    # Add summary info
                    summary = {
                        'chat_number': chat_data['chat_number'],
                        'title': chat_data['title'],
                        'created_at': chat_data['created_at'],
                        'updated_at': chat_data['updated_at'],
                        'status': chat_data['status'],
                        'message_count': len(chat_data.get('messages', [])),
                        'last_message': chat_data['messages'][-1] if chat_data.get('messages') else None
                    }
                    chats.append(summary)
            except Exception:
                continue
                
        return chats
    
    def get_active_chat(self, project_id: int, branch_id: int) -> Optional[int]:
        """Get the currently active chat number for a project/branch."""
        # Look for the most recently updated chat with 'active' or 'processing' status
        chats = self.list_chats(project_id, branch_id, limit=10)
        for chat in chats:
            if chat['status'] in ['active', 'processing']:
                return chat['chat_number']
        return None
    
    def set_chat_status(self, project_id: int, branch_id: int, chat_number: int, status: str) -> bool:
        """Update the status of a chat (active, processing, complete, error)."""
        return self.update_chat(project_id, branch_id, chat_number, {'status': status})
    
    def cleanup_old_chats(self, days_to_keep: int = 30):
        """Clean up chat files older than specified days."""
        from datetime import timedelta
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        
        for chat_file in self.data_dir.glob("chat_*.json"):
            try:
                with open(chat_file, 'r') as f:
                    chat_data = json.load(f)
                    updated_at = datetime.fromisoformat(chat_data.get('updated_at', ''))
                    if updated_at < cutoff_date:
                        chat_file.unlink()
            except Exception:
                continue
    
    def delete_project_chats(self, project_id: int) -> int:
        """Delete all chat files for a specific project."""
        deleted_count = 0
        
        # Delete all chat files for this project
        pattern = f"chat_p{project_id}_*.json"
        for chat_file in self.data_dir.glob(pattern):
            try:
                chat_file.unlink()
                deleted_count += 1
            except Exception:
                continue
        
        # Also delete metadata files
        meta_pattern = f"project_{project_id}_*.json"
        for meta_file in self.data_dir.glob(meta_pattern):
            try:
                meta_file.unlink()
            except Exception:
                continue
                
        return deleted_count


# Global singleton instance
_chat_manager = None

def get_chat_manager(data_dir: Optional[str] = None) -> ChatManager:
    """Get or create the global chat manager instance."""
    global _chat_manager
    if _chat_manager is None:
        if data_dir is None:
            data_dir = os.getenv('CEDARPY_CHAT_DIR', '/tmp/cedar_chats')
        _chat_manager = ChatManager(data_dir)
    return _chat_manager