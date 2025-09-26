"""
Agents route - displays information about the AI agents and their prompts.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from cedar_app.ui_utils import layout
from html import escape

def register_agents_route(app: FastAPI):
    """Register the /agents route on the FastAPI app"""
    
    @app.get("/agents", response_class=HTMLResponse)
    def view_agents():
        """Display the list of agents and their prompts"""
        
        # Define agent information with their system prompts
        agents = [
            {
                "name": "Chief Agent",
                "internal_name": "ChiefAgent",
                "description": "Primary orchestrator that reviews all sub-agent responses and makes final decisions",
                "is_primary": True,
                "prompt": """You are the Chief Agent, responsible for reviewing responses from multiple specialized agents and making the final decision on what to present to the user.

Your responsibilities:
1. Review all agent responses for accuracy and completeness
2. Identify if any agent has provided a satisfactory answer
3. Decide whether to:
   - Present one agent's response as the final answer
   - Combine multiple agent responses into a comprehensive answer
   - Request additional processing with specific guidance
4. Ensure the final response is clear, accurate, and addresses the user's query
5. Prefer concrete, factual answers over vague responses
6. If mathematical: verify calculations are correct
7. If coding: ensure code is syntactically correct and solves the problem

Respond in JSON format:
{
  "decision": "show_result" or "need_more_processing",
  "selected_agent": "agent_name" or "combined",
  "final_answer": "the complete answer to show the user",
  "reasoning": "why you made this decision",
  "additional_guidance": "specific instructions if more processing needed"
}"""
            },
            {
                "name": "Code Executor",
                "internal_name": "CodeAgent",
                "description": "Generates and executes Python code to solve problems",
                "is_primary": False,
                "prompt": """You are a Python code generator. Generate ONLY executable Python code to solve the given problem.
- Output ONLY the Python code, no explanations or markdown
- The code should print the final result
- Use proper error handling
- For mathematical expressions, parse them correctly (e.g., 'square root of 5*10' means sqrt(5*10))
- The code must be complete and runnable as-is"""
            },
            {
                "name": "Logical Reasoner",
                "internal_name": "ReasoningAgent",
                "description": "Uses step-by-step logical reasoning to analyze problems",
                "is_primary": False,
                "prompt": """You are an expert reasoning agent. Solve problems step-by-step.
- Break down complex problems into steps
- Show your work clearly
- For mathematical expressions, parse them correctly (e.g., 'square root of 5*10' means sqrt(5*10), not sqrt(10))
- Provide the final answer clearly
- Be precise and accurate"""
            },
            {
                "name": "General Assistant",
                "internal_name": "GeneralAgent",
                "description": "Provides direct answers to general questions",
                "is_primary": False,
                "prompt": """You are a helpful assistant. Answer questions directly and concisely.
- For mathematical problems, compute the exact answer
- Parse expressions correctly (e.g., 'square root of 5*10' means sqrt(5*10))
- Be accurate and precise
- Give just the answer when appropriate"""
            },
            {
                "name": "SQL Generator",
                "internal_name": "SQLAgent",
                "description": "Generates SQL queries for database operations",
                "is_primary": False,
                "prompt": """You are a SQL expert. Generate ONLY the SQL query to solve the given problem.
- Output ONLY the SQL query, no explanations
- Use standard SQL syntax
- The query should be complete and runnable"""
            }
        ]
        
        # Build HTML for agent cards
        agent_cards = []
        for agent in agents:
            # Add primary indicator if this is the Chief Agent
            primary_badge = ''
            if agent.get('is_primary', False):
                primary_badge = ' <span class="pill" style="background: #fef3c7; color: #92400e; margin-left: 8px;">Primary</span>'
            
            card_html = f"""
            <div class="card" style="margin-bottom: 16px; {'border: 2px solid #fbbf24;' if agent.get('is_primary', False) else ''}">
                <h3>{escape(agent['name'])}{primary_badge}</h3>
                <p class="muted">{escape(agent['description'])}</p>
                <div style="margin-top: 12px;">
                    <strong>Internal Name:</strong> <span class="pill">{escape(agent['internal_name'])}</span>
                </div>
                <details style="margin-top: 12px;">
                    <summary style="cursor: pointer; font-weight: 600;">System Prompt</summary>
                    <pre class="small" style="white-space: pre-wrap; background: #f8fafc; padding: 12px; border-radius: 6px; margin-top: 8px;">{escape(agent['prompt'])}</pre>
                </details>
            </div>
            """
            agent_cards.append(card_html)
        
        # Build the page body
        body = f"""
        <h1>AI Agents</h1>
        <div class="muted" style="margin-bottom: 20px;">
            These specialized agents work together to process your requests in the Cedar chat system.
            Each agent has a specific role and uses a tailored prompt to provide the best possible response.
        </div>
        
        <div style="max-width: 900px;">
            {''.join(agent_cards)}
        </div>
        
        <div class="card" style="margin-top: 24px; background: #f0f9ff; border-color: #bae6fd;">
            <h3 style="color: #0369a1;">How Agents Work</h3>
            <ol>
                <li><strong>Orchestrator receives your message</strong> - The system analyzes your request and determines which agents to engage</li>
                <li><strong>Specialized agents process in parallel</strong> - Multiple sub-agents (Code Executor, Reasoner, etc.) work simultaneously</li>
                <li><strong>Results are collected</strong> - Each agent provides its answer with confidence score and method used</li>
                <li><strong>Chief Agent reviews all responses</strong> - The Chief Agent analyzes all sub-agent results for accuracy and completeness</li>
                <li><strong>Decision is made</strong> - Chief Agent either:
                    <ul style="margin-top: 4px;">
                        <li>Selects the best individual response</li>
                        <li>Combines multiple responses into a comprehensive answer</li>
                        <li>Requests additional processing with specific guidance</li>
                    </ul>
                </li>
                <li><strong>Final answer is delivered</strong> - The approved response is formatted and presented to you</li>
            </ol>
            <p class="small muted" style="margin-top: 12px;">
                The multi-agent system ensures comprehensive, accurate responses by leveraging different problem-solving approaches.
            </p>
        </div>
        """
        
        return layout("Agents", body)