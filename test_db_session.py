#!/usr/bin/env python3
"""
Direct test of db_session creation for Notes Agent
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cedar_app.db_utils import RegistrySessionLocal
from cedar_orchestrator.chief_agent_notes import ChiefAgentNoteTaker
from main_models import Note
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_db_session():
    print("\n" + "="*50)
    print("TESTING DB SESSION CREATION")
    print("="*50)
    
    # Test 1: Can we import RegistrySessionLocal?
    print("\n1. RegistrySessionLocal import:")
    print(f"   Type: {type(RegistrySessionLocal)}")
    print(f"   Module: {RegistrySessionLocal.__module__ if hasattr(RegistrySessionLocal, '__module__') else 'N/A'}")
    
    # Test 2: Can we create a session?
    print("\n2. Creating session:")
    try:
        session = RegistrySessionLocal()
        print(f"   ✅ Session created: {type(session).__name__}")
        print(f"   Session bind: {session.bind}")
        
        # Test 3: Can we query the database?
        print("\n3. Testing database query:")
        try:
            count = session.query(Note).filter(Note.project_id == 2).count()
            print(f"   ✅ Query successful! Notes in project 2: {count}")
        except Exception as e:
            print(f"   ❌ Query failed: {e}")
        
        # Test 4: Can we create a ChiefAgentNoteTaker?
        print("\n4. Creating ChiefAgentNoteTaker:")
        try:
            note_taker = ChiefAgentNoteTaker(project_id=2, branch_id=1, db_session=session)
            print(f"   ✅ ChiefAgentNoteTaker created")
            
            # Test 5: Can we save a note?
            print("\n5. Testing note save:")
            from dataclasses import dataclass
            
            @dataclass
            class FakeAgentResult:
                agent_name: str
                display_name: str
                result: str
                confidence: float
                method: str
                summary: str = ""
            
            fake_result = FakeAgentResult(
                agent_name="TestAgent",
                display_name="Test Agent",
                result="Test result",
                confidence=0.9,
                method="test",
                summary="Test summary"
            )
            
            # Make it async since the method is async
            import asyncio
            
            async def test_save():
                note_id = await note_taker.save_agent_notes(
                    agent_results=[fake_result],
                    user_query="Test query from test_db_session.py",
                    chief_decision={"decision": "final", "selected_agent": "Test", "reasoning": "Testing"}
                )
                return note_id
            
            note_id = asyncio.run(test_save())
            if note_id:
                print(f"   ✅ Note saved with ID: {note_id}")
                
                # Verify it's in the database
                new_count = session.query(Note).filter(Note.project_id == 2).count()
                print(f"   Notes after save: {new_count}")
            else:
                print(f"   ❌ Note save returned None")
                
        except Exception as e:
            print(f"   ❌ ChiefAgentNoteTaker failed: {e}")
            import traceback
            traceback.print_exc()
        
        session.close()
        
    except Exception as e:
        print(f"   ❌ Session creation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_db_session()