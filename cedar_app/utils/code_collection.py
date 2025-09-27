"""
Code collection utilities for Cedar app.
Handles collecting and organizing code items from threads for display.
"""

import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from main_models import Thread, ThreadMessage


def collect_code_items(db: Session, project_id: int, threads: List[Thread]) -> List[dict]:
    """
    Collect all code items from thread messages for display in the UI.
    
    Extracts code blocks, tool results, and other structured data from thread messages
    and organizes them for display in the project view.
    
    Args:
        db: Database session
        project_id: Project ID to collect code from
        threads: List of threads to process
    
    Returns:
        List of code item dictionaries with metadata
    """
    code_items = []
    
    for thread in threads:
        # Get all messages for this thread
        messages = db.query(ThreadMessage).filter(
            ThreadMessage.project_id == project_id,
            ThreadMessage.thread_id == thread.id
        ).order_by(ThreadMessage.created_at.asc()).all()
        
        for msg_idx, msg in enumerate(messages):
            # Skip user messages and system messages
            if msg.role in ('user', 'system'):
                continue
                
            # Process non-user, non-system messages (Chief Agent or any sub-agent)
            if str(msg.role or '').lower() not in ('user', 'system'):
                # Check for code in display_title
                if msg.display_title and 'Tool:' in msg.display_title:
                    tool_name = msg.display_title.replace('Tool:', '').strip()
                    
                    # Try to extract code from payload
                    if msg.payload_json:
                        payload = msg.payload_json if isinstance(msg.payload_json, dict) else {}
                        
                        # Handle code tool results
                        if tool_name.lower() == 'code' and 'args' in payload:
                            args = payload.get('args', {})
                            source = args.get('source', '')
                            language = args.get('language', 'python')
                            
                            if source:
                                code_items.append({
                                    'thread_id': thread.id,
                                    'thread_title': thread.title,
                                    'message_id': msg.id,
                                    'message_idx': msg_idx,
                                    'type': 'code',
                                    'language': language,
                                    'content': source,
                                    'timestamp': msg.created_at.isoformat() if msg.created_at else None,
                                    'tool': tool_name,
                                    'result': payload.get('result', {})
                                })
                        
                        # Handle SQL tool results
                        elif tool_name.lower() in ('db', 'sql') and 'args' in payload:
                            args = payload.get('args', {})
                            sql = args.get('sql', '')
                            
                            if sql:
                                code_items.append({
                                    'thread_id': thread.id,
                                    'thread_title': thread.title,
                                    'message_id': msg.id,
                                    'message_idx': msg_idx,
                                    'type': 'sql',
                                    'language': 'sql',
                                    'content': sql,
                                    'timestamp': msg.created_at.isoformat() if msg.created_at else None,
                                    'tool': tool_name,
                                    'result': payload.get('result', {})
                                })
                        
                        # Handle shell/command results
                        elif tool_name.lower() in ('shell', 'command') and 'args' in payload:
                            args = payload.get('args', {})
                            script = args.get('script', '') or args.get('command', '')
                            
                            if script:
                                code_items.append({
                                    'thread_id': thread.id,
                                    'thread_title': thread.title,
                                    'message_id': msg.id,
                                    'message_idx': msg_idx,
                                    'type': 'shell',
                                    'language': 'bash',
                                    'content': script,
                                    'timestamp': msg.created_at.isoformat() if msg.created_at else None,
                                    'tool': tool_name,
                                    'result': payload.get('result', {})
                                })
                
                # Try to extract code from content (markdown code blocks)
                if msg.content:
                    content = str(msg.content)
                    
                    # Look for markdown code blocks
                    import re
                    code_block_pattern = r'```(\w+)?\n(.*?)```'
                    matches = re.findall(code_block_pattern, content, re.DOTALL)
                    
                    for match in matches:
                        language = match[0] or 'text'
                        code = match[1].strip()
                        
                        if code:
                            code_items.append({
                                'thread_id': thread.id,
                                'thread_title': thread.title,
                                'message_id': msg.id,
                                'message_idx': msg_idx,
                                'type': 'markdown_code',
                                'language': language,
                                'content': code,
                                'timestamp': msg.created_at.isoformat() if msg.created_at else None,
                                'tool': None,
                                'result': None
                            })
                    
                    # Also check for inline JSON structures (plans, etc)
                    try:
                        # Try to parse as JSON
                        if content.strip().startswith('{') or content.strip().startswith('['):
                            json_data = json.loads(content)
                            
                            # Check if it's a plan
                            if isinstance(json_data, dict) and 'function' in json_data:
                                if json_data.get('function') == 'plan' and 'steps' in json_data:
                                    code_items.append({
                                        'thread_id': thread.id,
                                        'thread_title': thread.title,
                                        'message_id': msg.id,
                                        'message_idx': msg_idx,
                                        'type': 'plan',
                                        'language': 'json',
                                        'content': json.dumps(json_data, indent=2),
                                        'timestamp': msg.created_at.isoformat() if msg.created_at else None,
                                        'tool': 'plan',
                                        'result': None,
                                        'plan_data': json_data
                                    })
                                elif json_data.get('function') in ('code', 'db', 'shell'):
                                    # Extract code from function calls
                                    args = json_data.get('args', {})
                                    if json_data['function'] == 'code':
                                        source = args.get('source', '')
                                        if source:
                                            code_items.append({
                                                'thread_id': thread.id,
                                                'thread_title': thread.title,
                                                'message_id': msg.id,
                                                'message_idx': msg_idx,
                                                'type': 'code',
                                                'language': args.get('language', 'python'),
                                                'content': source,
                                                'timestamp': msg.created_at.isoformat() if msg.created_at else None,
                                                'tool': json_data['function'],
                                                'result': None
                                            })
                                    elif json_data['function'] == 'db':
                                        sql = args.get('sql', '')
                                        if sql:
                                            code_items.append({
                                                'thread_id': thread.id,
                                                'thread_title': thread.title,
                                                'message_id': msg.id,
                                                'message_idx': msg_idx,
                                                'type': 'sql',
                                                'language': 'sql',
                                                'content': sql,
                                                'timestamp': msg.created_at.isoformat() if msg.created_at else None,
                                                'tool': json_data['function'],
                                                'result': None
                                            })
                    except (json.JSONDecodeError, ValueError):
                        # Not JSON, skip
                        pass
    
    # Sort by timestamp (newest first)
    code_items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    return code_items