"""
DataAgent - Extracted from specialized_agents.py

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

class DataAgent:
    """Agent that analyzes available databases and suggests SQL queries"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        self.project_id = None  # Will be set during processing
        
    async def process(self, task: str, project_id: Optional[int] = None) -> AgentResult:
        """Get database metadata and suggest relevant SQL queries"""
        start_time = time.time()
        logger.info(f"[DataAgent] Analyzing databases for: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: DataAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result=f"**Agent Failure Report:**\n\nThe Data Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to analyze data and suggest SQL queries. Without it, no data analysis is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot analyze data",
                summary="Data Agent failed: No LLM configured"
            )
        
        try:
            # Get database metadata if project_id is provided
            db_metadata = "No specific database context available"
            if project_id:
                try:
                    from cedar_app.db_utils import _project_dirs, _get_project_engine
                    db_path = _project_dirs(project_id)["db_path"]
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        
                        # Get all tables
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tables = cursor.fetchall()
                        
                        db_metadata = "Available tables:\n"
                        for table in tables:
                            table_name = table[0]
                            cursor.execute(f"PRAGMA table_info({table_name})")
                            columns = cursor.fetchall()
                            db_metadata += f"\n- {table_name}: "
                            db_metadata += ", ".join([f"{col[1]} ({col[2]})" for col in columns])
                        
                        conn.close()
                except Exception as e:
                    logger.warning(f"[DataAgent] Could not get database metadata: {e}")
            
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            logger.info(f"[DataAgent] Using model: {model}")
            
            completion_params = {
                "model": model,
                "messages": [
{
                    {
                        "role": "system",
                        "content": build_agent_system_prompt(
                            "DataAgent",
                            AGENT_ROLES.get("DataAgent", "to analyze database schemas and suggest SQL"),
                            """You are a data analysis expert. Based on the available database schema and the user's query, provide analysis.
                        You must respond ONLY with valid JSON matching this schema:
                            "relevant_tables": [
                                {
                                    "table_name": "table_name",
                                    "purpose": "what this table contains",
                                    "relevance": "why it matters for the query"
                                }
                            ],
                            "suggested_queries": [
                                {
                                    "sql": "SELECT ... FROM ...",
                                    "purpose": "what this query does",
                                    "expected_result": "what the result tells us"
                                }
                            ],
                            "analysis": "overall analysis of how to approach the data question",
                            "transformations_needed": ["transformation 1", "transformation 2"],
                            "summary": "brief summary for logging"
                        }
                        
Provide at least 1-3 concrete SQL queries that can be executed."""
                    )
                    },
                    {"role": "user", "content": f"Database Schema:\n{db_metadata}\n\nUser Query: {task}\n\nSuggest relevant SQL queries."}
                ]
            }

            response = await self.llm_client.chat.completions.create(**completion_params)
            raw_content = response.choices[0].message.content.strip()
            
            # Parse JSON response - fail fast if invalid
            data_analysis = json.loads(raw_content)
            
            logger.info(f"[DataAgent] Completed data analysis in {time.time() - start_time:.3f}s")
            
            # Format relevant tables
            tables_text = ""
            if data_analysis.get("relevant_tables"):
                tables_text = "\n**Relevant Tables:**\n"
                for table in data_analysis["relevant_tables"]:
                    tables_text += f"- **{table.get('table_name', 'Unknown')}**: {table.get('purpose', 'N/A')}\n"
                    if table.get('relevance'):
                        tables_text += f"  _Relevance: {table['relevance']}_\n"
            
            # Format suggested queries
            queries_text = ""
            if data_analysis.get("suggested_queries"):
                queries_text = "\n**Suggested SQL Queries:**\n"
                for idx, query in enumerate(data_analysis["suggested_queries"], 1):
                    queries_text += f"\n{idx}. {query.get('purpose', 'Query')}\n"
                    queries_text += f"```sql\n{query.get('sql', 'N/A')}\n```\n"
                    if query.get('expected_result'):
                        queries_text += f"_Expected Result: {query['expected_result']}_\n"
            
            # Format transformations
            transformations_text = ""
            if data_analysis.get("transformations_needed"):
                transformations_text = "\n**Recommended Transformations:**\n"
                for transform in data_analysis["transformations_needed"]:
                    transformations_text += f"- {transform}\n"
            
            analysis = data_analysis.get("analysis", "No analysis available")
            summary = data_analysis.get("summary", "Data analysis completed")
            
            formatted_output = f"""Answer: Database Analysis and SQL Suggestions

{analysis}
{tables_text}
{queries_text}
{transformations_text}

Why: Analyzed available databases and suggested relevant SQL queries"""
            
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result=formatted_output,
                confidence=0.70,
                method="Database analysis and SQL generation",
                explanation="Analyzed schema and suggested queries",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[DataAgent] Error: {e}")
            return AgentResult(
                agent_name="DataAgent",
                display_name="Data Agent",
                result=f"Answer: Data analysis failed\n\nPotential issues: {str(e)}",
                confidence=0.1,
                method="Error",
                explanation="Analysis error"
            )
