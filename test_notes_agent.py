#!/usr/bin/env python3
"""
Comprehensive test for Notes Agent functionality
Tests WebSocket queries, waits for responses, and verifies database notes
"""

import asyncio
import json
import sqlite3
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
import sys
import websockets
from typing import Dict, List, Optional, Any

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_notes_agent.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class NotesAgentTester:
    def __init__(self, project_id: int = 2, branch_id: int = 1):
        self.project_id = project_id
        self.branch_id = branch_id
        self.ws_url = f"ws://localhost:8000/ws/chat/{project_id}"
        self.db_path = Path.home() / "CedarPyData" / "projects" / str(project_id) / "database.db"
        self.test_queries = [
            "What is 2+2?",
            "Calculate the square root of 144",
            "What is the capital of France?",
            "Write a simple Python function to add two numbers"
        ]
        self.results = []
        
    def get_notes_count(self) -> int:
        """Get the current count of notes in the database"""
        logger.debug(f"Checking notes count in database: {self.db_path}")
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM notes WHERE branch_id = ?", (self.branch_id,))
            count = cursor.fetchone()[0]
            conn.close()
            logger.info(f"Current notes count: {count}")
            return count
        except Exception as e:
            logger.error(f"Failed to get notes count: {e}")
            return -1
    
    def get_latest_notes(self, limit: int = 5) -> List[Dict]:
        """Get the latest notes from the database"""
        logger.debug(f"Fetching latest {limit} notes from database")
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, branch_id, content, tags, created_at 
                FROM notes 
                WHERE branch_id = ?
                ORDER BY created_at DESC 
                LIMIT ?
            """, (self.branch_id, limit))
            
            notes = []
            for row in cursor.fetchall():
                notes.append({
                    'id': row[0],
                    'branch_id': row[1],
                    'content': row[2],
                    'tags': json.loads(row[3]) if row[3] else [],
                    'created_at': row[4]
                })
            conn.close()
            
            logger.info(f"Retrieved {len(notes)} notes")
            for note in notes:
                logger.debug(f"Note {note['id']}: {note['content'][:200]}...")
            
            return notes
        except Exception as e:
            logger.error(f"Failed to get latest notes: {e}")
            return []
    
    async def send_query_and_wait(self, query: str, timeout: int = 30) -> Dict[str, Any]:
        """Send a query via WebSocket and wait for the response"""
        logger.info("="*80)
        logger.info(f"SENDING QUERY: {query}")
        logger.info("="*80)
        
        result = {
            'query': query,
            'sent_at': datetime.now(timezone.utc).isoformat(),
            'responses': [],
            'final_response': None,
            'error': None,
            'duration': 0
        }
        
        start_time = time.time()
        
        try:
            logger.debug(f"Connecting to WebSocket: {self.ws_url}")
            async with websockets.connect(self.ws_url) as websocket:
                logger.info("WebSocket connected successfully")
                
                # Send the query
                message = {
                    "type": "message",
                    "content": query,
                    "branch_id": self.branch_id
                }
                
                logger.debug(f"Sending message: {json.dumps(message)}")
                await websocket.send(json.dumps(message))
                logger.info("Query sent, waiting for responses...")
                
                # Wait for responses
                while True:
                    try:
                        response = await asyncio.wait_for(
                            websocket.recv(), 
                            timeout=timeout
                        )
                        
                        response_data = json.loads(response)
                        response_type = response_data.get('type', 'unknown')
                        
                        logger.debug(f"Received {response_type} response: {json.dumps(response_data)[:500]}...")
                        result['responses'].append(response_data)
                        
                        # Log specific response types
                        if response_type == 'action':
                            logger.info(f"  ACTION: {response_data.get('function', 'unknown')}")
                        elif response_type == 'agent_result':
                            agent_name = response_data.get('agent_name', 'unknown')
                            logger.info(f"  AGENT RESULT: {agent_name}")
                            if 'summary' in response_data:
                                logger.debug(f"    Summary: {response_data['summary']}")
                        elif response_type == 'note_saved':
                            logger.info(f"  📝 NOTE SAVED: ID={response_data.get('note_id')}, Iteration={response_data.get('iteration')}")
                        elif response_type == 'final':
                            logger.info("  ✅ FINAL RESPONSE RECEIVED")
                            result['final_response'] = response_data
                            break
                        elif response_type == 'error':
                            logger.error(f"  ❌ ERROR: {response_data.get('error')}")
                            result['error'] = response_data.get('error')
                            break
                        
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout waiting for response after {timeout} seconds")
                        result['error'] = f"Timeout after {timeout} seconds"
                        break
                    except Exception as e:
                        logger.error(f"Error receiving response: {e}")
                        result['error'] = str(e)
                        break
                
                result['duration'] = time.time() - start_time
                logger.info(f"Query completed in {result['duration']:.2f} seconds")
                
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            result['error'] = str(e)
            result['duration'] = time.time() - start_time
        
        return result
    
    async def run_all_tests(self):
        """Run all test queries and verify notes are saved"""
        logger.info("="*80)
        logger.info("STARTING NOTES AGENT COMPREHENSIVE TEST")
        logger.info("="*80)
        
        # Check initial state
        initial_notes_count = self.get_notes_count()
        logger.info(f"Initial notes count: {initial_notes_count}")
        
        # Run each test query
        for i, query in enumerate(self.test_queries, 1):
            logger.info(f"\n{'='*40}")
            logger.info(f"TEST {i}/{len(self.test_queries)}")
            logger.info(f"{'='*40}")
            
            # Get notes count before query
            notes_before = self.get_notes_count()
            
            # Send query and wait for response
            result = await self.send_query_and_wait(query)
            self.results.append(result)
            
            # Wait a bit for database writes to complete
            logger.debug("Waiting 2 seconds for database writes to complete...")
            await asyncio.sleep(2)
            
            # Check notes count after query
            notes_after = self.get_notes_count()
            notes_added = notes_after - notes_before
            
            logger.info(f"Notes before: {notes_before}, after: {notes_after}, added: {notes_added}")
            
            # Check for note_saved messages in responses
            note_saved_count = sum(1 for r in result['responses'] if r.get('type') == 'note_saved')
            logger.info(f"Note saved messages received: {note_saved_count}")
            
            # Verify the result
            if result['error']:
                logger.error(f"❌ Test failed with error: {result['error']}")
            elif not result['final_response']:
                logger.error("❌ Test failed: No final response received")
            elif notes_added == 0:
                logger.warning("⚠️  Test completed but NO NOTES WERE SAVED TO DATABASE")
            else:
                logger.info(f"✅ Test passed: {notes_added} note(s) saved")
            
            # Show latest notes
            if notes_added > 0:
                latest_notes = self.get_latest_notes(notes_added)
                for note in latest_notes:
                    logger.info(f"  Note content preview: {note['content'][:100]}...")
                    logger.debug(f"  Tags: {note['tags']}")
            
            # Small delay between tests
            await asyncio.sleep(1)
        
        # Final summary
        logger.info("\n" + "="*80)
        logger.info("TEST SUMMARY")
        logger.info("="*80)
        
        final_notes_count = self.get_notes_count()
        total_notes_added = final_notes_count - initial_notes_count
        
        logger.info(f"Total queries run: {len(self.test_queries)}")
        logger.info(f"Total notes added: {total_notes_added}")
        logger.info(f"Average notes per query: {total_notes_added / len(self.test_queries):.2f}")
        
        successful = sum(1 for r in self.results if r['final_response'] and not r['error'])
        logger.info(f"Successful queries: {successful}/{len(self.test_queries)}")
        
        # Check for note-saving patterns
        total_note_saved_messages = sum(
            sum(1 for resp in r['responses'] if resp.get('type') == 'note_saved') 
            for r in self.results
        )
        logger.info(f"Total 'note_saved' messages received: {total_note_saved_messages}")
        
        # Show all notes created during test
        if total_notes_added > 0:
            logger.info("\nNotes created during test:")
            all_test_notes = self.get_latest_notes(total_notes_added)
            for i, note in enumerate(all_test_notes, 1):
                logger.info(f"\n  Note {i}:")
                logger.info(f"    Created: {note['created_at']}")
                logger.info(f"    Tags: {note['tags']}")
                logger.info(f"    Content preview: {note['content'][:200]}...")
        else:
            logger.error("\n❌ NO NOTES WERE SAVED DURING THE TEST!")
            logger.error("This indicates the Notes Agent is not working correctly.")
        
        return {
            'total_queries': len(self.test_queries),
            'successful_queries': successful,
            'total_notes_added': total_notes_added,
            'note_saved_messages': total_note_saved_messages,
            'results': self.results
        }

async def main():
    """Main test runner"""
    tester = NotesAgentTester(project_id=2, branch_id=1)
    
    # Ensure the database exists
    if not tester.db_path.exists():
        logger.error(f"Database does not exist at {tester.db_path}")
        logger.error("Make sure the project has been initialized and the server is running")
        return
    
    # Run the tests
    try:
        results = await tester.run_all_tests()
        
        # Save results to file
        results_file = Path('test_notes_agent_results.json')
        with open(results_file, 'w') as f:
            # Convert to JSON-serializable format
            json_results = {
                'test_run': datetime.now(timezone.utc).isoformat(),
                'summary': {
                    'total_queries': results['total_queries'],
                    'successful_queries': results['successful_queries'],
                    'total_notes_added': results['total_notes_added'],
                    'note_saved_messages': results['note_saved_messages']
                }
            }
            json.dump(json_results, f, indent=2)
            logger.info(f"\nResults saved to {results_file}")
        
        # Exit with appropriate code
        if results['total_notes_added'] == 0:
            logger.error("\n❌ TEST FAILED: No notes were saved!")
            sys.exit(1)
        else:
            logger.info(f"\n✅ TEST PASSED: {results['total_notes_added']} notes saved!")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Test failed with exception: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    # Check if server is running
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 8000))
    sock.close()
    
    if result != 0:
        print("❌ Server is not running. Start it with: python server_manager.py start")
        sys.exit(1)
    
    print("Starting Notes Agent test...")
    asyncio.run(main())