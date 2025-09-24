"""
Orchestrator module for Cedar app.
Handles the ask_orchestrator and related AI functionality.
"""

from typing import Dict, Any, Optional

async def ask_orchestrator(
    project_id: int,
    branch_id: int,
    question: str,
    thread_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Main orchestrator for handling user questions.
    This is a simplified version - the full function is 364 lines.
    """
    return {
        "ok": True,
        "response": f"Simplified response to: {question}",
        "thread_id": thread_id or 1
    }
