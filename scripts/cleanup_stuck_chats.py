#!/usr/bin/env python3
"""
Utility script to clean up stuck chat sessions.

Finds any chats that are stuck in 'processing' status and marks them as 'error'.
This can happen when:
- The WebSocket connection is lost during processing
- The orchestration crashes without proper cleanup
- The application is force-stopped while processing

Usage:
    python scripts/cleanup_stuck_chats.py
    
Or to run for a specific project:
    python scripts/cleanup_stuck_chats.py --project-id 1 --branch-id 1
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

def cleanup_stuck_chats(chat_dir: str, project_id: int = None, branch_id: int = None, max_age_minutes: int = 5):
    """
    Clean up chats stuck in 'processing' status.
    
    Args:
        chat_dir: Directory containing chat JSON files
        project_id: Optional - only clean up chats for specific project
        branch_id: Optional - only clean up chats for specific branch
        max_age_minutes: Only mark chats as error if they've been processing for longer than this
    """
    chat_path = Path(chat_dir)
    if not chat_path.exists():
        print(f"Chat directory does not exist: {chat_dir}")
        return 0
    
    # Build file pattern
    if project_id and branch_id:
        pattern = f"chat_p{project_id}_b{branch_id}_*.json"
    elif project_id:
        pattern = f"chat_p{project_id}_*.json"
    else:
        pattern = "chat_*.json"
    
    print(f"Searching for stuck chats with pattern: {pattern}")
    print(f"Max age threshold: {max_age_minutes} minutes")
    
    cleaned_count = 0
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    
    for chat_file in chat_path.glob(pattern):
        try:
            with open(chat_file, 'r') as f:
                data = json.load(f)
            
            status = data.get('status')
            chat_num = data.get('chat_number')
            proj_id = data.get('project_id')
            br_id = data.get('branch_id')
            updated_at = data.get('updated_at', '')
            
            # Check if stuck in processing
            if status == 'processing':
                # Parse updated timestamp
                try:
                    updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                except:
                    # If we can't parse the time, assume it's old enough to clean
                    updated_time = datetime.min.replace(tzinfo=timezone.utc)
                
                # Only clean up if it's been processing for longer than threshold
                if updated_time < cutoff_time:
                    print(f"\nFound stuck chat:")
                    print(f"  File: {chat_file.name}")
                    print(f"  Project: {proj_id}, Branch: {br_id}, Chat: {chat_num}")
                    print(f"  Status: {status}")
                    print(f"  Last updated: {updated_at}")
                    
                    # Update status to error
                    data['status'] = 'error'
                    data['updated_at'] = datetime.now(timezone.utc).isoformat()
                    
                    # Add system message about cleanup
                    if 'messages' not in data:
                        data['messages'] = []
                    data['messages'].append({
                        'role': 'System',
                        'content': 'Chat was stuck in processing status and automatically marked as error during cleanup',
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'metadata': {'type': 'cleanup_error'}
                    })
                    
                    # Save back to file
                    with open(chat_file, 'w') as f:
                        json.dump(data, f, indent=2)
                    
                    print(f"  ✓ Marked as error")
                    cleaned_count += 1
                else:
                    age_minutes = (datetime.now(timezone.utc) - updated_time).total_seconds() / 60
                    print(f"\nSkipping recent processing chat (age: {age_minutes:.1f} minutes):")
                    print(f"  Project: {proj_id}, Branch: {br_id}, Chat: {chat_num}")
        
        except Exception as e:
            print(f"Error processing {chat_file.name}: {e}")
            continue
    
    return cleaned_count

def main():
    parser = argparse.ArgumentParser(description='Clean up stuck chat sessions')
    parser.add_argument('--chat-dir', default='/tmp/cedar_chats',
                       help='Directory containing chat JSON files (default: /tmp/cedar_chats)')
    parser.add_argument('--project-id', type=int, help='Only clean chats for specific project')
    parser.add_argument('--branch-id', type=int, help='Only clean chats for specific branch')
    parser.add_argument('--max-age-minutes', type=int, default=5,
                       help='Only clean chats that have been processing for longer than this (default: 5)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be cleaned without making changes')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Cedar Chat Cleanup Utility")
    print("=" * 60)
    print()
    
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
        print()
    
    cleaned = cleanup_stuck_chats(
        args.chat_dir,
        project_id=args.project_id,
        branch_id=args.branch_id,
        max_age_minutes=args.max_age_minutes
    )
    
    print()
    print("=" * 60)
    print(f"Cleaned up {cleaned} stuck chat(s)")
    print("=" * 60)

if __name__ == '__main__':
    main()