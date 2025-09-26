#!/usr/bin/env python3
"""Test script to verify notes are being saved by the Chief Agent"""

import asyncio
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from main_models import Note

# Database path  
db_path = './.testdata_shell/cedarpy.db'

def check_notes_before():
    """Check how many notes exist before the test"""
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()
    
    count = session.query(Note).count()
    print(f"Notes in database before test: {count}")
    
    if count > 0:
        recent = session.query(Note).order_by(Note.created_at.desc()).first()
        print(f"Most recent note created at: {recent.created_at}")
    
    session.close()
    return count

def check_notes_after(initial_count):
    """Check how many notes exist after the test"""
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()
    
    count = session.query(Note).count()
    print(f"\nNotes in database after test: {count}")
    
    if count > initial_count:
        print(f"✓ {count - initial_count} new note(s) were saved!")
        
        # Show the new notes
        new_notes = session.query(Note).order_by(Note.created_at.desc()).limit(count - initial_count).all()
        for i, note in enumerate(reversed(new_notes), 1):
            print(f"\n--- New Note {i} ---")
            print(f"ID: {note.id}")
            print(f"Created: {note.created_at}")
            print(f"Tags: {note.tags}")
            print(f"Content preview: {note.content[:300] if note.content else '(empty)'}...")
    else:
        print("✗ No new notes were saved")
    
    session.close()

def simulate_agent_results():
    """Create mock agent results to test note saving"""
    from cedar_orchestrator.chief_agent_notes import ChiefAgentNoteTaker
    from types import SimpleNamespace
    
    # Mock agent results
    agent_results = [
        SimpleNamespace(
            agent_name="MathAgent",
            display_name="The Math Agent",
            confidence=0.95,
            method="calculation",
            result="Answer: 42\n\nWhy: The calculation was performed successfully.",
            needs_clarification=False,
            needs_rerun=False
        ),
        SimpleNamespace(
            agent_name="ResearchAgent", 
            display_name="The Research Agent",
            confidence=0.85,
            method="search",
            result="Answer: Found relevant information about the topic.\n\nWhy: Database search completed.",
            needs_clarification=False,
            needs_rerun=False
        )
    ]
    
    # Mock chief decision
    chief_decision = {
        'decision': 'final',
        'selected_agent': 'MathAgent',
        'reasoning': 'The Math Agent provided the most accurate answer',
        'final_answer': 'The answer is 42 based on mathematical calculation.',
        'thinking_process': 'Analyzed both agent responses and selected the math approach.'
    }
    
    # Create database session
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Create note taker (using project_id=1, branch_id=1 for test)
    note_taker = ChiefAgentNoteTaker(project_id=1, branch_id=1, db_session=session)
    
    # Save notes
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        note_id = loop.run_until_complete(
            note_taker.save_agent_notes(
                agent_results=agent_results,
                user_query="What is the answer to life, the universe, and everything?",
                chief_decision=chief_decision
            )
        )
        
        if note_id:
            print(f"\n✓ Successfully saved note with ID: {note_id}")
            session.commit()
        else:
            print("\n✗ Failed to save note (returned None)")
            
    except Exception as e:
        print(f"\n✗ Error saving note: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()
        loop.close()

if __name__ == "__main__":
    print("=== Testing Chief Agent Note Saving ===\n")
    
    # Check initial state
    initial_count = check_notes_before()
    
    # Run the test
    print("\n--- Running note save test ---")
    simulate_agent_results()
    
    # Check final state
    check_notes_after(initial_count)