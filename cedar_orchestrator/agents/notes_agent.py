"""
NotesAgent - Extracted from specialized_agents.py

Individual agent file created during Phase 3 refactoring.
"""

"""
Specialized Agents Module
Contains domain-specific agents for specialized tasks

These agents handle:
1. FormulaAgent - Mathematical derivations from first principles
2. ResearchAgent - Web research and citations
3. StrategyAgent - Strategic planning and coordination
4. DataAgent - Database schema analysis
5. NotesAgent - Documentation and note-taking
6. FileAgent - File downloads and management
"""

import os
import time
import json
import re
import sqlite3
import logging
import urllib.request
import tempfile
import mimetypes
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI

# Import AgentResult from execution_agents
from .agent_result import AgentResult
from cedar_orchestrator.cedar_product_preamble import build_agent_system_prompt, AGENT_ROLES

# Configure logging
logger = logging.getLogger(__name__)

class NotesAgent:
    """Agent that creates and manages structured notes from findings"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        self.existing_notes = []  # Will be populated with existing notes
        
    async def process(self, task: str, content_to_note: str = "", existing_notes: List[str] = None) -> AgentResult:
        """Create notes from content while avoiding duplication"""
        start_time = time.time()
        logger.info(f"[NotesAgent] Creating notes for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: NotesAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result=f"**Agent Failure Report:**\n\nThe Notes Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to create structured notes. Without it, no note creation is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot create notes",
                summary="Notes Agent failed: No LLM configured"
            )
        
        try:
            if existing_notes:
                self.existing_notes = existing_notes
            
            existing_notes_text = "\n".join(self.existing_notes) if self.existing_notes else "No existing notes"
            
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[NotesAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": build_agent_system_prompt(
                            "NotesAgent",
                            AGENT_ROLES.get("NotesAgent", "to create structured notes and documentation"),
                            """You are a note-taking expert. Create concise, well-organized notes.
                        You must respond ONLY with valid JSON matching this schema:
                        {
                            "title": "clear note title",
                            "timestamp": "current date/time or 'auto'",
                            "tags": ["tag1", "tag2", "tag3"],
                            "category": "main category (e.g., research, code, meeting, etc.)",
                            "key_points": [
                                "key point 1",
                                "key point 2"
                            ],
                            "details": "detailed notes in markdown format with headings, bullet points, code blocks, formulas",
                            "action_items": ["action 1", "action 2"],
                            "sources": ["source 1", "source 2"],
                            "new_content_only": true,
                            "summary": "brief summary for logging"
                        }
                        
Ensure notes avoid duplicating existing content and focus on new insights."""
                    )
                    },
                    {"role": "user", "content": f"Existing Notes:\n{existing_notes_text}\n\nContent to create notes from:\n{content_to_note or task}\n\nCreate new notes without duplicating existing ones."}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            raw_content = response.choices[0].message.content.strip()
            
            # Parse JSON response - fail fast if invalid
            notes_data = json.loads(raw_content)
            
            logger.info(f"[NotesAgent] Completed note creation in {time.time() - start_time:.3f}s")
            
            # Format notes output
            title = notes_data.get("title", "Notes")
            timestamp = notes_data.get("timestamp", time.strftime('%Y-%m-%d %H:%M:%S'))
            tags = notes_data.get("tags", [])
            category = notes_data.get("category", "general")
            key_points = notes_data.get("key_points", [])
            details = notes_data.get("details", "No details available")
            action_items = notes_data.get("action_items", [])
            sources = notes_data.get("sources", [])
            summary = notes_data.get("summary", "Notes created")
            
            # Build formatted output
            notes_output = f"# {title}\n\n"
            notes_output += f"**Date:** {timestamp}\n"
            notes_output += f"**Category:** {category}\n"
            if tags:
                notes_output += f"**Tags:** {', '.join(tags)}\n"
            notes_output += "\n---\n\n"
            
            if key_points:
                notes_output += "## Key Points\n"
                for point in key_points:
                    notes_output += f"- {point}\n"
                notes_output += "\n"
            
            notes_output += "## Details\n\n"
            notes_output += f"{details}\n\n"
            
            if action_items:
                notes_output += "## Action Items\n"
                for item in action_items:
                    notes_output += f"- [ ] {item}\n"
                notes_output += "\n"
            
            if sources:
                notes_output += "## Sources\n"
                for source in sources:
                    notes_output += f"- {source}\n"
            
            formatted_output = f"""Answer: Notes Created

{notes_output}

Why: Created structured notes from the provided content, avoiding duplication with existing notes"""
            
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result=formatted_output,
                confidence=0.85,
                method="Intelligent note creation",
                explanation="Created organized notes from findings",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[NotesAgent] Error: {e}")
            return AgentResult(
                agent_name="NotesAgent",
                display_name="Notes Agent",
                result=f"Answer: Note creation failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Note creation error"
            )

# Export the specialized agents
__all__ = ['FormulaAgent', 'ResearchAgent', 'StrategyAgent', 'DataAgent', 'NotesAgent', 'FileAgent']
