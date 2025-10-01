"""
SQLAgent - Extracted from execution_agents.py

Individual agent file created during Phase 3 refactoring.
"""

"""
Execution Agents Module
Contains core agents that execute concrete actions: shell commands, code, and SQL queries

These agents handle:
1. ShellAgent - Executes shell commands on the system
2. CodeAgent - Generates and executes Python code
3. SQLAgent - Creates and executes SQL queries
"""

import os
import time
import json
import math
import re
import sqlite3
import logging
import asyncio
import subprocess
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from openai import AsyncOpenAI
from openai import AsyncOpenAI
from fastapi import WebSocket

# Import AgentResult
from .agent_result import AgentResult
from cedar_orchestrator.cedar_product_preamble import build_agent_system_prompt, AGENT_ROLES

# Configure detailed logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SQLAgent:
    """Agent that uses LLM to write and execute SQL queries, create databases, and manage schemas"""
    
    def __init__(self, llm_client: Optional[AsyncOpenAI]):
        self.llm_client = llm_client
        
    async def process(self, task: str) -> AgentResult:
        """Use LLM to generate SQL for database creation, updates, and queries"""
        start_time = time.time()
        logger.info(f"[SQLAgent] Starting processing for task: {task[:100]}...")
        
        if not self.llm_client:
            error_details = f"""Agent: SQLAgent
Task: {task}
Error: No LLM client configured
API Key Status: {'Not provided' if not os.getenv('OPENAI_API_KEY') else 'Provided but client not initialized'}
Environment Variables: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}, CEDARPY_OPENAI_MODEL={os.getenv('CEDARPY_OPENAI_MODEL', 'NOT SET')}
Suggested Fix: Ensure OPENAI_API_KEY is set in environment and LLM client is properly initialized"""
            
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result=f"**Agent Failure Report:**\n\nThe SQL Agent was unable to process your request due to missing LLM configuration.\n\n**Error Details:**\n{error_details}\n\n**What the Chief Agent should know:**\nThis agent requires an LLM to generate SQL queries. Without it, no SQL generation is possible.",
                confidence=0.0,
                method="Configuration Error",
                explanation="LLM client not available - cannot generate SQL",
                summary="SQL Agent failed: No LLM configured"
            )
        
        # Check if this is actually a SQL/database task
        if not any(word in task.lower() for word in ["sql", "database", "table", "select", "query", "create", "insert", "update", "delete", "alter", "index"]):
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result="Not a database query task",
                confidence=0.1,
                method="Task mismatch",
                explanation="This doesn't appear to be a database-related task."
            )
        
        try:
            # Get model from environment
            model = os.getenv("CEDARPY_OPENAI_MODEL") or os.getenv("OPENAI_API_KEY_MODEL") or "gpt-5"
            # Ask LLM to write SQL query
            logger.info(f"[SQLAgent] Requesting SQL generation from LLM using model: {model}")
            completion_params = {
                "model": model,
                "messages": [
{
                    {
                        "role": "system",
                        "content": build_agent_system_prompt(
                            "SQLAgent",
                            AGENT_ROLES.get("SQLAgent", "to generate and manage SQL for databases"),
                            """You are a SQL expert.
You MUST respond with VALID JSON in this EXACT format:
{
  "answer": "Complete formatted response explaining the SQL and what it does. Use markdown. This is displayed AS-IS.",
  "sql": "executable_sql_statements_here",
  "operation_type": "CREATE_TABLE | SELECT | INSERT | UPDATE | DELETE | ALTER_TABLE | CREATE_INDEX | CREATE_DATABASE",
  "summary": "Brief 1-sentence description for logging"
}

IMPORTANT:
- 'answer' field: YOU format it with markdown - explain what the SQL does, displayed AS-IS
- 'sql' field: Our code will EXTRACT and EXECUTE this SQL (no markdown fences, just SQL)
- 'operation_type' field: Type of SQL operation
- 'summary' field: Brief summary for logs
- No text outside the JSON object

SQL CAPABILITIES:
- CREATE DATABASE statements for new databases
- CREATE TABLE with proper schemas and constraints
- INSERT, UPDATE, DELETE for data manipulation
- SELECT queries with JOINs, aggregations, subqueries
- ALTER TABLE for schema modifications
- CREATE INDEX for performance optimization

AVAILABLE TABLES:
The project database includes a 'notes' table:
CREATE TABLE notes (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  branch_id INTEGER NOT NULL,
  content TEXT NOT NULL,
  tags JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

REQUIREMENTS:
- Use SQLite/PostgreSQL compatible syntax
- Include proper constraints (PRIMARY KEY, FOREIGN KEY, NOT NULL, UNIQUE)
- For queries on notes table, you can search content, filter by tags, etc.

Example response:
{
  "answer": "**Query to find recent notes**\n\nThis SELECT query retrieves the 10 most recent notes, ordered by creation date.",
  "sql": "SELECT * FROM notes ORDER BY created_at DESC LIMIT 10;",
  "operation_type": "SELECT",
  "summary": "Query for 10 most recent notes"
}"""
                    )
                    },
                    {"role": "user", "content": task}
                ]
            }
            
            response = await self.llm_client.chat.completions.create(**completion_params)
            
            full_response = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                response_data = json.loads(full_response)
            except json.JSONDecodeError as e:
                logger.error(f"[SQLAgent] Failed to parse JSON response: {e}")
                logger.error(f"[SQLAgent] Raw response: {full_response[:500]}")
                return AgentResult(
                    agent_name="SQLAgent",
                    display_name="SQL Agent",
                    result=f"**JSON Parse Error:**\n\nThe LLM returned invalid JSON.\n\n**Error:** {e}\n\n**Raw Response (truncated):**\n```\n{full_response[:500]}\n```",
                    confidence=0.1,
                    method="JSON parse error",
                    explanation="LLM did not return valid JSON",
                    summary="Failed to parse LLM response as JSON"
                )
            
            # Extract fields from JSON
            answer = response_data.get('answer', '').strip()
            generated_sql = response_data.get('sql', '').strip()
            operation_type = response_data.get('operation_type', 'SQL Operation').strip()
            summary = response_data.get('summary', '').strip()
            
            if not generated_sql:
                return AgentResult(
                    agent_name="SQLAgent",
                    display_name="SQL Agent",
                    result="**Missing SQL:**\n\nThe LLM response did not include executable SQL in the 'sql' field.",
                    confidence=0.1,
                    method="Missing sql field",
                    explanation="No SQL provided by LLM",
                    summary="No SQL generated"
                )
            
            if not summary:
                summary = f"Generated {operation_type} SQL for: {task[:100]}"
            
            logger.info(f"[SQLAgent] Generated SQL: {generated_sql}")
            logger.info(f"[SQLAgent] Operation type: {operation_type}")
            logger.info(f"[SQLAgent] LLM-provided answer:\n{answer[:200]}...")
            
            # Build formatted output: LLM's answer + SQL code block
            formatted_output = answer  # Use LLM's pre-formatted answer AS-IS
            formatted_output += f"\n\n**Generated SQL:**\n```sql\n{generated_sql}\n```"
            
            # Determine confidence based on operation type
            if operation_type in ['CREATE_TABLE', 'CREATE_DATABASE', 'CREATE_INDEX']:
                confidence = 0.9
            else:
                confidence = 0.85
            
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result=formatted_output,
                confidence=confidence,
                method=f"LLM-generated {operation_type}",
                explanation=f"Generated {operation_type} SQL",
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"[SQLAgent] Error: {e}")
            return AgentResult(
                agent_name="SQLAgent",
                display_name="SQL Agent",
                result=f"Answer: Failed to generate SQL\n\nError: {str(e)}\n\nSuggested Next Steps: Check your query syntax and try again",
                confidence=0.1,
                method="Error",
                explanation=f"SQL generation error: {str(e)[:100]}"
            )

# Export the execution agents
__all__ = ['AgentResult', 'ShellAgent', 'CodeAgent', 'SQLAgent']
