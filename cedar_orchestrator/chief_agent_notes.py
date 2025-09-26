"""
Enhanced Chief Agent with automatic note-taking capability
This module extends the Chief Agent to automatically write notes to the SQL database
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class ChiefAgentNoteTaker:
    """Helper class for Chief Agent to manage notes in the SQL database"""
    
    def __init__(self, project_id: int, branch_id: int, db_session: Session):
        self.project_id = project_id
        self.branch_id = branch_id
        self.db = db_session
        
    async def save_agent_notes(self, agent_results: List[Any], user_query: str, chief_decision: Dict[str, Any]) -> Optional[int]:
        """Save notes from agent results to the SQL database"""
        try:
            from main_models import Note
            
            # Check if NotesAgent provided content
            notes_agent_content = None
            for result in agent_results:
                if hasattr(result, 'agent_name') and result.agent_name == "NotesAgent":
                    # Extract the actual notes from the NotesAgent response
                    notes_match = re.search(r'Answer: Notes Created\n\n(.+?)\n\nWhy:', result.result, re.DOTALL)
                    if notes_match:
                        notes_agent_content = notes_match.group(1).strip()
                    break
            
            # Build comprehensive notes from all agent findings
            note_content = self._build_comprehensive_notes(
                user_query=user_query,
                agent_results=agent_results,
                chief_decision=chief_decision,
                notes_agent_content=notes_agent_content
            )
            
            if not note_content:
                return None
                
            # Prepare tags
            tags = self._generate_tags(user_query, chief_decision)
            
            # Create and save the note
            note = Note(
                project_id=self.project_id,
                branch_id=self.branch_id,
                content=note_content,
                tags=tags  # This will be automatically converted to JSON by SQLAlchemy
            )
            
            self.db.add(note)
            self.db.commit()
            
            logger.info(f"[ChiefAgent] Saved note ID {note.id} with {len(tags)} tags")
            return note.id
            
        except Exception as e:
            logger.error(f"[ChiefAgent] Failed to save notes: {e}")
            try:
                self.db.rollback()
            except:
                pass
            return None
    
    def _build_comprehensive_notes(self, user_query: str, agent_results: List[Any], 
                                  chief_decision: Dict[str, Any], 
                                  notes_agent_content: Optional[str]) -> str:
        """Build comprehensive notes from all agent responses"""
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Start with header
        notes = f"## Query Analysis - {timestamp}\n\n"
        notes += f"**User Query:** {user_query}\n\n"
        
        # Add Notes Agent content if available
        if notes_agent_content:
            notes += f"### Structured Notes\n{notes_agent_content}\n\n"
        
        # Add Chief Agent decision summary
        notes += "### Chief Agent Analysis\n"
        notes += f"**Decision:** {chief_decision.get('decision', 'unknown')}\n"
        notes += f"**Selected Agent:** {chief_decision.get('selected_agent', 'unknown')}\n"
        notes += f"**Reasoning:** {chief_decision.get('reasoning', 'No reasoning provided')}\n\n"
        
        # Add key findings from each agent
        notes += "### Agent Findings\n"
        for result in agent_results:
            if not hasattr(result, 'agent_name'):
                continue
                
            # Skip NotesAgent since we already included it above
            if result.agent_name == "NotesAgent":
                continue
                
            notes += f"\n#### {result.display_name}\n"
            notes += f"- **Confidence:** {result.confidence:.2f}\n"
            notes += f"- **Method:** {result.method}\n"
            
            # Extract key findings from the result
            key_finding = self._extract_key_finding(result.result)
            if key_finding:
                notes += f"- **Key Finding:** {key_finding}\n"
        
        # Add final answer if available
        if chief_decision.get('final_answer'):
            notes += f"\n### Final Answer\n{chief_decision['final_answer'][:500]}\n"
            
        # Add any additional guidance for future reference
        if chief_decision.get('additional_guidance'):
            notes += f"\n### Future Guidance\n{chief_decision['additional_guidance']}\n"
            
        return notes
    
    def _extract_key_finding(self, result_text: str, max_length: int = 200) -> str:
        """Extract the key finding from an agent's result"""
        # Try to extract the Answer section
        answer_match = re.search(r'Answer:\s*(.+?)(?=\n\n|$)', result_text, re.DOTALL)
        if answer_match:
            finding = answer_match.group(1).strip()
            # Truncate if too long
            if len(finding) > max_length:
                finding = finding[:max_length] + "..."
            return finding
        
        # Fallback: use first line or portion
        lines = result_text.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('Why:'):
                if len(line) > max_length:
                    return line[:max_length] + "..."
                return line
        
        return ""
    
    def _generate_tags(self, user_query: str, chief_decision: Dict[str, Any]) -> List[str]:
        """Generate relevant tags for the note"""
        tags = []
        
        # Add agent-based tags
        selected_agent = chief_decision.get('selected_agent', '')
        if selected_agent and selected_agent != 'combined':
            tags.append(f"agent:{selected_agent.lower().replace(' ', '_')}")
        
        # Add query type tags
        query_lower = user_query.lower()
        if any(word in query_lower for word in ['calculate', 'compute', 'math']):
            tags.append("math")
        if any(word in query_lower for word in ['code', 'program', 'function']):
            tags.append("code")
        if any(word in query_lower for word in ['sql', 'database', 'query']):
            tags.append("database")
        if any(word in query_lower for word in ['research', 'find', 'search']):
            tags.append("research")
        if any(word in query_lower for word in ['plan', 'strategy', 'approach']):
            tags.append("strategy")
        if any(word in query_lower for word in ['explain', 'why', 'how']):
            tags.append("explanation")
            
        # Add decision type
        if chief_decision.get('decision') == 'loop':
            tags.append("iterative")
        else:
            tags.append("direct")
            
        # Add timestamp-based tag
        tags.append(f"date:{datetime.now().strftime('%Y-%m-%d')}")
        
        return tags
    
    async def get_existing_notes(self, limit: int = 10) -> List[str]:
        """Get existing notes for context"""
        try:
            from main_models import Note
            
            notes = self.db.query(Note).filter(
                Note.project_id == self.project_id,
                Note.branch_id == self.branch_id
            ).order_by(Note.created_at.desc()).limit(limit).all()
            
            return [note.content for note in notes]
            
        except Exception as e:
            logger.error(f"[ChiefAgent] Failed to get existing notes: {e}")
            return []


class EnhancedChiefAgentOrchestration:
    """Enhanced orchestration that integrates automatic note-taking"""
    
    @staticmethod
    async def process_with_notes(orchestrator, message: str, websocket, project_id: int, 
                                branch_id: int, db_session: Session, iteration: int = 0):
        """
        Process orchestration with automatic note-taking
        This wraps the standard orchestration to add note persistence
        """
        
        # Run standard orchestration first
        # We need to modify the orchestrate method to return results instead of just sending to websocket
        # For now, we'll hook into the existing flow by monitoring the websocket messages
        
        # Create note taker
        note_taker = ChiefAgentNoteTaker(project_id, branch_id, db_session)
        
        # Get existing notes for context
        existing_notes = await note_taker.get_existing_notes()
        
        # If NotesAgent will be used, provide existing notes
        if orchestrator.notes_agent:
            orchestrator.notes_agent.existing_notes = existing_notes
        
        # Run orchestration (this is a simplified version - in production you'd modify the orchestrate method)
        await orchestrator.orchestrate(message, websocket, iteration)
        
        # Note: In a full implementation, you would modify the orchestrate method to:
        # 1. Return the valid_results and chief_decision
        # 2. Call note_taker.save_agent_notes() after chief decision
        # 3. Include the note ID in the websocket response
        
        return True