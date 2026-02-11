# Epic 6: Error Handling, Resilience & Operations — Technical Review

**Reviewer role:** Senior Software Architect / Agile Team Lead  
**Scope:** Technical deep-dive audit of decomposed stories; data models, APIs, feasibility, security, MECE, DoD.  
**Context:** Parent Epic 6, ARCHITECTURE.md (Agentic Document Generator), Epic 4 (rollback), Epic 5 (conversion/quality failure state).

---

## Parent Epic Technical Context

### Architecture Assumptions

- **Error-handling subgraph (ARCHITECTURE §3.1):** Flow is **convert_docx** (fail) or **quality_check** (fail) → **ErrorClass** → Syntax/Encoding/Asset/Structural handlers → **Rollback** → Retry or End. Diagram shows Handlers → Rollback → Retry; story 6.3 specifies **rollback first, then handler** (restore checkpoint, then apply fix to restored file) — implementation order must be rollback → handler to avoid applying fixes on top of bad state.
- **Tech stack:** Python 3.13, uv; LangGraph state; no DB; session files only. Error handling is in-process (classifier + handlers + nodes); no external queues or caches. Observability is file-based JSONL per session (FC015).
- **State contract (ARCHITECTURE §5.1):** DocumentState includes `conversion_attempts`, `last_error`, `error_type`, `retry_count`, `status`. Epic 6 stories use **retry_count** as the single FC017 counter (max 3); **conversion_attempts** in ARCHITECTURE is also incremented on conversion failure — clarify **single source of truth** (recommend retry_count only for routing/DoD, and document conversion_attempts as optional audit/logging).
- **Epic 4 contract:** Epic 4.4 provides **restore_from_checkpoint(session_id, checkpoint_id) -> bool** in a shared module (e.g. `utils/checkpoint.py`). Path validation (basename only, no traversal). Epic 6 error_handler node calls it **before** invoking handlers when retrying. Missing checkpoint → skip rollback, log, still run handler on current temp_output.md.
- **Epic 5 handshake:** convert_docx sets `conversion_success=False`, `last_error=stderr`, increments conversion_attempts; quality_check sets `quality_passed=False`, `last_error=issues`. Both route to **error_handler**. Parse failure (no structure.json) also sets conversion_success=False and last_error; convert_docx short-circuits to error_handler. So **last_error** can be from markdownlint (validation), parse, docx-js subprocess, or quality validator — classifier must handle all formats.
- **Session layout:** Session dir = SessionManager.get_path(session_id); contains temp_output.md, checkpoints/, logs/, structure.json, output.docx, assets/. Handlers and save_results use SessionManager; no hardcoded "./docs/sessions/".

### Relevant ARCHITECTURE References

- **§4.8:** ErrorClassifier keyword rules; ErrorType enum; handler classes (Syntax, Encoding, Asset, Structural). ARCHITECTURE uses **class ErrorClassifier** with @staticmethod classify; stories say "module or equivalent" — align on class or module.
- **§4.8 Handler code:** Uses hardcoded `Path(f"./docs/sessions/{session_id}/temp_output.md")` — stories correctly require SessionManager.get_path(session_id); ARCHITECTURE should be updated to use session_path from SessionManager.
- **§5.3 error_handler_node:** ARCHITECTURE snippet does **not** call rollback; it only classifies, runs handler, increments retry_count. Stories 6.3 and Epic 4.4 require **rollback then handler**. Add rollback step to ARCHITECTURE §5.3.
- **§5.3 save_results_node:** Branches on `state["status"] == "failed" or state["retry_count"] >= 3`. When coming from quality_check (pass), status may be "complete" or "quality_checking" and retry_count < 3 → success. When coming from error_handler (fail), retry_count >= 3 → failure. **Entry condition:** save_results is reached from (a) quality_check → pass, (b) error_handler → fail. So branching must not rely on status alone (quality_check may not set status to "complete" before save_results). Recommend: **primary** branch = retry_count >= MAX_RETRY_ATTEMPTS → failure path; else if we have output_docx_path and quality_passed → success path; else failure (defensive).
- **§4.10 StructuredLogger:** session.jsonl; log_event, log_state_transition, log_tool_call, log_error. ARCHITECTURE does not show LOG_LEVEL from env; stories 6.5 add it.

### Dependencies Summary

| Dependency | Provider | Consumer | Contract |
|------------|----------|----------|----------|
| restore_from_checkpoint(session_id, checkpoint_id) -> bool | Epic 4.4 | Epic 6.3 error_handler | Path-validated; copies checkpoints/{id} → temp_output.md |
| last_error, conversion_success, quality_passed | Epic 5 | Epic 6.3, 6.4 | Set by convert_docx, parse node, quality_check |
| last_checkpoint_id | Epic 4 (checkpoint node / tools) | Epic 6.3 | Basename of last checkpoint file |
| SessionManager.get_path(session_id) | Epic 1 | Epic 6.2, 6.4, 6.5 | Session root path |
| DocumentState (retry_count, error_type, status) | ARCHITECTURE §5.1 | All Epic 6 stories | TypedDict; ensure error_metadata optional key if used |

---

## Story-by-Story Technical Audit

---

### Story 6.1: Error Classifier — Parse Error Message/Location, Return Type + Metadata; Wire Into Error Handler Node

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | Clear contract; metadata schema and keyword order need formalization. |
| Data Model | Needs Design Work | ErrorMetadata schema (TypedDict) not fully specified; optional fields (context, source) and normalization rules. |
| API/Integration | N/A | Pure function; consumed by error_handler node (Story 6.3). |
| Technical Feasibility | Sound | Keyword matching and regex are straightforward; docx-js/markdownlint stderr formats may vary. |
| Vertical Slice | Sound | Input (string) → output (type + metadata); no I/O. |
| Security/Compliance | Sound | No PII in classifier; message is already server-side. Truncate message in metadata if logged (e.g. max length). |
| Dependencies & Risks | Low | None; 6.3 depends on this. |
| MECE | Sound | Single responsibility; no overlap with handlers. |
| DoD Technical | Needs Design Work | Keyword evaluation order and ambiguous-message tests. |

#### Strengths

- Pure, stateless classifier; easy to unit test and reuse.
- ErrorType enum and metadata (line_number, message, timestamp) align with ARCHITECTURE §4.8 and FC013.
- Contract for error_handler node (state["last_error"] → type + metadata) is explicit.
- Risk of keyword overlap (e.g. "table") is acknowledged; evaluation order will resolve.

#### Critical Gaps (Data Model, APIs, Infra)

1. **ErrorMetadata schema:** Stories say "metadata schema (line_number, message, timestamp; optional context, source)" but no TypedDict or dataclass. Define **ErrorMetadata** (TypedDict total=False for optional) so error_handler and logging use the same shape; document in state or shared types.
2. **Keyword evaluation order:** "Table" can be Syntax (malformed table) or Structural (table of contents / heading). Recommend: **Syntax first** (unclosed, malformed, table, fence), then Encoding, Asset, Structural, Unknown. Add explicit table in DoD: order and keywords per type.
3. **Error message sources:** last_error can be (a) markdownlint JSON string or CLI stderr, (b) docx-js stderr, (c) parse error "Parse error: ...", (d) quality_check issues list. Classifier should handle multi-line and JSON-embedded messages; consider normalizing to single line or first line for keyword match, and document behavior for each source.
4. **Message length in metadata:** If message is very long (e.g. full stderr), storing in state and logs could be heavy. Add max length (e.g. 2000 chars) in metadata and document.

#### Proposed Technical Designs

**1. ErrorMetadata TypedDict**

```python
# error_handlers/types.py or classifier.py
from typing import TypedDict
from datetime import datetime

class ErrorMetadata(TypedDict, total=False):
    line_number: int | None
    message: str       # required; consider truncate to 2000
    timestamp: str     # ISO8601
    context: str       # optional snippet
    source: str        # optional: "markdownlint" | "docx-js" | "parse" | "quality"
```

**2. Classification order (canonical)**

| Order | Type       | Keywords / patterns (lowercased) |
|-------|------------|----------------------------------|
| 1     | Syntax     | unclosed, malformed, table, fence, code block |
| 2     | Encoding   | encoding, utf-8, decode, unicode |
| 3     | Asset      | image, file not found, asset, missing, enoent |
| 4     | Structural | heading, hierarchy, level, skip |
| 5     | Unknown    | (default) |

**3. Line-number extraction (multiple patterns)**

- `line (\d+)`, `line: (\d+)`, `at line (\d+)`, `:(\d+):` (common in linters). Use single regex or ordered list; first match wins.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 10 | Define ErrorMetadata TypedDict and use in classify return type | Dev | 0.5 SP | Export from error_handlers; document optional fields. |
| 11 | Document keyword evaluation order and add test for ambiguous "table" message | Dev/QA | 1 SP | Order: Syntax → Encoding → Asset → Structural → Unknown; fixture "table alignment" → Syntax. |
| 12 | Normalize long message in metadata (truncate to 2000 chars); document | Dev | 0.5 SP | metadata["message"] = message[:2000] if len(message) > 2000 else message. |
| 13 | Document expected last_error sources (markdownlint, docx-js, parse, quality) and test with sample stderr from each | Dev/QA | 1 SP | Fixtures per source; assert correct type. |

#### Revised Story (Technical Specs)

- **DoD addition:** ErrorMetadata TypedDict defined and used; keyword evaluation order documented and tested; message truncation (2000 chars) in metadata; classifier handles markdownlint, docx-js, parse, and quality_check error formats (document or test).
- **Contract:** classify(error_msg: str) -> Tuple[ErrorType, ErrorMetadata]; error_handler node (6.3) calls with state["last_error"] and uses type for routing and metadata for handler args (line_number) and logging.

---

### Story 6.2: Specialized Handlers — Syntax, Encoding, Asset, Structural; Each Updates Session Files

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Good coverage; handler interface, AssetHandler image path from classifier, and structure.json handling need design. |
| Data Model | Needs Design Work | Handler signature: session_id + optional metadata (line_number, image_path); no shared HandlerResult type. structure.json not in scope for handlers (only temp_output.md) — confirm. |
| API/Integration | Sound | Handlers are called by error_handler with (session_id, metadata); no HTTP. |
| Technical Feasibility | Sound | File read/write and regex/string ops; StructuralHandler heading logic is well specified. |
| Vertical Slice | Sound | session_id + optional args → file update → outcome string. |
| Security/Compliance | Needs Design Work | Path validation and session_id validation; image_name_or_path from metadata could be user-controlled (from error message) — must sanitize. |
| Dependencies & Risks | Low | Epic 1 SessionManager; 6.3 calls handlers. |
| MECE | Sound | Four handlers; no overlap. AssetHandler vs StructuralHandler boundaries clear. |
| DoD Technical | Needs Design Work | Idempotency and failure behavior (handler raises vs returns error string). |

#### Strengths

- Four handlers map 1:1 to FC013 types; each updates session files via SessionManager paths.
- FC005 (granular fix) reflected in optional line_number for Syntax and Asset.
- Path resolution and path traversal rejection are tasked.
- Idempotency (encoding, hierarchy) is called out.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Handler signature and metadata passing:** Error_handler has **error_type** and **metadata** (from classifier). AssetHandler needs **image path or name** — metadata may have no explicit "image_path"; classifier does not extract image path from message. Options: (a) classifier adds optional **image_path** to metadata when Asset type (regex for path in message), or (b) error_handler passes last_error snippet to AssetHandler and handler parses. Recommend: **classifier** extracts optional **asset_ref** (filename or path) from message when type is Asset; add to ErrorMetadata; error_handler passes metadata["asset_ref"] to AssetHandler.insert_placeholder(session_id, metadata.get("asset_ref") or "unknown_asset").
2. **Handler return type and failure:** Handlers return "outcome string". If a handler fails (e.g. file not found, permission), should it **raise** or return an error string (e.g. "Fix failed: ...")? Recommend: **return** outcome string; on exception catch and return "Fix failed: <reason>" so error_handler can log and still increment retry and route. Document in handler contract.
3. **AssetHandler placeholder pattern:** "Replace ![](path) or ![alt](path)" — path may be relative, absolute, or filename. Multiple missing images: replace all or first? Recommend: replace **all** matches for the given image_name_or_path (or all missing images if asset_ref not provided — then scan content for image syntax and replace those not present in assets/). Document behavior.
4. **StructuralHandler H1 handling:** "prev_level = 0" — first heading can be H1 (level 1) or H2. If first heading is ##, prev_level becomes 2; next # would become level 1 (correct). If first is #, prev_level=1. Ensure no skip (level > prev_level+1) and no negative level. Edge case: document only #–### (no ####) or allow any level.
5. **SessionManager dependency:** Handlers must receive **session_path: Path** or **session_id: str**. If session_id, each handler calls SessionManager.get_path(session_id). If session dir does not exist, fail fast with clear error (don't create dir in handlers). Document precondition: session exists.

#### Proposed Technical Designs

**1. Handler contract (shared)**

- Signature: `(session_id: str, **kwargs) -> str`. kwargs from error_handler: line_number (Syntax), asset_ref (Asset), etc. Return: human-readable outcome; on exception return "Fix failed: {exception}".
- Precondition: SessionManager.get_path(session_id) exists and is a directory.
- Paths: temp_output_path = session_path / "temp_output.md"; resolve via SessionManager only.

**2. Asset ref from classifier (Story 6.1 extension)**

- When ErrorType is ASSET, try to extract filename or path from message (e.g. regex `(?:file not found|missing|enoent).*?[/\\]([\w.-]+)` or `path ['"]?([^'"]+)['"]?`). Set metadata["asset_ref"] = extracted string or None. Error_handler passes to AssetHandler.insert_placeholder(session_id, metadata.get("asset_ref") or "unknown_asset").

**3. AssetHandler replace-all**

- If asset_ref provided: replace all occurrences of `![...](<path containing asset_ref>)` with placeholder. If not provided: optionally scan for all image syntax and check existence in assets/; replace missing. Document "replace all" in DoD.

**4. StructuralHandler level bounds**

- Clamp heading level to 1..6 (or 1..3 per FC002). prev_level in range 0..6; level = min(level, prev_level + 1) and level = max(1, level).

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 11 | Define handler contract: return outcome string; on exception return "Fix failed: ..." | Dev | 0.5 SP | Document in error_handlers package; no raise to error_handler. |
| 12 | AssetHandler: accept optional asset_ref from metadata; replace all image refs matching asset_ref | Dev | 1 SP | If no asset_ref, use "unknown_asset" or scan for broken refs. |
| 13 | Classifier (6.1): add optional asset_ref to metadata when type Asset (regex on message) | Dev | 1 SP | Coordinate with 6.1; pass to AssetHandler in 6.3. |
| 14 | StructuralHandler: clamp heading level to 1..3 (or 1..6); document | Dev | 0.5 SP | Prevent level < 1 or > 3. |
| 15 | Assert session dir exists at handler start; do not create; return "Fix failed: session not found" if missing | Dev | 0.5 SP | SessionManager.get_path; path.exists(). |

#### Revised Story (Technical Specs)

- **DoD addition:** Handler contract: return outcome string only; exceptions caught and returned as "Fix failed: ...". AssetHandler uses asset_ref from metadata (from classifier when type Asset). StructuralHandler clamps heading level to 1..3. Session existence asserted at handler start.
- **Contract:** Handlers (session_id, **kwargs) -> str; error_handler passes session_id and metadata (line_number, asset_ref); all paths via SessionManager.get_path(session_id).

---

### Story 6.3: Error Handler Node — Classify → Invoke Handler → Rollback (Epic 4) → Increment Retry; Conditional Edge Retry vs Fail

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Flow and state are clear; rollback vs fix order, re-entry point, and Logger dependency need specification. |
| Data Model | Needs Design Work | State keys: retry_count vs conversion_attempts; error_metadata in state for save_results; optional handler_outcome. |
| API/Integration | Sound | Node is state-in/state-out; conditional edge to agent vs save_results. |
| Technical Feasibility | Sound | Depends on 6.1, 6.2, Epic 4; Logger (6.5) may be needed — document "logger optional or stub" for ordering. |
| Vertical Slice | Sound | End-to-end from state (last_error, retry_count) to updated state and route. |
| Security/Compliance | Sound | No new auth; state already server-side. |
| Dependencies & Risks | Medium | Epic 4 restore_from_checkpoint must exist; 6.5 Logger used — implement 6.5 before or stub. |
| MECE | Sound | Single error_handler node; no duplicate rollback logic. |
| DoD Technical | Needs Design Work | Order of ops (rollback then handler) and re-entry (agent vs parse_to_json) must be explicit. |

#### Strengths

- Order of operations (rollback first, then handler) is correct and avoids applying fix on corrupted state.
- Conditional edge should_retry_conversion and MAX_RETRY_ATTEMPTS=3 match FC017.
- Rollback skip when last_checkpoint_id missing is documented.
- Unit and integration tests for routing and rollback are included.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Order of operations vs ARCHITECTURE diagram:** ARCHITECTURE §3.1 shows ErrorClass → Handlers → Rollback → Retry. Stories say **Rollback → Handler**. Implement: (1) Classify, (2) **Restore from checkpoint** if last_checkpoint_id present, (3) Invoke handler, (4) Increment retry_count, (5) Return state. Update ARCHITECTURE diagram or note in §5.3.
2. **Re-entry point:** Story says "document exact re-entry point (e.g. agent vs parse_to_json)". ARCHITECTURE §5.2 shows "retry" → "agent". Going to **agent** re-runs content generation from current state; going to **parse_to_json** would re-parse and re-convert without agent. Recommendation: **agent** — so that after fix we re-validate (validate_md) and then potentially parse_to_json → convert_docx. So retry → agent is correct. Document: "Retry re-enters at agent; agent may then complete and trigger parse_to_json → convert_docx again."
3. **Logger availability:** error_handler uses StructuredLogger(session_id). If Story 6.5 is not done, node will fail or need a no-op logger. Add task: "Use get_logger(session_id) or StructuredLogger(session_id); if 6.5 not implemented, use no-op logger or module-level fallback so node runs."
4. **State keys for save_results:** save_results needs error_type, retry_count, last_error for ERROR_REPORT.txt. Error_handler already sets error_type and retry_count. Ensure last_error is kept (not cleared). Optional: add **error_metadata** or **handler_outcome** to state for ERROR_REPORT if product wants "what fix was attempted".
5. **Unknown type:** For Unknown, node does not run a handler. It still must **increment retry_count** and then route (retry or fail). Otherwise Unknown errors would never increment retry and we could loop. Document: "For Unknown, skip handler invocation but still increment retry_count and route as usual."
6. **conversion_attempts vs retry_count:** ARCHITECTURE convert_docx increments conversion_attempts on failure; error_handler increments retry_count. For FC017 "max 3 conversion attempts", the gate is retry_count >= 3. So conversion_attempts can remain for logging; should_retry_conversion uses only retry_count. Document in DoD: "FC017 is enforced by retry_count; conversion_attempts is informational."

#### Proposed Technical Designs

**1. Error handler node algorithm (canonical)**

```
1. logger = get_logger(state["session_id"])  # or StructuredLogger; no-op if 6.5 not done
2. logger.log_state_transition(state["status"], "error_handling")
3. error_type, metadata = ErrorClassifier.classify(state["last_error"])
4. logger.log_event("error_classified", type=error_type.value, **metadata)
5. if last_checkpoint_id present and valid:
6.     restore_from_checkpoint(session_id, last_checkpoint_id)
7.     if not restored: log rollback_skipped
8. if error_type in (SYNTAX, ENCODING, ASSET, STRUCTURAL):
9.     outcome = invoke_handler(error_type, session_id, metadata)
10. else:
11.    outcome = "Unknown error - no fix applied"
12. logger.log_event("error_fix_attempted", result=outcome)
13. retry_count = state["retry_count"] + 1
14. return { ...state, error_type=error_type.value, retry_count=retry_count, ... }
15. (conditional edge) should_retry_conversion(state) -> "retry" | "fail"
```

**2. Re-entry**

- "retry" → **agent**. Rationale: Fix was applied to temp_output.md; we need agent to potentially continue or at least flow through tools → validate_md → checkpoint → ... → parse_to_json → convert_docx. So agent is the right re-entry.

**3. State output**

- error_type (str), retry_count (int), last_error (unchanged), optional handler_outcome (str) for logging. Do not clear last_error so save_results can write ERROR_REPORT.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 14 | Implement rollback-before-handler order; call restore_from_checkpoint then invoke handler | Dev | 1 SP | Already in AC; ensure code order matches. |
| 15 | For Unknown type: do not invoke handler; still increment retry_count and log | Dev | 0.5 SP | Avoid infinite loop; document in DoD. |
| 16 | Document re-entry: retry → agent; update ARCHITECTURE §5.2 if needed | Dev | 0.5 SP | DoD and ARCHITECTURE. |
| 17 | get_logger(session_id) or no-op fallback when 6.5 not implemented | Dev | 0.5 SP | So 6.3 can be tested before 6.5. |
| 18 | Document: FC017 enforced by retry_count only; conversion_attempts informational | Dev | 0.5 SP | DoD. |

#### Revised Story (Technical Specs)

- **DoD addition:** Order: classify → restore_from_checkpoint (if checkpoint) → invoke handler (or skip for Unknown) → increment retry_count. Unknown: no handler, still increment retry_count. Re-entry = agent. Logger fallback when 6.5 not done. FC017 = retry_count only.
- **Contract:** Node expects last_error, retry_count, last_checkpoint_id, session_id; outputs error_type, retry_count; calls Epic 4 restore_from_checkpoint(session_id, last_checkpoint_id) before handler.

---

### Story 6.4: Save-Results Node — On Success Archive Session; On Failure Write FAILED_conversion.md + ERROR_REPORT.txt and Set Status

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | Clear success/failure paths; branching condition and archive precondition need tightening. |
| Data Model | Needs Design Work | Branching logic: success vs failure must be unambiguous given two entry points (quality_check, error_handler). ERROR_REPORT schema (fields) not formalized. |
| API/Integration | Sound | Node state-in/state-out; single exit to END. |
| Technical Feasibility | Sound | File copy and write; SessionManager.cleanup(archive=True). |
| Vertical Slice | Sound | State → branch → archive or write files → status. |
| Security/Compliance | Sound | No content in ERROR_REPORT beyond error message (truncate if needed); session_id is UUID. |
| Dependencies & Risks | Low | Epic 1 cleanup; 6.3 sets retry_count and status. |
| MECE | Sound | Single save_results node; no duplicate finalization. |
| DoD Technical | Needs Design Work | Branch condition and archive dir creation. |

#### Strengths

- Success = archive + status complete; failure = FAILED_conversion.md + ERROR_REPORT.txt + status failed.
- File names and encoding (UTF-8) are specified.
- Edge case (no temp_output.md) is tasked.
- Unit tests for both paths.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Branch condition:** Node is entered from (a) quality_check (pass) and (b) error_handler (fail). When from quality_check, retry_count may be 0 or 1; status may be "quality_checking" or "complete". When from error_handler (fail), retry_count >= 3. So **failure path** = retry_count >= MAX_RETRY_ATTEMPTS (primary). **Success path** = not failure. But what if save_results is somehow invoked with retry_count=2 and status="error_handling"? That should not happen if graph is correct; defensively treat retry_count >= 3 as failure. Add: "Success = (retry_count < MAX_RETRY_ATTEMPTS) and (status != 'failed'); Failure = (retry_count >= MAX_RETRY_ATTEMPTS) or (status == 'failed')." And ensure quality_check path sets status to "complete" before or in save_results on success path.
2. **Archive directory:** SessionManager.cleanup(session_id, archive=True) moves to docs/archive/{session_id}. If docs/archive does not exist, cleanup may fail. Epic 1 or this story: ensure archive dir exists (create in SessionManager.cleanup or at startup). Add task: "Ensure archive parent dir exists before move (create if missing)."
3. **ERROR_REPORT format:** Propose a minimal schema: Session ID, Timestamp (ISO8601), Retry Count, Last Error (truncated e.g. 1000 chars), Error Type, Guidance (static or template). No PII. Document in DoD.
4. **Success path output_docx_path:** Stories say "Optional: copy or expose output_docx_path in state/message for caller." If main.py or API returns result to user, state["output_docx_path"] should be set or preserved so caller can return it. After archive, path may be docs/archive/{session_id}/output.docx — document so caller knows where to find the file.
5. **Failure path: session not deleted:** AC says "Do not delete session so user can inspect." So on failure we do **not** call cleanup(archive=True); we leave session in place. Confirm: success = move to archive; failure = leave in sessions/{id}. Document.

#### Proposed Technical Designs

**1. Branch condition (canonical)**

```python
def _is_failure_path(state: DocumentState) -> bool:
    return state.get("retry_count", 0) >= MAX_RETRY_ATTEMPTS or state.get("status") == "failed"
# Success = not _is_failure_path(state)
```

**2. ERROR_REPORT.txt schema (fields)**

- session_id (UUID)
- timestamp (ISO8601, now)
- retry_count (int)
- last_error (str, truncated 1000 chars)
- error_type (str)
- guidance (multi-line static text per AC6.4.3)

**3. Archive and success path**

- Before cleanup: ensure Path("docs/archive").exists() or create; then SessionManager.cleanup(session_id, archive=True). On success, set state["status"] = "complete" and state["output_docx_path"] = str(archive_path / session_id / "output.docx") if caller needs it, or document that output is under docs/archive/{session_id}/output.docx.

**4. Failure path**

- Do not call cleanup. Write FAILED_conversion.md (copy temp_output or placeholder), ERROR_REPORT.txt, set status="failed". Session remains under docs/sessions/{session_id}.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 12 | Define branch condition: failure = (retry_count >= MAX_RETRY_ATTEMPTS) or (status == "failed") | Dev | 0.5 SP | Single helper or inline; document. |
| 13 | Ensure archive dir exists before cleanup (create docs/archive if missing) | Dev | 0.5 SP | In SessionManager.cleanup or at node start. |
| 14 | Document ERROR_REPORT fields: session_id, timestamp, retry_count, last_error (trunc 1000), error_type, guidance | Dev | 0.5 SP | DoD. |
| 15 | On success, set or preserve output_docx_path for caller (archive path) | Dev | 0.5 SP | Document path after archive. |
| 16 | Document: failure path does not delete or archive session; session stays for inspection | Dev | 0.5 SP | DoD. |

#### Revised Story (Technical Specs)

- **DoD addition:** Branch condition uses retry_count >= MAX_RETRY_ATTEMPTS or status == "failed" for failure. Archive parent dir created if missing. ERROR_REPORT schema documented; last_error truncated (1000 chars). Success path preserves or sets output_docx_path (archive path). Failure path leaves session in place.
- **Contract:** save_results is the single exit node; state["status"] is "complete" or "failed"; success = archive session; failure = write FAILED_conversion.md and ERROR_REPORT.txt in session dir.

---

### Story 6.5: Structured Logger (FC015) — Session-Scoped JSONL Logs; Config (Env), Deployment Checklist, Security Notes

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | Logger design and security are clear; logger injection pattern and JSONL robustness need specification. |
| Data Model | Needs Design Work | Log line schema (required vs optional fields); event_type enum or allowlist. |
| API/Integration | Sound | Logger created per session; nodes get it via session_id (get_logger or state). |
| Technical Feasibility | Sound | FileHandler + JSON line; LOG_LEVEL from env. |
| Vertical Slice | Sound | Session → logs/session.jsonl; config from env. |
| Security/Compliance | Needs Design Work | No content in logs: args sanitization and result truncation; explicit allowlist for tool_call args. |
| Dependencies & Risks | Low | Epic 1 session layout; other nodes adopt incrementally. |
| MECE | Sound | Single logger component; deployment/security are cross-cutting docs. |
| DoD Technical | Needs Design Work | Logger injection (state vs global registry); JSONL write atomicity and rotation. |

#### Strengths

- Session-scoped JSONL matches FC015 and ARCHITECTURE §4.10.
- log_event, log_state_transition, log_tool_call, log_error cover state transitions, tool calls, errors.
- No document content or PII is required; truncation and sanitization are tasked.
- Deployment checklist and security notes in ARCHITECTURE.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Logger injection:** "Create logger, store in state or create per-node from session_id". If stored in state, DocumentState must have optional **logger** or **session_id** (and nodes create logger from session_id). LangGraph state is often serializable; logger instance is not. So **do not store logger in state**; use **get_logger(session_id)** that returns a logger for that session (singleton per session or create each time). Document: "Nodes call get_logger(state['session_id']); logger is not stored in state."
2. **Log line schema:** Every line is JSON. Required keys: timestamp, session_id, event_type. Optional: event-specific. Document that unknown kwargs in log_event are included (sanitized); avoid logging arbitrary user input. Consider allowlist of event_type values for analytics.
3. **Args sanitization for tool_call:** "args as keys only or safe summary" — define safe: no file content, no long strings. Log tool name and arg **names** only, or arg names + type (e.g. "filename: str"). Result truncated to 200 chars. Document in DoD.
4. **JSONL robustness:** If write fails mid-line, file could be corrupted. Option: write to temp and rename, or append with newline and flush. For simplicity, append one line + newline and flush after each write. No rotation in scope; document "no log rotation; session logs bounded by session lifecycle."
5. **LOG_PATH:** Story says "optional LOG_PATH". If LOG_PATH is set, does it override session dir? Or is it a base dir? Recommend: default = session_path / "logs" / "session.jsonl"; LOG_PATH if set could be a base (e.g. /var/log/doc-creator) and then {LOG_PATH}/{session_id}.jsonl — or ignore LOG_PATH for session-scoped and use only LOG_LEVEL. Document clearly.

#### Proposed Technical Designs

**1. get_logger(session_id) pattern**

```python
# utils/logger.py
_loggers: dict[str, StructuredLogger] = {}

def get_logger(session_id: str) -> StructuredLogger:
    if session_id not in _loggers:
        _loggers[session_id] = StructuredLogger(session_id)
    return _loggers[session_id]
```

- Session created in initialize_node; first node that needs logger calls get_logger(session_id). Logger not in state.

**2. Log line required fields**

- timestamp (str, ISO8601), session_id (str), event_type (str). All other fields optional. event_type one of: state_transition, tool_call, error, session_created, validation_ran, conversion_started, checkpoint_saved, error_classified, error_fix_attempted, session_completed, session_failed (allowlist in doc).

**3. tool_call sanitization**

- args: log only keys, or keys + type (e.g. {"filename": "<str>", "lines": "<int>"}). Never log args that might contain content. result: str(result)[:200]. Document: "Tool args: keys only or type-only values; result truncated 200 chars."

**4. LOG_LEVEL only (simplify)**

- LOG_LEVEL=INFO|DEBUG|WARNING|ERROR; applied to handler. Omit LOG_PATH for v1; always write to session_path/logs/session.jsonl. Document in config.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 13 | Implement get_logger(session_id); do not store logger in state | Dev | 1 SP | Module-level registry or create each time; document. |
| 14 | Document log line required fields and event_type allowlist | Dev | 0.5 SP | DoD or utils/logger.py. |
| 15 | Sanitize tool_call args: log keys only or type-only; never content | Dev | 1 SP | Implement in log_tool_call. |
| 16 | Write each log line with newline and flush; document no rotation | Dev | 0.5 SP | Bounded by session. |
| 17 | Document LOG_LEVEL only; log path always session_path/logs/session.jsonl | Dev | 0.5 SP | Config doc. |

#### Revised Story (Technical Specs)

- **DoD addition:** get_logger(session_id) pattern; logger not in state. Log line schema (timestamp, session_id, event_type) and event_type allowlist. tool_call: args keys or type-only; result 200 chars. Flush after each line; no rotation. LOG_LEVEL from env; path = session_path/logs/session.jsonl.
- **Contract:** Nodes call get_logger(state["session_id"]) for FC015 logging; no document content or PII in any log line.

---

## Overall Technical Roadmap

### Missing Foundational Work

1. **DocumentState schema (ARCHITECTURE §5.1):** Add **validation_passed**, **validation_issues** (Epic 4); confirm **error_type**, **retry_count**, **last_error**; add optional **error_metadata** or **handler_outcome** if product needs. Decide **conversion_attempts** vs **retry_count** (recommend retry_count for FC017 gate; conversion_attempts optional for audit).
2. **Epic 4 / Epic 6 rollback contract:** Epic 4.4 must deliver **restore_from_checkpoint(session_id, checkpoint_id) -> bool** in a shared module before or in parallel with Epic 6.3. Document in both epics.
3. **Logger ordering:** Story 6.5 (Structured Logger) should be implemented **before** or in parallel with 6.3; 6.3 can use get_logger with a no-op fallback if 6.5 is not done.

### Schema Proposals (Summary)

| Schema | Location | Purpose |
|--------|----------|---------|
| ErrorMetadata | error_handlers/classifier.py or types.py | TypedDict for classifier return; line_number, message, timestamp, optional context, source, asset_ref |
| ERROR_REPORT (content) | Story 6.4 DoD | session_id, timestamp, retry_count, last_error (trunc 1000), error_type, guidance |
| Log line (JSON) | Story 6.5 DoD | timestamp, session_id, event_type + event-specific; event_type allowlist |

### Architecture Decisions Needed

1. **Error handler flow in ARCHITECTURE §3.1:** Update diagram to "ErrorClass → Rollback (if checkpoint) → Handler → Retry | Fail" so it matches story 6.3 order (rollback then handler).
2. **ARCHITECTURE §5.3 error_handler_node:** Add step: call restore_from_checkpoint(session_id, last_checkpoint_id) before invoking handlers; document missing-checkpoint behavior.
3. **SessionManager.cleanup(archive=True):** Document that archive parent dir (docs/archive) must exist or be created by cleanup.
4. **Single FC017 counter:** Document in ARCHITECTURE that retry_count is the single source for "max 3 attempts"; conversion_attempts is optional/informational.

### Cross-Story Gaps (MECE)

- **6.1 ↔ 6.2:** Classifier should add **asset_ref** to metadata when type=Asset so AssetHandler has a concrete ref (Story 6.1 task 13; Story 6.2 task 12–13).
- **6.3 ↔ 6.5:** Error_handler uses logger; 6.5 provides get_logger. Either implement 6.5 first or add no-op fallback in 6.3 (task 17).
- **6.4 ↔ Epic 5:** Success path output_docx_path: after archive, path is docs/archive/{session_id}/output.docx; Epic 5 and main entry point should document this for API/caller.
- **Epic 4 ↔ 6.3:** restore_from_checkpoint signature and module must be fixed in Epic 4.4; 6.3 depends on it.

### DoD Technical Additions (Epic-Level)

- All error_handlers use SessionManager.get_path(session_id); no hardcoded session paths (align ARCHITECTURE §4.8 code with this).
- Test coverage: unit tests per story; integration test for convert_docx fail → error_handler → retry → success path (full loop).
- Performance: not critical for error path; document that handler file I/O is bounded by session size (e.g. temp_output.md < 100MB).
- Deployment: checklist in ARCHITECTURE §10; env vars (LOG_LEVEL, MAX_RETRY_ATTEMPTS optional); security: no content in logs, sandboxing in §14.

---

**Document Version:** 1.0  
**Last Updated:** 2025-02-11  
**Status:** Technical Review Complete  
**Next Steps:** Prioritize missing tasks in each story; align Epic 4.4 and 6.3 on restore_from_checkpoint; implement 6.5 before or with 6.3 for logger availability.
