#!/usr/bin/env python3
"""
Simplified single-query test for Notes Agent
"""
import asyncio
import json
import time
import logging
import websockets
import sqlite3
from pathlib import Path

# Ultra-verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_single_query():
    project_id = 2
    branch_id = 1
    ws_url = f"ws://localhost:8000/ws/chat/{project_id}"
    db_path = Path.home() / "CedarPyData" / "projects" / str(project_id) / "database.db"
    
    # Check notes before
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notes WHERE branch_id = ?", (branch_id,))
    notes_before = cursor.fetchone()[0]
    conn.close()
    print(f"\n📊 Notes before test: {notes_before}")
    
    print(f"\n🔌 Connecting to: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ Connected!")
            
            # Send query
            message = {
                "type": "message",
                "content": "What is 2+2?",
                "branch_id": branch_id
            }
            
            print(f"\n📤 Sending: {json.dumps(message)}")
            await websocket.send(json.dumps(message))
            
            # Receive responses
            print("\n📥 Receiving responses:")
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=30)
                    data = json.loads(response)
                    
                    response_type = data.get('type')
                    print(f"  - {response_type}: ", end="")
                    
                    if response_type == 'note_saved':
                        print(f"NOTE SAVED! ID={data.get('note_id')}, iteration={data.get('iteration')}")
                    elif response_type == 'final':
                        print("Final response received")
                        break
                    elif response_type == 'error':
                        print(f"ERROR: {data.get('error')}")
                        break
                    else:
                        print(f"{str(data)[:100]}...")
                        
                except asyncio.TimeoutError:
                    print("⏱️ Timeout!")
                    break
                    
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Wait for DB writes
    print("\n⏳ Waiting 3 seconds for DB writes...")
    await asyncio.sleep(3)
    
    # Check notes after
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notes WHERE branch_id = ?", (branch_id,))
    notes_after = cursor.fetchone()[0]
    
    # Get latest note if any
    cursor.execute("""
        SELECT id, substr(content, 1, 200), created_at 
        FROM notes 
        WHERE branch_id = ?
        ORDER BY created_at DESC 
        LIMIT 1
    """, (branch_id,))
    latest_note = cursor.fetchone()
    conn.close()
    
    print(f"\n📊 Notes after test: {notes_after}")
    print(f"📈 Notes added: {notes_after - notes_before}")
    
    if latest_note:
        print(f"\n📝 Latest note:")
        print(f"  ID: {latest_note[0]}")
        print(f"  Created: {latest_note[2]}")
        print(f"  Content: {latest_note[1]}...")
    
    if notes_after > notes_before:
        print("\n✅ SUCCESS: Notes were saved!")
    else:
        print("\n❌ FAILURE: No notes were saved!")

if __name__ == "__main__":
    print("Starting single query test...")
    asyncio.run(test_single_query())