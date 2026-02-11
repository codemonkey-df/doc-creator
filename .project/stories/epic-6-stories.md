# Epic 6: Error Handling, Resilience & Operations — Story Decomposition

**Epic ID:** 6  
**Epic Goal:** Classify conversion and validation errors, apply specialized fixes (syntax, encoding, asset, structural), enforce retry limits and graceful degradation, and add observability and production readiness.  
**Business Value:** Self-healing where possible; predictable failure behavior and clear reporting; operable and secure in production (logging, config, deployment, security).  
**Epic Acceptance Criteria (Reference):** FC005 (granular fixes by line where applicable; no full-doc rewrite when not needed); FC013 (classify errors: Syntax, Encoding, Asset, Structural, Unknown; route to correct handler); FC017 (max 3 conversion attempts; on final failure save best-effort markdown + error report and guidance); FC015 (structured JSON logging per session: state transitions, tool calls, errors); deployment checklist, env-based config, and security practices (sandboxing, no content in logs) addressed.

**Dependencies:** Epic 4 (Validation, Checkpointing & Recovery — rollback before retry). Epic 5 (conversion failure handling; last_error, conversion_success from parse/convert nodes).

**Architecture alignment:** ARCHITECTURE §3.1 (Error Classifier, Syntax/Encoding/Asset/Structural handlers, Rollback in Error Handling subgraph), §4.8 (ErrorClassifier, ErrorType enum, handler strategies), §4.10 (StructuredLogger FC015), §5.1 (DocumentState: conversion_attempts, last_error, error_type, retry_count, status), §5.2–5.3 (error_handler_node, save_results_node, should_retry_conversion; conditional edges convert_docx/quality_check → error_handler → retry vs save_results).

**Technical Review:** This backlog was updated with findings from the technical audit. See `.project/stories/epic-6-technical-review.md` for full detail. Key decisions: (1) ErrorMetadata TypedDict + keyword evaluation order (Syntax → Encoding → Asset → Structural → Unknown); message truncation 2000 chars; asset_ref in metadata for Asset type (6.1). (2) Handler contract: return outcome string only; on exception return "Fix failed: ..."; AssetHandler uses asset_ref; StructuralHandler clamps heading level 1..3; session existence asserted (6.2). (3) Order: classify → restore_from_checkpoint → invoke handler → increment retry_count; Unknown still increments retry_count; re-entry = agent; get_logger fallback; FC017 = retry_count only (6.3). (4) Branch: failure = (retry_count >= MAX) or (status == "failed"); archive dir created if missing; ERROR_REPORT schema; failure path leaves session in place (6.4). (5) get_logger(session_id), logger not in state; log line schema and event_type allowlist; tool_call args keys/type only; LOG_LEVEL only (6.5).

---

## Story 6.1: Error Classifier — Parse Error Message/Location, Return Type + Metadata; Wire Into Error Handler Node

### Refined Acceptance Criteria

- **AC6.1.1** An **ErrorClassifier** (or equivalent module) accepts a raw **error message** (string, e.g. from conversion stderr or validation output) and returns a **classified type** and **metadata**. Types SHALL be: **Syntax**, **Encoding**, **Asset**, **Structural**, **Unknown** (FC013; ARCHITECTURE §4.8).
- **AC6.1.2** **Metadata** SHALL use a defined **ErrorMetadata** schema (TypedDict): **line_number** (int or None), **message** (str; truncate to 2000 chars if longer), **timestamp** (ISO8601). Optional: **context**, **source** ("markdownlint" | "docx-js" | "parse" | "quality"), **asset_ref** (str, when type is Asset — filename/path extracted from message). Export from error_handlers for error_handler and logging.
- **AC6.1.3** Classification logic SHALL use **keyword/pattern matching** with **canonical evaluation order**: (1) **Syntax** — unclosed, malformed, table, fence, code block; (2) **Encoding** — encoding, utf-8, decode, unicode; (3) **Asset** — image, file not found, asset, missing, enoent; (4) **Structural** — heading, hierarchy, level, skip; (5) **Unknown** (default). Message lowercased; order and keywords documented and unit-tested (e.g. ambiguous "table" → Syntax).
- **AC6.1.4** Classifier is **pure** (no I/O, no session access); signature `classify(error_msg: str) -> Tuple[ErrorType, ErrorMetadata]`. **ErrorType** is an Enum exported for use by the error handler node. When type is Asset, classifier SHALL attempt to extract **asset_ref** from message (regex) and set in metadata for AssetHandler.
- **AC6.1.5** The **error_handler** graph node (Story 6.3) SHALL call the classifier with **state["last_error"]** and use the returned type and metadata to route to the appropriate handler and to populate **state["error_type"]** and optional **error_metadata** for logging. This story delivers the classifier module and its contract; wiring is completed in Story 6.3.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define ErrorType enum (Syntax, Encoding, Asset, Structural, Unknown) | Dev | 0.5 SP | Python Enum or Literal type; export in error_handlers/classifier.py or shared types. |
| 2 | Define metadata schema (line_number, message, timestamp; optional context, source) | Dev | 1 SP | TypedDict or dataclass; document in DoD. |
| 3 | Implement classify(error_msg: str) with keyword/pattern rules per AC6.1.3 | Dev | 3 SP | Lowercase message; regex for line number; if/elif keyword checks; return (ErrorType, metadata). |
| 4 | Add line-number extraction (e.g. "line 45", "line: 45") | Dev | 1 SP | re.search pattern; default None if not found. |
| 5 | Set metadata timestamp to datetime.now().isoformat() | Dev | 0.5 SP | In classify() before return. |
| 6 | Unit tests: each error type with representative messages | QA/Dev | 3 SP | Fixtures for Syntax, Encoding, Asset, Structural, Unknown; assert type and metadata.line_number where applicable. |
| 7 | Unit tests: unknown message → Unknown type; empty string edge case | QA/Dev | 1 SP | Assert Unknown; metadata present. |
| 8 | Document classification rules and keyword list in DoD or module docstring | Dev | 0.5 SP | Table or list of keywords per type; canonical order. |
| 9 | Export ErrorType and classify from error_handlers package for error_handler node | Dev | 0.5 SP | __all__ or explicit exports; contract for Story 6.3. |
| 10 | Define ErrorMetadata TypedDict and use in classify return type | Dev | 0.5 SP | Export from error_handlers; document optional fields (context, source, asset_ref). |
| 11 | Document keyword evaluation order and add test for ambiguous "table" message | Dev/QA | 1 SP | Order: Syntax → Encoding → Asset → Structural → Unknown; fixture "table alignment" → Syntax. |
| 12 | Normalize long message in metadata (truncate to 2000 chars); document | Dev | 0.5 SP | metadata["message"] = message[:2000] if len(message) > 2000 else message. |
| 13 | Document expected last_error sources (markdownlint, docx-js, parse, quality) and test with sample stderr from each | Dev/QA | 1 SP | Fixtures per source; assert correct type. |
| 14 | When type is Asset, extract optional asset_ref from message (regex); set in metadata | Dev | 1 SP | For AssetHandler in 6.2/6.3; e.g. filename or path from message. |

### Technical Risks & Dependencies

- **Risk:** Overlap between keywords (e.g. "table" in Syntax vs Structural); **evaluation order** (Syntax first) and tests for ambiguous messages address this.
- **Dependency:** None (classifier is stateless). Story 6.3 will call classify(state["last_error"]) and use result.

### Definition of Done

- [ ] ErrorType enum and classify(error_msg: str) -> Tuple[ErrorType, ErrorMetadata] implemented; ErrorMetadata TypedDict defined; metadata includes line_number, message (truncated 2000 chars), timestamp; optional context, source, asset_ref (when type Asset).
- [ ] Classification rules documented; **canonical keyword order** (Syntax → Encoding → Asset → Structural → Unknown) defined and tested; all five types covered; ambiguous-message test (e.g. "table" → Syntax).
- [ ] Unit tests for each type and edge cases; tests for markdownlint, docx-js, parse, quality_check error formats; no I/O. **Contract:** classify(error_msg: str) -> Tuple[ErrorType, ErrorMetadata]; error_handler node (6.3) calls with state["last_error"] and uses type for routing and metadata (line_number, asset_ref) for handlers and logging.

---

## Story 6.2: Specialized Handlers — Syntax, Encoding, Asset, Structural; Each Updates Session Files

### Refined Acceptance Criteria

- **AC6.2.1** **Four handler modules** (or classes) implement fixes that **update session files** (e.g. temp_output.md or structure.json) without full-doc rewrite where possible. Handlers: **SyntaxHandler**, **EncodingHandler**, **AssetHandler**, **StructuralHandler** (ARCHITECTURE §4.8).
- **AC6.2.2** **SyntaxHandler:** Fixes such as **unclosed code fences** (count ``` and add closing fence if odd), **malformed table** (document strategy: e.g. add missing pipes or reject; optional line_number for granular fix). At least **fix_unclosed_code_block(session_id, line_number: Optional[int])** implemented; updates temp_output.md; returns outcome string for logging.
- **AC6.2.3** **EncodingHandler:** **fix_invalid_utf8(session_id)** — read temp_output.md with encoding='utf-8', errors='replace'; rewrite with UTF-8. No full-doc rewrite of content; only normalize encoding. Returns outcome string.
- **AC6.2.4** **AssetHandler:** **insert_placeholder(session_id, image_name_or_path, \*\*kwargs)** — replace **all** matching missing image markdown (e.g. ![](path) or ![alt](path)) with text placeholder e.g. `**[Image Missing: filename]**`. Accept **asset_ref** from classifier metadata (Story 6.1); if not provided use "unknown_asset". Returns outcome string.
- **AC6.2.5** **StructuralHandler:** **fix_heading_hierarchy(session_id)** — read temp_output.md; adjust heading levels so no skip; **clamp level to 1..3** (FC002); prev_level tracking; level = min(level, prev_level+1), max(1, level). Returns outcome string.
- **AC6.2.6** All handlers use **SessionManager.get_path(session_id)** for paths; **no hardcoded session layout**. Path traversal and invalid session_id are rejected. **Handler contract:** return outcome string only; on exception **return** "Fix failed: &lt;reason&gt;" (do not raise). **Precondition:** session dir exists at handler start; if not, return "Fix failed: session not found". Handlers are **idempotent where possible**. Structured logging: log fix attempt and outcome (Story 6.5 logger or from error_handler node).

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Create error_handlers package layout (syntax_handler, encoding_handler, asset_handler, structural_handler) | Dev | 0.5 SP | Modules or classes under error_handlers/; export fix functions. |
| 2 | Implement SyntaxHandler: fix_unclosed_code_block(session_id, line_number optional) | Dev | 3 SP | Read temp_output.md; count ``` ; if odd append "\n```\n"; write back; return message. |
| 3 | SyntaxHandler: document malformed-table strategy (optional implementation or "escalate") | Dev | 0.5 SP | DoD: table fix optional; document in ARCHITECTURE or handler docstring. |
| 4 | Implement EncodingHandler: fix_invalid_utf8(session_id) | Dev | 2 SP | Open with utf-8, errors='replace'; read; write back utf-8. Use session path from SessionManager. |
| 5 | Implement AssetHandler: insert_placeholder(session_id, image_name_or_path) | Dev | 3 SP | Replace ![](path) or ![alt](path) with **[Image Missing: name]**; support line_number for single-line replace if provided. |
| 6 | Implement StructuralHandler: fix_heading_hierarchy(session_id) | Dev | 3 SP | Parse lines; track prev_level; if level > prev_level+1 set level=prev_level+1; rewrite line; write file. |
| 7 | All handlers: resolve paths via SessionManager.get_path(session_id); validate session_id/path | Dev | 2 SP | Reject path traversal; fail fast if session dir missing. |
| 8 | Unit tests: each handler with temp session dir and fixture (unclosed fence, bad UTF-8, missing image, skipped heading) | QA/Dev | 5 SP | Assert file content after fix; assert return string. |
| 9 | Unit tests: idempotency where applicable (encoding run twice; hierarchy run twice) | QA/Dev | 1 SP | No regression. |
| 10 | Document handler contract (session_id, optional line_number/context); log fix attempt/outcome | Dev | 1 SP | Docstrings; call logger.log_event in each handler or from error_handler node. |
| 11 | Define handler contract: return outcome string only; on exception return "Fix failed: ..." (no raise) | Dev | 0.5 SP | Document in error_handlers package; all handlers catch and return. |
| 12 | AssetHandler: accept optional asset_ref from metadata; replace all image refs matching asset_ref | Dev | 1 SP | If no asset_ref, use "unknown_asset" or scan for broken refs; document "replace all". |
| 13 | StructuralHandler: clamp heading level to 1..3; document | Dev | 0.5 SP | level = max(1, min(level, prev_level + 1)); FC002. |
| 14 | Assert session dir exists at handler start; do not create; return "Fix failed: session not found" if missing | Dev | 0.5 SP | SessionManager.get_path(session_id); path.exists(). |

### Technical Risks & Dependencies

- **Risk:** Syntax fixes (e.g. table) may be heuristic; document limitations and fallback to "Unknown" or retry without fix.
- **Dependency:** Epic 1 (SessionManager, session layout). Story 6.1 (asset_ref in metadata when type Asset). Story 6.3 invokes these handlers based on classifier output.

### Definition of Done

- [ ] Four handlers implemented; each updates session files (temp_output.md) and returns outcome string only (no raise; on exception return "Fix failed: ..."); path resolution via SessionManager.
- [ ] Syntax: unclosed fence fix; Encoding: UTF-8 replace; Asset: placeholder (asset_ref from metadata; replace all); Structural: heading hierarchy (level clamped 1..3). FC005 respected (granular where applicable).
- [ ] Session existence asserted at handler start; handler contract documented. Unit tests per handler; path validation; idempotency where applicable. **Contract:** Handlers (session_id, **kwargs) -> str; error_handler passes session_id and metadata (line_number, asset_ref); all paths via SessionManager.get_path(session_id).

---

## Story 6.3: Error Handler Node — Classify → Invoke Handler → Rollback (Epic 4) → Increment Retry; Conditional Edge Retry vs Fail

### Refined Acceptance Criteria

- **AC6.3.1** An **error_handler** graph node runs when conversion fails (convert_docx sets conversion_success=False) or quality check fails (quality_passed=False). Node reads **state["last_error"]**, **state["retry_count"]**, **state["conversion_attempts"]** (or single retry counter), and **state["last_checkpoint_id"]** (Epic 4).
- **AC6.3.2** Node flow (canonical order): (1) **Classify** via ErrorClassifier.classify(state["last_error"]) → ErrorType + ErrorMetadata. (2) **Rollback** when applicable: call **restore_from_checkpoint(session_id, last_checkpoint_id)** (Epic 4) to restore temp_output.md from last checkpoint; if last_checkpoint_id missing or invalid, skip rollback and log rollback_skipped. (3) **Invoke** handler for Syntax/Encoding/Asset/Structural (pass session_id and metadata, e.g. line_number, asset_ref); for **Unknown**, do not invoke handler but still **increment retry_count** and route (avoid infinite loop). (4) **Increment retry_count**. (5) Update state: **error_type**, **retry_count**, **last_error** (unchanged, for save_results); optional handler_outcome for logging.
- **AC6.3.3** **Conditional edge:** **should_retry_conversion(state)** → if retry_count >= MAX_RETRY_ATTEMPTS (3 per FC017) → **save_results** (fail); else → **agent** (retry). **Re-entry = agent** (so flow can re-validate and run parse_to_json → convert_docx again). FC017 is enforced by **retry_count only**; conversion_attempts is informational.
- **AC6.3.4** **Order of operations:** Classify → restore_from_checkpoint (if checkpoint) → invoke handler (or skip for Unknown) → increment retry_count. Rollback before handler ensures fix is applied to restored content. If rollback skipped, handler runs on current temp_output.md.
- **AC6.3.5** Use **get_logger(state["session_id"])** or StructuredLogger; if Story 6.5 not implemented, use no-op logger fallback so node runs. Structured logging: log state_transition into error_handling; log error_classified (type, metadata); log handler invocation and outcome; log retry_count and routing decision. FC015.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement error_handler node signature: state in → state out | Dev | 2 SP | Read last_error, retry_count, last_checkpoint_id, session_id; return updated state. |
| 2 | In node: call ErrorClassifier.classify(last_error); set state["error_type"] and error_metadata | Dev | 2 SP | Use Story 6.1 classifier; store type and metadata for save_results and logging. |
| 3 | Route by type to Syntax/Encoding/Asset/Structural handler; pass session_id and metadata (line_number, image path) | Dev | 3 SP | if error_type == Syntax: SyntaxHandler.fix_...(session_id, metadata.get("line_number")); etc. Unknown: no fix, log. |
| 4 | Before handler: call restore_from_checkpoint(session_id, last_checkpoint_id) when checkpoint available | Dev | 3 SP | Epic 4 contract; if checkpoint missing or invalid, skip rollback; then run handler. |
| 5 | After handler: increment retry_count (or conversion_attempts) in state | Dev | 1 SP | retry_count = state["retry_count"] + 1; cap not needed here (routing does it). |
| 6 | Implement should_retry_conversion(state): return "retry" if retry_count < 3 else "fail" | Dev | 1 SP | FC017 max 3 attempts; return edge key. |
| 7 | Wire conditional edge: error_handler → should_retry_conversion → {"retry": agent_or_parse, "fail": save_results} | Dev | 2 SP | add_conditional_edges("error_handler", should_retry_conversion, {...}). Decide re-entry: agent vs parse_to_json (recommend agent to re-validate). |
| 8 | Document rollback-then-fix order and missing-checkpoint behavior in DoD | Dev | 0.5 SP | DoD and ARCHITECTURE §5.3. |
| 9 | Structured logging: state_transition, error_classified, handler result, retry_count, route | Dev | 2 SP | Use session StructuredLogger; FC015. |
| 10 | Unit tests: error_handler with mocked classifier and handlers; assert state updates and retry_count | QA/Dev | 3 SP | Mock classify and handlers; assert error_type, retry_count, and that rollback is called when checkpoint present. |
| 11 | Integration test: convert_docx failure → error_handler → retry path (retry_count < 3) | QA/Dev | 2 SP | Simulate failure; assert route to agent or parse_to_json. |
| 12 | Integration test: retry_count >= 3 → route to save_results | QA/Dev | 1 SP | Set retry_count=3; assert route to fail. |
| 13 | Define MAX_RETRY_ATTEMPTS = 3 (config or constant); document FC017 | Dev | 0.5 SP | Single source of truth; DoD. |
| 14 | Implement rollback-before-handler order: restore_from_checkpoint then invoke handler | Dev | 1 SP | Ensure code order matches AC (classify → rollback → handler → increment). |
| 15 | For Unknown type: do not invoke handler; still increment retry_count and log | Dev | 0.5 SP | Avoid infinite loop; document in DoD. |
| 16 | Document re-entry: retry → agent; update ARCHITECTURE §5.2 if needed | Dev | 0.5 SP | DoD and ARCHITECTURE. |
| 17 | get_logger(session_id) or no-op fallback when 6.5 not implemented | Dev | 0.5 SP | So 6.3 can be tested before 6.5. |
| 18 | Document: FC017 enforced by retry_count only; conversion_attempts informational | Dev | 0.5 SP | DoD. |

### Technical Risks & Dependencies

- **Risk:** Rollback then fix overwrites any prior handler result; by design we rollback to clean state then re-apply fix once per attempt. Document.
- **Dependency:** Story 6.1 (classifier, ErrorMetadata, asset_ref), Story 6.2 (handlers), Epic 4 (restore_from_checkpoint, last_checkpoint_id). Epic 5 (last_error, conversion_success, quality_passed). Story 6.5 (logger) or no-op fallback.

### Definition of Done

- [ ] error_handler node implemented: **order** classify → restore_from_checkpoint (if checkpoint) → invoke handler (or skip for Unknown) → increment retry_count; state updated. For Unknown: no handler, still increment retry_count.
- [ ] Conditional edge: retry_count < 3 → **agent** (retry); retry_count >= 3 → save_results. MAX_RETRY_ATTEMPTS = 3 (FC017). Re-entry = agent. FC017 enforced by retry_count only (conversion_attempts informational).
- [ ] Rollback (Epic 4) called before handler when last_checkpoint_id valid; missing checkpoint → skip rollback, log. get_logger(session_id) or no-op fallback. Structured logging; unit and integration tests. **Contract:** Node expects last_error, retry_count, last_checkpoint_id, session_id; outputs error_type, retry_count; calls Epic 4 restore_from_checkpoint(session_id, last_checkpoint_id) before handler.

---

## Story 6.4: Save-Results Node — On Success Archive Session; On Failure Write FAILED_conversion.md + ERROR_REPORT.txt and Set Status

### Refined Acceptance Criteria

- **AC6.4.1** A **save_results** graph node runs after **quality_check** (success path) or after **error_handler** (fail path when retry_count >= 3). **Branch condition:** failure = (retry_count >= MAX_RETRY_ATTEMPTS) or (status == "failed"); success = not failure. Use single helper or inline; document.
- **AC6.4.2** **On success:** Ensure **archive parent dir** (e.g. docs/archive) exists (create if missing); call SessionManager.cleanup(session_id, archive=True). Set **state["status"] = "complete"**. Set or preserve **output_docx_path** for caller (e.g. docs/archive/{session_id}/output.docx) so API/main can return path.
- **AC6.4.3** **On failure:** (1) Copy **temp_output.md** to **FAILED_conversion.md** in session dir (or write placeholder if temp_output missing). (2) Write **ERROR_REPORT.txt** (UTF-8) with **schema:** session_id, timestamp (ISO8601), retry_count, last_error (truncate to 1000 chars), error_type, guidance (static template). (3) Set **state["status"] = "failed"**. **Do not archive or delete session** — leave in docs/sessions/{session_id} so user can inspect FAILED_conversion.md and ERROR_REPORT.txt.
- **AC6.4.4** Paths use **SessionManager.get_path(session_id)**. File names **FAILED_conversion.md** and **ERROR_REPORT.txt** are exact (document in DoD). Encoding for ERROR_REPORT.txt: UTF-8.
- **AC6.4.5** Structured logging: log event **session_completed** (success) or **session_failed** (failure) with session_id, status, and if failed retry_count and error_type. FC015.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement save_results node: branch on success vs failure | Dev | 2 SP | If status complete / quality_passed and not failed path: success; else if status failed or retry_count >= 3: failure. |
| 2 | Success path: call SessionManager.cleanup(session_id, archive=True) | Dev | 2 SP | Move session to archive; set status="complete"; return state. |
| 3 | Failure path: copy temp_output.md to FAILED_conversion.md in session dir | Dev | 2 SP | Use SessionManager.get_path(session_id); shutil.copy or Path.write_text(read_text()). |
| 4 | Failure path: write ERROR_REPORT.txt with session_id, retry_count, last_error, error_type, guidance | Dev | 2 SP | Template string or file; UTF-8; guidance per AC6.4.3. |
| 5 | Set state["status"] to "complete" or "failed" accordingly | Dev | 0.5 SP | Consistent with DocumentState.status literal. |
| 6 | Document exact file names and location (session dir) in DoD | Dev | 0.5 SP | FAILED_conversion.md, ERROR_REPORT.txt. |
| 7 | Structured logging: session_completed / session_failed with session_id, status, retry_count (if failed) | Dev | 1 SP | FC015. |
| 8 | Unit tests: success path (mock cleanup; assert status complete) | QA/Dev | 2 SP | Temp session; set state success; run node; assert cleanup called, status complete. |
| 9 | Unit tests: failure path (assert FAILED_conversion.md and ERROR_REPORT.txt exist and content) | QA/Dev | 3 SP | Temp session with temp_output.md; set state failed, retry_count=3, last_error; run node; assert files and guidance text. |
| 10 | Edge case: failure with no temp_output.md (e.g. parse failed) — create FAILED_conversion.md with placeholder or note in ERROR_REPORT | Dev | 1 SP | If temp_output missing, write minimal FAILED_conversion.md or note in ERROR_REPORT. |
| 11 | Wire save_results to END in workflow (both success and fail paths) | Dev | 0.5 SP | add_edge("save_results", END). |
| 12 | Define branch condition: failure = (retry_count >= MAX_RETRY_ATTEMPTS) or (status == "failed") | Dev | 0.5 SP | Single helper _is_failure_path(state) or inline; document. |
| 13 | Ensure archive parent dir exists before cleanup (create docs/archive if missing) | Dev | 0.5 SP | In SessionManager.cleanup or at node start. |
| 14 | Document ERROR_REPORT schema: session_id, timestamp, retry_count, last_error (trunc 1000), error_type, guidance | Dev | 0.5 SP | DoD. |
| 15 | On success, set or preserve output_docx_path for caller (archive path) | Dev | 0.5 SP | e.g. docs/archive/{session_id}/output.docx; document. |
| 16 | Document: failure path does not delete or archive session; session stays for inspection | Dev | 0.5 SP | DoD. |

### Technical Risks & Dependencies

- **Risk:** Archive dir may not exist; task 13 ensures parent dir created before move.
- **Dependency:** Epic 1 (SessionManager.get_path, cleanup). Story 6.3 (fail path routes to save_results with retry_count >= 3). Epic 5 (output_docx_path for success path). MAX_RETRY_ATTEMPTS from config/constant (same as 6.3).

### Definition of Done

- [ ] save_results node: **branch** failure = (retry_count >= MAX_RETRY_ATTEMPTS) or (status == "failed"); success → ensure archive dir exists, cleanup(session_id, archive=True), status=complete, output_docx_path set for caller; failure → FAILED_conversion.md + ERROR_REPORT.txt in session dir (last_error truncated 1000 chars), status=failed; **failure path does not archive or delete session**.
- [ ] ERROR_REPORT schema documented: session_id, timestamp, retry_count, last_error (trunc 1000), error_type, guidance. File names and encoding (UTF-8) documented.
- [ ] Unit tests for success and failure paths; edge case (no temp_output) handled. Structured logging; node wired to END. **Contract:** Node is the single exit; state["status"] is "complete" or "failed"; success = archive session; failure = write files in session dir and leave session in place.

---

## Story 6.5: Structured Logger (FC015) — Session-Scoped JSONL Logs; Config (Env), Deployment Checklist, Security Notes

### Refined Acceptance Criteria

- **AC6.5.1** A **StructuredLogger** provides **session-scoped** logging. Log file: **{session}/logs/session.jsonl** (one JSON object per line). **Required fields** per line: **timestamp** (ISO8601), **session_id**, **event_type**; event-specific fields optional. **event_type** allowlist: state_transition, tool_call, error, session_created, validation_ran, conversion_started, checkpoint_saved, error_classified, error_fix_attempted, session_completed, session_failed (document in DoD). FC015; ARCHITECTURE §4.10.
- **AC6.5.2** **tool_call:** log **tool_name**; **args** = keys only or type-only (e.g. {"filename": "&lt;str&gt;", "lines": "&lt;int&gt;"}) — **never** log arg values that might contain content; **result** truncated to 200 chars. **No file content or PII** in any log line.
- **AC6.5.3** Nodes obtain logger via **get_logger(session_id)** (module-level registry or create each time). **Do not store logger in state** (state must remain serializable). Methods: **log_event(event_type, \*\*kwargs)**, **log_state_transition(from_state, to_state)**, **log_tool_call(tool_name, args, result)**, **log_error(error_type, message)**. Write each line with newline and **flush**; no log rotation (bounded by session lifecycle).
- **AC6.5.4** **Configuration:** **LOG_LEVEL** from env (INFO|DEBUG|WARNING|ERROR); apply to handler. **Log path** = session_path/logs/session.jsonl (no LOG_PATH override for v1; document LOG_LEVEL only). **Deployment checklist:** ARCHITECTURE §10 or ops doc — env vars, file permissions, session cleanup cron, monitoring, backup, rate limiting, **logs must not contain document content**.
- **AC6.5.5** **Security notes:** Document sandboxing and no content in logs in ARCHITECTURE §14. Code: tool_call args keys/type only; result truncated 200 chars; no file contents or user inputs in logs.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement StructuredLogger class: __init__(session_id), log file at {session}/logs/session.jsonl | Dev | 3 SP | Create logs dir if needed; FileHandler; formatter output raw JSON line per record. |
| 2 | Implement log_event(event_type, **kwargs): build dict with timestamp, session_id, event_type, **kwargs; json.dumps; write line | Dev | 2 SP | timestamp = datetime.now().isoformat(); no mutable refs in log. |
| 3 | Implement log_state_transition(from_state, to_state, **kwargs) | Dev | 0.5 SP | Call log_event("state_transition", ...). |
| 4 | Implement log_tool_call(tool_name, args, result): truncate result to 200 chars; sanitize args (no content) | Dev | 2 SP | Log tool name; args as keys only or safe summary; result truncated. |
| 5 | Implement log_error(error_type, message, **kwargs) | Dev | 0.5 SP | Call log_event("error", ...). |
| 6 | Implement get_logger(session_id); nodes call get_logger(state["session_id"]); do not store logger in state | Dev | 2 SP | Module-level registry or create each time; document in DoD. |
| 7 | Add LOG_LEVEL from env; read in logger init or config; log path = session_path/logs/session.jsonl | Dev | 1 SP | os.getenv("LOG_LEVEL", "INFO"); no LOG_PATH for v1. |
| 8 | Document deployment checklist: env vars, permissions, cleanup cron, monitoring, no content in logs | Dev | 2 SP | ARCHITECTURE §10 or docs/deployment.md; checklist items. |
| 9 | Document security: sandboxing, no content in logs, subprocess timeouts (ARCHITECTURE §14) | Dev | 1 SP | Align with ARCHITECTURE §14.3 Data Privacy. |
| 10 | Review all log_event/log_tool_call call sites: ensure no document content or PII | Dev | 2 SP | Grep for log_event; truncate/sanitize; add tests that log line does not contain sample content. |
| 11 | Unit tests: logger writes valid JSONL; state_transition and tool_call entries have required fields | QA/Dev | 2 SP | Temp session; create logger; log events; read file; parse each line as JSON; assert keys. |
| 12 | Unit test: tool_call result truncated to 200 chars | QA/Dev | 0.5 SP | Log long result; assert len in JSON <= 200 or similar. |
| 13 | Document log line required fields (timestamp, session_id, event_type) and event_type allowlist | Dev | 0.5 SP | DoD or utils/logger.py. |
| 14 | Sanitize tool_call args: log keys only or type-only; never content | Dev | 1 SP | Implement in log_tool_call; document in DoD. |
| 15 | Write each log line with newline and flush; document no rotation | Dev | 0.5 SP | Bounded by session lifecycle. |
| 16 | Document LOG_LEVEL only; log path always session_path/logs/session.jsonl | Dev | 0.5 SP | Config doc. |

### Technical Risks & Dependencies

- **Risk:** Accidentally logging full file content; mitigate with args keys/type only and result truncation (task 15, 10).
- **Dependency:** Epic 1 (session layout with logs/). All nodes that need logging (Epic 2, 4, 5, 6) use get_logger(session_id); can be adopted incrementally.

### Definition of Done

- [ ] StructuredLogger implemented; **get_logger(session_id)** pattern; logger **not stored in state**. Session-scoped session.jsonl; log_event, log_state_transition, log_tool_call, log_error; **required fields** timestamp, session_id, event_type in every entry; **event_type allowlist** documented.
- [ ] **No document content or PII in logs;** tool_call args = keys only or type-only; result truncated 200 chars. Each line written with newline and flush; no rotation. **LOG_LEVEL** from env; log path = session_path/logs/session.jsonl (LOG_LEVEL only, no LOG_PATH for v1).
- [ ] Deployment checklist and security notes added to ARCHITECTURE or docs. Unit tests for JSONL format and truncation. **Contract:** Nodes call get_logger(state["session_id"]) for FC015 observability; no content in logs.

---

## Epic 6 Summary: Task Count and Ordering

Stories updated per technical review (`.project/stories/epic-6-technical-review.md`). Added: ErrorMetadata, keyword order, asset_ref, handler contract, rollback-before-handler order, branch condition, ERROR_REPORT schema, get_logger pattern, and related tasks.

| Story | Focus | Key Deliverable | Suggested Order |
|-------|--------|------------------|-----------------|
| 6.1 | Error Classifier | classify(msg) → (ErrorType, ErrorMetadata); keyword order; asset_ref | 1 |
| 6.2 | Specialized Handlers | Syntax, Encoding, Asset, Structural; handler contract; asset_ref; level 1..3 | 2 (parallel with 6.1 possible) |
| 6.5 | Structured Logger | get_logger(session_id); JSONL + LOG_LEVEL; deployment/security docs | 3 (before or with 6.3; used by 6.3, 6.4) |
| 6.3 | Error Handler Node | classify → rollback → handler → increment; retry → agent; FC017 = retry_count | 4 |
| 6.4 | Save-Results Node | Branch condition; archive dir; ERROR_REPORT schema; failure leaves session | 5 |

**Total story points (approximate):** 6.1 ~15 SP, 6.2 ~25 SP, 6.3 ~27 SP, 6.4 ~19 SP, 6.5 ~21 SP → ~107 SP (sprint planning to split as needed).
