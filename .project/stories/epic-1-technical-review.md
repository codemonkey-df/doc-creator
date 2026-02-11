# Epic 1: Secure Input & Session Foundation — Technical Review

**Reviewer role:** Senior Software Architect / Agile Team Lead  
**Scope:** Technical deep-dive audit of decomposed stories; data models, APIs, feasibility, security, MECE, DoD.  
**Context:** Parent Epic 1, ARCHITECTURE.md (Agentic Document Generator).

---

## Parent Epic Technical Context

### Architecture Assumptions

- **Orchestration:** LangGraph (≥1.0) with `StateGraph(DocumentState)`, `MemorySaver` checkpointer; workflow starts at an entry point that may sit outside the graph (stories propose validation + copy before graph invoke) or inside an "initialize" node (ARCHITECTURE shows session create + sanitize inside `initialize_node`). This **flow split** must be resolved (see Story 1.4).
- **Tech stack:** Python 3.13, uv, pathlib/shim for filesystem; no DB for Epic 1 — session and input metadata are in-memory (DocumentState) and on-disk (session dirs). Config via env + optional Pydantic.
- **Session model:** File-system only. Session = UUID directory under `./docs/sessions/{uuid}` with fixed subdirs: `inputs/`, `assets/`, `checkpoints/`, `logs/`. No session table or API; session_id is the UUID string passed through state.
- **Input model:** User provides list of file paths (strings). After validation they become a list of filenames (or paths) relative to session `inputs/`. No formal schema for "request payload" yet — currently CLI/list of paths.
- **Security:** All user path handling must go through InputSanitizer; base_dir is the only allowed root. FC015 (structured logging) is cross-cutting but not explicitly tasked in Epic 1 stories.

### Relevant ARCHITECTURE References

- **DocumentState (TypedDict):** `session_id`, `input_files: List[str]`, `current_file_index`, `status`, etc. Comment says "Validated file paths" — convention: after init, `input_files` = filenames in session `inputs/`.
- **Flow:** Start → initialize → scan_assets → … → save_results → END. initialize_node in ARCHITECTURE creates session, sanitizes paths, copies to session inputs, and returns state.
- **Config:** MAX_FILE_SIZE, SESSION_TIMEOUT, LOG_LEVEL in .env; no shared Pydantic config model yet for sanitizer/session paths.

---

## Story-by-Story Technical Audit

---

### Story 1.1: Implement InputSanitizer (Path Resolution, Extensions, Size, Boundary)

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | Clear contract; small gaps in schema and error taxonomy. |
| Data Model | N/A (stateless) | No persistent model; exception types are the "schema" for failure. |
| API/Integration | Sound | Single method `validate(path, base_dir) -> Path`; callers are file discovery and (indirectly) entry. |
| Technical Feasibility | Sound | Task breakdown is realistic; no new infra. |
| Vertical Slice | Partial | No UI/API in Epic 1; logic layer is complete. |
| Security/Compliance | Sound | Path traversal, blocklist, size, encoding covered; audit logging is cross-story. |
| Dependencies & Risks | Low | Python version for `is_relative_to` (3.12+); symlink handling called out. |
| MECE | Sound | No overlap with 1.2/1.3; config shared with 1.2. |
| DoD Technical | Needs Design Work | Coverage target present; no performance or security test criteria. |

#### Strengths

- Explicit exception types (`SecurityError` vs `ValueError`) and docstring contract.
- Extension whitelist/blocklist and size limit align with FC001/FC016.
- Config (Pydantic/env) and UTF-8/binary check are in scope.
- Symlink and `is_relative_to` fallback for older Python are mentioned in risks.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Error taxonomy not formalized:** No shared module for `SecurityError` (and optionally `ValidationError`) or error codes (e.g. PATH_ESCAPE, EXTENSION_BLOCKED, FILE_TOO_LARGE, ENCODING_ERROR). Downstream (file discovery, entry) will need to map exceptions to user-facing messages.
2. **Config schema missing:** Story says "Pydantic/env" but no shared `InputConfig` or `SanitizerConfig` with `allowed_extensions`, `blocked_extensions`, `max_file_size_bytes`. Risk of drift between sanitizer and env (e.g. MAX_FILE_SIZE in .env but not used by sanitizer).
3. **UTF-8 validation strategy undefined:** "Attempt read" vs "sniff" vs "sample first N bytes" — could open very large files if not done after size check; order of checks (size before read) must be explicit in DoD.
4. **No security test criteria:** DoD has >80% coverage but no explicit requirement for negative tests (path traversal, symlink escape, oversized) to be in a "security" test set or tagged.

#### Proposed Technical Designs

**1. Exception and error-code schema (recommended)**

```python
# utils/exceptions.py or utils/sanitizer.py
class SecurityError(Exception):
    """Raised when path escapes base or other security violation."""
    pass

class ValidationError(Exception):
    """Raised for extension, size, encoding (non-security) validation failure."""
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code  # e.g. "EXTENSION_BLOCKED", "FILE_TOO_LARGE", "INVALID_UTF8"
```

**2. Config schema (Pydantic) — align with ARCHITECTURE §8.1**

```python
# config/settings.py (or utils/config.py)
from pydantic import BaseModel
from pydantic_settings import BaseSettings

class SanitizerSettings(BaseSettings):
    allowed_extensions: set[str] = {".txt", ".log", ".md"}
    blocked_extensions: set[str] = {".exe", ".dll", ".so", ".bin", ".sh", ".bat"}
    max_file_size_bytes: int = 104_857_600  # 100MB
    model_config = {"env_prefix": "INPUT_", "extra": "ignore"}
```

**3. Validation order (in story or DoD)**

- Resolve path → check exists → check under base_dir → check extension (blocklist then whitelist) → check size → then UTF-8 (read or sample). Never read full file for size; use `stat().st_size` only.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 8 | Define shared exception types and optional error codes | Dev | 1 SP | Add `SecurityError` and `ValidationError` (with code); document in sanitizer contract. |
| 9 | Define Pydantic config model for sanitizer settings | Dev | 1 SP | SanitizerSettings with allowed/blocked exts and max_file_size; load from env. |
| 10 | Document validation order and add security test tag | Dev/QA | 1 SP | DoD: validation order documented; security-related tests tagged e.g. `@pytest.mark.security`. |

#### Revised Story (Technical Specs)

- **DoD addition:** Validation order: path resolve → exists → base_dir → extension → size → UTF-8. Security-related tests tagged; >80% coverage retained.
- **Contract:** `validate(path: str, base_dir: Path) -> Path`; raises `SecurityError` (path escape/symlink), `ValidationError` (extension/size/encoding) or `FileNotFoundError`. Config via `SanitizerSettings` (or equivalent) from env.

---

### Story 1.2: Implement SessionManager (Create UUID Dirs, Cleanup/Archive)

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | Layout and API match ARCHITECTURE; minor schema and lifecycle gaps. |
| Data Model | Needs Design Work | No explicit "session record" schema; directory layout is the only contract. Optional: session metadata for audit. |
| API/Integration | Sound | create/get_path/cleanup; no HTTP API. |
| Technical Feasibility | Sound | Realistic; mkdir/move/rmtree only. |
| Vertical Slice | Partial | Back-end only; sufficient for Epic 1. |
| Security/Compliance | Needs Design Work | Cleanup failure behavior and archive permissions not specified; audit (FC015) not tasked. |
| Dependencies & Risks | Low | Cleanup vs workflow usage called out. |
| MECE | Sound | Config base path shared with 1.1 (different keys). |
| DoD Technical | Sound | Layout and tests specified; add cleanup failure policy. |

#### Strengths

- Directory layout matches ARCHITECTURE exactly (`inputs`, `assets`, `checkpoints`, `logs`).
- UUID guarantees uniqueness; cleanup archive vs delete is clear.
- Config for base path and archive path is in scope.

#### Critical Gaps (Data Model, APIs, Infra)

1. **No session metadata schema:** Session is "directory only." If FC015 (audit) or future "list my sessions" is needed, there is no defined metadata (e.g. created_at, status, input_file_count). Optional for Epic 1 but should be a conscious decision.
2. **get_path(session_id) contract unclear:** Story says "invalid/missing session handled (e.g. raise or return None)." Returning `Path` for non-existent session can cause subtle bugs. Recommend: always return `Path`; document that path may not exist; or add `exists(session_id) -> bool` and document that `get_path` assumes valid id.
3. **Cleanup failure policy:** "Log and optionally raise" is vague. For archive: what if disk full or permission denied? Recommend: define "cleanup must not fail the request" (log + optional metric) vs "critical failure raises" and document in DoD.
4. **Archive directory creation:** ARCHITECTURE shows `shutil.move(path, f"./docs/archive/{session_id}")`; parent `archive` must exist. Task 4 should explicitly create `archive` if not exists.
5. **Configuration schema:** Same need as 1.1 — a `SessionSettings` (base_path, sessions_dir, archive_dir) so session and sanitizer don’t hardcode `./docs`.

#### Proposed Technical Designs

**1. Directory layout contract (formal)**

```
SESSION_ROOT = {base_path}/sessions/{session_id}/
  inputs/      # only input files
  assets/      # images etc.
  checkpoints/ # timestamp_label.md
  logs/        # session.jsonl etc.
ARCHIVE_ROOT = {base_path}/archive/{session_id}/  # same structure after move
```

**2. Optional session metadata (for audit/FC015)**

If logging "session created" with metadata, a simple schema:

```python
# Not persisted to DB; could be written to session_dir/metadata.json or logs only
class SessionMetadata(TypedDict, total=False):
    session_id: str
    created_at: str  # ISO8601
    input_file_count: int
    status: str  # "active" | "archived" | "deleted"
```

**3. get_path contract**

- `get_path(session_id: str) -> Path`: returns `Path(base / "sessions" / session_id)`. Does not check existence. Callers must ensure session_id was created by this manager (or add optional `exists(session_id)`).

**4. Cleanup failure policy**

- On archive: create `archive` parent if missing. On move failure: log error, optionally re-raise (configurable). On rmtree failure: log, re-raise so caller can retry or alert.
- DoD: document "cleanup failure handling" and "archive parent creation."

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 8 | Define get_path contract and optional exists(session_id) | Dev | 1 SP | Document that get_path returns path without existence check; add exists() if needed. |
| 9 | Ensure archive parent exists before move; document cleanup failure policy | Dev | 1 SP | mkdir(archive_parent, parents=True) before move; document log vs raise for failures. |
| 10 | Add SessionSettings (Pydantic) for base_path, sessions_dir, archive_dir | Dev | 1 SP | Load from env (e.g. DOCS_BASE_PATH, SESSIONS_DIR, ARCHIVE_DIR); use in create/cleanup. |

#### Revised Story (Technical Specs)

- **DoD addition:** Cleanup failure policy documented; archive parent created if missing. get_path contract (no existence check) documented.
- **Optional:** SessionMetadata schema and writing created_at (and optionally status) to logs or metadata.json for FC015 alignment.

---

### Story 1.3: File Discovery — List and Validate Requested Files Before Workflow Start

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | Good API shape; return type and base_dir validation need tightening. |
| Data Model | Needs Design Work | Return type "list of errors" is underspecified (structure for path + reason + code). |
| API/Integration | Sound | Two functions; integration with sanitizer is clear. |
| Technical Feasibility | Sound | No new infra. |
| Vertical Slice | Partial | Logic only; sufficient. |
| Security/Compliance | Sound | base_dir "resolved and restricted" is tasked; can tie to same base as sanitizer. |
| Dependencies & Risks | Low | Depends on 1.1; large dirs noted. |
| MECE | Sound | No overlap with 1.1/1.2; consumes 1.1. |
| DoD Technical | Sound | Unit + integration tests; clarify error structure in DoD. |

#### Strengths

- Clear separation: list available vs validate requested; reuses InputSanitizer.
- FC007 (validate against filesystem before workflow) is explicit.
- Base_dir safety is a dedicated task.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Validate return type underspecified:** Story says `tuple[list[Path], list[str]]` for (valid, errors). Errors as `list[str]` loses which path failed. Recommend: `list[tuple[str, str]]` (path, message) or a small `ValidationResult` with `valid: list[Path]`, `errors: list[FileValidationError]` (path, message, code).
2. **list_available_files return type:** "list of filenames or paths" — for consistency with later copy (which uses path.name), returning `list[str]` (filenames) or `list[Path]` should be fixed; if callers need to validate, they need full path to pass to sanitizer. Recommend: `list[Path]` (resolved under base_dir) so validate can accept same.
3. **Base_dir "restricted" not defined:** "Not world-writable or document allowed roots" — implementable only if "allowed roots" is a config list; otherwise just resolve and use as sanitizer base. Recommend: base_dir is the single allowed input root; document that it must be set to a dedicated input directory.
4. **Recursion:** list_available_files is "iterate over base_dir" — confirm non-recursive (no os.walk); Epic 1 is flat input dir only.

#### Proposed Technical Designs

**1. Validation result schema**

```python
# utils/file_discovery.py
class FileValidationError(TypedDict):
    path: str
    message: str
    code: str  # e.g. "MISSING", "EXTENSION_BLOCKED", "FILE_TOO_LARGE", "INVALID_UTF8", "PATH_ESCAPE"

def validate_requested_files(
    requested: list[str],
    base_dir: Path,
    sanitizer: InputSanitizer,
) -> tuple[list[Path], list[FileValidationError]]:
    ...
```

**2. list_available_files contract**

- `list_available_files(base_dir: Path, sanitizer: InputSanitizer | None = None) -> list[Path]`: list only direct children (non-recursive) that have allowed extension. Optionally run sanitizer (size, encoding) or only extension filter; document behavior. Return resolved Paths under base_dir so caller can pass to validate or copy.

**3. Base_dir contract**

- base_dir must be an absolute, resolved path. Single allowed input root; no "allowed roots" list in Epic 1. Document: "base_dir is the only directory from which user can request files."

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 7 | Define FileValidationError (path, message, code) and return structure | Dev | 1 SP | Replace list[str] errors with list[FileValidationError]; align codes with sanitizer. |
| 8 | Fix list_available_files return to list[Path] and document non-recursive | Dev | 1 SP | Return resolved Paths; document flat directory only. |
| 9 | Document base_dir as single allowed root and resolve before use | Dev | 0.5 SP | In docstring and DoD. |

#### Revised Story (Technical Specs)

- **API:**  
  - `list_available_files(base_dir: Path) -> list[Path]` (flat, allowed extension only).  
  - `validate_requested_files(requested: list[str], base_dir: Path) -> tuple[list[Path], list[FileValidationError]]`.
- **DoD:** Error structure includes path + message + code; base_dir contract and non-recursive behavior documented.

---

### Story 1.4: Copy Validated Inputs into Session `inputs/` and Wire Session Lifecycle into Workflow Entry

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Flow and state ownership are under-specified; entry vs graph boundary is inconsistent with ARCHITECTURE. |
| Data Model | Needs Design Work | DocumentState and entry payload need to be aligned; optional request/response schema for future API. |
| API/Integration | Critical Gaps | Entry signature and error response shape not specified; no mention of future REST/CLI contract. |
| Technical Feasibility | Sound | Tasks are doable; ordering and single cleanup owner must be explicit. |
| Vertical Slice | Needs Design Work | End-to-end slice is there but "workflow can run" is vague — graph may expect initialize node to create session; flow must be decided. |
| Security/Compliance | Sound | Copy uses validated paths only; destination name = path.name (no traversal). Audit (FC015) not in scope. |
| Dependencies & Risks | Medium | Race between cleanup and tools; duplicate filenames; flow vs ARCHITECTURE. |
| MECE | Sound | Integrates 1.1–1.3; no duplicate. |
| DoD Technical | Needs Design Work | Missing: state shape doc, entry contract, cleanup ownership, performance (e.g. max files). |

#### Strengths

- Clear sequence: create session → validate → copy → pass to workflow; cleanup on success and failure.
- Duplicate filenames and cleanup race are called out in risks.
- Integration test covers happy path and validation failure.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Entry vs graph flow mismatch:** ARCHITECTURE §5.3 has `initialize_node` creating session, sanitizing, and copying inside the graph. Stories 1.3/1.4 move "validate + copy" to before graph invoke. That implies either:  
   - **Option A:** Entry creates session, validates, copies, then invokes graph with state already containing session_id and input_files; **first node is not "initialize" but e.g. "scan_assets"** and the graph no longer has an "initialize" that creates session.  
   - **Option B:** Entry only validates; graph’s first node "initialize" creates session and copies. Then validation runs twice (once at entry for early failure, once in node) or entry only does "dry run" validation.  
   Recommendation: **Option A** — entry does session create + validate + copy; graph starts at scan_assets (or a thin "session_ready" node). Update ARCHITECTURE and graph edges accordingly. This must be an explicit architecture decision in this story.
2. **DocumentState and entry contract:** Entry must produce state that matches DocumentState: session_id, input_files (list of filenames in session inputs/), and required initial values for current_file_index, status, conversion_attempts, retry_count, etc. DocumentState has many keys; story should reference "initial state shape" and who sets defaults (entry vs first node).
3. **Entry signature and response schema:** `generate_document(input_files: List[str])` is mentioned; no return type. Recommend: `GenerateResult` TypedDict with success, session_id, output_path (if success), error (if failure), messages, validation_errors (if validation failed before session create).
4. **Single cleanup owner:** Cleanup must run exactly once per session and only after no node/tool will access the session. If workflow is synchronous, cleanup in entry after invoke is fine. If async or LangGraph interrupt is used, cleanup might run in save_results node (as in ARCHITECTURE). Story should state: "Cleanup is performed in [entry | save_results_node]; no other code path deletes/archives."
5. **Duplicate filenames:** Two requested paths with same name (e.g. from different dirs) overwrite in inputs/. DoD should state: "Duplicate destination names are overwritten (last wins) or rejected;" recommend document "last wins" and optionally add a task to dedupe (e.g. suffix with index).
6. **No performance/scale criteria:** DoD could add "max N input files per request" (e.g. 50) or "total size limit" to avoid abuse; optional.

#### Proposed Technical Designs

**1. Entry flow (Option A — recommended)**

```
Entry: input_paths: list[str], base_dir: Path (from config)
  1. validate_requested_files(input_paths, base_dir) -> valid Paths, errors
  2. If no valid files: return GenerateResult(success=False, validation_errors=errors)
  3. session_id = SessionManager().create()
  4. Copy each valid Path to get_path(session_id)/inputs/path.name
  5. initial_state = { session_id, input_files=[p.name for p in valid], status="scanning_assets", ... }
  6. result = workflow.invoke(initial_state, config)
  7. SessionManager().cleanup(session_id, archive=(result["status"]=="complete"))
  8. return GenerateResult(success=..., session_id=..., ...)
```

Graph: START → scan_assets (no "initialize" node that creates session).

**2. Initial state shape (subset of DocumentState)**

```python
def build_initial_state(session_id: str, input_files: list[str]) -> DocumentState:
    return {
        "session_id": session_id,
        "input_files": input_files,
        "current_file_index": 0,
        "current_chapter": 0,
        "conversion_attempts": 0,
        "retry_count": 0,
        "last_checkpoint_id": "",
        "document_outline": [],
        "missing_references": [],
        "user_decisions": {},
        "pending_question": "",
        "status": "scanning_assets",  # or "initializing" if kept for compatibility
        "messages": [],
        # temp_md_path, structure_json_path, output_docx_path can be set when created or in first node
    }
```

**3. Entry response schema**

```python
class GenerateResult(TypedDict, total=False):
    success: bool
    session_id: str
    output_path: str
    error: str
    validation_errors: list[FileValidationError]
    messages: list[str]
```

**4. Cleanup ownership**

- In **synchronous** entry: entry calls cleanup after workflow.invoke returns.  
- In **save_results_node**: node calls cleanup before returning (so graph owns cleanup).  
- Choose one and document; recommend entry-owned cleanup for Option A so all session lifecycle is in one place.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 8 | Architecture decision: entry creates session + copy; graph starts at scan_assets (or thin node) | Dev/Arch | 1 SP | Document flow; update graph to remove session creation from initialize or remove initialize. |
| 9 | Define initial state builder and DocumentState defaults | Dev | 2 SP | build_initial_state(session_id, input_files); document required keys and defaults. |
| 10 | Define GenerateResult and entry return contract | Dev | 1 SP | GenerateResult TypedDict; return on validation failure vs workflow failure vs success. |
| 11 | Document cleanup ownership (entry vs save_results) and duplicate-filename policy | Dev | 1 SP | Single place that calls cleanup; document "last wins" for duplicate names. |
| 12 | Integration test: graph receives pre-filled state and runs scan_assets without create | QA/Dev | 2 SP | Assert no session create inside graph; assert cleanup after invoke. |

#### Revised Story (Technical Specs)

- **Flow:** Entry: validate → [if no valid] return error; create session → copy → build_initial_state → workflow.invoke → cleanup(session_id, archive=success) → return GenerateResult. Graph: START → scan_assets (or session_ready) → … (no session create in graph).
- **Contract:** Entry function signature and GenerateResult; initial state shape documented; cleanup owned by entry; duplicate filenames = last wins, documented.
- **DoD:** State shape and cleanup ownership in DoD; integration test verifies no double-create and cleanup after invoke.

---

## Overall Technical Roadmap

### Missing Foundational Work

1. **Shared config module:** One Pydantic settings (or env) module for Epic 1: sanitizer (extensions, max size), session (base path, sessions dir, archive dir), and optionally base_dir for input. Recommend a single "Epic 1 config" task or spike (1–2 SP) before or in parallel with 1.1/1.2.
2. **Exception and error-code taxonomy:** Central place for `SecurityError`, `ValidationError`, and codes (PATH_ESCAPE, EXTENSION_BLOCKED, FILE_TOO_LARGE, INVALID_UTF8, MISSING). Used by 1.1 and 1.3; can be part of 1.1 and consumed by 1.3.
3. **Entry/graph boundary decision:** Document in ARCHITECTURE that "session create + validate + copy" is done at entry; graph starts after session is ready. Update diagram and node list (remove or repurpose initialize_node).

### Schema Proposals (Summary)

| Artifact | Purpose |
|----------|---------|
| SanitizerSettings (Pydantic) | allowed/blocked extensions, max_file_size; env-loaded. |
| SessionSettings (Pydantic) | base_path, sessions_dir, archive_dir; env-loaded. |
| SecurityError / ValidationError (code) | Consistent errors for sanitizer and discovery. |
| FileValidationError (path, message, code) | Structured validation errors from file discovery. |
| SessionMetadata (optional) | created_at, status for audit/FC015. |
| GenerateResult (TypedDict) | Entry return type (success, session_id, output_path, error, validation_errors, messages). |
| build_initial_state() | DocumentState initial slice for entry. |

### Architecture Decisions Needed

1. **Where does session creation live?** Recommendation: entry only; graph assumes session exists. Update ARCHITECTURE and Story 1.4 accordingly.
2. **Where does cleanup run?** Recommendation: entry, after invoke. Alternative: save_results node; then entry must not cleanup on failure if graph didn’t reach save_results (e.g. crash) — may need a "session lease" or timeout cleanup later.
3. **Do we need a formal "request" schema for future REST API?** Optional for Epic 1; if yes, add "Request: list of paths + optional base_dir override" and "Response: GenerateResult" to a future API story.

### Cross-Cutting Concerns (MECE)

- **Logging (FC015):** Not in Epic 1 scope; ensure session create/copy/cleanup log at least session_id and outcome. Structured logger can be added in a later epic; minimal logging in 1.2/1.4 is enough.
- **Monitoring:** No metrics in stories; optional: counter "sessions_created", "sessions_cleaned_up", "validation_failures" for observability.
- **Testing:** Security test tag (1.1), error-structure tests (1.3), and integration test for entry+graph+cleanup (1.4) close the main gaps.

### DoD Technical Additions (Epic-Level)

- **Performance:** Optional: "Entry completes validation + copy for up to N files (e.g. 50) within T seconds (e.g. 30) on reference hardware."
- **Deployment:** No deployment scripts in Epic 1; ensure docs mention env vars (MAX_FILE_SIZE, DOCS_BASE_PATH, etc.) for deployers.
- **Test coverage:** Keep >80% for new code; add security and integration criteria as above.

---

## Summary Table: Technical Scores

| Story | Technical Score | Main Gaps | Priority Fixes |
|-------|-----------------|-----------|----------------|
| 1.1 InputSanitizer | Architecturally Sound | Error taxonomy, config schema, validation order, security test tag | Add exception/code schema; Pydantic config; document order; tag security tests. |
| 1.2 SessionManager | Architecturally Sound | get_path contract, cleanup policy, archive parent, config schema | Document get_path; cleanup policy + archive mkdir; SessionSettings. |
| 1.3 File Discovery | Architecturally Sound | Error return structure, list return type, base_dir contract | FileValidationError; list[Path]; document base_dir and flat list. |
| 1.4 Copy + Wire Lifecycle | Needs Design Work | Entry vs graph flow, state shape, response schema, cleanup owner, duplicate names | Decide entry-owned create+copy; document state and GenerateResult; single cleanup owner; duplicate policy. |

**Overall:** Epic 1 is implementable with the revised stories and the added tasks/specs above. The only **Critical Gaps** are in Story 1.4 (flow and contract); resolving the entry/graph boundary and documenting state and response will make the epic ready for sprint execution.
