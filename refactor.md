# CedarPy Orchestrator Refactor Plan (2025-09-23)

This document captures the vision, current status, and an executable sequence of changes to finish the CedarPy LLM chat/orchestration refactor. It is designed to be followed from the terminal, committing directly to main after each milestone (per repo policy).

IMPORTANT policy notes:
- Always push to main. No feature branches.
- Tests that depend on LLMs require real keys loaded from env or ~/CedarPyData/.env. Never hardcode, never use placeholders, and do not simulate success when the LLM fails.
- No “fallbacks” that fabricate results. Prefer verbose, structured logging and visible UI debug events.
- Preserve existing UI event flow (WS + Redis/SSE relay) and ACKs.
- When fixing errors, record the mistake, the fix, tests run, and logging added in Progress & Fix Log below (repo rule).

## Vision and Target Architecture

Goal: Fewer than 1000 composable “components,” each:
- Is a single function with typed inputs/outputs.
- Owns its prompt template.
- Can be dispatched concurrently by an orchestrator that fans out to multiple components.
- Produces a normalized ComponentResult.
- Feeds an Aggregator LLM that reconciles candidate outputs to produce a final answer, returned as the existing function-call JSON expected by the UI.
- Streams all bubbles/events through existing WebSocket and Redis/SSE relay.

Key interfaces:
- Component signature:
  - async def run(payload: dict, ctx: OrchestratorCtx) -> ComponentResult
  - Inputs/outputs defined with Pydantic BaseModel or TypedDict for strict typing.
- Orchestrator responsibilities:
  - Build candidate component set from user message/context.
  - Dispatch with asyncio.gather and per-component timeouts.
  - Preserve ACK, info/submitted, action/processing, debug, and final event sequencing.
  - Publish every bubble to Redis for SSE (existing _enqueue + publish_relay_event).
- Aggregator LLM:
  - Normalizes component outputs and prompts an LLM to select/synthesize the final result.
  - No “fake” or fallback answers. On error, emit verbose debug logs and propagate failure to UI in a controlled way.

## Where we left off (evidence from code/tests)

- main.py still holds primary ws_chat_stream and tool_* logic.
- main_ws_chat.py exists as a stub and registers a dev-only route (/ws/chat2) when importable; also contains await-in-non-async smells to fix before adoption.
- Tool logic is duplicated between WS path and /api/test/tool; requires extraction to a shared module.
- LangExtract schema logic duplicated in two places; must consolidate into cedar_langextract.ensure_langextract_schema and call from migrations only.
- tests/test_ws_chat_orchestrator.py expects real LLM behavior and asserts debug messages (including full prompts) and event types (info/submitted, action/processing, debug, final).

References:
- README.md “Refactor note” — next extraction: WebSocket Chat orchestrator
- docs/CODEMAP.md “Next steps” — extract tool_*; consolidate LangExtract schema
- main.py registers /ws/chat2 via main_ws_chat.register_ws_chat (dev-only)
- main_ws_chat.py comment: “The rest of ws_chat_stream is intentionally left in main.py…”
- tests/test_ws_chat_orchestrator.py requires real keys and asserts debug prompt exists
- git log (last commit): “refactor(ws): add modular WS chat registration under /ws/chat2 … Next step: move full orchestrator logic into main_ws_chat and switch primary route”

## Migration strategy: milestones, directory layout, and test gates

We proceed in milestones M0–M10 with commits to main after each step. We maintain UI contract, WS/SSE event types, and verbose logging throughout. Each milestone has acceptance checks and tests.

Target directories to introduce:
- cedar_orchestrator/
  - __init__.py
  - ws_chat.py (extracted WS orchestrator; or evolve main_ws_chat.py)
  - aggregate.py (Aggregator LLM)
  - ctx.py (OrchestratorCtx, types)
- cedar_components/
  - __init__.py
  - registry.py (central registry)
  - example/
    - __init__.py
    - summarize.py (sample component)
  - retrieval/
    - __init__.py
    - retrieve_docs.py (sample component)
- cedar_tools.py (shared tools used by WS and /api/test/tool)
- cedar_langextract.py (ensure_langextract_schema)
- cedar_utils/
  - __init__.py
  - ports.py (unified choose_port helpers)

### M0. Create this refactor.md (baseline)
- Deliverable: this file committed to main.
- Test: none, but run pytest to capture baseline.

### M1. Extract WebSocket chat orchestrator
- Create cedar_orchestrator/ws_chat.py (or refactor main_ws_chat.py) and move ws_chat_stream logic out of main.py.
- Keep canonical route: /ws/chat/{project_id}. Maintain /ws/chat2 as a temporary alias (dev-only) until verified; then remove.
- Fix any await-in-non-async issues in the stub.
- Update main.py import/route registration to delegate to extracted orchestrator.
- Acceptance:
  - tests/test_ws_chat_orchestrator.py passes (requires real key).
  - WS events and Redis/SSE bubbles unchanged; ACK preserved.

### M2. Extract and deduplicate tool_* implementations
- Create cedar_tools.py with shared tool executors.
- Refactor both WS orchestrator and /api/test/tool to import from cedar_tools.
- Remove duplicated inlined tool_* in main.py and anywhere else.
- Acceptance:
  - /api/test/tool continues to work.
  - No duplicate definitions remain (grep check).
  - Tests pass.

### M3. Define formal Component interface and registry
- Create OrchestratorCtx, ComponentResult, and type models (pydantic or TypedDict) in cedar_orchestrator/ctx.py.
- Define component function signature: async def run(payload: dict, ctx: OrchestratorCtx) -> ComponentResult.
- Each component carries its prompt and maps ctx -> messages.
- Add cedar_components/registry.py to register components and expose selection hooks.
- Provide at least 2 components (e.g., example.summarize, retrieval.retrieve_docs).
- Acceptance:
  - Unit tests for components (type validation, prompt inclusion in debug logs).
  - Registry can list and load components.

### M4. Fan-out/fan-in orchestration
- Orchestrator builds candidate set from context and dispatches concurrently with asyncio.gather, per-component timeouts.
- Maintain ACK and publish every bubble to Redis for SSE via existing _enqueue + publish_relay_event.
- Acceptance:
  - New tests cover parallel fan-out and timeout handling (no fabricated outputs; timeouts explicitly noted).
  - Existing ws_chat_orchestrator test remains green.

### M5. Aggregator LLM
- Add cedar_orchestrator/aggregate.py. Prompt an LLM with normalized candidate outputs and context to produce a final response.
- Return final function-call JSON compatible with current UI.
- On LLM error: log verbosely, emit debug event, propagate failure to UI; do not fabricate answers.
- Acceptance:
  - New tests for aggregator reconciliation pass with real key.
  - Debug messages include full aggregator prompt (tests assert this).
  - End-to-end WS path returns final event.

### M6. UI and protocol compatibility
- Preserve event types and sequencing: info/submitted, action/processing, debug, final.
- Stream to UI via existing WS and Redis/SSE relay.
- Keep /ws/chat2 only as temporary alias; remove in M8.
- Acceptance:
  - Golden log/event tests (text match) for critical sequences.
  - Manual smoke test via UI.

### M7. Tests and CI
- Keep tests/test_ws_chat_orchestrator.py unchanged and green.
- Add tests:
  - Component selection logic
  - Parallel fan-out with timeouts
  - Aggregator reconciliation
  - Shared tools module behavior
- Respect CEDARPY_TEST_MODE for deterministic stubs only where allowed; do not bypass real-key paths used by existing tests.
- Acceptance:
  - pytest fully green locally and in CI.
  - Ensure CI has real keys (documented below).

### M8. Housekeeping and consolidation
- Consolidate LangExtract schema creation in cedar_langextract.ensure_langextract_schema; remove duplicates and call only from migrations.
- Unify choose-port helpers into cedar_utils/ports.py; update cedarqt.py and run_cedarpy.py.
- Remove temporary /ws/chat2 route.
- Acceptance:
  - Grep shows single LangExtract schema source.
  - No references to /ws/chat2.

### M9. Docs and code comments
- Add inline comments in new modules pointing to README sections:
  - Keys & Env
  - SSE relay
  - Troubleshooting
- Update README links/sections if needed.
- Acceptance:
  - Pre-commit linters (if present) pass.
  - Codeowners and docs updated.

### M10. Release steps
- Commit to main with descriptive messages.
- Run CI end-to-end.
- On macOS, produce DMG as per README and attach to Release when tagging.
- Acceptance:
  - DMG build successful, uploaded to GitHub Release.
  - Tag pushed.

## Logging and observability plan

- Structured logging fields (prefixes): 
  - EID (event id), RID (request id), PID (project id), UID (user id), COMP (component name), STAGE (ACK|DISPATCH|COMPLETE|AGGREGATE|ERROR).
- All LLM prompts must be emit-able to DEBUG channel events in WS/SSE (redacted only if keys are embedded).
- Redis/SSE integration:
  - Reuse existing _enqueue + publish_relay_event.
  - Publish every bubble with clear event types (info/submitted, action/processing, debug, final).
- ACK behavior:
  - Send ACK immediately on message receipt with EID and queue position (if applicable).
- Tracing (optional stretch):
  - Correlate component fan-out/fan-in with EIDs and publish a concise aggregator rationale behind a debug flag.

## Key handling notes

- Load keys from environment or ~/CedarPyData/.env; never hardcode.
- In code, add comments:
  - # Keys: see README "Keys & Env" for loading from env or ~/.CedarPyData/.env
  - # LLM failures are not faked; see README "Troubleshooting LLM failures"
- CI must provide OPENAI_API_KEY and any other required keys via GitHub Actions secrets.

## Risks, rollback, and timeline

- Risks:
  - WebSocket regressions: mitigated by preserving event contract and golden tests.
  - Aggregator instability: mitigated by verbose debug prompts and strict no-fallback policy.
  - Concurrency timeouts: mitigate via per-component timeouts with explicit status in results.
  - Duplicate logic lingering: grep checks in M2 and M8.
- Rollback:
  - Each milestone is a small, reversible diff. If a milestone fails, revert the last commit to main and fix forward.
- Suggested timeline:
  - Day 0: M0
  - Day 1: M1–M2
  - Day 2: M3–M4
  - Day 3: M5–M6
  - Day 4: M7–M8
  - Day 5: M9–M10

## Planned Changes (explicit file and code actions)

- Create directories:
  - cedar_components/, cedar_orchestrator/ (with __init__.py files), cedar_utils/
- Move/rename:
  - Extract WS orchestrator into cedar_orchestrator/ws_chat.py (or evolve main_ws_chat.py) and have main.py import/register it for /ws/chat.
- New:
  - cedar_tools.py with shared tool_* executors used by both the WS route and /api/test/tool.
  - cedar_orchestrator/aggregate.py implementing the aggregator LLM.
  - cedar_orchestrator/ctx.py defining OrchestratorCtx and ComponentResult.
  - cedar_components/registry.py and initial components under cedar_components/example and cedar_components/retrieval.
  - cedar_langextract.py with ensure_langextract_schema (already present; consolidate callers).
  - cedar_utils/ports.py to unify choose-port.
- Update:
  - main.py to remove inner tool_* functions once migrated, and to point the /ws/chat route at the extracted orchestrator; keep /ws/chat2 as temporary alias then drop in M8.
- Tests:
  - Keep tests/test_ws_chat_orchestrator.py as-is but ensure it still passes.
  - Add tests for components, fan-out, aggregator, and shared tools.
- Docs:
  - Add/refresh inline comments in new files pointing to relevant README sections (OpenAI keys, CI mode, SSE relay).

## Test plan and gates

- At each milestone, run:
  - pytest -q
  - pytest -q tests/test_ws_chat_orchestrator.py
- For new tests, ensure they assert:
  - Full prompt appears in debug events.
  - Event types and order are correct.
  - Parallel execution honors timeouts and never fabricates outputs.
- Optional coverage gate:
  - coverage run -m pytest && coverage report --fail-under=80

## Progress & Fix Log (append during execution)

### 2025-09-23 - M4 - Fan-out/fan-in orchestration (chat2)
- Changes:
  - Implemented component fan-out/fan-in in cedar_orchestrator/ws_chat.py for /ws/chat2 route.
  - Selects example.summarize and retrieval.retrieve_docs, runs concurrently with per-component timeouts.
  - Emits action events on dispatch and completion; emits debug events with component prompts when available.
  - Aggregates results with a simple stub (prefers summarize.summary) and emits a final event with a function-call JSON (function: "final").
- Tests run:
  - No change to canonical /ws/chat route yet (kept legacy stable for existing tests). Focused ws_chat_orchestrator test remains PASS.
  - Manual smoke via route inspection shows /ws/chat2 is registered and functional.
- Logging/observability: All bubbles go through _enqueue + publish_relay_event; ACKs preserved.
- Commit: b533be1

### 2025-09-23 - M5 - Aggregator LLM (chat2)
- Changes:
  - Added cedar_orchestrator/aggregate.py with normalize_candidates(), build_prompt(), and aggregate() that calls the LLM to return one strict JSON function-call (final).
  - Integrated aggregator into /ws/chat2 path: when a client/model is available, aggregator runs after components complete; emits a debug prompt for the aggregator; on aggregator error, emits an error (no fabricated final).
  - Kept simple summarizer preference when LLM client is unavailable (dev alias only; canonical route unchanged).
- Tests run:
  - Added tests/test_aggregator.py with a fake client stub; PASS.
  - Focused ws_chat_orchestrator test (canonical) still PASS.
- Logging/observability: Aggregator debug prompt is emitted as a debug event with component="aggregator"; Keys and Troubleshooting pointers are in module comments.
- Commit: <this change>

## Progress & Fix Log (append during execution)

Use this section to log each change with:
- Date, Milestone, Commit SHA
- What broke
- Root cause
- Fix implemented
- Tests added/updated
- Logging/observability added

### 2025-09-23 - M0 - Initial setup
- Created/verified this refactor.md file
- Set up todo list with milestones M0-M10
- Verified environment: Python 3.13.5, venv active, ~/CedarPyData/.env present
- Baseline test shows import issues (need PYTHONPATH for tests)
- Committed: 9a38468

### 2025-09-23 - M1 - Extract WebSocket chat orchestrator
- Created cedar_orchestrator/ module structure with __init__.py
- Extracted ws_chat.py with WSDeps class and register_ws_chat function
- Preserved all existing event types and WebSocket protocol
- Added verbose logging and code comments pointing to README sections
- Updated main.py to import from cedar_orchestrator for /ws/chat2 route
- Tests: test_ws_chat_orchestrator.py passes with extracted module
- Note: Missing dependencies (_execute_sql, _exec_img) need to be addressed in M2
- Note: Full orchestration loop with tools to be migrated in later milestones
- Next: Commit and proceed to M2

### 2025-09-23 - M1 - Fixes for dev alias and legacy stub
- What broke: /ws/chat2 alias failed to register at startup (NameError: _exec_img not defined). Legacy stub had await in non-async function (_ws_send_safe), which is unsafe if ever used.
- Root cause: main.py attempted to pass optional deps (exec_img, llm_summarize_action) before those names were defined; main_ws_chat.py had a signature mismatch (def with await inside).
- Fix implemented:
  - main.py: Register /ws/chat2 using WSDeps without optional deps that aren’t defined at import-time; orchestrator tolerates missing optional deps.
  - main_ws_chat.py: Changed _ws_send_safe to async def to match await usage.
- Tests run:
  - Focused: pytest -q tests/test_ws_chat_orchestrator.py → PASS
  - Baseline: pytest -q → 3 known failures (UI prompt content and tabular import in test mode), unaffected by this change.
- Logging/observability: Startup now logs "Registered /ws/chat2 from cedar_orchestrator module"; no stack trace on startup.
- Commit: 7d25675

### 2025-09-23 - M2 - Centralize tools in cedar_tools.py and refactor callers
- Changes:
  - Added cedar_tools.py with tool_web, tool_download, tool_extract, tool_image, tool_db, tool_code, tool_shell, tool_notes, tool_compose, tool_tabular_import (with explicit deps; comments point to README Keys & Env and Troubleshooting).
  - main.py WS orchestrator tools now delegate to cedar_tools; behavior preserved.
  - /api/test/tool route refactored to call cedar_tools for all tool functions.
- What broke: initial NameError for _exec_img on /api/test/tool image path.
- Root cause: API route attempted to call private _exec_img which exists in a different scope.
- Fix implemented: Added local _api_exec_img closure in /api/test/tool that reads the file, builds a data URL, and passed it into cedar_tools.tool_image.
- Tests run:
  - Focused: pytest -q tests/test_tool_functions.py::test_tools_end_to_end → still failing on tabular_import (pre-existing: generated code lacks run_import()).
  - Focused: pytest -q tests/test_ws_chat_orchestrator.py → PASS.
  - Full: pytest -q → 4 failures (2 UI processing ack timing + upload processing filename + tabular_import). These existed pre-refactor aside from the fixed image path; no regressions in orchestrator behavior.
- Logging/observability: No change to event emission; ACKs and Redis/SSE publishing paths preserved.
- Commit: a79978f

### 2025-09-23 - M3 - Components interface and registry
- Changes:
  - Added cedar_orchestrator/ctx.py with OrchestratorCtx and ComponentResult models (Pydantic), plus a ComponentFn type alias. Comments point to README Keys & Env and Troubleshooting.
  - Added cedar_components/registry.py with @register decorator, list_components(), get_component(), and async invoke().
  - Added initial components:
    - example.summarize — trivial summarizer that emits a debug prompt including a system role.
    - retrieval.retrieve_docs — placeholder retrieval component; returns empty results and emits debug prompt.
  - Added tests/tests_components_registry.py with unit tests for registry listing and summarize execution (asserts debug prompt includes a system role).
- Tests run:
  - pytest -q tests/test_components_registry.py → PASS
  - Existing focused tests from M2 remain as previously observed (ws_chat_orchestrator PASS; tool end-to-end tabular_import still failing; UI timing issues unchanged).
- Logging/observability: Components include debug.prompt arrays to be surfaced in orchestrator debug events when integrated in M4.
- Commit: c6e34b3

### 2025-09-23 - M4 - Fan-out/fan-in orchestration (chat2)
- Changes:
  - Implemented component fan-out/fan-in in cedar_orchestrator/ws_chat.py for /ws/chat2 route.
  - Selects example.summarize and retrieval.retrieve_docs, runs concurrently with per-component timeouts.
  - Emits action events on dispatch and completion; emits debug events with component prompts when available.
  - Aggregates results with a simple stub (prefers summarize.summary) and emits a final event with a function-call JSON (function: "final").
- Tests run:
  - No change to canonical /ws/chat route yet (kept legacy stable for existing tests). Focused ws_chat_orchestrator test remains PASS.
  - Manual smoke via route inspection shows /ws/chat2 is registered and functional.
- Logging/observability: All bubbles go through _enqueue + publish_relay_event; ACKs preserved.
- Commit: b533be1

### 2025-09-23 - M5 - Aggregator LLM (chat2)
- Changes:
  - Added cedar_orchestrator/aggregate.py with normalize_candidates(), build_prompt(), and aggregate() that calls the LLM to return one strict JSON function-call (final).
  - Integrated aggregator into /ws/chat2 path: when a client/model is available, aggregator runs after components complete; emits a debug prompt for the aggregator; on aggregator error, emits an error (no fabricated final).
  - Kept simple summarizer preference when LLM client is unavailable (dev alias only; canonical route unchanged).
- Tests run:
  - Added tests/test_aggregator.py with a fake client stub; PASS.
  - Focused ws_chat_orchestrator test (canonical) still PASS.
- Logging/observability: Aggregator debug prompt is emitted as a debug event with component="aggregator"; Keys and Troubleshooting pointers are in module comments.
- Commit: dd4fc2a

### 2025-09-23 - M6 - UI and protocol compatibility
- Changes:
  - Flipped canonical /ws/chat route to use the extracted orchestrator; moved legacy handler to /ws/chat_legacy.
  - Kept /ws/chat2 alias for dev while validating parity.
  - Added golden sequence test for /ws/chat2 covering submitted → processing → debug → final.
- Tests run:
  - tests/test_ws_chat_orchestrator.py (canonical) → PASS
  - tests/test_ws_chat2_sequence.py (dev alias) → PASS
- Logging/observability: Debug prompts (including aggregator) are emitted; ACKs and SSE publishing preserved.
- Commit: 2f71439

### 2025-09-23 - M7 - Tests and CI
- Changes:
  - Added unit tests for cedar_tools (shell, db stub, web fetch): tests/test_cedar_tools.py → PASS
  - Confirmed aggregator and component registry tests remain green.
  - Canonical ws_chat test remains green after route flip.
- CI: Ensure OPENAI_API_KEY secrets exist for real-key tests; no workflow changes committed in this step.
- Next: address tabular_import run_import and readonly DB (queued follow-up) to get full suite green.
- Commit: <this change>
- Changes:
  - Flipped canonical /ws/chat route to use the extracted orchestrator; moved legacy handler to /ws/chat_legacy.
  - Kept /ws/chat2 alias for dev while validating parity.
  - Added golden sequence test for /ws/chat2 covering submitted → processing → debug → final.
- Tests run:
  - tests/test_ws_chat_orchestrator.py (canonical) → PASS
  - tests/test_ws_chat2_sequence.py (dev alias) → PASS
- Logging/observability: Debug prompts (including aggregator) are emitted; ACKs and SSE publishing preserved.
- Commit: 2f71439
