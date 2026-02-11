# Epic 5: DOCX Conversion & Output Quality — Technical Review

**Reviewer role:** Senior Software Architect / Agile Team Lead  
**Scope:** Technical deep-dive audit of decomposed stories; data models, APIs, feasibility, security, MECE, DoD.  
**Context:** Parent Epic 5, ARCHITECTURE.md (Agentic Document Generator), Epic 6 (error-handling contract).

---

## Parent Epic Technical Context

### Architecture Assumptions

- **Conversion pipeline (ARCHITECTURE §3.1):** Flow is Agent → (complete) → **MdToJson** → **DocxJs** → **QualityCheck**. No direct MD→DOCX; FC002 requires intermediate structure. Pipeline runs after "generation complete" (route_after_tools returns `"complete"` when all files processed and no pending validation).
- **Tech stack:** Python 3.13, uv; LangGraph state; **Node.js** subprocess for docx generation (docx npm package); **python-docx** for read-only quality checks. No DB; session files only: `temp_output.md` → `structure.json` → `output.docx`.
- **State contract:** DocumentState must include at least: `structure_json_path`, `output_docx_path`, `conversion_success`, `conversion_attempts`, `last_error`, `quality_passed`, `quality_issues` (or `issues`). Status values: `"converting"`, `"quality_checking"`, `"error_handling"`, `"complete"`, `"failed"`.
- **Epic 6 handshake:** On conversion failure or quality failure, flow goes to **error_handler** (Epic 6). Error classifier (FC013) consumes `last_error`; handlers may rollback (Epic 4) and retry. FC017: max 3 conversion attempts; save_results node writes FAILED_conversion.md and ERROR_REPORT.txt on final failure. Epic 5 stories must ensure state keys and routing match what Epic 6 expects.
- **Session layout:** Session dir = `SessionManager.get_path(session_id)`; contains `temp_output.md`, `structure.json`, `output.docx`, `assets/`. Converter runs with **cwd = session dir** so relative image paths in structure.json (e.g. `./assets/fig.png`) resolve.

### Relevant ARCHITECTURE References

- **§4.6:** structure.json schema (metadata + sections with type); image path `./assets/...`; "Resolve image paths to absolute" in algorithm vs "session-relative" in story — **clarify:** resolver produces paths that are valid when cwd = session (so relative is correct).
- **§4.7:** converter.js reads argv[1]/argv[2]; docx Document with Code style; ImageRun from buffer; ARCHITECTURE example uses **Packer.toBuffer(doc).then(...)** (async) but script is written as sync — **implementation must resolve** (top-level await or sync Packer API if available).
- **§4.9:** QualityValidator returns `{ "pass", "issues", "score" }`; story 5.5 uses `quality_passed` in state — **align key:** validator returns `pass`, node maps to state `quality_passed`.
- **§5.2:** Edges: tools → (complete → parse_to_json); parse_to_json → convert_docx; convert_docx → quality_check (success) or error_handler (fail); quality_check → save_results (pass) or error_handler (fail).
- **§5.3 convert_with_docxjs_node:** timeout ARCHITECTURE shows 60s; Epic 5 stories specify 120s — **adopt 120s** per story and document in ARCHITECTURE.

---

## Story-by-Story Technical Audit

---

### Story 5.1: Design and Document JSON Schema for docx-js (Metadata, Section Types, Image Paths)

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | Clear contract; a few schema and validation details need tightening. |
| Data Model | Needs Design Work | Section type discriminator and optional fields not fully specified; no table cell type; no version field. |
| API/Integration | N/A | Schema is contract for 5.2 (parser) and 5.3 (Node); no HTTP API. |
| Technical Feasibility | Sound | JSON Schema draft-07 + markdown spec is standard. |
| Vertical Slice | N/A | Foundational; enables 5.2 and 5.3. |
| Security/Compliance | Sound | Image path rules restrict to session; no PII in schema. |
| Dependencies & Risks | Low | Schema drift risk mitigated by optional runtime validation (task 7). |
| MECE | Sound | Single source of truth for structure; no overlap with 5.2/5.3. |
| DoD Technical | Needs Design Work | No explicit schema versioning or backward-compat policy; validator key names for optional validation. |

#### Strengths

- Explicit section types (heading1–3, paragraph, code_block, table, image) and metadata align with ARCHITECTURE §4.6 and FC002.
- Image path semantics (session-relative, resolution owner) called out; reduces ambiguity for parser and Node.
- Optional runtime validation (task 7) reduces drift between Python output and Node expectations.
- Human-readable spec and machine-readable schema support both implementers and future changes.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Section discriminator and oneOf:** JSON Schema should use `oneOf` + `type` discriminator for sections; document that unknown `type` is ignored or invalid so Node/parser behave consistently. Table cell type not specified (string only?; nested tables out of scope and should be stated).
2. **Version and compatibility:** No `$schema` or `version` / `schemaVersion` field in the root; optional but recommended for future evolution (e.g. adding a new section type). DoD should state versioning approach (e.g. date or semver in spec).
3. **Edge cases in schema:** Empty `sections` array allowed? Required? code_block with empty `code` string; table with empty `headers` or `rows`; image with missing `path` — schema should define minItems/minLength or "optional but recommended" so converter.js can handle without crashing.
4. **Validator key alignment:** If Python uses jsonschema to validate before calling Node, use same key names as Node (e.g. `type`, `path`, `code`); document in spec so 5.2 and 5.3 stay aligned.

#### Proposed Technical Designs

**1. JSON Schema structure (minimal)**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["metadata", "sections"],
  "properties": {
    "metadata": {
      "type": "object",
      "required": ["title", "author", "created"],
      "properties": {
        "title": { "type": "string" },
        "author": { "type": "string" },
        "created": { "type": "string", "format": "date-time" }
      }
    },
    "sections": {
      "type": "array",
      "items": { "$ref": "#/definitions/section" }
    }
  },
  "definitions": {
    "section": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": { "enum": ["heading1", "heading2", "heading3", "paragraph", "code_block", "table", "image"] }
      },
      "oneOf": [
        { "properties": { "type": { "const": "heading1" }, "text": { "type": "string" }, "id": { "type": "string" } }, "required": ["text"] },
        { "properties": { "type": { "const": "heading2" }, "text": {}, "id": {} }, "required": ["text"] },
        { "properties": { "type": { "const": "heading3" }, "text": {}, "id": {} }, "required": ["text"] },
        { "properties": { "type": { "const": "paragraph" }, "text": {}, "formatting": { "type": "array", "items": { "type": "string" } } } },
        { "properties": { "type": { "const": "code_block" }, "language": {}, "code": { "type": "string" } }, "required": ["code"] },
        { "properties": { "type": { "const": "table" }, "headers": { "type": "array", "items": { "type": "string" } }, "rows": { "type": "array", "items": { "type": "array", "items": { "type": "string" } } } }, "required": ["headers", "rows"] },
        { "properties": { "type": { "const": "image" }, "path": { "type": "string" }, "alt": {}, "width": {}, "height": {} }, "required": ["path"] }
      ]
    }
  }
}
```

**2. Image path contract (for spec)**

- **Producer (parser):** Emit paths relative to session root, e.g. `./assets/filename.png`. No `../`; resolve any relative path from MD to session `assets/` and normalize to `./assets/<name>`.
- **Consumer (Node):** Resolve path relative to `process.cwd()`; cwd SHALL be session dir when invoked by Python. If path is absolute, use as-is (Python may inject absolute paths in future).
- **Supported image formats:** Document in spec (e.g. png, jpeg, gif, webp per docx/ImageRun support).

**3. Version field (recommended)**

- Add optional `schemaVersion: "1.0"` or `created` in spec header; parser may set it from Story 5.2; Node may ignore unknown versions or validate.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 8 | Add oneOf/discriminator for section types and document unknown-type behavior | Dev | 1 SP | JSON Schema oneOf per type; spec: "unknown type → skip or invalid". |
| 9 | Define edge cases: empty sections, empty code, empty table rows; minItems where needed | Dev | 0.5 SP | Schema or spec: empty sections allowed; code default ""; table rows length ≥ 0. |
| 10 | Add schema version or $schema and document compatibility policy | Dev | 0.5 SP | version/schemaVersion in spec; "backward-compat: add optional fields only". |

#### Revised Story (Technical Specs)

- **DoD addition:** JSON Schema includes oneOf for section types; edge cases (empty sections/code/table) documented; schema version or date in spec; ARCHITECTURE §4.6 references schema path and image path contract.
- **Contract:** Parser (5.2) and converter (5.3) MUST conform to the schema; unknown section types SHALL be skipped by converter (or invalid); image path format SHALL be session-relative `./assets/...` unless absolute path contract is used.

---

### Story 5.2: Implement MD→JSON Parser; Write structure.json in Session

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Good coverage; state contract, encoding, and security need explicit design. |
| Data Model | Needs Design Work | State keys for parse failure (parse_error vs conversion_success); metadata date format. |
| API/Integration | Sound | Node reads state; writes structure.json; edge from route_after_tools "complete". |
| Technical Feasibility | Sound | mistletoe is mature; table parsing may need custom or extension. |
| Vertical Slice | Sound | Input (state + temp_output.md) → parser → structure.json + state update. |
| Security/Compliance | Needs Design Work | Image path from MD could contain traversal (e.g. `![x](../../etc/passwd)`); must restrict to session. |
| Dependencies & Risks | Low | Epic 4 ensures valid MD; mistletoe may not have native table AST — custom or markdown-it. |
| MECE | Sound | No overlap with 5.1 (schema) or 5.3 (Node); clear boundary. |
| DoD Technical | Needs Design Work | Encoding (UTF-8), order of operations (no partial write), and list/blockquote fallback documented. |

#### Strengths

- Parser output conforms to Story 5.1 schema; structure.json written under session; no partial file on failure.
- All section types (headings, paragraph, code, table, image) and metadata extraction are in scope.
- Parse node integrates into graph and maps errors to state for routing; logging present.
- Unit tests for happy path and failure path.

#### Critical Gaps (Data Model, APIs, Infra)

1. **State keys on parse failure:** Story says "sets a failure state" and "error is mapped to state for routing (e.g. to error_handler)". DocumentState does not yet define **parse_error** or how parse failure is distinguished from conversion failure. Recommendation: set **conversion_success = False** and **last_error** to parse error message (and optionally **error_type** if Epic 6 uses it), and route to **error_handler** so one path handles both parse and conversion failure. Add explicit AC: "On parse failure, set conversion_success=False, last_error=<message>, and do not write structure.json."
2. **Entry condition and state preconditions:** Parse node runs when route_after_tools returns "complete". State MUST have **session_id** and **temp_md_path** (or path derived from session_id). ARCHITECTURE uses temp_md_path; ensure it is set by Epic 2/4 or derived as `SessionManager.get_path(session_id) / "temp_output.md"`. Document precondition in story.
3. **Encoding and read strategy:** temp_output.md SHALL be read as UTF-8; if read fails (e.g. invalid UTF-8), treat as parse failure. DoD should state "read with encoding='utf-8'; on UnicodeDecodeError set parse failure."
4. **Image path security:** Parser resolves image paths from MD to session-relative. If MD contains `![alt](../../etc/passwd)` or absolute path outside session, parser MUST normalize to session assets only (or emit placeholder path and document). Add task: "Validate image path is under session/assets; otherwise use placeholder or skip."
5. **Lists and blockquotes:** Mistletoe produces List/BlockQuote nodes; story says "fallback to paragraph". Define: emit as single paragraph with plain-text content (no nested structure in schema). Add test for list → paragraph.
6. **Metadata created format:** Schema says "created"; use ISO8601 (e.g. datetime.now().isoformat()) for consistency with logging and optional schema format.

#### Proposed Technical Designs

**1. Parse node state contract**

- **Input state:** `session_id` (required), `temp_md_path` (optional; if missing, derive from session_id).
- **Output state (success):** `structure_json_path` = str(session_path / "structure.json"); `status` = "converting" (or leave for convert_docx to set); do not set conversion_success (convert_docx sets it).
- **Output state (failure):** `conversion_success` = False; `last_error` = "Parse error: <reason>"; optionally `error_type` = "structural" or "syntax" for Epic 6; do not set structure_json_path; remove or do not write structure.json if partial write was started (write to temp then rename, or write only after full parse).
- **Routing:** Parse node does not branch; graph edge is parse_to_json → convert_docx. So on parse failure, parse node must still return state with failure flags, and **convert_docx** must short-circuit when structure_json_path is missing or conversion_success is already False — OR add conditional edge from parse_to_json: on failure go to error_handler, on success go to convert_docx. **Recommendation:** Add conditional edge from parse_to_json: if structure_json_path missing or parse_error set → error_handler; else → convert_docx. That requires a dedicated **parse_error** or "structure_json_path present" check; simpler: parse node on failure sets conversion_success=False and last_error, and **convert_docx** checks for existence of structure_json_path and valid file; if missing, skip subprocess and go to error_handling. So convert_docx node: "if not structure_json_path or not Path(structure_json_path).exists(): return state with conversion_success=False, last_error='No structure.json' → edge to error_handler." That way one edge parse_to_json → convert_docx and convert_docx handles missing input.

**2. Safe write (no partial structure.json)**

- Build full structure dict in memory; only after success call `Path(session_path / "structure.json").write_text(json.dumps(structure, indent=2), encoding="utf-8")`. On exception before write, do not write. If write fails (disk full, permission), catch and return failure state.

**3. Image path resolution (security)**

```python
def resolve_image_path(md_path_value: str, session_path: Path) -> str:
    """Resolve to session-relative path under assets/; else placeholder."""
    resolved = (session_path / "assets").resolve()
    candidate = (session_path / md_path_value.replace("\\", "/").lstrip("./")).resolve()
    if not str(candidate).startswith(str(resolved)) and "assets" not in md_path_value:
        return "./assets/placeholder.png"  # or skip section
    return os.path.relpath(candidate, session_path) if candidate.exists() else f"./assets/{Path(md_path_value).name}"
```

(Adjust logic to match "copy to assets" policy; goal: no path traversal.)

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 15 | Define parse failure state (conversion_success=False, last_error); convert_docx short-circuit if no structure.json | Dev | 1 SP | Parse node sets failure state; convert_docx checks structure_json_path exists, else skip and route to error_handler. |
| 16 | Document and implement UTF-8 read; UnicodeDecodeError → parse failure | Dev | 0.5 SP | open(encoding='utf-8'); except UnicodeDecodeError. |
| 17 | Restrict image path to session/assets; path traversal → placeholder or skip | Dev | 1 SP | Normalize path; reject outside session; emit ./assets/placeholder or omit. |
| 18 | Document list/blockquote → paragraph fallback; add test | Dev/QA | 0.5 SP | Spec + test. |
| 19 | Set metadata.created to ISO8601 | Dev | 0.5 SP | datetime.now().isoformat(). |

#### Revised Story (Technical Specs)

- **DoD addition:** Parse failure sets conversion_success=False and last_error; no partial structure.json; convert_docx node short-circuits when structure_json_path missing or file absent (return failure state). UTF-8 read; image path restricted to session. metadata.created = ISO8601.
- **Contract:** parse_md_to_structure(md_path, session_path) → dict; raises or returns; node catches all, maps to state. Output conforms to Story 5.1 schema.

---

### Story 5.3: Implement Node Script (converter.js) Using docx — Headings, Paragraphs, Code, Tables, Images

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Good mapping; async Packer, empty inputs, and JSON failure need resolution. |
| Data Model | Sound | Consumes structure.json per 5.1; no DB. |
| API/Integration | Sound | CLI only; no auth. |
| Technical Feasibility | Needs Design Work | docx Packer.toBuffer is async; script must use async/await or sync equivalent. |
| Vertical Slice | Sound | JSON in → DOCX out. |
| Security/Compliance | Sound | Paths from argv; image read under cwd (session). |
| Dependencies & Risks | Low | Pin docx version; document Node LTS version. |
| MECE | Sound | Clear boundary with 5.2 and 5.4. |
| DoD Technical | Needs Design Work | Empty sections/code/table handling; JSON parse failure exit code. |

#### Strengths

- All section types mapped to docx elements; Code style and image path resolution documented.
- Determinism and no hardcoded paths; image load failure → stderr and exit 1.
- Tests for all types and missing image.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Packer.toBuffer is async:** ARCHITECTURE §4.7 shows `Packer.toBuffer(doc).then(buffer => {...}).catch(...)`. If script is invoked as `node converter.js`, we need either top-level await (Node 18+) or wrap in async IIFE and .catch. Add task: "Use async entry (top-level await or async main) and await Packer.toBuffer; write synchronously after await."
2. **JSON parse failure:** If structure.json is malformed, JSON.parse throws. Script must try/catch, stderr message, exit 1. Add task.
3. **Empty or missing sections:** sections = [] or missing → document with no body (or title only). code_block with code "" → single empty Code paragraph or skip. Table with rows = [] → header row only or skip. Define in DoD and implement.
4. **Style name contract with QualityValidator:** Converter uses paragraph style id "Code"; QualityValidator (5.5) checks style.name == "Code". python-docx typically exposes style id; ensure validator checks by id or name consistently. Document "Code" as the canonical id/name.
5. **Node and docx version:** Pin in package.json (e.g. "docx": "^8.x" or exact); document required Node version (e.g. 18 LTS) for top-level await.

#### Proposed Technical Designs

**1. Async script structure**

```javascript
// converter.js - Node 18+ for top-level await
const fs = require('fs');
const path = require('path');
const { Document, Packer, ... } = require('docx');

async function main() {
  const jsonPath = process.argv[2];
  const docxPath = process.argv[3];
  if (!jsonPath || !docxPath) {
    console.error('Usage: node converter.js <jsonPath> <docxPath>');
    process.exit(1);
  }
  let structure;
  try {
    structure = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));
  } catch (e) {
    console.error('Invalid JSON:', e.message);
    process.exit(1);
  }
  const sections = structure.sections || [];
  // ... build doc ...
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(docxPath, buffer);
  console.log('Document created successfully');
}
main().catch(err => {
  console.error(err);
  process.exit(1);
});
```

**2. Empty inputs**

- sections.length === 0: build Document with single empty paragraph or metadata only.
- code_block with code "": emit one Code paragraph with "" or skip (recommend one empty line for consistency).
- table with rows []: emit table with header row only (headers from section.headers).

**3. Image path resolution**

- If section.path is relative, resolve with path.resolve(process.cwd(), section.path). If absolute, use as-is. On fs.readFileSync throw (e.g. ENOENT), log to stderr and process.exit(1).

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 14 | Use async entry and await Packer.toBuffer; handle rejections | Dev | 1 SP | Top-level await or async main(); exit 1 on catch. |
| 15 | JSON parse try/catch; stderr + exit 1 on invalid JSON | Dev | 0.5 SP | try/catch around JSON.parse. |
| 16 | Handle empty sections, empty code, empty table rows per DoD | Dev | 1 SP | sections=[] → minimal doc; code="" → one empty Code para; rows=[] → header only. |
| 17 | Pin docx version in package.json; document Node 18+ requirement | Dev | 0.5 SP | package.json engines or README. |

#### Revised Story (Technical Specs)

- **DoD addition:** Script uses async and await Packer.toBuffer; JSON parse failure and image load failure exit 1 with stderr. Empty sections/code/table behavior documented and implemented. Style id "Code" documented for QualityValidator alignment. docx version pinned; Node 18+ documented.
- **Contract:** `node converter.js <jsonPath> <docxPath>`; cwd = session dir; exit 0 on success, 1 on failure.

---

### Story 5.4: Python Conversion Node — Call Node Script, Timeout (e.g. 120s), Map Success/Failure to State

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | Clear state mapping and edges; node resolution and path handling need small additions. |
| Data Model | Sound | State keys align with ARCHITECTURE §5.1. |
| API/Integration | Sound | Subprocess only; no HTTP. |
| Technical Feasibility | Sound | subprocess.run with timeout is standard; Node discovery. |
| Vertical Slice | Sound | State in → subprocess → state out; edge to quality_check or error_handler. |
| Security/Compliance | Sound | cwd=session dir; no user input in command line beyond paths from state. |
| Dependencies & Risks | Low | Node not installed → FileNotFoundError or which('node') fails; document. |
| MECE | Sound | Complements 5.3 (implements caller); 5.5 consumes output_docx_path. |
| DoD Technical | Needs Design Work | Node executable resolution (Windows vs Unix); converter.js path when not in cwd. |

#### Strengths

- Timeout 120s, TimeoutExpired and non-zero exit mapped to state; conversion_attempts incremented.
- Conditional edge to quality_check (success) or error_handler (fail); configurable converter path.
- Unit tests for success, timeout, and failure; integration test with real Node when available.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Short-circuit when structure.json missing:** If parse node failed, structure_json_path may be missing or file absent. convert_docx should check and, without calling Node, return conversion_success=False, last_error="No structure.json", increment conversion_attempts, and route to error_handler. Add task and AC.
2. **Node executable resolution:** On Windows, `node` may be `node.exe` or not on PATH. Use shutil.which('node') or config NODE_PATH; if not found, set conversion_success=False, last_error="Node.js not found". Add to task 4 (catch FileNotFoundError).
3. **Converter script path:** When running from project root, converter.js may be at project root; when running from tests, may be different. CONVERTER_JS_PATH env: resolve to absolute; if relative, resolve relative to project root (e.g. Path(__file__).resolve().parent.parent / "converter.js"). Document.
4. **ARCHITECTURE timeout discrepancy:** ARCHITECTURE §4.7 Python example uses timeout=60; story uses 120. Update ARCHITECTURE to 120 and reference env CONVERSION_TIMEOUT_SECONDS (optional) for override.

#### Proposed Technical Designs

**1. convert_docx node pseudocode**

```python
def convert_with_docxjs_node(state: DocumentState) -> DocumentState:
    session_id = state["session_id"]
    session_path = SessionManager().get_path(session_id)
    json_path = state.get("structure_json_path") or str(session_path / "structure.json")
    if not Path(json_path).exists():
        return {**state, "conversion_success": False, "last_error": "No structure.json",
                "conversion_attempts": state["conversion_attempts"] + 1, "status": "error_handling", ...}
    output_path = session_path / "output.docx"
    node_exe = os.environ.get("NODE_PATH", "node")
    converter_script = os.environ.get("CONVERTER_JS_PATH", str(project_root / "converter.js"))
    try:
        result = subprocess.run(
            [node_exe, converter_script, str(Path(json_path).resolve()), str(output_path)],
            cwd=str(session_path),
            capture_output=True, text=True, timeout=120,
        )
        ...
    except FileNotFoundError as e:
        return {..., "last_error": "Node.js or converter not found", ...}
```

**2. Path resolution**

- structure_json_path from state may be relative; resolve to absolute for subprocess so Node receives absolute paths (and cwd is still session for relative image paths in JSON). Or pass as-is if already absolute.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 14 | Short-circuit: if structure_json_path missing or file not exists, skip subprocess, set failure state | Dev | 1 SP | Check at start of node; return failure state and increment conversion_attempts. |
| 15 | Resolve Node executable (NODE_PATH or shutil.which); document Windows | Dev | 0.5 SP | which('node'); if None, last_error "Node.js not found". |
| 16 | Resolve CONVERTER_JS_PATH relative to project root when path is relative | Dev | 0.5 SP | If not absolute, resolve from project root. |

#### Revised Story (Technical Specs)

- **DoD addition:** convert_docx short-circuits when structure.json is missing or not readable; Node executable from NODE_PATH or PATH; converter script path configurable and resolved from project root when relative. Timeout 120s (document; optional env CONVERSION_TIMEOUT_SECONDS). ARCHITECTURE §4.7 updated to 120s.
- **Contract:** Node invoked with cwd=session dir; arguments = absolute json path, absolute output path; state always updated (success or failure); conversion_attempts incremented on every attempt.

---

### Story 5.5: Quality Validator — Load DOCX (python-docx), Implement FC011 Checks; Set quality_passed and Issue List; Route Pass/Fail

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | FC011 coverage and routing clear; validator return key and python-docx API need alignment. |
| Data Model | Needs Design Work | Result key "pass" vs state "quality_passed"; quality_issues type (list of str). |
| API/Integration | Sound | Node reads state, calls validator, updates state, routing. |
| Technical Feasibility | Needs Design Work | python-docx image/rels API may differ; style name vs id. |
| Vertical Slice | Sound | output_docx_path → validator → state → edge. |
| Security/Compliance | Sound | No user input; read-only DOCX. |
| Dependencies & Risks | Low | Pin python-docx version; document. |
| MECE | Sound | Complements 5.4; Epic 6 error_handler consumes last_error. |
| DoD Technical | Needs Design Work | Style id "Code" vs name; image check implementation detail; empty doc. |

#### Strengths

- All four FC011 checks (heading hierarchy, images, code blocks, tables) in scope; result dict with pass, issues, score.
- Missing path or load error handled; no unhandled exceptions; routing to save_results or error_handler.
- last_error set for error_handler; unit tests for valid/invalid cases.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Validator return key:** ARCHITECTURE §4.9 uses `result["pass"]`; story uses `quality_passed` in state. Standardize: validator returns `{"pass": bool, "issues": [...], "score": int}`; node maps `result["pass"]` → state `quality_passed`. DoD should state this explicitly.
2. **python-docx image check:** ARCHITECTURE shows `doc.part.rels` and `rel.target_part.blob`. In python-docx, document has `document.part.related_parts` or relationships via `document.part.rels`; image parts are relationship targets. Correct API: iterate `document.part.rels`, filter by reltype containing "image", then access target_part.blob (or part.blob). Document and test with a DOCX that has one image; if API differs by version, pin version and add to DoD.
3. **Style check: "Code" by id or name:** docx library (Node) sets style id "Code". In python-docx, paragraph.style can be style name (e.g. "Code Block") or id. Ensure we check paragraph.style.name or paragraph._element.get('style') / style_id so "Code" is detected. Document "Code" as the style identifier used by converter and validator.
4. **Empty document:** If DOCX has no paragraphs or no headings, heading check should pass (no skip). If no tables, table check passes. Define in DoD.
5. **quality_issues in DocumentState:** Use same key as validator "issues" in state for clarity: e.g. quality_issues: List[str]. Epic 6 classifier will read last_error (summary string); optional future: structured quality_issues for smarter retry (e.g. type: "heading" | "image" | "code" | "table"). Not required for Epic 5; document as possible extension.

#### Proposed Technical Designs

**1. QualityValidator result schema**

```python
class QualityResult(TypedDict, total=False):
    pass: bool       # True iff issues is empty
    issues: List[str]
    score: int       # e.g. max(0, 100 - 10 * len(issues))
```

Validator returns dict with keys "pass", "issues", "score". Node: quality_passed = result["pass"], quality_issues = result["issues"].

**2. Image check (python-docx)**

```python
from docx.opc.constants import RELATIONSHIP_TYPE as RT
# Iterate document part relationships
for rel in doc.part.rels.values():
    if RT.IMAGE in rel.reltype or "image" in rel.reltype:
        try:
            _ = rel.target_part.blob
        except Exception as e:
            issues.append(f"Broken image: {rel.target_ref} ({e})")
```

(Verify exact API for your python-docx version; rel.target_part may be accessed differently.)

**3. Code style check**

- paragraph.style.name might be "Code Block" (display name) while style_id is "Code". Prefer checking style_id or paragraph._element's style reference. Example: `getattr(paragraph.style, 'style_id', None) == 'Code' or paragraph.style.name == 'Code' or 'Code' in (paragraph.style.name or '')`. Document and test.

**4. Missing output_docx_path**

- If output_docx_path missing or Path(output_docx_path).exists() is False: set quality_passed=False, quality_issues=["No DOCX output to validate"], last_error same; route to error_handler.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 17 | Align validator return key "pass" and state "quality_passed" in DoD | Dev | 0.5 SP | result["pass"] → state["quality_passed"]; document. |
| 18 | Implement image check using python-docx rels API; pin python-docx version | Dev | 1 SP | Iterate rels; filter image; try blob; pin version in pyproject.toml. |
| 19 | Code style check: use style id or name "Code" per converter contract | Dev | 0.5 SP | Check style_id or name; document "Code". |
| 20 | Define empty-document behavior (no headings/tables → pass) | Dev | 0.5 SP | DoD. |

#### Revised Story (Technical Specs)

- **DoD addition:** QualityValidator returns {"pass", "issues", "score"}; node sets quality_passed = result["pass"], quality_issues = result["issues"]. python-docx version pinned; image check and Code style check implementation documented. Empty document passes all checks. FC011 check list and result schema in ARCHITECTURE §4.9.
- **Contract:** quality_passed True iff issues list is empty; error_handler receives last_error as summary string; quality_issues preserved in state for logging/debugging.

---

## Overall Technical Roadmap

### Missing Foundational Work

1. **DocumentState consolidation (Epic 5 keys):** Ensure a single state definition (e.g. in `state.py` or `graph.py`) includes all Epic 5 keys: structure_json_path, output_docx_path, conversion_success, conversion_attempts, last_error, quality_passed, quality_issues. Epic 4/2 may already define some; avoid duplication and document ownership.
2. **Graph edge contract with Epic 4:** Epic 4 defines route_after_tools and when "complete" is returned. Confirm that "complete" is used only when generation is complete (all files processed) and that the edge from tools goes to **parse_to_json** (not to validate_md). ARCHITECTURE §5.2 shows "complete" → parse_to_json; Epic 4 stories should explicitly hand off to Epic 5 at that point.
3. **Epic 6 handshake:** Error_handler must accept failures from both **convert_docx** (conversion_success=False) and **quality_check** (quality_passed=False). last_error string is used for classification (FC013). Ensure ErrorClassifier can distinguish "conversion" (Node/timeout/parse) from "quality" (FC011 issues) if Epic 6 routes differently; otherwise single "conversion" bucket is fine. No change required in Epic 5 if Epic 6 classifies by message content.

### Schema Proposals

1. **Structure JSON Schema (Story 5.1):** Commit draft-07 schema with oneOf for section types, required metadata, and image path format; add optional schemaVersion. See Story 5.1 proposed design.
2. **QualityResult (Story 5.5):** TypedDict or Pydantic model for validator return: pass, issues, score. Keeps Python typing and docs clear.
3. **No DB schema:** Epic 5 remains file-based; no new tables or APIs.

### Architecture Decisions Needed

1. **Parse failure routing:** Decide: (A) parse node returns failure state and parse_to_json → convert_docx always; convert_docx short-circuits when no structure.json and routes to error_handler via existing conditional edge, or (B) add conditional edge from parse_to_json (success → convert_docx, failure → error_handler). Recommendation: (A) to avoid an extra conditional and keep convert_docx as single place that sets conversion_success and routes.
2. **Timeout and config:** Conversion timeout 120s; optional env CONVERSION_TIMEOUT_SECONDS for override. Document in ARCHITECTURE §8.1.
3. **Node/docx and python-docx versions:** Pin in package.json and pyproject.toml; document in ARCHITECTURE §7 (Installation) and in each story DoD.
4. **Style name "Code":** Converter (Node) and QualityValidator (Python) must agree on the same style identifier; document as shared contract in 5.3 and 5.5 DoD and in ARCHITECTURE §4.7 / §4.9.

### Cross-Story and MECE

- **5.1 vs 5.2 vs 5.3:** Schema (5.1) is contract; parser (5.2) produces; Node (5.3) consumes. No duplicate logic; optional jsonschema validate in 5.2 or 5.4 reduces drift.
- **5.4 vs 5.5:** 5.4 sets output_docx_path and conversion_success; 5.5 reads output_docx_path and sets quality_passed. Clear handoff.
- **Logging (FC015):** All five stories include or reference structured logging; ensure parse node, convert node, and quality node each log (parse_completed, conversion_started/success/failed, quality_check_completed) with session_id. No missing cross-cutting concern.
- **Test coverage:** Stories include unit tests; add one end-to-end test (Epic 5 slice): valid temp_output.md → parse → convert → quality_check → pass (can be in Epic 5 or integration test suite). Optional: add to Story 5.5 or as separate "Epic 5 E2E" task.

### Deployment and DoD

- **No new deployment steps** beyond Node.js and npm install for converter (already in ARCHITECTURE §7.2). Ensure deployment checklist (Epic 6 or ops) includes: Node LTS installed, CONVERTER_JS_PATH or default, NODE_PATH if needed.
- **DoD technical:** Each story has DoD; add to Epic 5 summary: "All Epic 5 state keys added to DocumentState; graph edges parse_to_json → convert_docx → quality_check and conditional edges to error_handler/save_results implemented and tested."

---

## Summary Scores

| Story | Technical Score | One-line summary |
|-------|-----------------|------------------|
| 5.1   | Architecturally Sound | Schema and spec solid; add oneOf, version, edge-case rules. |
| 5.2   | Needs Design Work     | State and routing on parse failure, encoding, image path security. |
| 5.3   | Needs Design Work     | Async Packer, JSON failure, empty inputs, style contract. |
| 5.4   | Architecturally Sound | Short-circuit when no structure.json; Node/converter path resolution. |
| 5.5   | Architecturally Sound | Align pass/quality_passed; python-docx API and style "Code" contract. |

**Recommendation:** Implement 5.1 first and lock schema/spec; then 5.2 and 5.3 in parallel with the added tasks above; then 5.4 (including short-circuit and path resolution); then 5.5 (with validator key and style contract). Resolve "Parse failure routing" and "Style name Code" in a short design sync before 5.2/5.3 implementation.
