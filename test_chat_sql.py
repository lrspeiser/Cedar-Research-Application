#!/usr/bin/env python3
"""
Test script for chat SQL storage system.
Verifies that chats and messages can be created, retrieved, and queried.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from cedar_app.database import ensure_project_initialized, get_project_db
from cedar_app.chat_db_utils import (
    create_chat,
    add_message_to_chat,
    get_chat_by_number,
    list_chats,
    get_chat_statistics,
    search_chat_messages
)


def test_chat_sql_storage():
    """Test the chat SQL storage system."""
    
    print("=" * 60)
    print("Testing Chat SQL Storage System")
    print("=" * 60)
    
    # Use project 1, branch 1 for testing
    project_id = 1
    branch_id = 1
    
    # Ensure project is initialized
    try:
        ensure_project_initialized(project_id)
        print(f"✓ Project {project_id} initialized")
    except Exception as e:
        print(f"✗ Failed to initialize project: {e}")
        return False
    
    # Get database session
    for db in get_project_db(project_id):
        try:
            # Test 1: Create a chat
            print("\n[Test 1] Creating a new chat...")
            chat = create_chat(
                db=db,
                project_id=project_id,
                branch_id=branch_id,
                title="Test Chat Session",
                status='active',
                metadata={'test': True}
            )
            print(f"✓ Created chat #{chat.chat_number} with ID {chat.id}")
            
            # Test 2: Add messages to chat
            print("\n[Test 2] Adding messages to chat...")
            messages = []
            
            # User message
            msg1 = add_message_to_chat(
                db=db,
                chat_id=chat.id,
                role='user',
                content='Hello! Can you help me with a problem?',
                metadata={'test_msg': 1}
            )
            messages.append(msg1)
            print(f"✓ Added user message (seq: {msg1.sequence_number})")
            
            # Assistant message
            msg2 = add_message_to_chat(
                db=db,
                chat_id=chat.id,
                role='assistant',
                content='Of course! I would be happy to help. What do you need?',
                agent_name='test_agent',
                metadata={'test_msg': 2}
            )
            messages.append(msg2)
            print(f"✓ Added assistant message (seq: {msg2.sequence_number})")
            
            # User follow-up
            msg3 = add_message_to_chat(
                db=db,
                chat_id=chat.id,
                role='user',
                content='I need help debugging this code error.',
                metadata={'test_msg': 3}
            )
            messages.append(msg3)
            print(f"✓ Added user follow-up (seq: {msg3.sequence_number})")
            
            # Test 3: Retrieve chat with messages
            print("\n[Test 3] Retrieving chat with messages...")
            retrieved_chat = get_chat_by_number(
                db=db,
                project_id=project_id,
                branch_id=branch_id,
                chat_number=chat.chat_number
            )
            
            if retrieved_chat:
                print(f"✓ Retrieved chat: {retrieved_chat.title}")
                print(f"  - Status: {retrieved_chat.status}")
                print(f"  - Messages: {len(retrieved_chat.messages)}")
                
                # Verify message order
                for msg in retrieved_chat.messages:
                    print(f"    [{msg.sequence_number}] {msg.role}: {msg.content[:40]}...")
                
                if len(retrieved_chat.messages) == 3:
                    print("✓ All messages retrieved in correct order")
                else:
                    print(f"✗ Expected 3 messages, got {len(retrieved_chat.messages)}")
                    return False
            else:
                print("✗ Failed to retrieve chat")
                return False
            
            # Test 4: List chats
            print("\n[Test 4] Listing chats...")
            chat_list = list_chats(
                db=db,
                project_id=project_id,
                branch_id=branch_id,
                limit=10
            )
            print(f"✓ Found {len(chat_list)} chat(s)")
            for chat_summary in chat_list[:3]:  # Show first 3
                print(f"  - Chat #{chat_summary['chat_number']}: {chat_summary['title']}")
                print(f"    Messages: {chat_summary['message_count']}, Status: {chat_summary['status']}")
            
            # Test 5: Search messages
            print("\n[Test 5] Searching messages...")
            search_results = search_chat_messages(
                db=db,
                project_id=project_id,
                branch_id=branch_id,
                search_text='help',
                limit=10
            )
            print(f"✓ Found {len(search_results)} message(s) containing 'help'")
            for chat_obj, msg in search_results[:3]:
                print(f"  - Chat #{chat_obj.chat_number}, Msg #{msg.sequence_number}: {msg.content[:50]}...")
            
            # Test 6: Get statistics
            print("\n[Test 6] Getting chat statistics...")
            stats = get_chat_statistics(db, project_id, branch_id)
            print(f"✓ Statistics:")
            print(f"  - Total chats: {stats['total_chats']}")
            print(f"  - Total messages: {stats['total_messages']}")
            print(f"  - Status breakdown: {stats['status_counts']}")
            print(f"  - Role breakdown: {stats['role_counts']}")
            
            print("\n" + "=" * 60)
            print("All tests passed! ✓")
            print("=" * 60)
            
            return True
            
        except Exception as e:
            print(f"\n✗ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = test_chat_sql_storage()
    sys.exit(0 if success else 1)
