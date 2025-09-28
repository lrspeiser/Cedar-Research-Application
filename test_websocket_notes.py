#!/usr/bin/env python
"""
Comprehensive test to verify notes are saved via websocket agent flow.

This test will:
1. Connect to the websocket for a specific project
2. Send test queries through the websocket
3. Wait for agent responses and note_saved messages
4. Query the database to verify notes were saved
5. Report on all findings
"""

import asyncio
import json
import sqlite3
import websockets
from datetime import datetime, timezone
import logging
import time
import sys
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Test configuration
PROJECT_ID = 2
BRANCH_ID = 1
WEBSOCKET_URL = f"ws://localhost:8000/ws/chat/{PROJECT_ID}"
DATABASE_PATH = "/Users/leonardspeiser/CedarPyData/cedarpy.db"

# Test queries
TEST_QUERIES = [
    "What is 2 + 2?",
    "Tell me about the weather today",
    "Calculate 15 * 7"
]

async def test_websocket_note_saving():
    """Main test function"""
    logging.info("="*60)
    logging.info("WEBSOCKET NOTE SAVING COMPREHENSIVE TEST")
    logging.info("="*60)
    
    # Get initial note count
    initial_notes = get_notes_count()
    logging.info(f"Initial notes in database: {initial_notes}")
    
    results = []
    
    for i, query in enumerate(TEST_QUERIES, 1):
        logging.info(f"\n{'='*40}")
        logging.info(f"TEST {i}: {query}")
        logging.info("="*40)
        
        try:
            # Test single query
            result = await test_single_query(query)
            results.append(result)
            
            # Wait between queries
            if i < len(TEST_QUERIES):
                logging.info("⏳ Waiting 2 seconds before next query...")
                await asyncio.sleep(2)
                
        except Exception as e:
            logging.error(f"❌ Failed to test query '{query}': {e}")
            results.append({"query": query, "success": False, "error": str(e)})
    
    # Final database check
    logging.info(f"\n{'='*60}")
    logging.info("FINAL DATABASE VERIFICATION")
    logging.info("="*60)
    
    final_notes = get_notes_count()
    logging.info(f"Final notes in database: {final_notes}")
    logging.info(f"Notes added during test: {final_notes - initial_notes}")
    
    # Get recent notes
    recent_notes = get_recent_notes(limit=10)
    if recent_notes:
        logging.info(f"\nRecent notes (last {len(recent_notes)}):")
        for note in recent_notes:
            logging.info(f"  ID {note['id']}: {note['preview'][:100]}...")
            logging.info(f"    Type: {note['note_type']}, Agent: {note['agent_name']}")
            logging.info(f"    Created: {note['created_at']}")
    
    # Summary
    logging.info(f"\n{'='*60}")
    logging.info("TEST SUMMARY")
    logging.info("="*60)
    
    successful = sum(1 for r in results if r.get("success", False))
    logging.info(f"✅ Successful queries: {successful}/{len(results)}")
    logging.info(f"📝 Notes saved: {final_notes - initial_notes}")
    
    for result in results:
        status = "✅" if result.get("success") else "❌"
        logging.info(f"  {status} {result['query']}")
        if result.get("note_saved"):
            logging.info(f"      Note saved: Yes")
        elif not result.get("success"):
            logging.info(f"      Error: {result.get('error', 'Unknown')}")

async def test_single_query(query: str) -> Dict[str, Any]:
    """Test a single query through websocket"""
    
    result = {
        "query": query,
        "success": False,
        "messages_received": [],
        "note_saved": False,
        "error": None
    }
    
    try:
        logging.info(f"🔌 Connecting to {WEBSOCKET_URL}")
        
        async with websockets.connect(WEBSOCKET_URL) as websocket:
            logging.info("✅ Connected to websocket")
            
            # Send query using correct message format
            message = json.dumps({
                "type": "message",
                "content": query,
                "branch_id": BRANCH_ID
            })
            
            logging.info(f"📤 Sending: {message}")
            await websocket.send(message)
            
            # Collect responses
            start_time = time.time()
            timeout = 30  # seconds
            
            while time.time() - start_time < timeout:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(response)
                    
                    msg_type = data.get("type", "unknown")
                    result["messages_received"].append(msg_type)
                    
                    logging.info(f"📥 Received {msg_type}: {json.dumps(data, indent=2)[:500]}")
                    
                    # Check for note_saved message
                    if msg_type == "note_saved":
                        result["note_saved"] = True
                        logging.info(f"✅ NOTE SAVED: {data}")
                    
                    # Check for final response
                    if msg_type == "final":
                        result["success"] = True
                        logging.info("✅ Received final response")
                        
                        # Wait a bit more for note_saved message
                        try:
                            response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                            data = json.loads(response)
                            if data.get("type") == "note_saved":
                                result["note_saved"] = True
                                logging.info(f"✅ NOTE SAVED (after final): {data}")
                        except asyncio.TimeoutError:
                            pass
                        
                        break
                        
                except asyncio.TimeoutError:
                    logging.info("⏱️ Timeout waiting for message")
                    break
                except Exception as e:
                    logging.error(f"Error receiving message: {e}")
                    result["error"] = str(e)
                    break
            
            if not result["success"]:
                logging.warning("⚠️ Did not receive final response")
                
    except Exception as e:
        logging.error(f"❌ WebSocket error: {e}")
        result["error"] = str(e)
    
    # Give database time to write
    await asyncio.sleep(1)
    
    return result

def get_notes_count() -> int:
    """Get count of notes in database"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notes WHERE project_id = ?", (PROJECT_ID,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_recent_notes(limit: int = 5) -> List[Dict[str, Any]]:
    """Get recent notes from database"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            id,
            substr(content, 1, 200) as preview,
            note_type,
            agent_name,
            created_at
        FROM notes 
        WHERE project_id = ?
        ORDER BY created_at DESC 
        LIMIT ?
    """, (PROJECT_ID, limit))
    
    columns = [desc[0] for desc in cursor.description]
    notes = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    conn.close()
    return notes

if __name__ == "__main__":
    try:
        asyncio.run(test_websocket_note_saving())
    except KeyboardInterrupt:
        logging.info("\n⚠️ Test interrupted by user")
    except Exception as e:
        logging.error(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()