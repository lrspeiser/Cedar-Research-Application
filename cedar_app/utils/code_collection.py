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
    Collect all code items from thread messages and SavedCode table for display in the UI.
    Ensures each item has a consistent shape used by the UI (mid/idx/code/created_at/thread_title/language/title).
    """
    code_items: List[Dict[str, Any]] = []

    # Helper to normalize item shape
    def _norm_item(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'mid': raw.get('mid'),
            'idx': int(raw.get('idx', 0)),
            'thread_id': raw.get('thread_id'),
            'thread_title': raw.get('thread_title'),
            'type': raw.get('type') or 'code',
            'language': raw.get('language') or 'text',
            'code': raw.get('code') or raw.get('content') or '',
            'created_at': raw.get('created_at'),
            'title': raw.get('title') or '',
        }

    # Visible branch IDs derived from provided threads
    try:
        branch_ids = list({int(getattr(t, 'branch_id', 0) or 0) for t in (threads or []) if getattr(t, 'branch_id', None) is not None})
        if not branch_ids:
            branch_ids = []
    except Exception:
        branch_ids = []

    # 1) Collect from ThreadMessage records (legacy + ask orchestrator paths)
    for thread in threads:
        messages = db.query(ThreadMessage).filter(
            ThreadMessage.project_id == project_id,
            ThreadMessage.thread_id == thread.id
        ).order_by(ThreadMessage.created_at.asc()).all()
        for msg_idx, msg in enumerate(messages):
            if msg.role in ('user', 'system'):
                continue
            # Payload-based tools
            if str(msg.role or '').lower() not in ('user', 'system'):
                if msg.display_title and 'Tool:' in msg.display_title and msg.payload_json:
                    payload = msg.payload_json if isinstance(msg.payload_json, dict) else {}
                    tool_name = msg.display_title.replace('Tool:', '').strip().lower()
                    if tool_name == 'code' and 'args' in payload:
                        args = payload.get('args', {})
                        src = str(args.get('source') or '')
                        lang = str(args.get('language') or 'python')
                        if src:
                            code_items.append(_norm_item({
                                'mid': msg.id,
                                'idx': msg_idx,
                                'thread_id': thread.id,
                                'thread_title': thread.title,
                                'type': 'code',
                                'language': lang,
                                'code': src,
                                'created_at': getattr(msg, 'created_at', None),
                                'title': (getattr(msg, 'display_title', None) or '').strip() or 'Code snippet',
                            }))
                    elif tool_name in ('db', 'sql') and 'args' in payload:
                        args = payload.get('args', {})
                        sql = str(args.get('sql') or '')
                        if sql:
                            code_items.append(_norm_item({
                                'mid': msg.id,
                                'idx': msg_idx,
                                'thread_id': thread.id,
                                'thread_title': thread.title,
                                'type': 'sql',
                                'language': 'sql',
                                'code': sql,
                                'created_at': getattr(msg, 'created_at', None),
                                'title': 'SQL query',
                            }))
                    elif tool_name in ('shell', 'command') and 'args' in payload:
                        args = payload.get('args', {})
                        script = str(args.get('script') or args.get('command') or '')
                        if script:
                            code_items.append(_norm_item({
                                'mid': msg.id,
                                'idx': msg_idx,
                                'thread_id': thread.id,
                                'thread_title': thread.title,
                                'type': 'shell',
                                'language': 'bash',
                                'code': script,
                                'created_at': getattr(msg, 'created_at', None),
                                'title': 'Shell script',
                            }))
            # Markdown code blocks in content
            if msg.content:
                import re
                matches = re.findall(r'```(\w+)?\n(.*?)```', str(msg.content), re.DOTALL)
                for m in matches:
                    lang = m[0] or 'text'
                    src = (m[1] or '').strip()
                    if src:
                        code_items.append(_norm_item({
                            'mid': msg.id,
                            'idx': msg_idx,
                            'thread_id': thread.id,
                            'thread_title': thread.title,
                            'type': 'markdown_code',
                            'language': lang,
                            'code': src,
                            'created_at': getattr(msg, 'created_at', None),
                            'title': f"{lang} block",
                        }))

    # 2) Collect from SavedCode table (new persisted snippets from Coding Agent)
    try:
        from main_models import SavedCode  # avoid circular imports
        q = db.query(SavedCode).filter(SavedCode.project_id == project_id)
        if branch_ids:
            q = q.filter(SavedCode.branch_id.in_(branch_ids))
        saved = q.order_by(SavedCode.created_at.desc()).limit(500).all()
        for sc in saved:
            code_items.append(_norm_item({
                'mid': sc.id,
                'idx': 0,
                'thread_id': getattr(sc, 'thread_id', None),
                'thread_title': getattr(sc, 'name', None) or 'Saved Code',
                'type': 'code',
                'language': getattr(sc, 'language', None) or 'python',
                'code': getattr(sc, 'code', None) or '',
                'created_at': getattr(sc, 'created_at', None),
                'title': getattr(sc, 'name', None) or 'Saved Code',
            }))
    except Exception:
        # If SavedCode isn't available, skip gracefully
        pass

    # Sort by created_at (newest first); fall back to None-safe key
    def _key(ci: Dict[str, Any]):
        try:
            return ci.get('created_at') or ''
        except Exception:
            return ''
    code_items.sort(key=_key, reverse=True)

    return code_items
