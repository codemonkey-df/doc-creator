# Epic 2: AI-Powered Content Generation Pipeline — Story Decomposition

**Epic ID:** 2  
**Epic Goal:** Deliver the core agent loop: LLM reads source files, maintains context, and produces structured markdown (chapters/sections/subsections) with strict fidelity and human-in-the-loop for missing refs.  
**Business Value:** Core product value (raw files → structured narrative); quality and safety (no summarization, user resolves missing references).  
**Epic Acceptance Criteria (Reference):** FC002 (structure), FC003 (context), FC004 (fidelity), FC006 (human-in-the-loop), plus agent system prompt and tool usage per spec.

**Dependencies:** Epic 1 (Secure Input & Session Foundation) — session created at entry, graph starts at `scan_assets` with `session_id` and `input_files` in state.

**Technical Review:** This backlog was updated with findings from the technical audit. See `.project/stories/epic-2-technical-review.md` for full detail. Key decisions: (1) DocumentState in single module with optional/required keys and `generation_complete`; (2) minimal `scan_assets` node implemented in 2.1 so graph is runnable; (3) tool factory `get_tools(session_id)` and `list_files(session_id)` only; path validation on all tools; (4) state `messages` as `List[BaseMessage]` for agent/tool loop; agent node single-step; (5) `user_decisions` schema and `interrupt_before`; upload path validation; (6) custom tools node or state updater so `route_after_tools` has `last_checkpoint_id` and `pending_question`.

---

## Story 2.1: Define LangGraph DocumentState and Integrate with Workflow Start

### Refined Acceptance Criteria

- **AC2.1.1** `DocumentState` is a single TypedDict (or equivalent) defining all keys used by the agent loop: `session_id`, `input_files`, `current_file_index`, `temp_md_path`, `structure_json_path`, `output_docx_path`, `last_checkpoint_id`, `current_chapter`, `document_outline`, `conversion_attempts`, `last_error`, `error_type`, `retry_count`, `missing_references`, `user_decisions`, `pending_question`, `status`, `messages`, `validation_passed`, `validation_issues`, `generation_complete` (and any extras per ARCHITECTURE §5.1). Required vs optional keys are documented; defaults set in build_initial_state so no key is missing when scan_assets runs.
- **AC2.1.2** Reducer semantics are explicit where needed: e.g. `messages` and `missing_references` use `Annotated[List, operator.add]` (or LangGraph convention) so nodes can append without overwriting. If agent/tool loop uses LangChain, `messages` may be `List[BaseMessage]` (see Story 2.3).
- **AC2.1.3** `build_initial_state(session_id, input_files)` (from Epic 1.4) returns a state dict that conforms to `DocumentState` with all required keys and defaults; no key required by the graph is missing.
- **AC2.1.4** Workflow start: graph’s entry is `scan_assets`. No session creation or sanitization inside the graph; state is pre-populated by entry. **Minimal scan_assets node** is implemented in this story: reads input files, detects image refs (regex), sets `missing_references` and `pending_question` or `status="processing"`; no asset copy if deferred to Epic 3.
- **AC2.1.5** DocumentState is defined in a **single module** (e.g. `state.py` or `graph.py`); build_initial_state and graph import the same type. First node (scan_assets) receives state containing `session_id` and `input_files`; all subsequent nodes and tools consume `session_id` from state for paths.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define DocumentState TypedDict with all keys from ARCHITECTURE | Dev | 3 SP | Implement in `graph.py` or `state.py`: session, input, processing paths, context, error, human-in-the-loop, status, messages; type hints and docstrings. |
| 2 | Add reducer annotations for list fields (messages, missing_references) | Dev | 2 SP | Use `Annotated[List[str], operator.add]` (or LangGraph equivalent) so nodes can append; document semantics. |
| 3 | Align build_initial_state output with DocumentState | Dev | 2 SP | Ensure build_initial_state returns dict with every key the graph expects; set defaults (e.g. current_file_index=0, status="scanning_assets", conversion_attempts=0, retry_count=0, document_outline=[], user_decisions={}). |
| 4 | Wire graph START to first node (scan_assets or session_ready) | Dev | 2 SP | StateGraph entry edge: START → scan_assets; no initialize node that creates session; document that entry injects state. |
| 5 | Ensure first node reads only from state (no SessionManager.create) | Dev | 1 SP | scan_assets (or session_ready) uses state["session_id"] and state["input_files"]; add assertion or contract comment. |
| 6 | Document DocumentState and initial state shape | Dev | 1 SP | In ARCHITECTURE or code: required keys, defaults, who sets them (entry vs first node). |
| 7 | Unit test: build_initial_state conforms to DocumentState | QA/Dev | 2 SP | Assert all required keys present and types match; test reducer behavior if testable in isolation. |
| 8 | Integration test: graph receives state and first node runs | QA/Dev | 2 SP | Invoke graph with built initial state; assert scan_assets runs and uses session_id/input_files. |
| 9 | Define optional vs required state keys and defaults in build_initial_state | Dev | 1 SP | TypedDict total=False or full defaults; document which keys are set by which node. |
| 10 | Implement minimal scan_assets node | Dev | 3 SP | Read input files, detect image refs (regex), set missing_references and pending_question or status=processing; no asset copy if deferred to Epic 3. |
| 11 | Document DocumentState in single module; graph and entry import same type | Dev | 0.5 SP | state.py or graph.py; build_initial_state uses same keys. |
| 12 | Integration test: scan_assets routes to human_input or agent | QA/Dev | 2 SP | With missing refs → human_input path; without → agent path. |

### Technical Risks & Dependencies

- **Risk:** LangGraph version may use different reducer syntax; verify with LangGraph ≥1.0.
- **Dependency:** Epic 1.4 (build_initial_state, entry flow) must be done; DocumentState must match what entry provides.

### Definition of Done

- [ ] `DocumentState` implemented with full type hints; reducer annotations for append-only list fields; required vs optional keys and defaults documented.
- [ ] `build_initial_state` returns state conforming to DocumentState; single module for state type; graph and entry import same DocumentState.
- [ ] Minimal scan_assets node implemented; graph starts at scan_assets; no session create inside graph.
- [ ] Unit test for initial state shape; integration tests for first node and for scan_assets exit paths (human_input vs agent).
- [ ] Lint and type-check pass; state shape documented.

---

## Story 2.2: Implement Tool Node — list_files, read_file, read_generated_file, append_to_markdown, edit_markdown_line, Checkpoint Tools

### Refined Acceptance Criteria

- **AC2.2.1** Tools are session-scoped: every file path is under `SessionManager.get_path(session_id)`. Session ID is **injected via tool factory** `get_tools(session_id)` so tools never accept session_id from the agent; Tool Node uses `get_tools(state["session_id"])`.
- **AC2.2.2** `list_files(session_id)` lists only `{session}/inputs/` (FC007); **no directory argument from agent** to prevent path escape. Returns list of filenames valid for processing.
- **AC2.2.3** `read_file(filename, session_id)` reads `{session}/inputs/{filename}` as UTF-8; **filename must not contain `/`, `\`, or `..`** (path validation); raises clear error if file missing or not UTF-8 (FC001).
- **AC2.2.4** `read_generated_file(lines, session_id)` returns last N lines of `{session}/temp_output.md`; returns empty string if file does not exist (FC003).
- **AC2.2.5** `append_to_markdown(content, session_id)` appends content + newlines to `{session}/temp_output.md`; creates file if missing (FC002, FC004).
- **AC2.2.6** `edit_markdown_line(line_number, new_content, session_id)` replaces line at 1-based index in `temp_output.md` (FC005); validates line_number in range.
- **AC2.2.7** `create_checkpoint(label, session_id)` copies `temp_output.md` to `{session}/checkpoints/{timestamp}_{label}.md`; **label sanitized** (no path chars, no `..`); returns checkpoint_id (FC009).
- **AC2.2.8** `rollback_to_checkpoint(checkpoint_id, session_id)` copies checkpoint file back to `temp_output.md`; **checkpoint_id must be basename only** (resolve and assert under session path); returns confirmation (FC009).
- **AC2.2.9** All tools invokable via LangGraph Tool Node; tool factory and path validation ensure no arbitrary paths from agent; docstrings enable LLM to choose correct tool.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define tool module and session path helper | Dev | 1 SP | e.g. `tools.py`; helper `_session_path(session_id) -> Path` for inputs, temp_output, checkpoints. |
| 2 | Implement list_files(session_id) and read_file | Dev | 3 SP | list_files: list only session_path/inputs; read_file: read UTF-8 from inputs/; clear errors. |
| 3 | Implement read_generated_file and append_to_markdown | Dev | 3 SP | read_generated_file: last N lines of temp_output.md; append_to_markdown: append to temp file, create if missing. |
| 4 | Implement edit_markdown_line | Dev | 2 SP | 1-based line index; read lines, replace, write back; validate range. |
| 5 | Implement create_checkpoint and rollback_to_checkpoint | Dev | 3 SP | create: copy temp_output to checkpoints/{timestamp}_{label}.md; rollback: copy checkpoint to temp_output. |
| 6 | Expose tools to LangGraph via tool factory get_tools(session_id) | Dev | 2 SP | Tool Node uses get_tools(state["session_id"]); tools never receive session_id from agent. |
| 7 | Unit tests per tool (paths, errors, edge cases) | QA/Dev | 4 SP | Temp session dir; test list_files, read_file (missing/encoding), read_generated_file (empty), append, edit_line, checkpoint create/rollback. |
| 8 | Docstrings and tool descriptions for LLM | Dev | 1 SP | Clear descriptions so agent knows when to use each tool (per ARCHITECTURE §4.4). |
| 9 | Design and implement session_id injection (tool factory get_tools(session_id)) | Dev | 2 SP | get_tools(state["session_id"]) returns tools with session_id bound; graph passes state into Tool Node. |
| 10 | Change list_files to list_files(session_id) and list only session inputs/ | Dev | 1 SP | Remove directory arg; list session_path/inputs for safety. |
| 11 | Add path and argument validation to all tools (filename, label, checkpoint_id) | Dev | 2 SP | Reject path traversal and invalid args; raise ValueError with clear message. |
| 12 | Unit tests: path traversal attempts rejected (security) | QA/Dev | 1 SP | Try "../etc/passwd", "..", path separators in filename/label; assert rejected. |

### Technical Risks & Dependencies

- **Risk:** Passing `session_id` into tools: use **tool factory** get_tools(session_id) so tools are bound at node run time; document in DoD.
- **Dependency:** Epic 1 (SessionManager, session layout); Story 2.1 (DocumentState with session_id).

### Definition of Done

- [ ] All 7 tools implemented in `tools.py` (or agreed path); session-scoped paths only; list_files(session_id) only.
- [ ] Tool factory get_tools(session_id) implemented; Tool Node uses get_tools(state["session_id"]); no tool accepts arbitrary paths from agent.
- [ ] Path validation on every tool (filename, label, checkpoint_id); security tests for path traversal.
- [ ] Unit tests for each tool and for path traversal rejection; FC001, FC002, FC003, FC004, FC005, FC007, FC009 satisfied.
- [ ] Lint and type-check pass.

---

## Story 2.3: Implement Agent Node — System Prompt, Tool Binding, State Updates

### Refined Acceptance Criteria

- **AC2.3.1** Agent uses a system prompt that enforces: (1) structure (Chapters → Sections → Subsections; # → ## → ###, no skips), (2) fidelity (code/logs verbatim in fenced blocks; no summarization), (3) context (read current document state before appending), (4) when to interrupt (on missing external file reference — ask user) (FC002, FC003, FC004, FC006).
- **AC2.3.2** Prompt is configurable (e.g. from file or env) or at least a single maintainable constant; workflow instructions and formatting guidelines match ARCHITECTURE §4.3.
- **AC2.3.3** Agent is bound to all tools from Story 2.2; LLM can invoke list_files, read_file, read_generated_file, append_to_markdown, edit_markdown_line, create_checkpoint, rollback_to_checkpoint.
- **AC2.3.4** Agent node is **single-step**: one LLM invoke per node run; reads state["messages"] (as `List[BaseMessage]` for agent/tool loop), appends user prompt and AIMessage, returns state with messages, **generation_complete**, and **pending_question** set from response. No internal ReAct loop (graph provides agent → tools → agent). User prompt includes **validation_issues** when returning from validate_md so agent can fix.
- **AC2.3.5** LLM integration uses LiteLLM with model and temperature from config; no hardcoded secrets. Tools bound via get_tools(state["session_id"]) from Story 2.2.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Capture system prompt text from ARCHITECTURE §4.3 | Dev | 2 SP | Fidelity, structure, context, interrupt rules, workflow steps, formatting guidelines; store as constant or template. |
| 2 | Build user prompt template with state (current file, chapter, session) | Dev | 2 SP | e.g. “You are processing file: {current_file}; Chapter: {current_chapter}; call read_file, read_generated_file, append_to_markdown…” |
| 3 | Initialize LLM (LiteLLM) with config (model, temperature) | Dev | 2 SP | Use env/config for model and temperature; no API keys in code. |
| 4 | Bind tools to agent (create_react_agent or ToolNode + agent) | Dev | 3 SP | Pass list of tools; ensure session_id is available (injected from state into tool wrappers if needed). |
| 5 | Implement agent_node(state) -> state update | Dev | 4 SP | Build messages from state; call LLM with tools; parse response; update state (current_chapter, messages, pending_question if external ref detected). |
| 6 | Detect “external reference” / “interrupt” from agent output | Dev | 2 SP | If agent indicates missing file or asks user, set pending_question and/or flag for routing to human_input. |
| 7 | Unit test: agent prompt contains required instructions | QA/Dev | 1 SP | Assert system prompt includes fidelity, structure, interrupt keywords. |
| 8 | Integration test: agent + tools (mock LLM or small model) | QA/Dev | 3 SP | Run agent_node with mock state; verify tool calls possible and state shape after step. |
| 9 | Align state["messages"] with LangChain BaseMessage for agent/tool loop | Dev | 3 SP | Use List[BaseMessage]; update build_initial_state; ensure Tool Node receives/returns same format. |
| 10 | Implement agent_node as single-step (no internal ReAct loop); return state with messages + flags | Dev | 2 SP | One LLM invoke per node run; append AIMessage; set generation_complete and pending_question from response. |
| 11 | Define completion detection (generation_complete) and optional request_human_input tool | Dev | 2 SP | Set generation_complete when LLM signals done; add tool or parse content for pending_question. |
| 12 | User prompt template: include validation_issues when returning from validate_md | Dev | 1 SP | When state has validation_issues, inject into user prompt so agent can fix. |

### Technical Risks & Dependencies

- **Risk:** Token limits: prompt + last 100 lines + tools may be large; consider truncation or summarization of “read_generated_file” in prompt.
- **Dependency:** Story 2.1 (state), Story 2.2 (tools); Epic 1 (session_id in state).

### Definition of Done

- [ ] System prompt and user prompt template implemented; content matches ARCHITECTURE; prompt includes validation_issues when present.
- [ ] state["messages"] is List[BaseMessage]; agent node single-step; state updated with generation_complete and pending_question.
- [ ] Completion detection and external reference detection documented and implemented.
- [ ] LLM config from env; no hardcoded secrets. Tests for prompt content and agent+tool integration.
- [ ] Lint and type-check pass.

---

## Story 2.4: Implement Human-in-the-Loop — Interrupt on Missing Reference, Inject User Decision, Resume

### Refined Acceptance Criteria

- **AC2.4.1** When missing external file references are detected (e.g. in scan_assets or by agent), the workflow pauses and prompts the user (FC006): e.g. “Upload file or Skip?” with list of missing refs.
- **AC2.4.2** User decision is injected into state: **user_decisions schema** — `dict[str, str]` mapping ref to `"skip"` or **validated path** for upload (path must be validated with InputSanitizer before copy to session assets). Document contract; no arbitrary paths.
- **AC2.4.3** After user input, entry (or human_input node) validates upload paths, copies to session assets, updates state; workflow resumes to agent. Routing deterministic; human_input node returns state and edges to agent.
- **AC2.4.4** LangGraph **interrupt_before=["human_input"]** used; when graph would transition to human_input, it returns; caller injects user_decisions, then **resume** (update_state + invoke or invoke with state). Checkpointer and thread_id required; document resume API for LangGraph 1.x.
- **AC2.4.5** At most two interrupt points in Epic 2 scope: (1) after scan_assets when missing_references non-empty, (2) when agent sets pending_question (external ref during generation). Both lead to same “ask user” flow and resume.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define conditional edge: scan_assets → human_input when missing_references | Dev | 2 SP | If state["missing_references"]: route to human_input (interrupt); else route to agent. |
| 2 | Define human_input node and interrupt semantics | Dev | 3 SP | Node that presents pending_question to “user”; in tests, inject user_decisions; in production, callback or API returns user response. |
| 3 | Implement state update from user: user_decisions, clear pending_question | Dev | 2 SP | When resuming, state includes user_decisions (ref → upload/skip); clear missing_references for “skip” or after handling. |
| 4 | Resume routing: after human_input → agent or asset handling | Dev | 2 SP | If upload: copy file to session assets, update refs; then go to agent. If skip: mark ref as skipped, go to agent. |
| 5 | Wire agent → human_input when agent sets pending_question (external ref) | Dev | 2 SP | Conditional edge from tools/agent: if pending_question set, route to human_input; same inject/resume flow. |
| 6 | Use LangGraph checkpointer for interrupt/resume | Dev | 2 SP | Compile graph with checkpointer (e.g. MemorySaver); invoke with config that allows resume; document thread_id usage. |
| 7 | Unit test: state transition with mock user_decisions | QA/Dev | 2 SP | Simulate user choosing “skip”; assert state updated and next node is agent. |
| 8 | Integration test: full interrupt → inject → resume | QA/Dev | 3 SP | Run until interrupt; inject user_decisions; resume; assert processing continues. |
| 9 | Define user_decisions schema (ref → "skip" | validated path for upload) | Dev | 1 SP | TypedDict or dict contract; document that upload path must be validated. |
| 10 | Use interrupt_before=["human_input"] and document resume (update_state or invoke) | Dev | 2 SP | Compile with interrupt_before; document how entry resumes with user_decisions. |
| 11 | Validate upload paths with InputSanitizer before copy to session assets | Dev | 2 SP | When user provides path for upload, validate then copy to session_path/assets. |
| 12 | human_input node: no-op or process user_decisions; edge to agent | Dev | 1 SP | Node returns state; edge human_input → agent; entry or node does copy. |

### Technical Risks & Dependencies

- **Risk:** “Upload” may require async file upload in real API; for CLI/minimal flow, “skip” and optional path injection may suffice first.
- **Dependency:** Story 2.1 (state with missing_references, user_decisions, pending_question), Story 2.3 (agent sets pending_question).

### Definition of Done

- [ ] Two interrupt points implemented: scan_assets and agent; both route to human_input; interrupt_before and resume flow documented.
- [ ] user_decisions schema documented; upload path validated with InputSanitizer before copy; human_input node and edge defined.
- [ ] Checkpointer used; resume with same thread_id works in test.
- [ ] Unit and integration tests for interrupt and resume; FC006 satisfied.
- [ ] Lint and type-check pass.

---

## Story 2.5: Wire Agent ↔ Tools Loop and Routing (Validate, Conversion, Ask User)

### Refined Acceptance Criteria

- **AC2.5.1** Agent and tools form a loop: agent → tools → (route) → agent | validate_md | human_input | parse_to_json (conversion path). No infinite loop: routing eventually sends to validate, human_input, or conversion.
- **AC2.5.2** `route_after_tools(state)` implements: (1) if pending_question → human_input, (2) if last_checkpoint_id set → validate_md, (3) if generation_complete → parse_to_json (complete), (4) else → agent. last_checkpoint_id and pending_question set by custom tools node or state updater after running tools.
- **AC2.5.3** validate_md node runs markdown validation (markdownlint); sets validation_passed and validation_issues; on fail routes back to agent; on pass continues to agent. markdownlint dependency documented in DoD.
- **AC2.5.4** Conversion path: when routing chooses “complete”, flow goes to parse_to_json (or equivalent); conversion and quality check nodes are out of scope for Epic 2 but the edge and state keys (e.g. structure_json_path, output_docx_path) are prepared.
- **AC2.5.5** Graph is compilable and runnable end-to-end for the “content generation” slice: scan_assets → agent ↔ tools → validate (when needed) → (when complete) → next phase; human_input interrupts as in Story 2.4.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement route_after_tools(state) with four outcomes | Dev | 3 SP | Return "agent" | "validate" | "human_input" | "complete" based on checkpoint, pending_question, file index, completion flag. |
| 2 | Add conditional edges: tools → route_after_tools → agent/validate/human_input/parse_to_json | Dev | 3 SP | workflow.add_conditional_edges("tools", route_after_tools, {...}). |
| 3 | Implement validate_md node (markdownlint or equivalent) | Dev | 3 SP | Run validation on temp_output.md; set state validation_passed and last_error/validation_issues; return state. |
| 4 | Add edges: validate_md → agent (fix) or continue to agent (next chapter) | Dev | 2 SP | If validation failed: state with issues back to agent; if passed: back to agent for next chunk or route to complete. |
| 5 | Define “complete” path: to parse_to_json (stub or real) | Dev | 2 SP | Edge from route_after_tools "complete" to parse_to_json node; parse_to_json can stub that only sets structure_json_path if conversion not in scope. |
| 6 | Ensure agent node sets generation_complete when done | Dev | 2 SP | State updates in agent_node: set generation_complete when LLM signals completion (Story 2.3). |
| 7 | Integration test: agent → tools → validate → agent loop | QA/Dev | 4 SP | Run graph with mock LLM or scripted tool responses; assert validation runs after checkpoint and routing returns to agent or to complete. |
| 8 | Document routing table and when each branch is taken | Dev | 1 SP | In code or ARCHITECTURE: table of route_after_tools outcomes and conditions. |
| 9 | Custom tools node or state updater: set last_checkpoint_id and pending_question from tool results | Dev | 3 SP | After running tools, update state from create_checkpoint and request_human_input (if used) so route_after_tools can branch. |
| 10 | route_after_tools: use generation_complete for complete branch; document order of checks | Dev | 1 SP | Prefer generation_complete; document priority (human_input > validate > complete > agent). |
| 11 | parse_to_json stub: write minimal structure.json and set structure_json_path | Dev | 1 SP | File and state key so conversion epic can consume. |
| 12 | DoD: markdownlint dependency and install path; max agent iterations or deadlock note | Dev/QA | 1 SP | Document markdownlint; optional max_steps to prevent infinite loop. |

### Technical Risks & Dependencies

- **Risk:** Completion uses state["generation_complete"] from agent node; routing needs last_checkpoint_id and pending_question from tools (custom node or state updater).
- **Dependency:** Stories 2.1–2.4; validate_md node (FC010); parse_to_json stub for Epic 2.

### Definition of Done

- [ ] route_after_tools implemented with four-way routing; state updated from tool results (last_checkpoint_id, pending_question); conditional edges wired.
- [ ] validate_md node implemented; sets validation_passed and validation_issues; routes back to agent on fail, continues on pass.
- [ ] parse_to_json stub writes structure.json and sets structure_json_path; complete path leads to stub.
- [ ] markdownlint dependency and (optional) max agent iterations documented; integration test for full loop; no deadlock.
- [ ] Routing logic documented; lint and type-check pass.

---

## Epic 2 Summary: Prioritization and Estimates

| Story | Summary | Story Points | Priority | Dependencies |
|-------|---------|--------------|----------|--------------|
| 2.1 | DocumentState + workflow start + minimal scan_assets | 22 | P0 | Epic 1.4 |
| 2.2 | Tool Node (7 tools) + factory, path validation | 25 | P0 | 2.1, Epic 1 |
| 2.3 | Agent node (prompt, tools, BaseMessage, generation_complete) | 27 | P0 | 2.1, 2.2 |
| 2.4 | Human-in-the-loop (interrupt_before, user_decisions, upload validation) | 24 | P1 | 2.1, 2.3 |
| 2.5 | Agent ↔ tools loop, custom tools/state updater, routing, validate_md, stub | 26 | P1 | 2.1, 2.2, 2.3, 2.4 |

**Suggested sprint order:** 2.1 → 2.2 and 2.3 (2.2 first or in parallel with 2.3) → 2.4 → 2.5.  
**Total Epic 2:** ~124 SP (includes technical review additions; adjust to team scale).

---

## Architecture Decisions (Epic 2)

- **DocumentState:** Single TypedDict in one module (state.py or graph.py); optional/required keys documented; list fields with reducer; add generation_complete, validation_passed, validation_issues; built by entry via build_initial_state (Epic 1.4).
- **Graph start:** START → scan_assets; minimal scan_assets implemented in 2.1 (detect missing refs; no session create in graph).
- **Tools:** Tool factory get_tools(session_id) so session_id is never from agent; list_files(session_id) only; path validation on all tools (no traversal). Custom tools node or state updater sets last_checkpoint_id and pending_question from tool results for routing.
- **Messages:** state["messages"] as List[BaseMessage] for agent/tool loop (LangGraph/LangChain compatibility); agent node single-step.
- **Interrupts:** interrupt_before=["human_input"]; user_decisions schema (ref → "skip" | validated path); upload path validated with InputSanitizer; resume via update_state or invoke with state.
- **Routing:** route_after_tools uses pending_question, last_checkpoint_id, generation_complete; priority human_input > validate > complete > agent.

---

## MECE & Vertical Slice Check

- **MECE:** State (2.1) | Tools (2.2) | Agent (2.3) | Human-in-the-loop (2.4) | Routing and loop (2.5) are non-overlapping. Together they cover the “agent reads source, maintains context, produces markdown, interrupts for user” scope.
- **Vertical slice:** Story 2.5 delivers the end-to-end content-generation slice: scan_assets → agent ↔ tools → validate → (optional human_input) → complete; 2.1–2.4 are enabling.
- **Epic alignment:** FC002 (structure), FC003 (context), FC004 (fidelity), FC006 (human-in-the-loop), and agent/tool spec from ARCHITECTURE are covered by the five stories above.
