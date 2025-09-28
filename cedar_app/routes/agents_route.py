"""
Agents route - displays information about the AI agents and their prompts.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from cedar_app.ui_utils import layout
from html import escape
from typing import Optional

# Dynamic context helpers
from cedar_app.db_utils import _project_dirs, _get_project_engine, ensure_project_initialized
from sqlalchemy.orm import sessionmaker
from main_models import Project, Branch, Thread, ThreadMessage, Dataset
from main_helpers import ensure_main_branch


def register_agents_route(app: FastAPI):
    """Register the /agents route on the FastAPI app"""
    
    @app.get("/agents", response_class=HTMLResponse)
    def view_agents(project_id: Optional[int] = None, branch_id: Optional[int] = None, thread_id: Optional[int] = None):
        """Display the list of agents and their prompts, plus optional dynamic context preview.
        Use query params: /agents?project_id=1&branch_id=1&thread_id=2
        """
        
        # Optional dynamic context preview
        context_card = ""
        try:
            if project_id is not None and int(project_id) > 0:
                ensure_project_initialized(int(project_id))
                eng = _get_project_engine(int(project_id))
                SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
                with SessionLocal() as db:
                    proj = db.query(Project).filter(Project.id == int(project_id)).first()
                    if not proj:
                        raise ValueError("Project not found")
                    # Resolve branch
                    if branch_id is None:
                        b = ensure_main_branch(db, proj.id)
                    else:
                        b = db.query(Branch).filter(Branch.id == int(branch_id), Branch.project_id == proj.id).first() or ensure_main_branch(db, proj.id)
                    # Resolve thread
                    th = None
                    if thread_id is not None:
                        th = db.query(Thread).filter(Thread.id == int(thread_id), Thread.project_id == proj.id).first()
                    if th is None:
                        th = db.query(Thread).filter(Thread.project_id == proj.id, Thread.branch_id == b.id).order_by(Thread.created_at.desc()).first()
                    # Latest user prompt in this thread
                    user_prompt = None
                    if th:
                        um = db.query(ThreadMessage).filter(ThreadMessage.project_id == proj.id, ThreadMessage.thread_id == th.id, ThreadMessage.role == 'user').order_by(ThreadMessage.created_at.desc()).first()
                        user_prompt = (um.content if um else None)
                    # Datasets for this branch
                    datasets = db.query(Dataset).filter(Dataset.project_id == proj.id, Dataset.branch_id == b.id).order_by(Dataset.created_at.desc()).all()
                    ds_links = [
                        {
                            "id": d.id,
                            "name": d.name,
                            "href": f"/project/{proj.id}?branch_id={b.id}&dataset_id={d.id}"
                        }
                        for d in datasets
                    ]
                    # Paths
                    paths = _project_dirs(proj.id)
                    sqlite_path = paths.get("db_path")
                    files_root = paths.get("files_root")
                    uploads_base = f"/uploads/{proj.id}"
                    payload = {
                        "project_id": proj.id,
                        "project_title": proj.title,
                        "branch_id": b.id,
                        "branch_name": b.name,
                        "thread_id": getattr(th, 'id', None),
                        "thread_title": getattr(th, 'title', None),
                        "user_query": (user_prompt[:500] + ("…" if user_prompt and len(user_prompt) > 500 else "")) if user_prompt else None,
                        "sqlite_path": sqlite_path,
                        "uploads_base": uploads_base,
                        "files_root": files_root,
                        "dataset_links": ds_links,
                    }
                    import json as _json
                    payload_json = escape(_json.dumps(payload, ensure_ascii=False, indent=2))
                    # Pretty dataset links
                    ds_html = ''.join([f"<li><a href='{escape(d['href'])}'>{escape(str(d['name']))}</a></li>" for d in ds_links]) or "<li class='muted small'>(none)</li>"
                    project_link = f"/project/{proj.id}?branch_id={b.id}"
                    context_card = f"""
                    <div class='card' style='margin-bottom:16px; background:#fff7ed; border-color:#fed7aa'>
                      <h3 style='color:#9a3412; margin-top:0'>Dynamic Context Preview</h3>
                      <div class='small muted'>This preview shows what the orchestrator passes to agents when project/thread context is present.</div>
                      <div style='display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; margin-top:12px'>
                        <div>
                          <div><strong>Project:</strong> <a href='{escape(project_link)}'>#{proj.id} – {escape(proj.title)}</a></div>
                          <div><strong>Branch:</strong> #{b.id} – {escape(b.name)}</div>
                          <div><strong>Thread:</strong> {('#'+str(th.id)+' – '+escape(th.title)) if th else '(none)'} </div>
                          <div><strong>SQLite DB:</strong> <code>{escape(sqlite_path or '')}</code></div>
                          <div><strong>Uploads base:</strong> <code>{escape(uploads_base)}</code></div>
                        </div>
                        <div>
                          <div><strong>Datasets (links)</strong></div>
                          <ul style='margin:6px 0 0 18px'>
                            {ds_html}
                          </ul>
                        </div>
                      </div>
                      <details style='margin-top:12px'>
                        <summary style='cursor:pointer; font-weight:600'>Raw context payload</summary>
                        <pre class='small' style='white-space:pre-wrap; background:#f8fafc; padding:12px; border-radius:6px'>{payload_json}</pre>
                      </details>
                    </div>
                    """
        except Exception:
            context_card = ""
        
        # Define agent information with their system prompts
        # ⚠️ IMPORTANT: When updating agent prompts in orchestrator.py, ALSO UPDATE HERE!
        # This page should always reflect the actual prompts being used by the agents.
        agents = [
            {
                "name": "The Chief Agent",
                "internal_name": "ChiefAgent",
                "description": "Primary orchestrator that reviews all sub-agent responses and makes final decisions",
                "is_primary": True,
                "prompt": """You are the Chief Agent - an intelligent orchestrator who analyzes queries and deploys the right agents to get confident, accurate answers.

🎯 YOUR PRIMARY DIRECTIVE:
ASSESS the query complexity, then deploy AS MANY agents as needed to achieve HIGH CONFIDENCE in the answer.

CURRENT ITERATION STATUS:
- Iteration: {iteration + 1} of {max_iterations}
- Remaining loops: {remaining_loops}

You MUST respond in this EXACT JSON format:
{
  "decision": "final" or "loop" or "clarify",
  "query_assessment": "Assess complexity: Is this simple (basic math/facts), moderate (requires research/analysis), or complex (multi-step reasoning/multiple data sources)? What confidence level do we need?",
  "thinking_process": "SPECIFIC to THIS query: 'User asks about X. To get a confident answer, I need Y and Z. I will use [specific agents] because [specific reasons].'",
  "user_facing_message": "Start with the answer/punchline if you have it! Then explain what data was gathered and what might be done next. Be conversational and helpful.",
  "final_answer": "The comprehensive answer to the user's question (only if 'final')",
  "additional_guidance": "SPECIFIC next action: 'Run Coding Agent with THIS specific code' or 'Query SQL for THIS specific data' (only if 'loop')",
  "clarification_question": "SPECIFIC question about ambiguity: 'When you say X, do you mean Y or Z?' (only if 'clarify')",
  "selected_agent": "Single agent name OR 'combined' for multiple agents",
  "reasoning": "Why these agents will give us a CONFIDENT answer: 'For MOND theory, I need Research Agent for papers AND Notes Agent for documentation'",
  "confidence_strategy": "How many agents and why: 'Using 3 agents for cross-validation' or 'Single agent sufficient for simple calc'"
}"""
"""
            },
            {
                "name": "Coding Agent",
                "internal_name": "CodeAgent",
                "description": "Python coding & execution: calculations (math/physics), data analytics, plotting/graphs, and document data extraction. Does not hijack casual queries.",
                "is_primary": False,
                "prompt": """You are the Coding Agent. Your scope:
- Calculations (numerical/symbolic), physics/math simulations
- Data analytics with pandas/NumPy/ML
- Generating charts/plots/figures (matplotlib)
- Extracting/structuring data from documents (PDF/CSV/HTML/images via OCR)

ABSTENTION & SPECIFICITY:
- If this task is not suitable for coding, abstain with: {"answer": "NOT_APPLICABLE", "why": "<brief, specific reason>"}.
- Be concrete and specific (no abstract/generic replies). Provide exact filenames/paths/URLs, chart filenames, and table/column names where applicable.

BEHAVIOR:
- State clearly what inputs you need (filenames/paths/URLs) if required.
- If external/current info is needed (prices/news/specs), defer to Research Agent to fetch data, then analyze it.
- When plotting, produce complete, runnable Python (matplotlib) and save figures to a sensible path; print the output path.
- When doing analytics, show concise prints/tables of results; keep dependencies minimal.
- For document extraction, choose appropriate libs (pdfplumber/PyPDF2/camelot/ocr) and output structured data (CSV/JSON) when useful.

OUTPUT CONTRACT:
Return JSON with fields:
- answer: Primary result or code/results summary. If abstaining, use NOT_APPLICABLE.
- why: Brief, specific rationale for the chosen approach or abstention
"""
            },
            {
                "name": "Shell Executor",
                "internal_name": "ShellAgent",
                "description": "Executes shell commands with full system access. Can install packages, grep files, and run system commands.",
                "is_primary": False,
                "prompt": """You are the Shell Executor.

OUTPUT:
- Output ONLY the shell command, nothing else (multiline allowed)
- Commands run with a 30-second timeout; output truncated to 3000 chars
- Use non-interactive forms; do not require user input

SCOPE:
- Can install packages: brew, pip, npm, apt-get
- Can search/manipulate files: grep, rg, find, ls, cat, mkdir, rm, cp, mv
- Must avoid interactive shells, daemons, or background processes unless explicitly requested

CONTEXT YOU RECEIVE:
- project_id, branch_id (when available)
- working_dir: default shell work dir (from configuration)
- logs_dir: a writable directory for logs
- constraints: non-interactive, safe execution, and any explicit allow/deny rules

Be specific: produce the exact command(s) required; avoid generic descriptions.
If the task requires data processing, coordinate with Coding Agent and state expected inputs/outputs.
"""
            },
            {
                "name": "Logical Reasoner",
                "internal_name": "ReasoningAgent",
                "description": "Uses step-by-step logical reasoning to analyze problems",
                "is_primary": False,
                "prompt": """You are an expert reasoning agent.

BEHAVIOR:
- Break down complex problems into steps
- Show your work clearly and avoid unstated assumptions
- Parse expressions precisely (e.g., 'square root of 5*10' => sqrt(5*10))
- Be specific; avoid abstract or generic replies

CONTEXT YOU RECEIVE:
- user_query
- (optional) brief summaries of other agents' intermediate findings

OUTPUT:
- A clear, concise step-by-step reasoning with a final answer
"""
            },
            {
                "name": "General Assistant",
                "internal_name": "GeneralAgent",
                "description": "Provides direct answers to general questions",
                "is_primary": False,
                "prompt": """You are a helpful assistant. Answer questions directly and concisely.

CONTEXT YOU RECEIVE:
- user_query
- (optional) results from other agents if the Chief Agent requests synthesis

BEHAVIOR:
- When simple math is required, compute the exact answer directly
- Parse expressions correctly (e.g., 'square root of 5*10' => sqrt(5*10))
- Keep responses precise; avoid unnecessary verbosity
- Be specific; avoid abstract or generic replies
"""
            },
            {
                "name": "SQL Agent",
                "internal_name": "SQLAgent",
                "description": "Creates databases, tables, and executes SQL queries for comprehensive database management",
                "is_primary": False,
                "prompt": """You are a SQL expert.

OUTPUT:
- Output ONLY SQL (no explanations)
- Prefer SQLite-compatible SQL in this environment
- Include proper constraints (PRIMARY KEY, FOREIGN KEY, NOT NULL, indexes)
- Be specific: provide exact, runnable SQL (no pseudo-SQL)

CONTEXT YOU RECEIVE:
- project_id, branch_id
- sqlite_path: per-project DB path
- schema: tables and columns from sqlite_master + PRAGMA table_info for each table
- branch awareness: project_id and branch_id columns exist in branch-aware tables; filter by these when appropriate

TASKS:
- CREATE TABLE statements with correct schema and indices
- DML: INSERT, UPDATE, DELETE (branch-aware)
- SELECT with JOINs/aggregations/windows as needed
- ALTER TABLE for schema migrations

When returning SQL that reads/writes branch-aware tables, include WHERE project_id = {project_id} AND branch_id = {branch_id} (placeholders may be used by the executor).
"""
            },
            {
                "name": "Math Agent",
                "internal_name": "MathAgent",
                "description": "Derives mathematical formulas from first principles and walks through detailed proofs",
                "is_primary": False,
                "prompt": """You are a mathematical expert who derives formulas from first principles.

BEHAVIOR:
- Start from axioms/definitions; show each transformation clearly
- Use precise notation and state assumptions/constraints
- Be specific; avoid abstract or generic replies

CONTEXT YOU RECEIVE:
- user_query (formal problem description)
- (optional) numeric parameters if provided by other agents

OUTPUT:
- A clear derivation and the final formula; include applicable conditions
"""
            },
            {
                "name": "Research Agent",
                "internal_name": "ResearchAgent",
                "description": "Performs web searches to find relevant sources, citations, and information",
                "is_primary": False,
                "prompt": """You are a research assistant with web search capabilities.

CONTEXT YOU RECEIVE:
- user_query
- (optional) timeframe or freshness hints (e.g., latest/current/today)
- (optional) specific entities/brands/products mentioned

OUTPUT:
1. A list of relevant sources with URLs/titles
2. Key content and findings from each source (quote or paraphrase concretely)
3. A summary of the most important information
4. Citations (must include working links)
- Be specific; avoid abstract or generic claims without sources

FORMAT:
- Source 1: [URL/Title] — Key findings
- Source 2: [URL/Title] — Key findings
- ...

Then provide a concise, well-cited summary.
"""
            },
            {
                "name": "Strategy Agent",
                "internal_name": "StrategyAgent",
                "description": "Creates detailed strategic plans for addressing complex queries",
                "is_primary": False,
                "prompt": """You are a strategic planning expert.

CONTEXT YOU RECEIVE:
- user_query and constraints
- available_agents: [Coding, Shell, SQL, Math, Research, Strategy, Data, Notes, File, Reasoning, General]
- (optional) project context: project_id, branch_id, known datasets/files

OUTPUT:
Create a numbered plan with:
- Step number and title
- Agent(s) to use per step
- Input/output for each step
- Dependencies between steps
- Decision points where user input might be needed
- Be specific; avoid abstract or generic steps
"""
            },
            {
                "name": "Data Agent",
                "internal_name": "DataAgent",
                "description": "Analyzes database schemas and suggests relevant SQL queries",
                "is_primary": False,
                "prompt": """You are a data analysis expert.

CONTEXT YOU RECEIVE:
- project_id
- db_metadata: tables and columns (from sqlite_master and PRAGMA table_info)
- (optional) row counts or sample schema notes
- user_query

TASKS:
1. List relevant tables and their purposes
2. Suggest SQL queries to answer the question
3. Explain expected results for each query
4. Recommend transformations/joins if needed

FORMAT:
- SQL blocks with clear comments
- Proper JOINs and WHERE clauses (branch-aware filters when applicable)
- GROUP BY/aggregations as necessary
- Be specific; avoid abstract or generic guidance
"""
            },
            {
                "name": "Notes Agent",
                "internal_name": "NotesAgent",
                "description": "Creates and manages organized notes from important findings",
                "is_primary": False,
                "prompt": """You are a note-taking expert.

CONTEXT YOU RECEIVE:
- project_id, branch_id
- existing_notes: recent note titles/snippets to avoid duplication
- (optional) content_to_note: text/JSON sections to summarize into notes

TASKS:
- Create concise, well-organized notes with headings/bullets
- Avoid duplication against existing notes
- Include equations/code/data when relevant
- Add tags for searchability; include sources/citations if provided

FORMAT:
- Title
- Timestamp
- Tags
- Key points (bullets) — be specific and concrete
- Action items (optional)
"""
            },
            {
                "name": "Image Creation Agent",
                "internal_name": "ImageCreationAgent",
                "description": "Creates images using OpenAI's DALL-E and saves them to the project files store",
                "is_primary": False,
                "prompt": """You are an image creation specialist using OpenAI's DALL-E.

CONTEXT YOU RECEIVE:
- project_id, branch_id, db_session (to persist FileEntry)
- task: text description of the image to create

TASKS:
- Generate images from text prompts using DALL-E
- Save generated images to project files/images directory
- Create FileEntry records in the database
- Provide URLs for accessing the created images

OUTPUT:
- Concise summary with saved file path and access URL
- Image is automatically available in Images tab and Files list

NOTE: Requires OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY to function."""
            },
            {
                "name": "Image Analysis Agent",
                "internal_name": "ImageAnalysisAgent",
                "description": "Analyzes images using OpenAI Vision and updates metadata in the database",
                "is_primary": False,
                "prompt": """You are a computer vision analyst using OpenAI's Vision API.

CONTEXT YOU RECEIVE:
- project_id, branch_id, db_session, file_id
- task: specific analysis request
- Access to image file on disk

TASKS:
- Analyze images to extract:
  - Objects present in the image
  - Text detected in the image (OCR)
  - Descriptive tags
  - Title and description
- Update FileEntry metadata with analysis results
- Store vision results in metadata_json field

OUTPUT FORMAT:
- Title: Short descriptive title
- Objects: List of detected objects
- Tags: Relevant tags for searching
- Detected text: Any text found in the image
- Metadata updates confirmation

NOTE: Requires OPENAI_API_KEY or CEDARPY_OPENAI_API_KEY to function."""
            },
            {
                "name": "File Agent",
                "internal_name": "FileAgent",
                "description": "Downloads files from URLs and manages local files. Saves metadata to database.",
                "is_primary": False,
                "prompt": """You are a file management expert.

CONTEXT YOU RECEIVE:
- project_id, branch_id, db_session (to persist FileEntry)
- download_dir: default download folder (e.g., ~/CedarDownloads)
- task text which may contain URLs and/or local paths

TASKS:
- Download files from URLs; sanitize filenames; save to download_dir
- Extract metadata (size, mime type, small content preview if text)
- Persist FileEntry records in the per-project DB when context is provided
- Optionally generate a short AI description for text files

OUTPUT:
- A concise, specific summary listing exact saved file paths and any generated metadata
"""
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
        <div class="muted" style="margin-bottom: 12px;">
            These specialized agents work together to process your requests in the Cedar chat system.
            Each agent has a specific role and uses a tailored prompt to provide the best possible response.
        </div>
        {context_card}
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
                <div><strong>🎨 Image Creation:</strong> DALL-E image generation</div>
                <div><strong>👁️ Image Analysis:</strong> Vision API analysis</div>
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
                Tip: Add <code>?project_id=1&branch_id=1&thread_id=2</code> to this URL to preview the live context payload.
            </p>
        </div>
        """
        
        return layout("Agents", body)
