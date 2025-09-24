"""
Thinker module - analyzes queries and determines what agents should be used.
Streams its thinking process back to the user in real-time.
"""

import asyncio
import json
from typing import Dict, Any, List, AsyncGenerator, Optional
from dataclasses import dataclass
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)

@dataclass
class ThinkerContext:
    """Context provided to the thinker"""
    query: str
    chat_history: List[Dict[str, Any]]
    files: List[Dict[str, Any]]
    databases: List[Dict[str, Any]]
    notes: List[Dict[str, Any]]
    code_snippets: List[Dict[str, Any]]
    changelog: List[Dict[str, Any]]
    available_agents: List[str]

@dataclass
class ThinkerOutput:
    """Output from the thinker"""
    thinking_notes: str
    suggested_agents: List[str]
    initial_strategy: str
    expected_iterations: int

class Thinker:
    """Analyzes queries and determines processing strategy"""
    
    def __init__(self, openai_client: AsyncOpenAI):
        self.client = openai_client
        self.model = "gpt-4o"  # Using gpt-4o for better reasoning
        
    async def think(self, context: ThinkerContext) -> AsyncGenerator[str, None]:
        """
        Stream thinking process about how to handle the query.
        Yields chunks of text as they're generated.
        """
        # Build the system prompt
        system_prompt = """You are the Thinker, an analytical component that determines how to process user queries.

Your role is to:
1. Analyze the user's query and available context
2. Think through what needs to be done step by step
3. Identify which agents should be involved
4. Explain your reasoning clearly

Available agents and their capabilities:
- plan: Creates structured execution plans
- code: Writes and executes code
- web: Searches and retrieves web content
- file: Reads, writes, and manipulates files
- db: Queries and manipulates databases
- notes: Creates and retrieves notes
- images: Processes and analyzes images
- question: Asks clarifying questions
- final: Provides final answers

Think out loud and explain your reasoning process. Be thorough but concise.
End your thinking with a clear summary of:
1. What agents should be used
2. In what order or combination
3. What the expected outcome should be"""

        # Build the user prompt with context
        user_prompt = f"""Query: {context.query}

Chat History (last 5 messages):
{json.dumps(context.chat_history[-5:] if context.chat_history else [], indent=2)}

Available Files ({len(context.files)}):
{json.dumps([f.get('name', 'unnamed') for f in context.files[:10]], indent=2)}

Available Databases ({len(context.databases)}):
{json.dumps([db.get('name', 'unnamed') for db in context.databases[:10]], indent=2)}

Recent Notes ({len(context.notes)}):
{json.dumps([note.get('title', 'untitled') for note in context.notes[:5]], indent=2)}

Recent Changelog ({len(context.changelog)}):
{json.dumps([change.get('summary', '') for change in context.changelog[:5]], indent=2)}

Think through how to best handle this query."""

        try:
            # Stream the response
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=True,
                temperature=0.7,
                max_tokens=2000
            )
            
            full_response = ""
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_response += text
                    yield text
            
            # Store the full response for later use
            self.last_thinking_notes = full_response
            
        except Exception as e:
            logger.error(f"Error in thinker: {e}")
            yield f"\n\n[Error in thinking process: {str(e)}]"
    
    def parse_thinking_output(self, thinking_notes: str) -> ThinkerOutput:
        """Parse the thinking notes to extract structured information"""
        # Simple parsing - in production, could use more sophisticated parsing
        suggested_agents = []
        
        # Look for agent names mentioned in the thinking
        agent_names = ['plan', 'code', 'web', 'file', 'db', 'notes', 'images', 'question', 'final']
        for agent in agent_names:
            if agent in thinking_notes.lower():
                suggested_agents.append(agent)
        
        # Always include 'final' agent to provide an answer
        if 'final' not in suggested_agents:
            suggested_agents.append('final')
        
        # Determine strategy based on query complexity
        if 'simple' in thinking_notes.lower() or 'straightforward' in thinking_notes.lower() or 'basic' in thinking_notes.lower():
            strategy = "direct_answer"
            iterations = 1
            # For direct answers, prioritize final agent
            if 'final' in suggested_agents:
                suggested_agents.remove('final')
                suggested_agents.insert(0, 'final')
        elif 'complex' in thinking_notes.lower() or 'multiple steps' in thinking_notes.lower():
            strategy = "multi_step"
            iterations = 3
        else:
            strategy = "standard"
            iterations = 2
        
        return ThinkerOutput(
            thinking_notes=thinking_notes,
            suggested_agents=suggested_agents,
            initial_strategy=strategy,
            expected_iterations=iterations
        )
