#!/usr/bin/env python3
"""
Integration script to wire the new thinker-orchestrator flow into the existing Cedar app.
This replaces the old ws_chat.py implementation with the new one.
"""

import os
import shutil
from pathlib import Path

def integrate():
    """Integrate new flow into existing app"""
    project_root = Path(__file__).parent
    
    print("Integration Script for New Thinker-Orchestrator Flow")
    print("=" * 60)
    
    # Backup old ws_chat.py if it exists
    old_ws_chat = project_root / "ws_chat.py"
    if old_ws_chat.exists():
        backup_path = project_root / "ws_chat_old_backup.py"
        print(f"✓ Backing up old ws_chat.py to {backup_path.name}")
        shutil.copy2(old_ws_chat, backup_path)
    
    # Copy new ws_chat to replace old one
    new_ws_chat = project_root / "ws_chat_new.py"
    if new_ws_chat.exists():
        print(f"✓ Replacing ws_chat.py with new implementation")
        shutil.copy2(new_ws_chat, old_ws_chat)
    else:
        print("✗ ws_chat_new.py not found!")
        return False
    
    # Update routing.py or main application file to use new endpoint
    # NOTE: This would need to be customized based on actual app structure
    print("\nTo complete integration, update your main application:")
    print("1. Import the new websocket_endpoint from ws_chat")
    print("2. Replace the WebSocket route with:")
    print("   from ws_chat import websocket_endpoint")
    print("   app.websocket('/ws/chat/{project_id}')(websocket_endpoint)")
    
    print("\nNew modules added:")
    print("  - thinker.py: Analyzes queries and streams thinking process")
    print("  - orchestrator.py: Manages agent execution")
    print("  - agents/: Agent implementations")
    print("    - base_agent.py: Base class for all agents")
    print("    - final.py: Provides final answers")
    print("    - code.py: Generates and executes code")
    print("    - __init__.py: Other agent stubs and registry")
    
    print("\nEnvironment setup:")
    print("  - Ensure OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY is set")
    print("  - The system works without API key for simple arithmetic")
    
    print("\nFrontend updates needed:")
    print("  - Handle new event types:")
    print("    - assistant.thinking_start/chunk/complete")
    print("    - system.orchestration_start")
    print("    - system.agent_result")
    print("    - assistant.result")
    print("    - assistant.final")
    print("    - assistant.question")
    
    print("\n✓ Integration script completed!")
    print("Run 'python3 test_new_flow.py' to test the new flow")
    
    return True

if __name__ == "__main__":
    success = integrate()
    exit(0 if success else 1)