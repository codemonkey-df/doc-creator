# Epic 2: AI-Powered Content Generation Pipeline — Technical Review

**Reviewer role:** Senior Software Architect / Agile Team Lead  
**Scope:** Technical deep-dive audit of decomposed stories; data models, APIs, feasibility, security, MECE, DoD.  
**Context:** Parent Epic 2, ARCHITECTURE.md (Agentic Document Generator), Epic 1 (entry-owned session, graph starts at scan_assets).

---

## Parent Epic Technical Context

### Architecture Assumptions

- **Orchestration:** LangGraph ≥1.0 with `StateGraph(DocumentState)`, `MemorySaver` checkpointer. Per Epic 1 technical review: **entry** creates session, copies files, builds initial state; **graph starts at `scan_assets`** (no `initialize` node that creates session). Epic 2 stories align with this.
- **Tech stack:** Python 3.13, uv, LangGraph, LiteLLM (langchain-litellm), markdownlint (CLI or lib). No DB; state is in-memory (DocumentState) and on-disk (session dirs, temp_output.md, checkpoints).
- **State model:** DocumentState is the single source of truth for the agent loop. Built by `build_initial_state(session_id, input_files)` at entry; all nodes read/update state. List fields use reducers (append-only).
- **Agent pattern:** Agent node invokes LLM with tools; Tool Node executes tool calls from the last message; conditional routing (route_after_tools) sends control to agent | validate_md | human_input | parse_to_json. Completion and interrupt semantics must be explicit.

### Relevant ARCHITECTURE References

- **DocumentState (§5.1):** session_id, input_files, current_file_index, temp_md_path, structure_json_path, output_docx_path, last_checkpoint_id, current_chapter, document_outline, conversion_attempts, last_error, error_type, retry_count, missing_references (reducer), user_decisions, pending_question, status, messages (reducer).
- **Graph (§5.2):** ARCHITECTURE still shows START → initialize; Epic 1 review and Epic 2 stories assume START → scan_assets. DocumentState and graph edges in Epic 2 must assume **no initialize node**.
- **scan_assets_node (§5.3):** Scans input files for image refs, copies existing images to session assets, collects missing_references. **Ownership:** Epic 2 does not task implementing scan_assets; it is the first node. Either 2.1 includes a minimal scan_assets (or stub) or Epic 3 (Asset Reference Management) owns it. Recommendation: 2.1 includes **minimal scan_assets** (read input files, collect missing refs, no copy yet if deferred to Epic 3) so the graph is runnable.
- **Tools (§4.4):** All take session_id; paths are under session root. validate_markdown is a tool in ARCHITECTURE; Epic 2.5 also has validate_md as a **node** (post-tool routing). Both are valid: tool for agent to call, node for the formal “after checkpoint” validation step.
- **Human-in-the-loop:** interrupt before human_input; resume with updated state (user_decisions). Checkpointer required for resume.

### Cross-Epic Dependencies

- **Epic 1.4:** build_initial_state(session_id, input_files), GenerateResult, entry flow (validate → create session → copy → invoke graph → cleanup). DocumentState must match what build_initial_state and the graph expect.
- **Epic 3 (Asset Reference Management):** Full image copy, path resolution, placeholder logic. Epic 2 can stub or minimally implement scan_assets and “upload” handling so interrupts work; Epic 3 can enhance.

---

## Story-by-Story Technical Audit

---

### Story 2.1: Define LangGraph DocumentState and Integrate with Workflow Start

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | State schema and first-node implementation ownership need tightening; reducer and optional keys must be decided. |
| Data Model | Needs Design Work | DocumentState has optional vs required keys (e.g. temp_md_path set only when file exists); TypedDict total=False and defaults not specified. |
| API/Integration | Sound | State is internal; build_initial_state contract is in Epic 1.4; alignment task is present. |
| Technical Feasibility | Sound | LangGraph reducer syntax is version-dependent; task calls this out. |
| Vertical Slice | Needs Design Work | “First node” is scan_assets but scan_assets is not implemented in Epic 2; graph cannot run without it. |
| Security/Compliance | Sound | State carries session_id; no PII in state beyond paths. |
| Dependencies & Risks | Medium | Epic 1.4 must provide build_initial_state; LangGraph reducer semantics. |
| MECE | Sound | State and workflow start only; no overlap with 2.2–2.5. |
| DoD Technical | Sound | Tests and docs; add scan_assets ownership and state key contract. |

#### Strengths

- DocumentState key list aligns with ARCHITECTURE §5.1; reducer for messages and missing_references is specified.
- Explicit alignment of build_initial_state with DocumentState and graph START → scan_assets (no session create in graph).
- Unit and integration tests for initial state and first node.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Optional vs required state keys:** Keys like `temp_md_path`, `structure_json_path`, `output_docx_path`, `last_checkpoint_id` are set only after certain nodes run. TypedDict should use `total=False` for those, or document “set by first node that needs them” and provide defaults (e.g. `""`) in build_initial_state.
2. **scan_assets node not tasked:** Graph starts at scan_assets, but no story implements it. Without it, the graph has no runnable first node. Either add “Implement minimal scan_assets node” to 2.1 (or a new story) or depend on Epic 3 and accept a stub (e.g. scan_assets returns state unchanged and routes to agent). Recommendation: **2.1 includes minimal scan_assets** that: reads state["input_files"], optionally scans for image refs (regex), sets missing_references and pending_question when refs are missing, else sets status to "processing" and leaves state ready for agent; no file copy (can be Epic 3).
3. **Reducer semantics and LangGraph version:** LangGraph 1.x uses `Annotated[List[T], operator.add]` for append-only; document exact import and behavior. If messages are later changed to `List[BaseMessage]` for agent/tools (see 2.3), reducer still applies but type changes.
4. **Single source of truth for state shape:** DocumentState should live in one module (e.g. `state.py` or `graph.py`); build_initial_state (Epic 1.4) and all nodes import the same type. Add task: “DocumentState defined in single module; build_initial_state and graph import from it.”

#### Proposed Technical Designs

**1. DocumentState schema (with optional keys)**

```python
# state.py or graph.py
from typing import TypedDict, List, Annotated, Literal, NotRequired
import operator

class DocumentState(TypedDict, total=False):
    # Required at entry (build_initial_state)
    session_id: str
    input_files: List[str]
    current_file_index: int
    current_chapter: int
    conversion_attempts: int
    retry_count: int
    status: str
    messages: Annotated[List[str], operator.add]  # or List[BaseMessage] if using LangChain messages
    missing_references: Annotated[List[str], operator.add]
    user_decisions: dict
    pending_question: str
    last_checkpoint_id: str
    document_outline: List[str]
    # Set by nodes later
    temp_md_path: str
    structure_json_path: str
    output_docx_path: str
    last_error: str
    error_type: str
    validation_passed: bool
    validation_issues: list
    generation_complete: bool  # set by agent or routing when done
```

Use `total=False` and document which keys are required at entry vs set by nodes. Alternatively keep `total=True` and set all keys in build_initial_state with defaults (e.g. `""`, `[]`, `0`, `False`).

**2. build_initial_state defaults (align with Epic 1.4)**

- Required at graph start: session_id, input_files, current_file_index=0, current_chapter=0, conversion_attempts=0, retry_count=0, status="scanning_assets", messages=[], missing_references=[], user_decisions={}, pending_question="", last_checkpoint_id="", document_outline=[]. Optional for later: temp_md_path="", structure_json_path="", output_docx_path="", last_error="", error_type="", generation_complete=False. So build_initial_state sets all of these so no key is missing when scan_assets runs.

**3. Minimal scan_assets node (for 2.1)**

- Input: state with session_id, input_files.
- Logic: For each file in session inputs/, read content; regex `!\[.*?\]\((.*?)\)` for image refs; for each ref (skip http), check if path exists (relative to session or cwd). If missing, append to missing_references. If any missing_references, set pending_question and return state; else set status="processing", clear missing_references, return state.
- Output: state with missing_references, pending_question, status updated. No copy to assets in Epic 2 if Epic 3 owns that; or minimal copy for existing files so agent can proceed.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 9 | Define optional vs required state keys and defaults in build_initial_state | Dev | 1 SP | TypedDict total=False or full defaults; document which keys are set by which node. |
| 10 | Implement minimal scan_assets node | Dev | 3 SP | Read input files, detect image refs (regex), set missing_references and pending_question or status=processing; no asset copy if deferred to Epic 3. |
| 11 | Document DocumentState in single module; graph and entry import same type | Dev | 0.5 SP | state.py or graph.py; build_initial_state uses same keys. |
| 12 | Integration test: scan_assets runs and routes to human_input or agent | QA/Dev | 2 SP | With missing refs → human_input path; without → agent path. |

#### Revised Story (Technical Specs)

- **DoD addition:** DocumentState has documented required vs optional keys and defaults; single module for state type; minimal scan_assets implemented and tested; integration test covers both scan_assets exit paths.
- **Contract:** build_initial_state sets every key the graph uses (with defaults); graph START → scan_assets only; scan_assets is the first node and must be implemented in this epic (or explicitly stubbed and ownership in Epic 3 documented).

---

### Story 2.2: Implement Tool Node — list_files, read_file, read_generated_file, append_to_markdown, edit_markdown_line, Checkpoint Tools

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Session-scoping and session_id injection are under-specified; path safety and tool–state wiring need design. |
| Data Model | Sound | No persistent model; tool I/O is strings and session paths. |
| API/Integration | Needs Design Work | How tools get session_id (wrapper vs agent-passed); list_files(directory) vs list_files(session_id) for safety. |
| Technical Feasibility | Sound | Task breakdown is realistic; markdownlint not required in 2.2. |
| Vertical Slice | Partial | Tools only; no agent yet. |
| Security/Compliance | Critical Gaps | Path injection: filename/directory/label must be validated (no path traversal, no escape from session). |
| Dependencies & Risks | Low | Story 2.1, Epic 1. |
| MECE | Sound | Tools only; 2.3 binds them to agent. |
| DoD Technical | Needs Design Work | Add path-validation and session_id-injection design; security tests. |

#### Strengths

- All seven tools from ARCHITECTURE are listed; session-scoped paths and SessionManager.get_path are specified.
- Unit tests for paths and edge cases are in scope.

#### Critical Gaps (Data Model, APIs, Infra)

1. **session_id injection:** LangGraph Tool Node receives state and the last message’s tool_calls; it does not automatically pass state["session_id"] into each tool. So either: (a) tools take only (filename, content, …) and a **wrapper** or **tool factory** binds session_id from state when the node runs (e.g. `get_tools(state) -> list` that returns tools with session_id closed over), or (b) tools take session_id as an argument and the agent is instructed to pass it (fragile and token-costly). Recommendation: **tool factory** `get_tools_for_state(state)` returning tools that already have session_id bound (e.g. partial application or wrapper). Document in story.
2. **list_files(directory) is unsafe:** ARCHITECTURE shows `list_files(directory: str)`. If the agent passes an arbitrary path, it could escape the session. Recommendation: **list_files(session_id: str)** that lists only `session_path / "inputs"` (or a fixed subdir). If “directory” is kept, it must be a literal like "inputs" or validated to be a single segment under session.
3. **Path validation in every tool:** read_file(filename): reject filename if it contains `/`, `\`, or `..`. edit_markdown_line(line_number): ensure line_number in range. create_checkpoint(label): sanitize label (no path chars, no `..`). rollback_to_checkpoint(checkpoint_id): ensure checkpoint_id is basename only (e.g. `{timestamp}_{label}.md`). Add explicit validation and raise ValueError for invalid args.
4. **Tool Node and state updates:** Standard LangGraph Tool Node only appends tool results to messages; it does not set state["last_checkpoint_id"] or state["pending_question"] from tool returns. So either: custom Tools node that runs tools and then updates state from tool results (e.g. if create_checkpoint was called, set last_checkpoint_id), or route_after_tools infers from messages (fragile). Recommend: **custom tools node** that (1) runs tool invocations, (2) parses which tools were called and their results, (3) updates state (last_checkpoint_id, etc.) and appends tool messages. Add task or call out in 2.5.

#### Proposed Technical Designs

**1. Tool factory (session_id bound)**

```python
# tools.py
def get_tools(session_id: str) -> list:
    """Return tools bound to session_id. Called by graph with state['session_id']."""
    return [
        _bind(list_files_inputs, session_id),
        _bind(read_file, session_id),
        _bind(read_generated_file, session_id),
        _bind(append_to_markdown, session_id),
        _bind(edit_markdown_line, session_id),
        _bind(create_checkpoint, session_id),
        _bind(rollback_to_checkpoint, session_id),
    ]
# ToolNode in graph: use get_tools(state["session_id"]) so tools never see raw state.
```

**2. Path and argument validation**

- `read_file(filename, session_id)`: assert "/" not in filename and "\\" not in filename and ".." not in filename; reject empty.
- `create_checkpoint(label, session_id)`: sanitize label to alphanumeric + underscore; reject ".." and path separators.
- `rollback_to_checkpoint(checkpoint_id, session_id)`: resolve path as session/checkpoints/{checkpoint_id}; assert path.resolve().is_relative_to(session_path) (no escape).
- `list_files(session_id)`: list only `session_path / "inputs"`. No directory argument from agent.

**3. Tool Node state updates (for 2.5)**

- In 2.5, when implementing routing: either use a custom tools node that, after executing tool calls, sets state["last_checkpoint_id"] from create_checkpoint result and handles other tool-derived state, or document that route_after_tools infers from last message content (and add a task to implement custom tools node if inference is unreliable).

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 9 | Design and implement session_id injection (tool factory get_tools(session_id)) | Dev | 2 SP | get_tools(state["session_id"]) returns tools with session_id bound; graph passes state into Tool Node. |
| 10 | Change list_files to list_files(session_id) and list only session inputs/ | Dev | 1 SP | Remove directory arg; list session_path/inputs for safety. |
| 11 | Add path and argument validation to all tools (filename, label, checkpoint_id) | Dev | 2 SP | Reject path traversal and invalid args; raise ValueError with clear message. |
| 12 | Unit tests: path traversal attempts rejected (security) | QA/Dev | 1 SP | Try "../etc/passwd", "..", path separators in filename/label; assert rejected. |

#### Revised Story (Technical Specs)

- **DoD addition:** session_id injected via tool factory; list_files(session_id) only; path validation on every tool; security tests for path traversal.
- **Contract:** All tools receive session_id via factory (not from agent); no tool accepts arbitrary paths from the agent; Tool Node uses get_tools(state["session_id"]).

---

### Story 2.3: Implement Agent Node — System Prompt, Tool Binding, State Updates

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Message format (str vs BaseMessage), agent/tool loop structure, and completion signal are under-specified. |
| Data Model | Critical Gaps | state["messages"] as List[str] conflicts with LangGraph/LangChain ReAct pattern (expects BaseMessage list for tool_calls). |
| API/Integration | Needs Design Work | Agent node output must be compatible with Tool Node input (messages with tool_calls); state updates (generation_complete) not specified. |
| Technical Feasibility | Sound | Prompt and LLM config are standard; token limit is called out. |
| Vertical Slice | Partial | Agent + tools loop is in 2.5; 2.3 delivers the agent node only. |
| Security/Compliance | Sound | No secrets in prompt; config from env. |
| Dependencies & Risks | Medium | Token limits; dependency on 2.1 (state), 2.2 (tools). |
| MECE | Sound | Agent only; 2.5 wires the loop. |
| DoD Technical | Needs Design Work | Message format and completion detection in DoD. |

#### Strengths

- System prompt content and workflow (structure, fidelity, interrupt) are specified; config from env is in scope.
- Tool binding and state updates (current_chapter, pending_question) are mentioned.
- Unit test for prompt content and integration test with mock LLM.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Message format:** ARCHITECTURE and stories use `messages: Annotated[List[str], operator.add]`. LangGraph/LangChain ReAct and Tool Node expect `messages` to be a list of BaseMessage (HumanMessage, AIMessage, ToolMessage). AIMessage can carry tool_calls; Tool Node runs those and appends ToolMessage(s). So DocumentState should have `messages: Annotated[List[BaseMessage], operator.add]` for the agent↔tools loop to work. This is a **breaking** alignment: either change state to BaseMessage and update all nodes that read/write messages, or use a custom agent that works with string messages (non-standard). Recommendation: **adopt BaseMessage** for the agent loop; keep a separate `messages_display: List[str]` for logging/UI if needed.
2. **Agent node responsibility:** Agent node should: (1) read state["messages"], (2) build prompt from state (current file, chapter, etc.) as HumanMessage or system + user, (3) invoke LLM with tools bound (from 2.2 factory), (4) get AIMessage (possibly with tool_calls), (5) return state with messages appended (and optionally current_chapter, pending_question, generation_complete). It should **not** run the full ReAct loop internally (that would duplicate the graph). So the graph is: agent → tools → route_after_tools → agent | …; agent node is one step.
3. **Completion signal:** When is “generation complete”? Option A: agent returns a special message or tool call (e.g. “finish”). Option B: state flag `generation_complete: bool` set by agent node when LLM output indicates done. Option C: route_after_tools infers from “no tool_calls in last message” and “current_file_index >= len(input_files)-1”. Recommend: add **generation_complete** to state; agent node sets it to True when LLM response indicates completion (e.g. final message without tool_calls and content like “I have finished…”); route_after_tools uses it for “complete” branch.
4. **External reference detection:** Story says “if agent indicates missing file, set pending_question”. Detection could be: (1) parse LLM content for keywords (“missing file”, “external reference”, “need user”); (2) dedicated tool “request_human_input(question)” that agent calls; (3) structured output from LLM. Option 2 is clean: add tool `request_human_input(question: str, session_id: str)` that returns “pending” and the tools node (or custom node) sets state["pending_question"] = question. Then route_after_tools sends to human_input when pending_question non-empty.

#### Proposed Technical Designs

**1. Message format (DocumentState)**

- For the subgraph agent ↔ tools: use `messages: Annotated[List[BaseMessage], operator.add]`. build_initial_state sets messages=[] (empty list). Agent node appends HumanMessage (and optionally system); LLM returns AIMessage (with optional tool_calls); Tool Node appends ToolMessage(s). Other nodes (scan_assets, validate_md) can append HumanMessage or a simple string to a separate “log” key if needed.
- Alternative: keep messages as List[str] and use a **custom** agent implementation that doesn’t use LangChain’s create_react_agent (e.g. manual loop in one node that calls LLM, then runs tools, then calls LLM again until no tool_calls). That avoids changing state shape but duplicates logic. Prefer standard message format.

**2. Agent node signature and flow**

```python
def agent_node(state: DocumentState) -> DocumentState:
    session_id = state["session_id"]
    messages = state["messages"]  # List[BaseMessage]
    # Build next user message from state (current file, chapter, validation_issues if any)
    user_content = build_user_prompt(state)
    messages = messages + [HumanMessage(content=user_content)]
    # Invoke LLM with tools (from get_tools(session_id))
    response = llm.with_structured_output(...).invoke(messages)  # or llm.bind_tools(tools).invoke(messages)
    messages = messages + [response]  # AIMessage possibly with tool_calls
    # Detect completion and pending_question
    generation_complete = _is_completion(response)
    pending_question = _extract_pending_question(response) or state.get("pending_question") or ""
    return {
        **state,
        "messages": messages,
        "generation_complete": generation_complete,
        "pending_question": pending_question,
        "current_chapter": state["current_chapter"] + 1 if _chapter_advanced(response) else state["current_chapter"],
    }
```

**3. Completion and interrupt detection**

- _is_completion: True if last AIMessage has no tool_calls and content indicates done (e.g. “finished”, “complete”, or use a structured field).
- _extract_pending_question: True if agent called request_human_input tool or content contains “missing file” / “need user” (or add request_human_input tool and set pending_question from tool result in tools node).

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 9 | Align state["messages"] with LangChain BaseMessage for agent/tool loop | Dev | 3 SP | Use List[BaseMessage]; update build_initial_state; ensure Tool Node receives/returns same format. |
| 10 | Implement agent_node as single-step (no internal ReAct loop); return state with messages + flags | Dev | 2 SP | One LLM invoke per node run; append AIMessage; set generation_complete and pending_question from response. |
| 11 | Define completion detection (generation_complete) and optional request_human_input tool | Dev | 2 SP | Set generation_complete when LLM signals done; add tool or parse content for pending_question. |
| 12 | User prompt template: include validation_issues when returning from validate_md | Dev | 1 SP | When state has validation_issues, inject into user prompt so agent can fix. |

#### Revised Story (Technical Specs)

- **DoD addition:** messages in state are BaseMessage for agent↔tools; agent node is single-step; generation_complete and pending_question set in state; completion and interrupt detection documented.
- **Contract:** Agent node reads/writes state["messages"] as List[BaseMessage]; tools bound via get_tools(state["session_id"]); prompt includes current file, chapter, and optional validation_issues.

---

### Story 2.4: Implement Human-in-the-Loop — Interrupt on Missing Reference, Inject User Decision, Resume

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | user_decisions schema, resume flow, and “upload” handling are under-specified; LangGraph interrupt API should be pinned. |
| Data Model | Needs Design Work | user_decisions shape (ref → action; where is uploaded file path?) not defined. |
| API/Integration | Needs Design Work | How entry/resume works (interrupt_before, update_state, invoke again); human_input node behavior. |
| Technical Feasibility | Sound | LangGraph supports interrupt; checkpointer is in scope. |
| Vertical Slice | Partial | Interrupt and resume only; full flow in 2.5. |
| Security/Compliance | Critical Gaps | Upload path must be validated (sanitizer); user_decisions must not accept arbitrary paths. |
| Dependencies & Risks | Medium | “Upload” implies file receipt; CLI vs API affects design. |
| MECE | Sound | HITL only; 2.5 wires it. |
| DoD Technical | Sound | Tests for interrupt and resume; add schema and upload validation. |

#### Strengths

- Two interrupt points (scan_assets, agent) and same human_input flow are clear.
- Checkpointer and thread_id for resume are in scope.
- Unit and integration tests for state transition and resume.

#### Critical Gaps (Data Model, APIs, Infra)

1. **user_decisions schema:** Story says “ref → upload | skip”. For “upload”, the system needs the path of the uploaded file. Propose: `user_decisions: dict[str, Union[Literal["skip"], dict]]` e.g. `{ "ref1": "skip", "ref2": {"action": "upload", "path": "/validated/path" } }`. Or separate `uploaded_paths: dict[str, str]` (ref → path). Entry (or human_input node when resumed) must validate any path through InputSanitizer and resolve under allowed base before copying to session assets.
2. **human_input node behavior:** When graph routes to human_input, we need to **interrupt** (pause) and return control to caller. So human_input can be: (1) a node that returns state unchanged and is preceded by `interrupt_before=["human_input"]` so the graph stops before running it, or (2) a node that runs and returns state (with user_decisions already injected by caller). Option 1: use LangGraph `interrupt_before=["human_input"]`; when we would transition to human_input, graph returns and caller gets state; caller injects user_decisions (and optionally uploaded file), then calls `workflow.invoke(None, config)` or `workflow.update_state(...)` and continues. Option 2: human_input node runs; it reads a “callback” or “injected_decisions” from config; that’s awkward. Recommendation: **interrupt_before=["human_input"]**; caller updates state with user_decisions (and processes uploads, then sets paths in state); then resume. human_input node itself can be a no-op (return state) or it can “process” user_decisions (copy uploads to assets, clear missing_references). Prefer: human_input node runs **after** resume with updated state, and its job is to copy uploaded files to session assets and clear missing_references for skipped refs; then return state and edge to agent.
3. **Resume API:** Document: “When graph returns due to interrupt, entry receives state; entry calls workflow.update_state(thread_id, state_updates) then workflow.invoke(None, config) to resume.” Or use invoke with input_state that merges user_decisions. Exact LangGraph API (update_state vs invoke with state) depends on version; document and add task to verify with LangGraph 1.x.
4. **Upload path validation:** Any path in user_decisions for “upload” must be validated with InputSanitizer (or at least path under base_dir, allowed extension for images). Add task: validate upload paths before copying to session assets.

#### Proposed Technical Designs

**1. user_decisions and upload schema**

```python
# Option A: flat
user_decisions: dict[str, str]  # ref -> "skip" | path (validated path for upload)

# Option B: explicit
UserDecision = Literal["skip"] | TypedDict("Upload", {"action": Literal["upload"], "path": str})
user_decisions: dict[str, UserDecision]
# path must be validated (InputSanitizer or allowlist) before use
```

**2. Interrupt and resume flow**

- Compile: `workflow.compile(checkpointer=memory, interrupt_before=["human_input"])`.
- When scan_assets or route_after_tools sends to human_input, graph returns with state and next node = human_input.
- Entry: get state; present pending_question to user; collect decisions (skip ref1, upload ref2 with file at path P); validate P with InputSanitizer; set state["user_decisions"] = {"ref1": "skip", "ref2": P}; clear state["pending_question"] and optionally state["missing_references"] for skipped; for upload, copy P to session assets and update refs. Then resume: workflow.invoke(None, config) or update_state + invoke. human_input node: when it runs (after resume), it can no-op (entry did everything) or do the copy (if entry only set user_decisions and path). Recommend: **entry validates and copies**; human_input node just returns state and edges to agent. So human_input is a no-op that allows “interrupt before it” to work; after resume we might go to human_input then agent, or directly to agent. LangGraph: if we use interrupt_before human_input, after resume the graph will run human_input then follow its edge. So human_input node: return state unchanged (entry already updated it); edge human_input → agent.

**3. human_input node**

- Input: state (with user_decisions and possibly missing_references already updated by entry).
- Logic: optional — if user_decisions contains upload paths, copy to session assets (or leave to entry). Output: state.
- Edge: human_input → agent.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 9 | Define user_decisions schema (ref → "skip" | validated path for upload) | Dev | 1 SP | TypedDict or dict contract; document that upload path must be validated. |
| 10 | Use interrupt_before=["human_input"] and document resume (update_state or invoke) | Dev | 2 SP | Compile with interrupt_before; document how entry resumes with user_decisions. |
| 11 | Validate upload paths with InputSanitizer before copy to session assets | Dev | 2 SP | When user provides path for upload, validate then copy to session_path/assets. |
| 12 | human_input node: no-op or process user_decisions; edge to agent | Dev | 1 SP | Node returns state; edge human_input → agent; entry or node does copy. |

#### Revised Story (Technical Specs)

- **DoD addition:** user_decisions schema documented; interrupt_before and resume flow documented and tested; upload path validation; human_input node and edge defined.
- **Contract:** Interrupt at human_input; entry (or human_input node) validates upload paths and copies to session assets; resume with same thread_id and updated state.

---

### Story 2.5: Wire Agent ↔ Tools Loop and Routing (Validate, Conversion, Ask User)

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | route_after_tools input (how state is updated from tool results), completion condition, and validate_md/parse_to_json stubs need design. |
| Data Model | Needs Design Work | State keys set by tools node (last_checkpoint_id) and by validate_md (validation_passed, validation_issues) must be in DocumentState. |
| API/Integration | Sound | Conditional edges and node wiring are clear. |
| Technical Feasibility | Sound | markdownlint is a system/CLI dependency; add to DoD. |
| Vertical Slice | Sound | End-to-end agent ↔ tools ↔ validate ↔ complete. |
| Security/Compliance | Sound | validate_md runs on session temp_output only. |
| Dependencies & Risks | Medium | Completion heuristic vs explicit flag; tools → state update. |
| MECE | Sound | Routing and loop only. |
| DoD Technical | Needs Design Work | markdownlint dependency; max iterations / deadlock prevention. |

#### Strengths

- Four-way route_after_tools (agent, validate, human_input, complete) and validate_md behavior (fix vs continue) are specified.
- parse_to_json stub and “complete” path are in scope.
- Integration test for full loop and routing table documentation.

#### Critical Gaps (Data Model, APIs, Infra)

1. **route_after_tools input:** It needs to know “did agent just call create_checkpoint?” and “is there a pending_question?”. If the Tool Node does not write last_checkpoint_id or pending_question to state, route_after_tools cannot read them. So either: (1) **Custom tools node** that, after executing tools, updates state from tool results (e.g. last_checkpoint_id from create_checkpoint return, pending_question from request_human_input if used), or (2) route_after_tools parses the last message(s) (e.g. last AIMessage.tool_calls and corresponding ToolMessages) to infer what was called. Option 1 is robust; add task “Custom tools node or post-tool state updater that sets last_checkpoint_id and pending_question from tool results”.
2. **Completion condition:** Story says “current_file_index >= len(input_files)-1 and agent signaled done”. Agent may process multiple chapters per file; “done” is when agent has finished all content. So use state["generation_complete"] (set by agent node) as the primary signal; optionally require current_file_index to be past last file. Add to route_after_tools: if state.get("generation_complete") and no pending_question → "complete".
3. **validate_md node:** Runs markdownlint on session temp_output.md. markdownlint may be CLI (`markdownlint path --json`) or a Python wrapper; document. If CLI, subprocess; capture stdout/stderr; parse JSON for issues. Set state["validation_passed"] = (returncode==0), state["validation_issues"] = parsed issues. Dependency: markdownlint must be installed (npm or system). DoD: “markdownlint available (path or install instruction)”.
4. **parse_to_json stub:** Must set state["structure_json_path"] so downstream (Epic 5) can use it. Stub can write minimal JSON `{"metadata": {}, "sections": []}` to session/structure.json and set state["structure_json_path"] = path. Add task explicitly.
5. **Infinite loop prevention:** Agent → tools → agent could loop forever if agent never sets generation_complete and never triggers validate/complete. Add max_iterations or max_agent_steps (e.g. 100) and fail or force-complete; or document as operational limit in DoD.
6. **validate_md → agent:** When validation fails, state must carry validation_issues so agent can fix (Story 2.3 user prompt should include them). Ensure validate_md returns state with validation_issues set.

#### Proposed Technical Designs

**1. route_after_tools logic (pseudocode)**

```python
def route_after_tools(state: DocumentState) -> str:
    if state.get("pending_question"):
        return "human_input"
    if state.get("last_checkpoint_id"):  # set by custom tools node after create_checkpoint
        return "validate"
    if state.get("generation_complete"):
        return "complete"
    return "agent"
```

**2. Custom tools node (optional but recommended)**

- After ToolNode.run(tool_calls) or equivalent: for each tool result, if tool was create_checkpoint then state["last_checkpoint_id"] = result; if request_human_input then state["pending_question"] = result. Then return merged state. Implement as a wrapper around LangGraph’s ToolNode or a single node that (1) gets tool_calls from last message, (2) runs tools via get_tools(state["session_id"]), (3) builds ToolMessage(s), (4) updates state (last_checkpoint_id, etc.), (5) appends messages and returns state.

**3. validate_md node**

- Input: state with session_id.
- Run: `subprocess.run(["markdownlint", str(session_path / "temp_output.md"), "--json"], capture_output=True, text=True)`.
- Output: state with validation_passed=(returncode==0), validation_issues=parsed_json or [].

**4. parse_to_json stub**

- Write `session_path / "structure.json"` with `{"metadata": {"title": "", "author": "", "created": ""}, "sections": []}`.
- Set state["structure_json_path"] = str(session_path / "structure.json").
- Return state; edge to END or to convert_docx (stub) for Epic 2.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 9 | Custom tools node or state updater: set last_checkpoint_id and pending_question from tool results | Dev | 3 SP | After running tools, update state from create_checkpoint and request_human_input (if used) so route_after_tools can branch. |
| 10 | route_after_tools: use generation_complete for complete branch; document order of checks | Dev | 1 SP | Prefer generation_complete over file index; document priority (human_input > validate > complete > agent). |
| 11 | parse_to_json stub: write minimal structure.json and set structure_json_path | Dev | 1 SP | File and state key so conversion epic can consume. |
| 12 | DoD: markdownlint dependency and install path; max agent iterations or deadlock note | Dev/QA | 1 SP | Document markdownlint; optional max_steps to prevent infinite loop. |

#### Revised Story (Technical Specs)

- **DoD addition:** State updated from tool results (last_checkpoint_id, pending_question); route_after_tools uses generation_complete; parse_to_json stub writes structure.json; markdownlint and iteration limit documented.
- **Contract:** route_after_tools has access to last_checkpoint_id and pending_question (set by tools node or custom updater); validate_md sets validation_passed and validation_issues; stub sets structure_json_path.

---

## Overall Technical Roadmap

### Missing Foundational Work

1. **State and message format:** Decide once whether messages are `List[str]` or `List[BaseMessage]`. Recommendation: BaseMessage for the agent↔tools subgraph; document and implement in 2.1/2.3.
2. **Tool → state updates:** Either custom tools node or a dedicated “post_tools” node that sets last_checkpoint_id and pending_question from tool results. Required for route_after_tools to work; implement in 2.2 or 2.5.
3. **scan_assets ownership:** Implement minimal scan_assets in 2.1 so the graph has a runnable first node; Epic 3 can extend for full asset management.
4. **LangGraph version and interrupt API:** Pin LangGraph version (e.g. 1.x) and document interrupt_before and resume (update_state vs invoke) in one place (2.4).

### Schema Proposals (Summary)

| Artifact | Purpose |
|----------|---------|
| DocumentState (TypedDict) | Single module; required vs optional keys; reducer for messages, missing_references. |
| messages as List[BaseMessage] | Agent/tool loop compatibility with LangGraph Tool Node. |
| generation_complete: bool | Explicit completion signal for route_after_tools. |
| user_decisions schema | ref → "skip" \| validated path for upload; document validation. |
| get_tools(session_id) | Tool factory for session-scoped tools and session_id injection. |
| build_initial_state (Epic 1.4) | Must set all DocumentState keys used by graph (with defaults). |

### Architecture Decisions Needed

1. **Message type in state:** BaseMessage (recommended) vs List[str] with custom agent loop. Decision affects 2.1 and 2.3.
2. **Who updates state from tool results:** Custom tools node (recommended) vs parsing messages in route_after_tools.
3. **human_input node:** No-op (entry does all work before resume) vs node that copies uploads and clears refs. Recommendation: entry validates and copies; human_input returns state and edges to agent.
4. **scan_assets in Epic 2:** Minimal implementation in 2.1 (detect missing refs, set state) so graph is runnable; full copy and image handling in Epic 3.

### Cross-Cutting Concerns (MECE)

- **Logging (FC015):** Not explicitly in Epic 2 stories. Recommend: each node logs state transition and key state keys (session_id, status); optional StructuredLogger in 2.1 or separate story.
- **Observability:** Tool calls and errors could be logged (tool name, session_id, success/failure). Optional for Epic 2.
- **Testing:** Integration test for full loop (scan_assets → agent → tools → validate → complete) with mock LLM or scripted tool responses; test interrupt and resume in 2.4; test path validation in 2.2.

### DoD Technical Additions (Epic-Level)

- **Performance:** Optional: “Single agent step completes within T seconds (e.g. 60) for typical prompt size”; “Graph with N files does not exceed M agent steps without completion or interrupt.”
- **Dependencies:** markdownlint (CLI or package) documented; LangGraph and LiteLLM versions in pyproject/requirements.
- **Deadlock:** Document or implement max agent iterations (e.g. 100) and behavior (fail or force-complete).

---

## Summary Table: Technical Scores

| Story | Technical Score | Main Gaps | Priority Fixes |
|-------|-----------------|-----------|-----------------|
| 2.1 DocumentState + workflow start | Needs Design Work | Optional keys, scan_assets not implemented, single state module | Add minimal scan_assets; document state key contract; single module. |
| 2.2 Tool Node | Needs Design Work | session_id injection, list_files safety, path validation, tool→state | Tool factory; list_files(session_id); path validation; security tests. |
| 2.3 Agent node | Needs Design Work | Message format (BaseMessage), completion signal, single-step agent | BaseMessage; generation_complete; agent node as one step; completion detection. |
| 2.4 Human-in-the-loop | Needs Design Work | user_decisions schema, interrupt/resume API, upload validation | user_decisions schema; interrupt_before + resume; validate upload paths. |
| 2.5 Agent ↔ tools loop and routing | Needs Design Work | Tool results → state, completion condition, validate_md/parse stub, markdownlint | Custom tools node or state updater; generation_complete; stub; markdownlint in DoD. |

**Overall:** Epic 2 is implementable after incorporating the proposed designs and missing tasks. No **Critical Gaps** that block development; the main risks are **message format** (BaseMessage vs str), **tool→state updates** for routing, and **scan_assets** implementation so the graph is runnable from 2.1. Resolving these in the revised stories will make the epic ready for sprint execution.
