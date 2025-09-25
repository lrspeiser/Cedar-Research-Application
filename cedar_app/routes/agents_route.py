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
                "name": "Code Executor",
                "internal_name": "CodeAgent",
                "description": "Generates and executes Python code to solve problems",
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
                "prompt": """You are a SQL expert. Generate ONLY the SQL query to solve the given problem.
- Output ONLY the SQL query, no explanations
- Use standard SQL syntax
- The query should be complete and runnable"""
            }
        ]
        
        # Build HTML for agent cards
        agent_cards = []
        for agent in agents:
            card_html = f"""
            <div class="card" style="margin-bottom: 16px;">
                <h3>{escape(agent['name'])}</h3>
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
                <li><strong>Orchestrator receives your message</strong> - The system analyzes your request</li>
                <li><strong>Agents process in parallel</strong> - Multiple agents work simultaneously on your query</li>
                <li><strong>Results are collected</strong> - Each agent provides its answer with confidence score</li>
                <li><strong>Best answer is selected</strong> - The orchestrator chooses the most confident response</li>
                <li><strong>Response is formatted</strong> - The final answer is presented with proper formatting</li>
            </ol>
            <p class="small muted" style="margin-top: 12px;">
                The multi-agent system ensures comprehensive, accurate responses by leveraging different problem-solving approaches.
            </p>
        </div>
        """
        
        return layout("Agents", body)