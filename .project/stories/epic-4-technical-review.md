# Epic 4: Validation, Checkpointing & Recovery — Technical Review

**Reviewer role:** Senior Software Architect / Agile Team Lead  
**Scope:** Technical deep-dive audit of decomposed stories; data models, APIs, feasibility, security, MECE, DoD.  
**Context:** Parent Epic 4, ARCHITECTURE.md (Agentic Document Generator), Epic 2 (agent/tools, “chapter done”), Epic 6 (error_handler, rollback handshake).

---

## Parent Epic Technical Context

### Architecture Assumptions

- **Orchestration:** LangGraph StateGraph(DocumentState); graph runs agent → tools → conditional (validate_md | agent | human_input | complete). Validation runs **after** “chapter done”; checkpoint node runs **after** validation when valid. Rollback runs **before** retry when error_handler chooses retry (Epic 6).
- **Tech stack:** Python 3.13, uv, LangGraph, LiteLLM; **markdownlint** (CLI) for MD validation; no DB — state in-memory and session dirs on disk (`checkpoints/`, `temp_output.md`).
- **State model:** DocumentState holds session_id, last_checkpoint_id, current_chapter, validation_passed, validation_issues, status, etc. ARCHITECTURE §5.1 **does not** list `validation_passed` or `validation_issues` in the TypedDict; they are used in §5.3 — **schema gap**.
- **Flow:** Tools node must expose **tool result to state** (e.g. last_checkpoint_id when create_checkpoint is called) so route_after_tools can send to validate_md. ARCHITECTURE §5.2 shows `ToolNode(get_all_tools())` without session_id binding; Epic 2 technical review recommends **tool factory** `get_tools(state["session_id"])` and **custom tools node** that updates state from tool results.

### Relevant ARCHITECTURE References

- **§3.1:** MdValidator (FC010), Checkpointer (FC009); flow Agent → Tools → (Chapter Done) → MdValidator → (Issues → Agent | Valid → Checkpoint → Agent).
- **§4.4:** create_checkpoint(label), rollback_to_checkpoint(checkpoint_id), validate_markdown — tools; paths under session.
- **§4.5:** markdownlint CLI, JSON response with lineNumber, ruleDescription, errorDetail; agent fixes reported issues.
- **§5.1 DocumentState:** last_checkpoint_id, status; **missing:** validation_passed, validation_issues, chapter_done / generation_complete (if used).
- **§5.2:** validate_md node; conditional edges tools → route_after_tools; validate_md → fix | continue; **no checkpoint node** in snippet — only validate_md → agent; ARCHITECTURE diagram §3.1 shows MdValidator → Valid → Checkpoint → Agent.
- **§5.3 validate_markdown_node:** Uses `markdownlint path --json`, json.loads(result.stdout). Note: some markdownlint variants write JSON to file with `-o`; clarify **stdout vs file** and **exact JSON schema** (markdownlint-cli vs markdownlint-cli2 differ).
- **§5.3 route_after_tools:** Uses last_checkpoint_id to route to "validate" — so last_checkpoint_id must be set **by the tools node** when create_checkpoint was called (not only by the checkpoint node after validation).

### Cross-Epic Dependencies

- **Epic 2:** Tool Node must update state from create_checkpoint result (last_checkpoint_id or chapter_done); get_tools(session_id); agent prompt includes validation_issues when on fix path.
- **Epic 6:** error_handler node invokes rollback **before** retry; Epic 4 provides shared **rollback helper** and documents contract (session_id, last_checkpoint_id, restore temp_output.md).
- **Epic 1:** Session layout with `checkpoints/` created at session creation.

---

## Story-by-Story Technical Audit

---

### Story 4.1: Checkpoint Node and Tool Integration — Save After Each Successful Chapter, Rollback Available

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Label source, timestamp uniqueness, and single source of checkpoint identity need design. |
| Data Model | Needs Design Work | last_checkpoint_id is in state; no schema for checkpoint metadata (list of ids, retention); temp_md_path vs derived path inconsistency. |
| API/Integration | Sound | Node is state-in/state-out; tools (Epic 2) already define create_checkpoint/rollback_to_checkpoint. |
| Technical Feasibility | Sound | File copy and state update are straightforward; duplicate timestamp risk is acknowledged. |
| Vertical Slice | Sound | Node + graph wiring + tests; rollback via existing tool. |
| Security/Compliance | Sound | Path/label sanitization and no traversal are in scope. |
| Dependencies & Risks | Medium | Epic 2 Tool Node must set last_checkpoint_id from create_checkpoint result for routing; Story 4.3 wires edges. |
| MECE | Sound | Checkpoint node vs tool: node = automatic post-validation save; tool = agent-requested save. |
| DoD Technical | Needs Design Work | Add timestamp uniqueness strategy; document label source (state vs tool) and retention. |

#### Strengths

- Clear separation: checkpoint **node** runs after validation (automatic); **rollback** via existing tool; state last_checkpoint_id for downstream.
- Label sanitization and path validation for checkpoint_id are tasked.
- Integration test for validate → checkpoint → agent path.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Label source ambiguity:** AC4.1.1 says label "derived from state (e.g. chapter_{current_chapter}) or provided by agent via last tool call." If the agent called create_checkpoint("ch2"), the **tool** already wrote a file; the **node** runs after validation and writes again. Need a single rule: (a) checkpoint node **always** uses state-derived label (e.g. chapter_{current_chapter}) so one canonical post-validation checkpoint per chapter, or (b) node reuses the last tool result checkpoint_id and only updates state (no second file write). Recommendation: **node always writes** with state-derived label; tool-created checkpoint is optional pre-validation snapshot; last_checkpoint_id after node = node-created id (post-validation).
2. **Timestamp uniqueness:** Same-second or clock skew can produce duplicate filenames. Add design: use `datetime.now().strftime("%Y%m%d_%H%M%S")` plus a **sequence suffix** (e.g. `_0`, `_1`) or **monotonic** when same second, or document "last write wins" for same second.
3. **temp_md_path in state:** ARCHITECTURE DocumentState has temp_md_path. Checkpoint node should resolve path as `SessionManager.get_path(session_id) / "temp_output.md"` (or state["temp_md_path"] if set) for consistency; document that node uses session-relative path.
4. **Checkpoint retention:** No policy for max checkpoints per session (disk growth). Optional: add config MAX_CHECKPOINTS_PER_SESSION and prune oldest; or document "unbounded, cleanup in session archive" for DoD.
5. **checkpoints/ existence:** AC4.1.5 assumes Epic 1 creates it; add assertion at node start (or create if missing) to fail fast if Epic 1 contract is broken.

#### Proposed Technical Designs

**1. Checkpoint node label and id (single source)**

- **Label:** Always `chapter_{current_chapter}` from state (no agent label in node). Tool create_checkpoint(label) can use agent-provided label for pre-validation snapshots; node uses state only.
- **Checkpoint id:** `f"{timestamp}_{label}.md"` with timestamp from `datetime.now().strftime("%Y%m%d_%H%M%S")`; if file already exists (same second), append sequence: `f"{timestamp}_{label}_{seq}.md"` (seq = 0, 1, …) or use `time.time_ns()` for uniqueness.
- **State update:** Return state with `last_checkpoint_id = <basename of written file>` (no path).

**2. Checkpoint metadata (optional for future)**

- No DB; optional in-memory or file `checkpoints/manifest.json`: `{"checkpoints": [{"id": "...", "label": "...", "created": "ISO8601"}]}` for list_checkpoints tool or rollback UI. Out of scope for 4.1 unless product needs "choose which checkpoint to rollback to"; then add in 4.1 or later story.

**3. Path resolution**

- `session_path = SessionManager.get_path(session_id)`  
- `src = session_path / "temp_output.md"` (or state.get("temp_md_path") resolved under session)  
- `dst = session_path / "checkpoints" / f"{timestamp}_{label}.md"`  
- Assert `session_path / "checkpoints"`.exists() or create and log.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 11 | Decide and document label source: node uses state-only label (e.g. chapter_{n}) | Dev | 0.5 SP | DoD: label = chapter_{current_chapter}; tool label independent. |
| 12 | Implement timestamp uniqueness (sequence or time_ns) when file exists | Dev | 1 SP | If destination exists, append _seq or use time_ns; avoid overwrite. |
| 13 | Assert or create checkpoints/ at node start; use SessionManager path for temp_output | Dev | 0.5 SP | Fail fast if checkpoints/ missing; document path resolution. |
| 14 | Optional: document checkpoint retention (unbounded vs MAX_CHECKPOINTS) | Dev | 0.5 SP | DoD or ADR: retention policy. |

#### Revised Story (Technical Specs)

- **DoD addition:** Label for checkpoint node is state-derived only (`chapter_{current_chapter}`); timestamp uniqueness strategy implemented and tested; checkpoints/ asserted or created; path resolution uses SessionManager.
- **Contract:** Checkpoint node writes exactly one file per run; last_checkpoint_id is the basename of that file; rollback_to_checkpoint tool accepts that basename.

---

### Story 4.2: Markdown Validator Node — Run markdownlint, Map Output to State

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | DocumentState schema and markdownlint JSON format need to be pinned; subprocess robustness (timeout, stderr) under-specified. |
| Data Model | Critical Gaps | validation_passed and validation_issues not in ARCHITECTURE §5.1 TypedDict; validation_issues schema (TypedDict) not defined. |
| API/Integration | Sound | Node is state-in/state-out; agent consumes validation_issues from state. |
| Technical Feasibility | Needs Design Work | markdownlint-cli vs markdownlint-cli2 have different JSON; stdout vs -o file; subprocess timeout for large files. |
| Vertical Slice | Sound | Node + state mapping + tests. |
| Security/Compliance | Sound | No user content in logs (only issue count/line numbers); path is session-scoped. |
| Dependencies & Risks | Medium | markdownlint CLI must be installed; version and JSON shape vary. |
| MECE | Sound | Validation only; 4.3 consumes state. |
| DoD Technical | Needs Design Work | Pin CLI and JSON schema; add ValidationIssue TypedDict; subprocess timeout. |

#### Strengths

- Structured validation_issues with line_number and message for agent fixes (FC010).
- Graceful handling of missing markdownlint or subprocess failure (synthetic issue).
- Unit tests for pass/fail and error paths.

#### Critical Gaps (Data Model, APIs, Infra)

1. **DocumentState schema:** ARCHITECTURE §5.1 does not include `validation_passed: bool` or `validation_issues: List[...]`. These must be added to DocumentState (in Epic 2.1 or this story) and documented. **validation_issues** item schema must be defined (e.g. TypedDict with line_number, rule, message).
2. **markdownlint JSON format:** markdownlint-cli with `--json` typically outputs to **stdout** an array of objects; format varies (e.g. lineNumber, ruleNames, ruleDescription, errorDetail). markdownlint-cli2 uses a formatter and may write to a file. Story must **pin** one CLI (e.g. `markdownlint-cli` npm package) and document the exact JSON shape, or implement a **normalizer** that accepts common shapes and outputs ValidationIssue.
3. **Subprocess timeout:** Large temp_output.md could cause markdownlint to hang; add timeout (e.g. 30s) to subprocess.run and treat timeout as validation_passed=False with synthetic issue "Validation timeout".
4. **Stderr handling:** On non-zero return, markdownlint may write errors to stderr; stdout might still be JSON. Document whether we parse stdout only or merge stderr into synthetic issue.
5. **File missing:** temp_output.md may not exist (e.g. first validation before any content); node should set validation_passed=False and synthetic issue "File not found: temp_output.md" without crashing.

#### Proposed Technical Designs

**1. DocumentState and ValidationIssue schema**

```python
# state.py or validators/markdown_validator.py
from typing import TypedDict

class ValidationIssue(TypedDict, total=False):
    line_number: int
    rule: str
    rule_description: str
    message: str
    error_detail: str

# In DocumentState (add to §5.1):
# validation_passed: bool
# validation_issues: List[ValidationIssue]
```

- **Normalized schema:** Every consumer (agent prompt, logs) uses line_number, rule (or rule_description), message (or error_detail). Mapper from markdownlint JSON → List[ValidationIssue].

**2. markdownlint CLI contract**

- **Pinned tool:** `markdownlint-cli` (npm), flag `-j` or `--json`, output to **stdout**.
- **Command:** `markdownlint <path> -j` (no -o so stdout is used).
- **JSON shape (example):** `[{"lineNumber": 5, "ruleNames": ["MD047"], "ruleDescription": "...", "errorDetail": "..."}]`. Implement mapper: line_number ← lineNumber, rule ← ruleNames[0] or ruleDescription, message ← errorDetail or ruleDescription.
- **Version:** Document in DoD: "Tested with markdownlint-cli @ X.Y.Z"; add to ARCHITECTURE §7.3.

**3. Subprocess and errors**

```python
try:
    result = subprocess.run(
        ["markdownlint", str(md_path), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
except subprocess.TimeoutExpired:
    return {**state, "validation_passed": False, "validation_issues": [{"message": "Validation timeout (30s)"}]}
except FileNotFoundError:  # markdownlint not installed
    return {**state, "validation_passed": False, "validation_issues": [{"message": "markdownlint not found"}]}
if not md_path.exists():
    return {**state, "validation_passed": False, "validation_issues": [{"message": "temp_output.md not found"}]}
# Parse result.stdout; on JSON decode error use synthetic issue
```

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 12 | Add validation_passed and validation_issues to DocumentState; define ValidationIssue TypedDict | Dev | 2 SP | state.py or graph.py; export ValidationIssue; document in ARCHITECTURE §5.1. |
| 13 | Pin markdownlint CLI (markdownlint-cli) and document JSON shape; implement normalizer to ValidationIssue | Dev | 2 SP | Map lineNumber, ruleNames, ruleDescription, errorDetail to ValidationIssue; handle array vs single object. |
| 14 | Add subprocess timeout (e.g. 30s) and handle TimeoutExpired | Dev | 1 SP | validation_passed=False, synthetic issue "Validation timeout". |
| 15 | Handle missing temp_output.md before calling markdownlint | Dev | 0.5 SP | If not path.exists(), return failed with synthetic issue. |
| 16 | Document markdownlint-cli version and JSON contract in DoD and §7.3 | Dev | 0.5 SP | Version and example JSON in ARCHITECTURE. |

#### Revised Story (Technical Specs)

- **DoD addition:** DocumentState includes validation_passed and validation_issues; ValidationIssue schema defined and used; markdownlint-cli pinned with JSON normalizer; subprocess timeout and missing-file handling; version and JSON contract documented.
- **Contract:** validate_markdown node always returns state with validation_passed and validation_issues set; no unhandled exception; agent receives list of issues with line_number and message.

---

### Story 4.3: Conditional Edges — After Tools → Validate When Chapter Complete; Validate → Agent (Fix) or Continue

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | "Chapter complete" detection depends on Tool Node updating state from tool results; DocumentState and routing order must be explicit. |
| Data Model | Needs Design Work | chapter_done or last_checkpoint_id set by tools node not in ARCHITECTURE; generation_complete vs current_file_index for "complete". |
| API/Integration | Sound | route_after_tools and validate_md conditional are graph-internal. |
| Technical Feasibility | Critical Gaps | LangGraph Tool Node does not update state from tool results by default; **custom tools node** or state updater required (Epic 2.2 review). |
| Vertical Slice | Sound | Routing + agent context (validation_issues) end-to-end. |
| Security/Compliance | Sound | No new external surface. |
| Dependencies & Risks | High | Epic 2 must implement state update from create_checkpoint result; otherwise route_after_tools cannot detect chapter complete. |
| MECE | Sound | Edges only; 4.1/4.2 provide nodes. |
| DoD Technical | Needs Design Work | Routing table; fix-attempt cap in state and logic. |

#### Strengths

- Clear routing matrix: tools → validate | agent | human_input | complete; validate_md → agent (fix) | checkpoint.
- validation_issues passed to agent on fix path.
- Integration tests for each branch.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Chapter complete detection:** ARCHITECTURE route_after_tools uses `if state["last_checkpoint_id"]: return "validate"`. So last_checkpoint_id must be set **when the agent called create_checkpoint** — i.e. **by the tools node** after executing the tool, not only by the checkpoint node (which runs after validation). So the **Tool Node must write state["last_checkpoint_id"]** from the create_checkpoint tool return value. Standard LangGraph ToolNode only appends tool messages to state; it does not set custom state keys. So either: (a) **Custom tools node** that runs tools, then inspects last tool calls and sets state["last_checkpoint_id"] from create_checkpoint result, or (b) a **state updater** that runs after tools and parses messages to set last_checkpoint_id. This is a **critical dependency** on Epic 2; add explicit task or dependency: "Epic 2 implements tools node (or post-tools updater) that sets state['last_checkpoint_id'] when create_checkpoint was the last tool called."
2. **Routing order:** route_after_tools must check in a defined order: (1) pending_question → human_input, (2) last_checkpoint_id (chapter done) → validate, (3) generation_complete or current_file_index >= len(input_files)-1 → complete, (4) else → agent. ARCHITECTURE has last_checkpoint_id first; stories say "chapter complete (e.g. create_checkpoint or dedicated signal)". Document order and semantics (e.g. "if both pending_question and last_checkpoint_id, prefer human_input").
3. **generation_complete:** "Complete" might be signaled by agent (e.g. final message or tool) or by current_file_index. Document: generation_complete set by agent node when done, or inferred from file index; route_after_tools returns "complete" when generation_complete or all files processed.
4. **fix_attempts cap:** Task 11 is optional; if implemented, add fix_attempts to DocumentState and increment when routing to agent for fix; when fix_attempts >= max (e.g. 3), route to "complete" or "error" to avoid infinite loop. Recommend making it **required** for DoD: add state key and logic.
5. **validate_md → checkpoint edge:** ARCHITECTURE §5.2 shows validate_md → "fix" | "continue" with "continue" going to agent; diagram §3.1 shows Valid → Checkpoint → Agent. So "continue" should go to **checkpoint** node, then checkpoint → agent. Story 4.3 has this; ensure graph snippet in ARCHITECTURE is updated to add checkpoint node and edge validate_md → checkpoint → agent.

#### Proposed Technical Designs

**1. Tools node state update (Epic 2 / 4.3 contract)**

- **Option A (recommended):** Custom tools node in Epic 2:
  - Execute tool calls from last message.
  - For each tool call, if tool name == "create_checkpoint", set state["last_checkpoint_id"] = result (checkpoint_id returned by tool).
  - Append tool results to messages; return updated state.
- **Option B:** After tools, add a small **state_updater** node that reads last message's tool_calls and results, sets last_checkpoint_id if create_checkpoint was called, then conditional edge from state_updater to route_after_tools targets. Simpler but extra node.
- Document in Epic 4.3 DoD: "Precondition: state['last_checkpoint_id'] is set by tools node when agent called create_checkpoint; otherwise route_after_tools cannot route to validate."

**2. route_after_tools order and semantics**

```python
def route_after_tools(state: DocumentState) -> str:
    # 1. Human-in-the-loop takes precedence
    if state.get("pending_question"):
        return "human_input"
    # 2. Chapter done → validate
    if state.get("last_checkpoint_id"):
        return "validate"
    # 3. Generation complete
    if state.get("generation_complete") or (
        state["current_file_index"] >= len(state["input_files"]) - 1
        and state["current_file_index"] >= 0
    ):
        return "complete"
    return "agent"
```

- Document: when last_checkpoint_id is set by **checkpoint node** (after validation), we are already past tools; so when we're in route_after_tools we're coming from tools — and last_checkpoint_id here means "create_checkpoint was just called". After validate_md → checkpoint node, we go to agent; next time we hit route_after_tools we may not have last_checkpoint_id (unless agent called create_checkpoint again). So the semantics are correct: last_checkpoint_id in route_after_tools = "tool just wrote a checkpoint, now validate."

**3. Fix-attempt cap**

- Add to DocumentState: `fix_attempts: int` (default 0 in build_initial_state).
- When routing from validate_md to agent with validation_passed=False, increment fix_attempts (in validate_md return or in a wrapper). If fix_attempts >= MAX_FIX_ATTEMPTS (e.g. 3), route to "complete" or "error" instead of "agent" (to avoid infinite fix loop). When validation_passed=True, reset fix_attempts to 0 (optional).
- Add task: "Implement fix_attempts in state and cap in validate_md conditional edge."

**4. Routing table (document in DoD)**

| From | Condition | To |
|------|-----------|-----|
| tools | pending_question | human_input |
| tools | last_checkpoint_id | validate_md |
| tools | generation_complete or all files processed | complete |
| tools | else | agent |
| validate_md | not validation_passed | agent (fix) |
| validate_md | validation_passed | checkpoint |
| checkpoint | — | agent |

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 12 | Document dependency: Epic 2 tools node (or updater) sets state["last_checkpoint_id"] from create_checkpoint result | Dev | 0.5 SP | DoD and Epic 2 contract. |
| 13 | Define and document route_after_tools evaluation order (pending_question, last_checkpoint_id, complete, agent) | Dev | 1 SP | Code comment and story DoD. |
| 14 | Add fix_attempts to DocumentState; cap in validate_md routing (max 3 fix attempts then route to complete/error) | Dev | 2 SP | state key; conditional: if fix_attempts >= MAX, route to complete; else agent. |
| 15 | Add routing table to ARCHITECTURE or story DoD | Dev | 0.5 SP | Table: from-node, condition, to-node. |

#### Revised Story (Technical Specs)

- **DoD addition:** route_after_tools order and semantics documented; fix_attempts in state with cap (e.g. 3); Epic 2 contract for setting last_checkpoint_id from tools node documented; routing table in DoD/ARCHITECTURE.
- **Contract:** "Chapter complete" is detected when state["last_checkpoint_id"] is set by the tools node after create_checkpoint; validate_md conditional routes to agent (fix) or checkpoint; agent receives validation_issues when on fix path.

---

### Story 4.4: Error-Handling Path Triggers Rollback to Last Checkpoint Before Retry (Epic 6 Handshake)

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Shared rollback interface and ownership (Epic 4 vs Epic 6) must be explicit; missing-checkpoint behavior and state after rollback need specification. |
| Data Model | Sound | Uses existing last_checkpoint_id; no new schema. |
| API/Integration | Needs Design Work | Rollback helper signature and module location; Epic 6 error_handler calls it — contract must be written. |
| Technical Feasibility | Sound | File copy and conditional edge are straightforward. |
| Vertical Slice | Sound | Rollback helper + integration into retry path + tests. |
| Security/Compliance | Sound | Path validation under session; no escape. |
| Dependencies & Risks | Medium | Epic 6 owns error_handler; Epic 4 provides helper; first-chapter failure (no checkpoint) handled. |
| MECE | Sound | Rollback only; Epic 6 does classify + handlers + retry decision. |
| DoD Technical | Needs Design Work | Shared module and function signature; Epic 6 contract; state-after-rollback semantics. |

#### Strengths

- Clear rollback-before-retry semantics (FC009, FC017).
- Missing last_checkpoint_id or missing file handled without crash.
- Unit and integration tests for rollback and missing checkpoint.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Shared rollback interface:** "Rollback helper" must be a **single function** in a **shared module** (e.g. `utils/checkpoint.py` or `nodes/checkpoint.py`) so that (a) Epic 4.4 uses it in the retry path, (b) Epic 6 error_handler (or a dedicated rollback node) calls the same function, (c) rollback_to_checkpoint **tool** (Epic 2) can reuse the same logic to avoid duplication. Propose: `restore_from_checkpoint(session_id: str, checkpoint_id: str) -> bool` (returns True if restored, False if file missing/invalid); path validation inside; used by tool and by error path.
2. **Ownership of "rollback node":** Story says rollback either inside error_handler or in a dedicated rollback node. Epic 6 story 3 says "Error handler node: classify → invoke handler → **rollback if applicable (Epic 4)** → increment retry". So Epic 6 implements the node that **calls** rollback; Epic 4 implements the **rollback helper**. Recommend: **Epic 4.4** implements `restore_from_checkpoint(session_id, checkpoint_id)` and documents it; **Epic 6** error_handler node (or a rollback node in Epic 6) calls it when should_retry_conversion returns "retry". Epic 4.4 can add a **rollback node** that only calls the helper and then routes to agent, so the graph is error_handler → rollback_node → agent when retry; or Epic 6 error_handler does the call inline. Document the chosen approach in both epics.
3. **Missing checkpoint behavior:** AC4.4.3 says "skip rollback (retry with current temp_output.md) or treat as unrecoverable". Recommend: **skip rollback** and log warning; still route to agent for retry (so we don't fail fast on first-chapter conversion error). Document in DoD.
4. **State after rollback:** Should last_error / error_type be cleared when retrying? Recommendation: **keep** for audit trail; optional: add state key last_rollback_checkpoint_id for logging. No need to clear retry_count (error_handler increments it).
5. **Tool reuse:** rollback_to_checkpoint(session_id, checkpoint_id) tool (Epic 2) should call the same restore_from_checkpoint helper so logic lives in one place.

#### Proposed Technical Designs

**1. Shared rollback function**

```python
# utils/checkpoint.py or nodes/checkpoint.py

def restore_from_checkpoint(session_id: str, checkpoint_id: str) -> bool:
    """
    Copy session/checkpoints/{checkpoint_id} to session/temp_output.md.
    Path-validates checkpoint_id (basename only, under session).
    Returns True if restored, False if file missing or invalid.
    """
    session_path = SessionManager().get_path(session_id)
    # Reject path traversal: checkpoint_id must be basename
    if os.path.basename(checkpoint_id) != checkpoint_id or ".." in checkpoint_id:
        return False
    src = session_path / "checkpoints" / checkpoint_id
    if not src.exists():
        return False
    dst = session_path / "temp_output.md"
    shutil.copy(src, dst)
    return True
```

- **Tool:** rollback_to_checkpoint(session_id, checkpoint_id) calls restore_from_checkpoint(session_id, checkpoint_id) and returns message "Restored {id}" or "Checkpoint not found".
- **Error path:** When retry, call restore_from_checkpoint(state["session_id"], state["last_checkpoint_id"]); if False, log rollback_skipped and still proceed to agent.

**2. Epic 6 contract**

- Epic 6 error_handler (or rollback node) **must** call `restore_from_checkpoint(session_id, last_checkpoint_id)` when should_retry_conversion(state) == "retry", **before** transitioning to agent. Epic 4 provides the function and documents signature. Epic 6 story 3 DoD: "When retry, call Epic 4 restore_from_checkpoint(session_id, last_checkpoint_id); if False, log and continue to agent."

**3. Graph shape**

- **Option A:** error_handler → (retry → rollback_node → agent | fail → save_results). Rollback node: call restore_from_checkpoint, log, return state, edge to agent.
- **Option B:** error_handler calls restore_from_checkpoint internally when retry, then returns state, conditional edge to agent. Fewer nodes; logic in one place.
- Document in Epic 4.4 and Epic 6: "Rollback before retry is performed by [rollback node | error_handler node] using utils.checkpoint.restore_from_checkpoint."

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 11 | Implement restore_from_checkpoint(session_id, checkpoint_id) in shared module; use in rollback_to_checkpoint tool | Dev | 2 SP | utils/checkpoint.py or nodes/checkpoint.py; path validation; return bool; tool delegates to it. |
| 12 | Document Epic 6 contract: error_handler (or rollback node) calls restore_from_checkpoint before agent on retry | Dev | 1 SP | DoD and Epic 6 story 3. |
| 13 | Document missing-checkpoint behavior: skip rollback, log warning, still route to agent | Dev | 0.5 SP | DoD. |
| 14 | Decide and document: rollback in dedicated node vs inside error_handler | Dev | 0.5 SP | Architecture decision; both epics. |

#### Revised Story (Technical Specs)

- **DoD addition:** restore_from_checkpoint(session_id, checkpoint_id) in shared module; rollback_to_checkpoint tool uses it; Epic 6 contract and missing-checkpoint behavior documented; rollback node vs inline decided and documented.
- **Contract:** Epic 4 provides restore_from_checkpoint; Epic 6 invokes it when retrying; on missing checkpoint, skip rollback and continue to agent.

---

## Overall Technical Roadmap

### Missing Foundational Work

1. **DocumentState schema (Epic 2.1 / Epic 4):** Add to single source of truth (state.py): `validation_passed: bool`, `validation_issues: List[ValidationIssue]`, `fix_attempts: int`, and optionally `generation_complete: bool`. Ensure build_initial_state sets defaults for all keys used by Epic 4 nodes.
2. **Tool Node state update (Epic 2):** Implement custom tools node (or post-tools state updater) that sets `state["last_checkpoint_id"]` when create_checkpoint was the last tool called. Without this, Story 4.3 cannot route to validate_md on "chapter complete."
3. **markdownlint contract:** Pin markdownlint-cli version; document JSON output format and normalize to ValidationIssue in one place (validators/markdown_validator.py or similar).

### Schema Proposals Summary

| Schema | Location | Purpose |
|--------|----------|---------|
| ValidationIssue | state.py or validators | line_number, rule, message; consumed by agent and logs |
| DocumentState extensions | state.py | validation_passed, validation_issues, fix_attempts |
| restore_from_checkpoint(session_id, checkpoint_id) -> bool | utils/checkpoint.py | Shared rollback; used by tool and error path |

### Architecture Decisions Needed

1. **Checkpoint node vs tool:** Node = post-validation automatic save with state-derived label; tool = agent-requested save (pre-validation). Both can coexist; last_checkpoint_id after node run = node-created id. **Decision:** Document in Epic 4.1 DoD.
2. **Rollback placement:** Dedicated rollback node (error_handler → rollback → agent) vs inline in error_handler. **Decision:** Document in Epic 4.4 and Epic 6; recommend **inline** to reduce nodes unless reuse elsewhere.
3. **Fix loop cap:** Make fix_attempts and MAX_FIX_ATTEMPTS required (e.g. 3) to avoid unbounded validation-fix loops. **Decision:** Add to Story 4.3 DoD and state schema.
4. **markdownlint CLI:** Pin markdownlint-cli (npm) and --json stdout; document in ARCHITECTURE §7.3. **Decision:** Story 4.2.

### Recommended Implementation Order (Revised)

1. **Epic 2 (blocking):** Ensure tools node updates state from create_checkpoint result (last_checkpoint_id); get_tools(session_id).
2. **State schema:** Add validation_passed, validation_issues, ValidationIssue, fix_attempts to DocumentState (Epic 2.1 or 4.2).
3. **Story 4.2** (validator node + schema + markdownlint pin).
4. **Story 4.1** (checkpoint node + label/timestamp design).
5. **Story 4.3** (conditional edges + fix cap + routing table).
6. **Story 4.4** (restore_from_checkpoint + Epic 6 contract).
7. **Epic 6** error_handler (or rollback node) calls restore_from_checkpoint on retry.

### Cross-Cutting Concerns

- **Logging (FC015):** All four stories include structured logging; ensure event names are consistent (checkpoint_saved, validation_ran, rollback_performed, rollback_skipped) and session_id in every log.
- **Monitoring:** No new metrics called out; optional: counter for validation_failed, rollback_performed for dashboards.
- **Testing:** Performance criteria not specified (e.g. validation timeout 30s); add to DoD if needed. Deployment: markdownlint-cli as system/npm dependency in deployment checklist (Epic 6 or ops).

---

**Document Version:** 1.0  
**Last Updated:** 2025-02-11  
**Status:** Technical review complete; stories should be updated with missing tasks and revised DoDs above.
