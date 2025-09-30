"""
ResearchAgent - Extracted from specialized_agents.py

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

# Configure logging

class ResearchAgent:
    """Agent that performs web searches using GPT's web search capabilities"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Run web search and return relevant sites and content"""
        start_time = time.time()
        logger.info(f"[ResearchAgent] Starting web research for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: ResearchAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result=f"**Agent Failure Report:**\n\nThe Research Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to perform web research. Without it, no research is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot perform research",
                summary="Research Agent failed: No LLM configured"
            )
        
        try:
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[ResearchAgent] Using model: {model}")
            
            # Research using structured JSON schema
            completion_params = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a research assistant with web search capabilities.
                        You must respond ONLY with valid JSON matching this schema:
                        {
                            "sources": [
                                {
                                    "title": "source title",
                                    "url_or_reference": "URL or citation",
                                    "key_findings": "main findings from this source",
                                    "relevance": "why this source matters"
                                }
                            ],
                            "synthesis": "comprehensive summary integrating all sources",
                            "key_insights": ["insight 1", "insight 2"],
                            "confidence_notes": "any limitations or caveats",
                            "summary": "brief executive summary for logging"
                        }
                        
                        Provide at least 3-5 relevant sources with concrete findings."""
                    },
                    {"role": "user", "content": f"Research this topic and find relevant sources: {task}"}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            raw_content = response.choices[0].message.content.strip()
            
            # Parse JSON response - fail fast if invalid
            research_data = json.loads(raw_content)
            
            logger.info(f"[ResearchAgent] Completed research in {time.time() - start_time:.3f}s")
            
            # Format sources
            sources_text = ""
            if research_data.get("sources"):
                sources_text = "\n\n**Sources:**\n"
                for idx, source in enumerate(research_data["sources"], 1):
                    sources_text += f"{idx}. **{source.get('title', 'Unknown')}**\n"
                    if source.get('url_or_reference'):
                        sources_text += f"   - Reference: {source['url_or_reference']}\n"
                    sources_text += f"   - Findings: {source.get('key_findings', 'N/A')}\n"
                    if source.get('relevance'):
                        sources_text += f"   - Relevance: {source['relevance']}\n"
                    sources_text += "\n"
            
            # Format key insights
            insights_text = ""
            if research_data.get("key_insights"):
                insights_text = "\n**Key Insights:**\n"
                for insight in research_data["key_insights"]:
                    insights_text += f"- {insight}\n"
            
            synthesis = research_data.get("synthesis", "No synthesis available")
            confidence_notes = research_data.get("confidence_notes", "")
            summary = research_data.get("summary", "Research completed")
            
            formatted_output = f"""Answer: Web Research Results

{synthesis}
{insights_text}
{sources_text}
{f'**Caveats:** {confidence_notes}' if confidence_notes else ''}

Why: Conducted web research to find relevant sources and synthesize information"""
            
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result=formatted_output,
                confidence=0.75,
                method="Web search and research",
                explanation="Found and analyzed relevant web sources",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[ResearchAgent] Error: {e}")
            return AgentResult(
                agent_name="ResearchAgent",
                display_name="Research Agent",
                result=f"Answer: Research failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Research error"
            )
