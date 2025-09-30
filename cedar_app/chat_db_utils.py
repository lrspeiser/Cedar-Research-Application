"""
Chat database utilities for SQL-based chat storage.

This module provides functions for:
- Creating new chats with sequential numbering
- Adding messages to chats (each message is a separate DB record)
- Querying chat history
- Migrating file-based chats to SQL
- Generating chat summaries and analytics

See README_CHAT_HISTORY_SQL.md for detailed documentation.
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path

from sqlalchemy import func, desc, and_
from sqlalchemy.orm import Session, joinedload

from main_models import Chat, ChatMessage, Project, Branch


def get_next_chat_number(db: Session, project_id: int, branch_id: int) -> int:
    """
    Get the next sequential chat number for a project/branch.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        
    Returns:
        Next available chat number (starts at 1)
    """
    max_num = db.query(func.max(Chat.chat_number)).filter(
        Chat.project_id == project_id,
        Chat.branch_id == branch_id
    ).scalar()
    
    return (max_num or 0) + 1


def create_chat(
    db: Session,
    project_id: int,
    branch_id: int,
    title: Optional[str] = None,
    thread_id: Optional[int] = None,
    status: str = 'active',
    metadata: Optional[Dict[str, Any]] = None
) -> Chat:
    """
    Create a new chat session in the database.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        title: Chat title (defaults to "Chat {number}")
        thread_id: Optional associated thread ID
        status: Chat status (active, processing, complete, error)
        metadata: Optional metadata dictionary
        
    Returns:
        Created Chat object
        
    Raises:
        ValueError: If project/branch doesn't exist
    """
    # Get next chat number
    chat_number = get_next_chat_number(db, project_id, branch_id)
    
    # Default title
    if not title:
        title = f"Chat {chat_number}"
    
    # Create chat
    chat = Chat(
        project_id=project_id,
        branch_id=branch_id,
        chat_number=chat_number,
        thread_id=thread_id,
        title=title,
        status=status,
        metadata_json=metadata or {}
    )
    
    db.add(chat)
    db.commit()
    db.refresh(chat)
    
    print(f"[chat-db] Created chat {chat_number} for project {project_id}, branch {branch_id}")
    
    return chat


def add_message_to_chat(
    db: Session,
    chat_id: int,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    agent_name: Optional[str] = None
) -> ChatMessage:
    """
    Add a message to an existing chat.
    Each message gets a sequential number within the chat.
    
    Args:
        db: Database session
        chat_id: ID of the chat to add message to
        role: Message role (user, assistant, system, agent)
        content: Message content
        metadata: Optional metadata (agent results, prompts, etc.)
        agent_name: Optional name of agent that generated this message
        
    Returns:
        Created ChatMessage object
        
    Raises:
        ValueError: If chat doesn't exist
    """
    # Get the chat
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise ValueError(f"Chat {chat_id} not found")
    
    # Get next sequence number for this chat
    max_seq = db.query(func.max(ChatMessage.sequence_number)).filter(
        ChatMessage.chat_id == chat_id
    ).scalar()
    
    sequence_number = (max_seq or 0) + 1
    
    # Create message
    message = ChatMessage(
        chat_id=chat_id,
        project_id=chat.project_id,
        branch_id=chat.branch_id,
        sequence_number=sequence_number,
        role=role,
        content=content,
        metadata_json=metadata or {},
        agent_name=agent_name
    )
    
    db.add(message)
    
    # Update chat's updated_at timestamp
    chat.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(message)
    
    print(f"[chat-db] Added message {sequence_number} to chat {chat_id} (role: {role})")
    
    return message


def get_chat_by_number(
    db: Session,
    project_id: int,
    branch_id: int,
    chat_number: int,
    include_messages: bool = True
) -> Optional[Chat]:
    """
    Get a chat by its sequential number within a project/branch.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        chat_number: Sequential chat number
        include_messages: Whether to eager-load messages
        
    Returns:
        Chat object or None if not found
    """
    query = db.query(Chat).filter(
        Chat.project_id == project_id,
        Chat.branch_id == branch_id,
        Chat.chat_number == chat_number
    )
    
    if include_messages:
        query = query.options(joinedload(Chat.messages))
    
    return query.first()


def get_chat_messages(
    db: Session,
    chat_id: int,
    limit: Optional[int] = None,
    offset: int = 0
) -> List[ChatMessage]:
    """
    Get messages for a chat, ordered by sequence number.
    
    Args:
        db: Database session
        chat_id: Chat ID
        limit: Maximum number of messages to return
        offset: Number of messages to skip
        
    Returns:
        List of ChatMessage objects
    """
    query = db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat_id
    ).order_by(ChatMessage.sequence_number.asc())
    
    if offset:
        query = query.offset(offset)
    
    if limit:
        query = query.limit(limit)
    
    return query.all()


def list_chats(
    db: Session,
    project_id: int,
    branch_id: int,
    limit: int = 50,
    status: Optional[str] = None,
    include_message_count: bool = True
) -> List[Dict[str, Any]]:
    """
    List chats for a project/branch with summary info.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        limit: Maximum number of chats to return
        status: Filter by status (optional)
        include_message_count: Whether to include message counts
        
    Returns:
        List of chat summary dictionaries
    """
    query = db.query(Chat).filter(
        Chat.project_id == project_id,
        Chat.branch_id == branch_id
    )
    
    if status:
        query = query.filter(Chat.status == status)
    
    query = query.order_by(Chat.created_at.desc()).limit(limit)
    
    chats = query.all()
    
    result = []
    for chat in chats:
        summary = {
            'id': chat.id,
            'chat_number': chat.chat_number,
            'title': chat.title,
            'status': chat.status,
            'thread_id': chat.thread_id,
            'created_at': chat.created_at.isoformat() + 'Z',
            'updated_at': chat.updated_at.isoformat() + 'Z',
            'metadata': chat.metadata_json or {}
        }
        
        if include_message_count:
            count = db.query(func.count(ChatMessage.id)).filter(
                ChatMessage.chat_id == chat.id
            ).scalar()
            summary['message_count'] = count
        
        result.append(summary)
    
    return result


def update_chat_status(
    db: Session,
    chat_id: int,
    status: str
) -> bool:
    """
    Update the status of a chat.
    
    Args:
        db: Database session
        chat_id: Chat ID
        status: New status (active, processing, complete, error)
        
    Returns:
        True if updated, False if chat not found
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        return False
    
    chat.status = status
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    print(f"[chat-db] Updated chat {chat_id} status to {status}")
    return True


def get_active_chat(
    db: Session,
    project_id: int,
    branch_id: int
) -> Optional[Chat]:
    """
    Get the most recently active chat for a project/branch.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        
    Returns:
        Chat object or None
    """
    return db.query(Chat).filter(
        Chat.project_id == project_id,
        Chat.branch_id == branch_id,
        Chat.status.in_(['active', 'processing'])
    ).order_by(Chat.updated_at.desc()).first()


def search_chat_messages(
    db: Session,
    project_id: int,
    branch_id: int,
    search_text: str,
    role: Optional[str] = None,
    agent_name: Optional[str] = None,
    limit: int = 100
) -> List[Tuple[Chat, ChatMessage]]:
    """
    Search for messages containing specific text.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        search_text: Text to search for in message content
        role: Optional role filter
        agent_name: Optional agent name filter
        limit: Maximum results
        
    Returns:
        List of (Chat, ChatMessage) tuples
    """
    query = db.query(Chat, ChatMessage).join(
        ChatMessage, Chat.id == ChatMessage.chat_id
    ).filter(
        Chat.project_id == project_id,
        Chat.branch_id == branch_id,
        ChatMessage.content.contains(search_text)
    )
    
    if role:
        query = query.filter(ChatMessage.role == role)
    
    if agent_name:
        query = query.filter(ChatMessage.agent_name == agent_name)
    
    query = query.order_by(ChatMessage.created_at.desc()).limit(limit)
    
    return query.all()


def migrate_file_based_chat_to_sql(
    db: Session,
    project_id: int,
    branch_id: int,
    chat_file_path: str
) -> Optional[Chat]:
    """
    Migrate a file-based chat (JSON) to SQL storage.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        chat_file_path: Path to the JSON chat file
        
    Returns:
        Created Chat object or None on error
    """
    try:
        with open(chat_file_path, 'r') as f:
            chat_data = json.load(f)
        
        # Check if this chat already exists
        existing = get_chat_by_number(
            db, project_id, branch_id, 
            chat_data['chat_number'], 
            include_messages=False
        )
        
        if existing:
            print(f"[chat-migration] Chat {chat_data['chat_number']} already exists, skipping")
            return existing
        
        # Create chat
        chat = Chat(
            project_id=project_id,
            branch_id=branch_id,
            chat_number=chat_data['chat_number'],
            thread_id=chat_data.get('thread_id'),
            title=chat_data.get('title', f"Chat {chat_data['chat_number']}"),
            status=chat_data.get('status', 'complete'),
            created_at=datetime.fromisoformat(chat_data['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(chat_data['updated_at'].replace('Z', '+00:00')),
            metadata_json=chat_data.get('metadata', {})
        )
        
        db.add(chat)
        db.flush()  # Get chat.id without committing
        
        # Add messages
        for idx, msg in enumerate(chat_data.get('messages', []), start=1):
            message = ChatMessage(
                chat_id=chat.id,
                project_id=project_id,
                branch_id=branch_id,
                sequence_number=idx,
                role=msg['role'],
                content=msg['content'],
                metadata_json=msg.get('metadata', {}),
                agent_name=msg.get('metadata', {}).get('agent_name'),
                created_at=datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
            )
            db.add(message)
        
        db.commit()
        db.refresh(chat)
        
        print(f"[chat-migration] Migrated chat {chat.chat_number} with {len(chat_data.get('messages', []))} messages")
        
        return chat
        
    except Exception as e:
        print(f"[chat-migration-error] Failed to migrate {chat_file_path}: {e}")
        db.rollback()
        return None


def get_chat_statistics(
    db: Session,
    project_id: int,
    branch_id: int
) -> Dict[str, Any]:
    """
    Get statistics about chats for a project/branch.
    
    Args:
        db: Database session
        project_id: Project ID
        branch_id: Branch ID
        
    Returns:
        Dictionary with chat statistics
    """
    total_chats = db.query(func.count(Chat.id)).filter(
        Chat.project_id == project_id,
        Chat.branch_id == branch_id
    ).scalar()
    
    total_messages = db.query(func.count(ChatMessage.id)).filter(
        ChatMessage.project_id == project_id,
        ChatMessage.branch_id == branch_id
    ).scalar()
    
    status_counts = dict(
        db.query(Chat.status, func.count(Chat.id)).filter(
            Chat.project_id == project_id,
            Chat.branch_id == branch_id
        ).group_by(Chat.status).all()
    )
    
    role_counts = dict(
        db.query(ChatMessage.role, func.count(ChatMessage.id)).filter(
            ChatMessage.project_id == project_id,
            ChatMessage.branch_id == branch_id
        ).group_by(ChatMessage.role).all()
    )
    
    return {
        'total_chats': total_chats,
        'total_messages': total_messages,
        'status_counts': status_counts,
        'role_counts': role_counts
    }
