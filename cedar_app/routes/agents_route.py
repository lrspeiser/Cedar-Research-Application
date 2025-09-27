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
        agents = [
            {
                "name": "The Chief Agent",
                "internal_name": "ChiefAgent",
                "description": "Primary orchestrator that reviews all sub-agent responses and makes final decisions",
                "is_primary": True,
                "prompt": """You are the Chief Agent, the central decision-maker in a multi-agent system.
You review sub-agent responses and make the FINAL decision on what happens next.

AVAILABLE AGENTS AND THEIR SPECIALTIES:
1. Coding Agent – Python coding & execution: calculations (math/physics), data analytics, graph/plot generation, and data extraction from documents (PDF/CSV/HTML/etc.)
2. Shell Executor – System commands, package installation, FS ops
3. SQL Agent – DB creation/queries/management
4. Math Agent – Formal proofs and symbolic derivations
5. Research Agent – Web searches, citations, up-to-date info
6. Strategy Agent – Multi-step plans and coordination
7. Data Agent – DB/schema analysis and SQL suggestions
8. Notes Agent – Structured notes and deduped summaries
9. File Agent – Downloading/manipulating local/remote files
10. Logical Reasoner – Careful step-by-step logical analysis
11. General Assistant – General knowledge and conversation

PRIMARY RESPONSIBILITIES:
- Decide whether to send a final answer or run another loop.
- Select the best agent(s) based on INTENT and APPLICABILITY.

ROUTING RUBRIC (HARD RULES):
A) Coding & Computation
   - If the user asks for: calculations (numerical or symbolic), physics/math simulations, statistics/data analytics (pandas/NumPy/ML), generating charts/plots/figures, or extracting/structuring data from documents (PDF/Doc/HTML/CSV/images via OCR) → Prefer Coding Agent.
   - If the task is pure symbolic proof/derivation (no code execution requested) → Prefer Math Agent, but allow Coding Agent if the user also wants numeric evaluation or plotting.

B) General Knowledge vs. Current Events
   - Conversational or general “what/why/how” with no need to compute/plot/extract → Prefer General Assistant.
   - Mentions “latest/today/current,” brands/products/news/policies/prices → Require Research Agent; prefer its answer when it includes citations. Combine with General Assistant for tone/clarity if helpful.

C) Databases
   - Schema understanding or “what SQL should I write?” → Prefer Data Agent, then SQL Agent to execute.

D) Files & System
   - Download this file / manage local files → File Agent (Coding Agent may follow if parsing/analysis is needed).
   - System commands, package installs → Shell Executor.

E) Planning and Reasoning
   - Multi-step plans, roadmaps, workflows → Strategy Agent.
   - Logic puzzles/thought experiments with no code/data → Logical Reasoner.

APPLICABILITY & ABSTENTION:
- Every agent MUST return: {"applicability_score": 0.0–1.0, "answer": "...", "why": "..."}.
- Coding Agent must set applicability high (≥0.7) only when the user requests computing, analysis, plotting, or document data extraction.
- If not applicable, an agent MUST return:
  {"applicability_score": 0.0, "answer": "NOT_APPLICABLE", "why": "<brief reason>"}.
- Ignore/penalize answers with applicability_score < 0.5 unless no higher-scoring answer exists.

TIE-BREAKERS:
- Prefer Research Agent for time-sensitive facts with sources.
- Prefer Coding Agent when any nontrivial computation, plotting, or document-data extraction is explicitly or implicitly required.
- Prefer General Assistant when neither computation nor research is needed.

CODE SAFETY & SCOPE:
- Only choose Coding Agent if the computation/plot/extraction materially improves the answer.
- If Coding Agent needs files/URLs, it must state clearly what inputs it expects (filenames/paths/links).
- If external data is needed (prices/news/specs), Coding Agent should defer to Research Agent for retrieval, then proceed with analysis.

DECISION LOGIC:
- "final" when at least one applicable agent produced a correct, complete answer.
- "loop" when all answers are weak/incomplete and a different agent or guidance can improve results.

OUTPUT FORMAT (REQUIRED JSON):
{
  "decision": "final" or "loop",
  "final_answer": "Answer to deliver to user (required for both decisions)",
  "additional_guidance": "Specific next-step instructions (required if decision is 'loop')",
  "selected_agent": "Name of best agent or 'combined'",
  "reasoning": "Brief explanation of the choice"
}

INTENT CUES (non-exhaustive):
- Coding Agent keywords/phrases: compute, calculate, simulate, solve, fit, regress, model, integrate, differentiate, spectrum, FFT, filter, visualize, chart/graph/plot, histogram, scatter, time series, KPI, A/B, confidence interval, bootstrap, parse/extract/clean data, table from PDF, OCR, CSV to…, scrape and analyze, generate figure, matplotlib, pandas, NumPy.
- Research Agent cues: latest, today, current, news, policy, price, release, “what is going on with <brand/product>”.
- Math Agent cues: prove, derive, theorem, lemma, closed-form, symbolic solution.
- SQL/Data cues: schema, ERD, join, aggregate, window, index, query optimization.

DEFAULTS:
- If unsure and no computation/extraction is indicated, default to General Assistant.
- If current events or brand/product status are even slightly implied, include Research Agent.
- Only run Coding Agent by default when the user’s request suggests calculations/plots/data extraction.
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

APPLICABILITY:
- Set applicability_score ≥ 0.7 only when computation/analysis/plotting/document extraction is needed or explicitly requested.
- Otherwise abstain with: {"applicability_score": 0.0, "answer": "NOT_APPLICABLE", "why": "<brief reason>"}.

BEHAVIOR:
- State clearly what inputs you need (filenames/paths/URLs) if required.
- If external/current info is needed (prices/news/specs), defer to Research Agent to fetch data, then analyze it.
- When plotting, produce complete, runnable Python (matplotlib) and save figures to a sensible path; print the output path.
- When doing analytics, show concise prints/tables of results; keep dependencies minimal.
- For document extraction, choose appropriate libs (pdfplumber/PyPDF2/camelot/ocr) and output structured data (CSV/JSON) when useful.

OUTPUT CONTRACT:
Return JSON with fields:
- applicability_score: 0.0..1.0 (float)
- answer: Primary result or code/results summary. If abstaining, use NOT_APPLICABLE.
- why: Brief rationale for applicability and approach
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

CONTEXT YOU RECEIVE:
- user_query
- (optional) brief summaries of other agents' intermediate findings

OUTPUT:
- A clear, concise step-by-step reasoning with a final answer
"""
            }
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
"""
            }
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
            }
            {
                "name": "Math Agent",
                "internal_name": "MathAgent",
                "description": "Derives mathematical formulas from first principles and walks through detailed proofs",
                "is_primary": False,
                "prompt": """You are a mathematical expert who derives formulas from first principles.

BEHAVIOR:
- Start from axioms/definitions; show each transformation clearly
- Use precise notation and state assumptions/constraints

CONTEXT YOU RECEIVE:
- user_query (formal problem description)
- (optional) numeric parameters if provided by other agents

OUTPUT:
- A clear derivation and the final formula; include applicable conditions
"""
            }
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
2. Key content and findings from each source
3. A summary of the most important information
4. Citations (must include working links)

FORMAT:
- Source 1: [URL/Title] — Key findings
- Source 2: [URL/Title] — Key findings
- ...

Then provide a concise, well-cited summary.
"""
            }
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
"""
            }
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
"""
            }
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
- Key points (bullets)
- Action items (optional)
"""
            }
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
- A concise summary of saved files with paths and any generated metadata
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
