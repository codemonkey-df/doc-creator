# Epic 4: Validation, Checkpointing & Recovery — Story Decomposition

**Epic ID:** 4  
**Epic Goal:** Ensure intermediate markdown is valid before conversion and support rollback on failure via checkpoints.  
**Business Value:** Catches syntax/structure issues early (before docx-js); enables retry from last good state instead of full restart.  
**Epic Acceptance Criteria (Reference):** FC009 (save checkpoint after each successful chapter; format `{timestamp}_{label}.md`; support rollback), FC010 (run markdownlint before conversion; return structured issues e.g. line numbers to agent for fixes). Validation triggers after "chapter done"; failed validation routes back to agent with issue payload.

**Dependencies:** Epic 2 (AI-Powered Content Generation Pipeline — agent/tools and "chapter done" semantics). Epic 6 (Error-handling path handshake for rollback before retry).

**Architecture alignment:** ARCHITECTURE §3.1 (MdValidator, Checkpointer in Agent Loop), §4.4 (create_checkpoint, rollback_to_checkpoint, validate_markdown tools), §4.5 (Markdown Validator FC010), §5.1 (DocumentState: last_checkpoint_id, validation_passed, validation_issues), §5.2–5.3 (validate_md node, conditional edges, checkpoint after valid, error_handler → Rollback).

**Technical Review:** This backlog was updated with findings from the technical audit. See `.project/stories/epic-4-technical-review.md` for full detail. Key decisions: (1) Checkpoint node label is state-derived only (`chapter_{current_chapter}`); timestamp uniqueness (sequence or time_ns); (2) DocumentState + ValidationIssue schema; markdownlint-cli pinned with JSON normalizer; subprocess timeout and missing-file handling; (3) route_after_tools order and fix_attempts cap; Epic 2 tools node must set last_checkpoint_id from create_checkpoint result; (4) Shared restore_from_checkpoint(session_id, checkpoint_id) in utils/checkpoint.py; Epic 6 contract; missing checkpoint → skip rollback, still route to agent.

---

## Story 4.1: Checkpoint Node and Tool Integration — Save After Each Successful Chapter, Rollback Available

### Refined Acceptance Criteria

- **AC4.1.1** A **checkpoint graph node** runs after markdown validation passes (i.e. when the flow is: tools → validate_md → valid → checkpoint node → agent). The node copies `{session}/temp_output.md` to `{session}/checkpoints/{timestamp}_{label}.md`; timestamp format is deterministic (e.g. `%Y%m%d_%H%M%S`) with **timestamp uniqueness** (sequence or time_ns if file exists). **Label is state-derived only:** `chapter_{current_chapter}` (no agent label in node). Tool create_checkpoint(label) remains for agent-requested pre-validation snapshots; node writes one canonical post-validation checkpoint per chapter (FC009).
- **AC4.1.2** After the checkpoint node runs, state is updated with **last_checkpoint_id** (basename of written file, e.g. `{timestamp}_{label}.md`) so that rollback and error-handling can target this checkpoint. The node does not invoke the agent; it only performs the file copy and state update. Path resolution uses **SessionManager.get_path(session_id)** for temp_output and checkpoints.
- **AC4.1.3** **Rollback** to a chosen checkpoint is available via the existing **rollback_to_checkpoint(checkpoint_id, session_id)** tool (Epic 2.2), which SHALL call the shared **restore_from_checkpoint(session_id, checkpoint_id)** helper (Story 4.4). Checkpoint_id must be a basename under `{session}/checkpoints/` (path validation, no traversal).
- **AC4.1.4** Checkpoint **label** is sanitized (no path separators, no `..`); the **node** always uses state-derived label; the create_checkpoint **tool** sanitizes agent-provided label independently.
- **AC4.1.5** Session directory `checkpoints/` is created at session creation (Epic 1); the checkpoint node **asserts it exists** (or creates and logs) at node start to fail fast. Logging: log event when checkpoint is saved (checkpoint_id, session_id, label) per FC015. Checkpoint retention: document as unbounded per session or MAX_CHECKPOINTS (DoD).

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define checkpoint node signature and state contract | Dev | 2 SP | Node: state in → state out; reads session_id, temp_md_path, current_chapter (or last_checkpoint_id from tool); writes last_checkpoint_id; uses SessionManager.get_path(session_id). |
| 2 | Implement checkpoint node: copy temp_output.md to checkpoints/{timestamp}_{label}.md | Dev | 3 SP | Generate timestamp (e.g. datetime.now().strftime), label from state or default "chapter_{n}"; copy file; set last_checkpoint_id in returned state. |
| 3 | Add label sanitization and path validation for checkpoint_id | Dev | 2 SP | Label: no `/`, `\`, `..`; checkpoint_id in rollback: resolve under session/checkpoints, reject traversal. |
| 4 | Integrate checkpoint node into graph (after validate_md when valid) | Dev | 2 SP | Conditional edge: validate_md → (valid → checkpoint node → agent). Add node to workflow and edge from validate_md. |
| 5 | Ensure rollback_to_checkpoint tool is used for restore (document usage from error path) | Dev | 1 SP | Document that error_handler (Story 4.4) or agent can call rollback_to_checkpoint; ensure tool is in get_tools. |
| 6 | Structured logging in checkpoint node (FC015) | Dev | 1 SP | Log event: checkpoint_saved, checkpoint_id, session_id, label. |
| 7 | Unit tests: checkpoint node with temp session (copy, state update) | QA/Dev | 3 SP | Create temp_output.md, run node, assert file in checkpoints/ and last_checkpoint_id set. |
| 8 | Unit tests: rollback_to_checkpoint restores temp_output.md | QA/Dev | 2 SP | Create checkpoint file, run rollback tool, assert temp_output.md content matches checkpoint. |
| 9 | Integration test: validate → checkpoint → agent path | QA/Dev | 2 SP | Run graph segment; assert checkpoint created and state has last_checkpoint_id. |
| 10 | Document checkpoint format and label source (state vs tool) in DoD | Dev | 0.5 SP | DoD: format {timestamp}_{label}.md; label from state or default. |
| 11 | Decide and document label source: node uses state-only label (chapter_{current_chapter}) | Dev | 0.5 SP | DoD: label = chapter_{current_chapter}; tool label independent. |
| 12 | Implement timestamp uniqueness (sequence or time_ns) when destination file exists | Dev | 1 SP | If destination exists, append _seq or use time_ns; avoid overwrite. |
| 13 | Assert or create checkpoints/ at node start; use SessionManager path for temp_output | Dev | 0.5 SP | Fail fast if checkpoints/ missing; document path resolution. |
| 14 | Optional: document checkpoint retention (unbounded vs MAX_CHECKPOINTS) | Dev | 0.5 SP | DoD or ADR: retention policy. |

### Technical Risks & Dependencies

- **Risk:** Clock skew or high frequency could produce duplicate timestamps; address with sequence or time_ns (task 12).
- **Dependency:** Epic 1 (session layout with checkpoints/); Epic 2.2 (create_checkpoint, rollback_to_checkpoint tools); Story 4.3 (conditional edge from validate_md to checkpoint node).

### Definition of Done

- [ ] Checkpoint graph node implemented; copies temp_output.md to checkpoints/{timestamp}_{label}.md; updates last_checkpoint_id; label is state-derived only (`chapter_{current_chapter}`); label sanitized.
- [ ] Timestamp uniqueness strategy implemented and tested; checkpoints/ asserted or created; path resolution uses SessionManager.
- [ ] Node integrated after validate_md on "valid" path; rollback via existing tool (delegating to restore_from_checkpoint when implemented) documented and available.
- [ ] Unit and integration tests; structured logging; lint and type-check pass. **Contract:** Checkpoint node writes exactly one file per run; last_checkpoint_id is the basename of that file.

---

## Story 4.2: Markdown Validator Node — Run markdownlint, Map Output to State

### Refined Acceptance Criteria

- **AC4.2.1** A **validate_markdown** graph node runs when the workflow routes to validation (after "chapter done" — see Story 4.3). The node runs **markdownlint-cli** (pinned npm package) on `{session}/temp_output.md` with **JSON to stdout** (`markdownlint <path> -j` or `--json`). **Subprocess timeout** (e.g. 30s) is enforced; on timeout, validation_passed=False with synthetic issue "Validation timeout".
- **AC4.2.2** Node maps markdownlint output to state via a **ValidationIssue** schema: **validation_passed** (bool); **validation_issues** (List[ValidationIssue]) with at least **line_number**, **rule** or **rule_description**, **message** or **error_detail**. **ValidationIssue** is a TypedDict (total=False) and is added to DocumentState; normalizer maps markdownlint JSON (e.g. lineNumber, ruleNames, ruleDescription, errorDetail) to ValidationIssue (FC010).
- **AC4.2.3** If markdownlint is not installed, subprocess fails, **temp_output.md is missing**, or JSON parse fails: set validation_passed=False and validation_issues with a single synthetic issue; no unhandled exception.
- **AC4.2.4** State keys **validation_passed** and **validation_issues** are added to DocumentState in this story; agent node reads validation_issues when routing back to fix (Story 4.3).
- **AC4.2.5** Structured logging: log event (validation_ran, passed/failed, issue_count); FC015. **markdownlint-cli** version and JSON contract documented in DoD and ARCHITECTURE §7.3.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define validation_issues schema (line_number, rule, message) and DocumentState keys | Dev | 2 SP | TypedDict or list of dicts; add validation_passed (bool) and validation_issues (list) to DocumentState. |
| 2 | Implement validate_markdown node: subprocess markdownlint --json | Dev | 3 SP | Run markdownlint on session temp_output.md; capture stdout; parse JSON; map to validation_issues list. |
| 3 | Map markdownlint JSON format to validation_issues (line numbers, rule, detail) | Dev | 2 SP | Handle markdownlint JSON shape (e.g. lineNumber, ruleNames, ruleDescription, errorDetail); normalize to common schema. |
| 4 | Set validation_passed and validation_issues in returned state | Dev | 1 SP | returncode 0 → passed, issues=[]; else passed=False, issues=parsed list. |
| 5 | Handle missing markdownlint or subprocess errors | Dev | 2 SP | FileNotFoundError, non-zero exit for non-JSON; set validation_passed=False, one synthetic issue with message. |
| 6 | Add validate_markdown node to workflow | Dev | 1 SP | workflow.add_node("validate_md", validate_markdown_node). |
| 7 | Structured logging (validation_ran, passed, issue_count) | Dev | 1 SP | Use session logger; log after run. |
| 8 | Unit tests: node with valid markdown (passed=True, issues=[]) | QA/Dev | 2 SP | Temp session with valid temp_output.md; assert state. |
| 9 | Unit tests: node with invalid markdown (unclosed fence, bad table) | QA/Dev | 3 SP | Fixture with known lint errors; assert validation_issues populated with line numbers. |
| 10 | Unit tests: markdownlint missing or subprocess failure | QA/Dev | 2 SP | Mock or skip-if-no-cli; assert no crash, validation_passed=False and synthetic issue. |
| 11 | Document markdownlint CLI requirement and JSON format in DoD | Dev | 0.5 SP | DoD: markdownlint-cli with --json; schema of validation_issues. |
| 12 | Add validation_passed and validation_issues to DocumentState; define ValidationIssue TypedDict | Dev | 2 SP | state.py or graph.py; export ValidationIssue; document in ARCHITECTURE §5.1. |
| 13 | Pin markdownlint CLI (markdownlint-cli) and document JSON shape; implement normalizer to ValidationIssue | Dev | 2 SP | Map lineNumber, ruleNames, ruleDescription, errorDetail to ValidationIssue; handle array vs single object. |
| 14 | Add subprocess timeout (e.g. 30s) and handle TimeoutExpired | Dev | 1 SP | validation_passed=False, synthetic issue "Validation timeout". |
| 15 | Handle missing temp_output.md before calling markdownlint | Dev | 0.5 SP | If not path.exists(), return failed with synthetic issue. |
| 16 | Document markdownlint-cli version and JSON contract in DoD and §7.3 | Dev | 0.5 SP | Version and example JSON in ARCHITECTURE. |

### Technical Risks & Dependencies

- **Risk:** markdownlint JSON format may vary by version; pin markdownlint-cli and implement normalizer (tasks 13, 16).
- **Dependency:** Epic 2 (temp_output.md produced by agent); Story 4.3 (conditional edge from tools to validate_md). System dependency: markdownlint-cli installed (document in ARCHITECTURE §7.3).

### Definition of Done

- [ ] DocumentState includes validation_passed and validation_issues; **ValidationIssue** schema defined and used.
- [ ] validate_markdown node implemented; runs markdownlint-cli --json; sets validation_passed and validation_issues in state; normalizer to ValidationIssue.
- [ ] Subprocess timeout (e.g. 30s) and missing temp_output.md handled; no unhandled exception.
- [ ] markdownlint-cli version and JSON contract documented in DoD and ARCHITECTURE §7.3.
- [ ] Unit tests for pass/fail and error paths; structured logging; lint and type-check pass. **Contract:** Node always returns state with validation_passed and validation_issues set; agent receives list of issues with line_number and message.

---

## Story 4.3: Conditional Edges — After Tools → Validate When Chapter Complete; Validate → Agent (Fix) or Continue

### Refined Acceptance Criteria

- **AC4.3.1** **After tools:** A conditional edge from the **tools** node routes via **route_after_tools(state)** with **defined evaluation order**: (1) **pending_question** → human_input, (2) **last_checkpoint_id** (chapter complete) → validate_md, (3) **generation_complete** or all files processed (current_file_index) → complete, (4) else → agent. **Precondition (Epic 2):** Tools node (or state updater) MUST set state["last_checkpoint_id"] from create_checkpoint tool result when that tool was called; otherwise route_after_tools cannot route to validate_md.
- **AC4.3.2** **Chapter complete** = state["last_checkpoint_id"] set by the tools node after create_checkpoint was executed (custom tools node or post-tools state updater in Epic 2).
- **AC4.3.3** **After validate_md:** Conditional edge: (a) **agent** (fix path) when validation_passed is False, with **fix_attempts** incremented; if fix_attempts >= MAX_FIX_ATTEMPTS (e.g. 3), route to complete/error instead to avoid infinite loop; (b) **checkpoint** node when validation_passed is True (then checkpoint → agent).
- **AC4.3.4** When routing to **agent for fix**, the agent's user prompt includes **validation_issues** (line numbers and messages). **fix_attempts** is in DocumentState (default 0); reset to 0 when validation_passed is True (optional).
- **AC4.3.5** Edges are implemented in the LangGraph workflow; document **routing table** (from-node, condition, to-node) in DoD or ARCHITECTURE.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement route_after_tools(state) with chapter_done / last_checkpoint_id logic | Dev | 3 SP | Detect chapter complete (e.g. last tool was create_checkpoint or state has chapter_done); return "validate" | "agent" | "human_input" | "complete". |
| 2 | Wire tools node conditional edge to route_after_tools | Dev | 2 SP | add_conditional_edges("tools", route_after_tools, {"validate": "validate_md", "agent": "agent", ...}). |
| 3 | Ensure tools node or state updater sets chapter_done or last_checkpoint_id when create_checkpoint runs | Dev | 3 SP | Tool node must update state with last_checkpoint_id (or chapter_done) from tool result so route_after_tools can read it. |
| 4 | Implement validate_md conditional edge: fix vs continue | Dev | 2 SP | If not state["validation_passed"] → "agent" (fix); else → "checkpoint" (then checkpoint → agent). |
| 5 | Wire validate_md → checkpoint → agent path | Dev | 2 SP | add_edge("validate_md", ...) conditional; add_edge("checkpoint", "agent"). |
| 6 | Pass validation_issues into agent context when routing to fix | Dev | 2 SP | Agent node reads state["validation_issues"] and includes in user prompt so LLM sees line numbers and messages. |
| 7 | Document chapter_done semantics and routing table | Dev | 1 SP | When we consider "chapter done"; table of from-node → conditions → to-node. |
| 8 | Integration test: tools → validate when create_checkpoint was called | QA/Dev | 3 SP | Simulate state after create_checkpoint; run route_after_tools; assert "validate". |
| 9 | Integration test: validate_md → agent (fix) when issues present | QA/Dev | 2 SP | State with validation_passed=False, validation_issues set; assert next node is agent. |
| 10 | Integration test: validate_md → checkpoint → agent when valid | QA/Dev | 2 SP | State with validation_passed=True; assert path goes to checkpoint then agent. |
| 11 | Implement fix_attempts in state and cap in validate_md conditional edge (max 3, then route to complete/error) | Dev | 1 SP | State key fix_attempts; if fix_attempts >= MAX_FIX_ATTEMPTS, route to complete or error; document. |
| 12 | Document dependency: Epic 2 tools node (or updater) sets state["last_checkpoint_id"] from create_checkpoint result | Dev | 0.5 SP | DoD and Epic 2 contract. |
| 13 | Define and document route_after_tools evaluation order (pending_question, last_checkpoint_id, complete, agent) | Dev | 1 SP | Code comment and story DoD. |
| 14 | Add fix_attempts to DocumentState; cap in validate_md routing (max 3 fix attempts then route to complete/error) | Dev | 2 SP | state key; conditional: if fix_attempts >= MAX, route to complete; else agent. |
| 15 | Add routing table to ARCHITECTURE or story DoD | Dev | 0.5 SP | Table: from-node, condition, to-node. |

### Routing Table (DoD)

| From | Condition | To |
|------|-----------|-----|
| tools | pending_question | human_input |
| tools | last_checkpoint_id | validate_md |
| tools | generation_complete or all files processed | complete |
| tools | else | agent |
| validate_md | not validation_passed and fix_attempts < MAX | agent (fix) |
| validate_md | not validation_passed and fix_attempts >= MAX | complete or error |
| validate_md | validation_passed | checkpoint |
| checkpoint | — | agent |

### Technical Risks & Dependencies

- **Risk:** Detecting "chapter done" requires Epic 2 to implement custom tools node or state updater that sets last_checkpoint_id from create_checkpoint result.
- **Dependency:** Story 4.1 (checkpoint node); Story 4.2 (validate_md node); **Epic 2 (tools node must set last_checkpoint_id when create_checkpoint called)**.

### Definition of Done

- [ ] route_after_tools implemented with documented evaluation order; chapter complete routes to validate_md; validate_md routes to agent (fix) or checkpoint → agent.
- [ ] **fix_attempts** in DocumentState with cap (e.g. MAX_FIX_ATTEMPTS=3); when exceeded, route to complete/error.
- [ ] validation_issues passed to agent when on fix path; Epic 2 contract for tools node setting last_checkpoint_id documented; routing table in DoD or ARCHITECTURE.
- [ ] Integration tests for all routing branches; lint and type-check pass. **Contract:** "Chapter complete" = state["last_checkpoint_id"] set by tools node after create_checkpoint.

---

## Story 4.4: Error-Handling Path Triggers Rollback to Last Checkpoint Before Retry (Epic 6 Handshake)

### Refined Acceptance Criteria

- **AC4.4.1** When the **error_handler** node runs (conversion failed or quality check failed), and the decision is to **retry**, the flow **restores** `temp_output.md` from the **last checkpoint** (state["last_checkpoint_id"]) before sending control back to the agent. Rollback is implemented by a **shared helper** **restore_from_checkpoint(session_id: str, checkpoint_id: str) -> bool** in a shared module (e.g. `utils/checkpoint.py` or `nodes/checkpoint.py`). The **rollback_to_checkpoint** tool (Epic 2) SHALL call this helper; the error path (Epic 6) SHALL call it when retrying (FC009, FC017).
- **AC4.4.2** Rollback is performed either: (a) **inline** inside the error_handler node (Epic 6), or (b) via a dedicated **rollback node** (error_handler → rollback → agent). **Decide and document** the chosen approach in this story and Epic 6.
- **AC4.4.3** **Missing checkpoint behavior:** If last_checkpoint_id is missing or the checkpoint file does not exist: **skip rollback**, log warning (rollback_skipped, reason), and **still route to agent** for retry (do not fail fast on first-chapter conversion error). Document in DoD.
- **AC4.4.4** **Epic 6 contract:** Epic 6 error_handler (or rollback node) MUST call restore_from_checkpoint(session_id, last_checkpoint_id) when should_retry_conversion(state) == "retry", before transitioning to agent; if helper returns False, log and continue to agent.
- **AC4.4.5** State after rollback: temp_output.md is restored when helper returns True; last_error/error_type kept for audit. Structured logging: rollback_performed or rollback_skipped with reason.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement restore_from_checkpoint(session_id, checkpoint_id) -> bool in shared module | Dev | 3 SP | utils/checkpoint.py or nodes/checkpoint.py; copy checkpoints/{checkpoint_id} to temp_output.md; path validate (basename only, no traversal); return True if restored, False if missing/invalid. |
| 2 | Use restore_from_checkpoint in rollback_to_checkpoint tool (Epic 2) | Dev | 1 SP | Tool delegates to helper; return "Restored {id}" or "Checkpoint not found". |
| 3 | Integrate rollback into retry path (inside error_handler or separate node) | Dev | 3 SP | When should_retry_conversion(state) returns "retry", call restore_from_checkpoint(state["session_id"], state["last_checkpoint_id"]) before routing to agent. |
| 4 | Handle missing last_checkpoint_id or missing checkpoint file | Dev | 2 SP | Log warning (rollback_skipped); skip rollback; still route to agent (do not fail). |
| 5 | Add conditional edge: error_handler → rollback (when retry) → agent | Dev | 2 SP | If separate rollback node: error_handler → rollback → agent when retry; else rollback inside error_handler then → agent. |
| 6 | Document Epic 6 contract: error_handler (or rollback node) calls restore_from_checkpoint before agent on retry | Dev | 1 SP | DoD and Epic 6 story 3. |
| 7 | Document missing-checkpoint behavior: skip rollback, log warning, still route to agent | Dev | 0.5 SP | DoD. |
| 8 | Decide and document: rollback in dedicated node vs inside error_handler | Dev | 0.5 SP | Architecture decision; both epics. |
| 9 | Structured logging for rollback performed / skipped | Dev | 1 SP | Log rollback_performed or rollback_skipped with reason. |
| 10 | Unit test: restore_from_checkpoint restores temp_output from checkpoint | QA/Dev | 2 SP | Temp session, create checkpoint file, run helper, assert temp_output.md content. |
| 11 | Unit test: restore_from_checkpoint when checkpoint missing (returns False, no crash) | QA/Dev | 2 SP | last_checkpoint_id set but file deleted; assert False, log and skip. |
| 12 | Integration test: conversion fail → error_handler → rollback → agent | QA/Dev | 3 SP | Simulate conversion failure, set last_checkpoint_id, run error path; assert temp_output restored and flow to agent. |
| 13 | Document rollback-before-retry in ARCHITECTURE §5.2 / §4 (Rollback) | Dev | 0.5 SP | FC009, FC017; when rollback runs; missing checkpoint = skip and continue. |

### Technical Risks & Dependencies

- **Risk:** If error_handler runs before any checkpoint exists (e.g. first chapter), last_checkpoint_id may be empty; skip rollback and still route to agent.
- **Dependency:** Story 4.1 (last_checkpoint_id set by checkpoint node); Epic 6 (error_handler node, should_retry_conversion); Epic 2 (rollback_to_checkpoint tool to use restore_from_checkpoint).

### Definition of Done

- [ ] **restore_from_checkpoint(session_id, checkpoint_id) -> bool** implemented in shared module; path validation; used by rollback_to_checkpoint tool and by error path.
- [ ] Rollback runs before retry when last_checkpoint_id is set; temp_output.md restored when helper returns True.
- [ ] Missing checkpoint or last_checkpoint_id: skip rollback, log warning, still route to agent; no unhandled exception.
- [ ] Epic 6 contract and missing-checkpoint behavior documented; rollback node vs inline decided and documented.
- [ ] Unit and integration tests; lint and type-check pass. **Contract:** Epic 4 provides restore_from_checkpoint; Epic 6 invokes it when retrying.

---

## Epic 4 Summary — Prioritization & Effort

| Story | Summary | Total Effort (SP) | Priority |
|-------|---------|-------------------|----------|
| 4.1 | Checkpoint node and tool integration | ~21 SP | P1 (foundation) |
| 4.2 | Markdown validator node | ~24 SP | P1 (validation gate) |
| 4.3 | Conditional edges (route after tools, after validate) | ~27 SP | P1 (flow) |
| 4.4 | Error-handling rollback before retry (restore_from_checkpoint, Epic 6 contract) | ~21 SP | P2 (resilience) |

**Recommended order:** Epic 2 (tools node sets last_checkpoint_id) → state schema (validation_passed, validation_issues, ValidationIssue, fix_attempts) → 4.2 → 4.1 → 4.3 → 4.4 (see technical review).

**Technical risks:** markdownlint CLI/JSON version (mitigated by pin and normalizer); chapter_done detection requires Epic 2 custom tools node or state updater; first-chapter failure with no checkpoint (skip rollback, continue to agent).

**MECE / vertical slicing:** 4.2 = validation result in state + ValidationIssue schema; 4.1 = checkpoint on disk and in state (state-derived label, timestamp uniqueness); 4.3 = correct routing + fix_attempts cap + Epic 2 contract; 4.4 = shared restore_from_checkpoint + Epic 6 contract.
