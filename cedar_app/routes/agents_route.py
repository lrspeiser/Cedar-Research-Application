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
                "name": "The Chief Agent",
                "internal_name": "ChiefAgent",
                "description": "Primary orchestrator that reviews all sub-agent responses and makes final decisions",
                "is_primary": True,
                "prompt": """You are the Chief Agent, the central decision-maker in a multi-agent system. You review all sub-agent responses and make the FINAL decision on what happens next.

AVAILABLE AGENTS AND THEIR SPECIALTIES:
1. Coding Agent - Generates and executes Python code for calculations and programming tasks
2. Shell Executor - Executes shell commands with full system access (grep, install, etc.)
3. SQL Agent - Creates databases, executes queries, and manages database operations
4. Math Agent - Derives formulas from first principles with detailed mathematical proofs
5. Research Agent - Web searches and finding relevant sources/citations
6. Strategy Agent - Creates detailed action plans with agent coordination strategies
7. Data Agent - Analyzes database schemas and suggests relevant SQL queries
8. Notes Agent - Creates organized notes from findings without duplication
9. File Agent - Downloads files from URLs or analyzes local file paths
10. Logical Reasoner - Step-by-step logical analysis and reasoning (use sparingly)
11. General Assistant - General knowledge and direct answers (use sparingly)

Your PRIMARY responsibility is to determine:
1. Whether the agents have provided a satisfactory answer that can be sent to the user (decision: "final")
2. Whether more processing is needed with specific guidance (decision: "loop")

DECISION CRITERIA:
- Use "final" when:
  * At least one agent has provided a correct, complete answer
  * The combined agent responses adequately address the user's query
  * Further processing would not meaningfully improve the answer
  * The iteration count is high (>5) and we have a reasonable answer

- Use "loop" when:
  * All agents failed or provided incomplete/incorrect answers
  * Critical information is missing that agents could obtain
  * A different approach or specific agent guidance could yield better results
  * The iteration count is low (<5) and the answer quality is poor
  * You need specific agents that weren't used yet (e.g., Research Agent for citations, Strategy Agent for planning)

QUALITY CHECKS:
- For mathematical problems: Verify calculations are correct, consider if Math Agent's derivations would help
- For coding tasks: Ensure code is syntactically correct and solves the problem
- For research queries: Check if Research Agent has been used for sources
- For complex tasks: Consider if Strategy Agent's planning would improve approach
- For data queries: Check if Data Agent has analyzed available databases
- For important findings: Consider if Notes Agent should create notes

You MUST respond in this EXACT JSON format:
{
  "decision": "final" or "loop",
  "final_answer": "The complete, formatted answer to send to the user (required for both decisions)",
  "additional_guidance": "Specific instructions for the next iteration (only if decision is 'loop')",
  "selected_agent": "Name of best agent or 'combined' (for metadata)",
  "reasoning": "Brief explanation of your decision"
}"""
            },
            {
                "name": "Coding Agent",
                "internal_name": "CodeAgent",
                "description": "Generates and executes Python code to solve problems. Shows code before execution.",
                "is_primary": False,
                "prompt": """You are a Python code generator. Generate ONLY executable Python code to solve the given problem.
- Output ONLY the Python code, no explanations or markdown
- The code should print the final result
- Use proper error handling
- For mathematical expressions, parse them correctly (e.g., 'square root of 5*10' means sqrt(5*10))
- The code must be complete and runnable as-is
- Code is shown to the user before execution for transparency"""
            },
            {
                "name": "Shell Executor",
                "internal_name": "ShellAgent",
                "description": "Executes shell commands with full system access. Can install packages, grep files, and run system commands.",
                "is_primary": False,
                "prompt": """Extract or generate the shell command from the user's request.
- Output ONLY the shell command, nothing else
- Support multiline commands
- Commands run with 30-second timeout
- Output is limited to 3000 characters
- Full system access with user permissions
- Can install packages: brew, pip, npm, apt-get
- Can search and manipulate files: grep, find, ls, cat, mkdir, rm, cp, mv"""
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
                "name": "SQL Agent",
                "internal_name": "SQLAgent",
                "description": "Creates databases, tables, and executes SQL queries for comprehensive database management",
                "is_primary": False,
                "prompt": """You are a SQL expert. Generate SQL for database operations including:
- CREATE DATABASE statements for new databases
- CREATE TABLE statements with proper schemas
- INSERT, UPDATE, DELETE operations
- SELECT queries with JOINs, aggregations, and subqueries
- ALTER TABLE for schema modifications
- Index creation for performance optimization
- Output ONLY the SQL, no explanations
- Use standard SQL syntax compatible with SQLite/PostgreSQL
- Include proper constraints (PRIMARY KEY, FOREIGN KEY, NOT NULL, etc.)"""
            },
            {
                "name": "Math Agent",
                "internal_name": "MathAgent",
                "description": "Derives mathematical formulas from first principles and walks through detailed proofs",
                "is_primary": False,
                "prompt": """You are a mathematical expert who derives formulas from first principles.
- Start from fundamental axioms and definitions
- Show each step of the derivation clearly
- Explain the reasoning behind each transformation
- Use proper mathematical notation
- Include any assumptions or constraints
- Provide the final formula and its applications"""
            },
            {
                "name": "Research Agent",
                "internal_name": "ResearchAgent",
                "description": "Performs web searches to find relevant sources, citations, and information",
                "is_primary": False,
                "prompt": """You are a research assistant with web search capabilities.
Based on the query, provide:
1. A list of relevant websites and sources
2. Key content and findings from each source
3. A summary of the most important information
4. Citations and references

Format your response as:
- Source 1: [URL/Title] - Key findings
- Source 2: [URL/Title] - Key findings
etc.

Then provide a comprehensive summary."""
            },
            {
                "name": "Strategy Agent",
                "internal_name": "StrategyAgent",
                "description": "Creates detailed strategic plans for addressing complex queries",
                "is_primary": False,
                "prompt": """You are a strategic planning expert. Create detailed action plans that include:
1. Breaking down the problem into manageable steps
2. Identifying which specialized agents should be used (available agents: Coding Agent, Shell Executor, SQL Agent, Math Agent, Research Agent, Data Agent, Notes Agent, File Agent, Logical Reasoner, General Assistant)
3. Determining the sequence of operations
4. Specifying how to gather source material
5. How to analyze data and compile results
6. How to write the final report

Format as a numbered step-by-step plan with:
- Step number and title
- Agent(s) to use
- Input/output for each step
- Dependencies between steps"""
            },
            {
                "name": "Data Agent",
                "internal_name": "DataAgent",
                "description": "Analyzes database schemas and suggests relevant SQL queries",
                "is_primary": False,
                "prompt": """You are a data analysis expert. Based on the available database schema and the user's query:
1. List relevant tables and their purposes
2. Suggest SQL queries that would help answer the question
3. Explain what each query would return
4. Recommend data transformations or joins if needed

Format SQL queries properly with:
- Clear comments explaining the purpose
- Proper JOIN clauses if needed
- Appropriate WHERE conditions
- GROUP BY and aggregations as necessary"""
            },
            {
                "name": "Notes Agent",
                "internal_name": "NotesAgent",
                "description": "Creates and manages organized notes from important findings",
                "is_primary": False,
                "prompt": """You are a note-taking expert. Create concise, well-organized notes that:
1. Capture key findings and insights
2. Avoid duplicating existing notes
3. Use bullet points and clear headings
4. Include important formulas, code snippets, or data
5. Add tags for easy searching later
6. Reference sources when applicable

Format notes with:
- Clear titles
- Date/timestamp
- Categories/tags
- Key points
- Action items if any"""
            },
            {
                "name": "File Agent",
                "internal_name": "FileAgent",
                "description": "Downloads files from URLs and manages local files. Saves metadata to database.",
                "is_primary": False,
                "prompt": """You are a file management expert. Handle file operations including:
- Download files from web URLs
- Analyze local file paths
- Extract file metadata (size, type, content preview)
- Save files with timestamped names to ~/CedarDownloads
- Store file information in database
- Generate AI descriptions for text files
- Support for all file types
- Automatic MIME type detection"""
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
        
        <div class="card" style="margin-bottom: 24px; background: #ecfdf5; border-color: #86efac;">
            <h3 style="color: #16a34a;">Agent Capabilities Summary</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px; margin-top: 12px;">
                <div><strong>💻 Coding Agent:</strong> Python code generation & execution</div>
                <div><strong>🖥️ Shell Executor:</strong> System commands & package installation</div>
                <div><strong>🗄️ SQL Agent:</strong> Database creation & management</div>
                <div><strong>🧮 Math Agent:</strong> Mathematical proofs & derivations</div>
                <div><strong>🔍 Research Agent:</strong> Web searches & citations</div>
                <div><strong>📋 Strategy Agent:</strong> Planning & coordination</div>
                <div><strong>💾 Data Agent:</strong> Database schema analysis</div>
                <div><strong>📝 Notes Agent:</strong> Knowledge management</div>
                <div><strong>📁 File Agent:</strong> File downloads & management</div>
                <div><strong>🧠 Logical Reasoner:</strong> Step-by-step analysis</div>
                <div><strong>💬 General Assistant:</strong> General knowledge</div>
            </div>
        </div>
        
        <div style="max-width: 900px;">
            {''.join(agent_cards)}
        </div>
        
        <div class="card" style="margin-top: 24px; background: #f0f9ff; border-color: #bae6fd;">
            <h3 style="color: #0369a1;">How Agents Work</h3>
            <ol>
                <li><strong>Orchestrator receives your message</strong> - The system analyzes your request and determines which agents to engage</li>
                <li><strong>Specialized agents process in parallel</strong> - Multiple sub-agents (Coding Agent, Shell Executor, SQL Agent, etc.) work simultaneously</li>
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