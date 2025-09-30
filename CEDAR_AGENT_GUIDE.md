# Cedar Agent Guide

These are the agents available in Cedar and what they do. The **ChiefAgent** orchestrates everything and may call several agents to achieve a high-confidence answer. If there are supporting files, images, or databases already in your project, prefer agents that can read/write those assets directly.

---

## CodeAgent

**Role:** General-purpose processing (strongest agent)

* Python execution for calculations, simulations, data analysis (pandas/NumPy/ML).
* Generates charts/plots/figures (matplotlib).
* Extracts/structures data from documents (CSV/PDF/HTML; OCR where needed).
* Can read **and** write to databases.
* Can create/process images programmatically.
* If supporting documents or databases exist in the system, use them as inputs/outputs.

**Examples:**

* Calculate "What is 2+2?" or run physics/math simulations.
* Parse/export tables from a PDF into CSV/Parquet; produce summary plots.
* Train/evaluate a lightweight model and save artifacts to project files.
* Write analysis results back into the project database.

---

## FormulaAgent

**Role:** Derivations and proofs

* Step-by-step derivations from first principles; formal proofs with assumptions/conditions.

**Examples:**

* Prove that the harmonic series diverges.
* Derive the wave equation from Maxwell's equations.
* Prove 2+2=4 in a formal system.

---

## ResearchAgent

**Role:** Web research and citations

* Finds sources on the web; extracts key facts and returns a cited summary.
* Use when external/current info is needed.

**Examples:**

* Explain MOND vs. dark matter with citations.
* Summarize recent (past 12 months) policy changes; link to official pages.
* Historical "who/when/where" questions needing sources.

---

## StrategyAgent

**Role:** Multi-step planning and orchestration design

* Produces a numbered plan with steps, inputs/outputs, agent assignments, decision points, and dependencies.
* Knows each agent's capabilities and lays out how ChiefAgent should coordinate them.
* Ideal for prompts that require many steps, multiple sources, or iterative checks.

**Examples:**

* Plan: "Ingest these PDFs, extract tables, load to DB, build charts, generate a report, and post a summary."
* Incident playbook: detection → triage → shell/SQL investigations → code fixes → comms → postmortem notes.
* Data product rollout: schema design → ETL → backfills → dashboards → QA → docs → handoff.

---

## SQLAgent

**Role:** SQL definition and manipulation

* Outputs executable SQL only (SQLite-compatible preferred).
* Creates/updates tables, indexes, constraints; runs SELECT/INSERT/UPDATE/DELETE.
* If a project database exists, reads/writes to it directly.

**Examples:**

* Create `daily_metrics` with indexes.
* Backfill columns with defaults.
* Aggregations and joins across existing tables.

---

## DataAgent

**Role:** Schema analysis and query guidance

* Reads database metadata; proposes concrete SQL to answer questions.
* Explains expected results, joins, and transformations.
* Works best when a database already exists in the system.

**Examples:**

* Conversion funnels from users/sessions/purchases with recommended indexes.
* Orphan detection (FK integrity issues) and cleanup queries.
* Designing a reporting table for LLM token costs and refresh cadence.

---

## NotesAgent

**Role:** Organized notes and summaries

* Turns raw bullets or JSON into clean notes with headings/tags and timestamps.
* Maintains a running note per thread; avoids duplication.
* Can embed equations/code/data snippets and record citations from ResearchAgent.

**Examples:**

* Meeting minutes with action items.
* Consolidate three summaries into one concise note.
* Running log for a multi-day investigation.

---

## ShellAgent

**Role:** System commands (non-interactive)

* File searches, grep, disk usage, small utilities, package installs.
* Coordinates with CodeAgent/SQLAgent when data processing is required.

**Examples:**

* Find recently modified files under `src/`.
* Search logs for "rate limit exceeded" with context.
* Show disk usage by folder.

---

## FileAgent

**Role:** File import and management

* Downloads from URLs to project storage; sanitizes filenames; records metadata.
* Makes files available to CodeAgent/DataAgent/ImageAnalysisAgent.
* If supporting documents exist, use FileAgent to fetch/add more or to catalog what's present.

**Examples:**

* Download a PDF/CSV and store with size/MIME preview.
* Fetch `robots.txt` and save.
* Register local files into the project's index.

---

## ImageCreationAgent

**Role:** Text-to-image generation

* Creates images (e.g., diagrams, mockups) and saves to project files with URLs.

**Examples:**

* Concept art for a robot mascot.
* Simple storyboard frames for a product video.

---

## ImageAnalysisAgent

**Role:** Image understanding and OCR

* Detects objects, tags, and text; updates image metadata in the database.
* Works on images already in the system.

**Examples:**

* OCR a chart to extract axis labels and annotations.
* Auto-tag uploaded photos/diagrams for search.

---

## Routing Patterns (Multi-Agent)

* **Research-then-Analyze:** ResearchAgent → CodeAgent (analyze/plot) → NotesAgent (document).
* **Ingest-Transform-Report:** FileAgent (import) → CodeAgent (extract/clean/plot) → SQLAgent/DataAgent (load/query) → NotesAgent (report).
* **Complex Orchestration:** StrategyAgent (plan) → ChiefAgent (dispatch and iterate) using Shell/SQL/Code/Notes as specified.

---

## Trigger Word Cheat Sheet

| Trigger words/phrases in user prompt                                                      | Route to agent                             | Example prompt (→ agent)                                                                     |
| ----------------------------------------------------------------------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------- |
| plan, roadmap, steps, orchestrate, "many steps", dependencies, handoff, QA, rollback      | **StrategyAgent** (to plan for ChiefAgent) | "Build a pipeline to ingest PDFs → tables → DB → charts → report → publish."                 |
| calculate, simulate, analyze, plot, script, Python, parse, extract tables, transform data | **CodeAgent**                              | "Simulate a random walk and plot distribution"; "Extract tables from this PDF and save CSV." |
| derive, prove, closed-form, theorem, "show that", limit                                   | **FormulaAgent**                           | "Prove 2+2=4 in Peano arithmetic"; "Derive logistic growth solution."                        |
| explain, summarize, compare, latest, cite, who/when/where (needs sources)                 | **ResearchAgent**                          | "Summarize the latest App Store policy changes with citations."                              |
| SELECT, JOIN, CREATE TABLE, ALTER, index, backfill (SQL only)                             | **SQLAgent**                               | "Create `daily_metrics` and backfill `ai_category` with default."                            |
| schema, tables, indexes, how to query, design a reporting table                           | **DataAgent**                              | "Compute signup→first purchase conversion weekly; propose indexes and queries."              |
| summarize notes, structure bullets, running log, tags, timestamp                          | **NotesAgent**                             | "Turn these bullets into notes with action items and tags."                                  |
| find files, grep, disk usage, list largest, install, chmod                                | **ShellAgent**                             | "Search `logs/` for 'rate limit exceeded' with 2 lines of context."                          |
| download file, import URL, save to project, metadata                                      | **FileAgent**                              | "Download https://example.org/data.pdf and record metadata."                                 |
| generate image, illustration, concept art, diagram from text                              | **ImageCreationAgent**                     | "Create a stylized cedar-tree brain logo concept."                                           |
| analyze image, OCR, detect objects/tags, title/description                                | **ImageAnalysisAgent**                     | "OCR this chart image and tag it for search."                                                |

**Quick disambiguations:**

* "What is 2+2?" → **CodeAgent** (calculation).
* "Prove 2+2=4." → **FormulaAgent** (proof).
* "Who invented algebra?" → **ResearchAgent** (historical, cited).
* "Ingest these PDFs and build a dashboard from them." → **StrategyAgent** (plan) → ChiefAgent executes via **FileAgent + CodeAgent + SQLAgent/DataAgent + NotesAgent**.

---

## Using Supporting Assets in the System

* If PDFs/CSVs/images are already in the project:
  * Prefer **CodeAgent** to parse/transform/analyze them,
  * **ImageAnalysisAgent** to tag/OCR images,
  * **SQLAgent/DataAgent** to load/query the project database,
  * **NotesAgent** to document findings.
* If you need new files: use **FileAgent** to download/import first.
* **CodeAgent** can also write outputs (CSV/Parquet/plots) back into project files and update databases.

---

## When to Start with StrategyAgent

* The prompt spans multiple modalities (files + web + DB + plots).
* There are unclear dependencies or decision points (e.g., "if extraction fails, try OCR").
* You want a reusable, auditable plan ChiefAgent can run step by step.

**Example high-level plan outline StrategyAgent can produce:**

1. Inventory inputs (FileAgent)
2. Extract/clean (CodeAgent)
3. Load/validate (SQLAgent/DataAgent)
4. Analyze/visualize (CodeAgent)
5. Document outcome (NotesAgent)
6. Optional web context (ResearchAgent)
7. Final handoff/artifacts (ChiefAgent merges)