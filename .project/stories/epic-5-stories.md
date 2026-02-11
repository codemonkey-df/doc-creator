# Epic 5: DOCX Conversion & Output Quality — Story Decomposition

**Epic ID:** 5  
**Epic Goal:** Convert validated markdown to DOCX via an intermediate JSON schema and docx-js, and verify output quality (headings, images, code, tables).  
**Business Value:** Delivers the actual artifact users need (DOCX); quality checks ensure headings, code blocks, tables, and images meet standards.  
**Epic Acceptance Criteria (Reference):** FC002 (intermediate markdown produced, then converted — no direct MD→DOCX without structure); FC011 (post-generation checks: heading hierarchy, image rendering, code block formatting, table structure). Markdown → JSON schema (metadata + sections: heading1–3, paragraph, code_block, table, image). docx-js (Node subprocess) produces DOCX from JSON; Python invokes it with timeouts/errors; quality validator sets quality_passed and issue list and routes pass/fail.

**Dependencies:** Epic 4 (Validation, Checkpointing & Recovery — valid markdown before conversion). Epic 2 (temp_output.md produced by agent). Epic 6 (error-handling path handshake when conversion/quality fails).

**Architecture alignment:** ARCHITECTURE §3.1 (MdToJson, DocxJs, QualityCheck in Conversion Pipeline), §4.6 (MD→JSON parser, structure.json schema), §4.7 (docx-js converter, converter.js, Python subprocess), §4.9 (QualityValidator FC011), §5.1 (DocumentState: structure_json_path, output_docx_path, conversion_success, quality_passed), §5.2–5.3 (parse_to_json, convert_docx, quality_check nodes; conditional edges to quality_check and error_handler).

**Technical Review:** This backlog was updated with findings from the technical audit. See `.project/stories/epic-5-technical-review.md` for full detail. Key decisions: (1) JSON Schema oneOf + edge cases + schema version (5.1); (2) Parse failure → conversion_success=False, last_error; convert_docx short-circuits when no structure.json; UTF-8 read; image path restricted to session (5.2, 5.4); (3) Node script async + Packer.toBuffer; JSON parse failure exit 1; empty sections/code/table; style id "Code" contract with 5.5; docx and Node 18+ pinned (5.3); (4) Validator returns "pass", node maps to quality_passed; python-docx pinned; Code style check by id/name (5.5).

---

## Story 5.1: Design and Document JSON Schema for docx-js (Metadata, Section Types, Image Paths)

### Refined Acceptance Criteria

- **AC5.1.1** A **documented JSON schema** defines the structure consumed by the Node.js docx-js converter. The schema SHALL include **metadata** (title, author, created) and **sections** as an ordered array of section objects. Section types SHALL be: **heading1**, **heading2**, **heading3**, **paragraph**, **code_block**, **table**, **image** (FC002, ARCHITECTURE §4.6).
- **AC5.1.2** Each section type has **defined fields**: heading* (text, optional id); paragraph (text, optional formatting); code_block (language, code); table (headers[], rows[][]); image (path, alt, optional width/height). **Image path** is documented as session-relative (e.g. `./assets/filename.png`) or absolute within session; path resolution rules (relative to structure.json location or session root) are explicit.
- **AC5.1.3** Schema is expressed in a **machine-readable form** (JSON Schema draft-07 or equivalent) and committed under `docs/` or `schemas/`; a short **human-readable spec** (markdown) describes usage, field semantics, and examples. Schema version or date is recorded for compatibility.
- **AC5.1.4** ARCHITECTURE §4.6 is updated to reference the schema location and any deviations from the example JSON in the doc (e.g. optional fields, extensions).
- **AC5.1.5** JSON Schema SHALL use **oneOf** (or equivalent) per section type; unknown section types SHALL be documented as "converter skips or invalid". Edge cases: empty sections array allowed; code_block may have empty `code`; table may have empty `rows`; behavior documented so converter does not crash. Optional **schemaVersion** or `$schema` and backward-compatibility policy (e.g. add optional fields only) documented in spec.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Draft JSON schema: metadata + sections array with type discriminator | Dev | 3 SP | Define metadata (title, author, created); sections[].type enum; per-type required/optional fields. |
| 2 | Define section type contracts: heading1–3, paragraph, code_block, table, image | Dev | 2 SP | Document field names, types (string, array), and semantics for each section type. |
| 3 | Document image path semantics (session-relative, resolution rules) | Dev | 1 SP | Path format (./assets/... or absolute under session); who resolves: parser vs Node script. |
| 4 | Add JSON Schema file (e.g. structure.schema.json) and version/date | Dev | 2 SP | Valid draft-07 schema; version or created date in schema or adjacent README. |
| 5 | Write human-readable spec (markdown) with examples and usage notes | Dev | 2 SP | Examples for each section type; how parser and converter use the schema. |
| 6 | Update ARCHITECTURE §4.6 with schema path and reference | Dev | 0.5 SP | Link to schema file and spec; note any deviations from in-doc example. |
| 7 | Optional: add schema validation in Python (jsonschema) for structure.json before calling Node | Dev | 1 SP | Validate generated structure.json against schema in parse node or before convert. |
| 8 | Add oneOf/discriminator for section types; document unknown-type behavior | Dev | 1 SP | JSON Schema oneOf per type; spec: "unknown type → skip or invalid". |
| 9 | Define edge cases: empty sections, empty code, empty table rows; minItems where needed | Dev | 0.5 SP | Schema or spec: empty sections allowed; code default ""; table rows length ≥ 0. |
| 10 | Add schema version or $schema and document compatibility policy | Dev | 0.5 SP | version/schemaVersion in spec; "backward-compat: add optional fields only". |

### Technical Risks & Dependencies

- **Risk:** Schema drift between parser output and Node script expectations; mitigate with shared schema and optional runtime validation (task 7).
- **Dependency:** None (this story is the contract for Stories 5.2 and 5.3).

### Definition of Done

- [ ] JSON schema file committed; all section types (heading1–3, paragraph, code_block, table, image) and metadata defined with field semantics; **oneOf** for section types; edge cases (empty sections/code/table) documented.
- [ ] Human-readable spec with examples; image path resolution rules documented; **schema version or date** in spec; ARCHITECTURE §4.6 references schema path and image path contract.
- [ ] ARCHITECTURE §4.6 updated with schema reference. **Contract:** Parser (5.2) and converter (5.3) MUST conform to this schema; unknown section types SHALL be skipped by converter; image path format SHALL be session-relative `./assets/...` unless absolute path contract is used.

---

## Story 5.2: Implement MD→JSON Parser; Write structure.json in Session

### Refined Acceptance Criteria

- **AC5.2.1** An **MD→JSON parser** converts `{session}/temp_output.md` into a structure conforming to the schema from Story 5.1. Parser SHALL emit **metadata** (title from first H1 or default, author, created timestamp) and **sections** in document order. Implementation MAY use **mistletoe** (or similar) for AST-based parsing or a hybrid approach; choice documented (ARCHITECTURE §4.6).
- **AC5.2.2** Parser SHALL recognize: **headings** (# → heading1, ## → heading2, ### → heading3), **paragraphs**, **fenced code blocks** (language + code), **tables** (markdown table syntax), **images** (![alt](path)). Inline formatting (bold, italic) may be captured in paragraph formatting or as plain text; decision documented.
- **AC5.2.3** **structure.json** is written to `{session}/structure.json` (SessionManager.get_path(session_id)). Image paths in sections SHALL be session-relative (e.g. resolve to `./assets/` or session root) so the Node script can resolve them when run with cwd = session dir (or paths passed as absolute).
- **AC5.2.4** A **parse_markdown_to_json** graph node (or equivalent) reads state (**session_id** required; **temp_md_path** optional — if missing, derive as SessionManager.get_path(session_id) / "temp_output.md"), runs the parser, writes structure.json, and updates state with **structure_json_path**. **On parse failure** (invalid MD, I/O error, UnicodeDecodeError): set **conversion_success=False**, **last_error** = "Parse error: &lt;reason&gt;", do **not** write structure.json (no partial file). convert_docx node (Story 5.4) SHALL short-circuit when structure_json_path missing or file absent and route to error_handler.
- **AC5.2.5** temp_output.md SHALL be read with **encoding='utf-8'**; on UnicodeDecodeError treat as parse failure. **Image path security:** paths from MD (e.g. `![alt](../../path)`) MUST be restricted to session/assets; path traversal → emit placeholder or skip. **metadata.created** SHALL be ISO8601 (datetime.now().isoformat()). Lists/blockquotes → emit as paragraph (plain text); document fallback. Structured logging: log event (parse_completed, section_count, parse_error if any); FC015.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement parser module (e.g. parsers/md_to_json.py) with function parse_md_to_structure(md_path, session_path) -> dict | Dev | 5 SP | Read markdown; produce dict matching schema; resolve image paths relative to session. |
| 2 | Map headings (H1–H3) to heading1–heading3 with text | Dev | 1 SP | Use mistletoe or regex; emit type and text. |
| 3 | Map paragraphs and fenced code blocks (language, code) | Dev | 2 SP | Paragraphs: concatenate inline content; code: extract language and raw code. |
| 4 | Map markdown tables to table sections (headers[], rows[][]) | Dev | 3 SP | Parse pipe tables; handle alignment row; emit headers and rows. |
| 5 | Map image syntax to image sections; resolve path to session-relative | Dev | 2 SP | ![](path) → path relative to session (e.g. ./assets/name); ensure path exists or document placeholder. |
| 6 | Extract metadata (title from first H1 or default, author, created) | Dev | 1 SP | Set metadata in output dict per schema. |
| 7 | Write structure.json to session dir; set structure_json_path in state | Dev | 2 SP | Use SessionManager.get_path(session_id); write JSON with indent; return state update. Build full structure in memory; write only after success (no partial file). |
| 8 | Implement parse_markdown_to_json node; handle parse/I/O errors → state | Dev | 2 SP | Try/except; on failure set conversion_success=False, last_error; do not write structure.json. |
| 9 | Add parse node to workflow (after validation/checkpoint when generation complete) | Dev | 1 SP | Edge from "complete" or from route_after_tools "complete" → parse_to_json → convert_docx. |
| 10 | Structured logging (parse_completed, section_count, error if any) | Dev | 0.5 SP | FC015. |
| 11 | Unit tests: parse minimal MD (one H1, one paragraph) → valid structure.json | QA/Dev | 2 SP | Assert metadata and sections shape. |
| 12 | Unit tests: parse code block, table, image → correct section types | QA/Dev | 3 SP | Fixtures for each; assert fields. |
| 13 | Unit tests: parse failure (e.g. I/O) → no partial file, state updated | QA/Dev | 1 SP | Mock or temp; assert error path. |
| 14 | Document parser choice (mistletoe/hybrid) and inline-format handling in DoD | Dev | 0.5 SP | ARCHITECTURE or story DoD. |
| 15 | Define parse failure state (conversion_success=False, last_error); ensure convert_docx short-circuits if no structure.json | Dev | 1 SP | Parse node sets failure state; convert_docx (5.4) checks structure_json_path exists, else skip subprocess and route to error_handler. |
| 16 | Document and implement UTF-8 read; UnicodeDecodeError → parse failure | Dev | 0.5 SP | open(encoding='utf-8'); except UnicodeDecodeError. |
| 17 | Restrict image path to session/assets; path traversal → placeholder or skip | Dev | 1 SP | Normalize path; reject outside session; emit ./assets/placeholder or omit. |
| 18 | Document list/blockquote → paragraph fallback; add test | Dev/QA | 0.5 SP | Spec + test. |
| 19 | Set metadata.created to ISO8601 | Dev | 0.5 SP | datetime.now().isoformat(). |

### Technical Risks & Dependencies

- **Risk:** Edge cases (nested lists, block quotes) may need explicit handling or fallback to paragraph; document and add tests as needed.
- **Dependency:** Story 5.1 (schema); Epic 4 (temp_output.md valid and present); SessionManager (Epic 1). Story 5.4 convert_docx short-circuits when structure.json missing. Optional: mistletoe in pyproject.toml.

### Definition of Done

- [ ] Parser produces schema-conformant structure; structure.json written to session only after full parse success; structure_json_path in state. Parse failure sets conversion_success=False and last_error; no partial structure.json.
- [ ] All section types (heading1–3, paragraph, code_block, table, image) implemented; image paths session-relative; **path traversal rejected** (placeholder or skip). **UTF-8 read**; UnicodeDecodeError → parse failure. **metadata.created** = ISO8601. List/blockquote → paragraph documented and tested.
- [ ] Parse node integrated; convert_docx short-circuits when structure_json_path missing or file absent. Structured logging; unit tests. **Contract:** parse_md_to_structure(md_path, session_path) → dict; output conforms to Story 5.1 schema.

---

## Story 5.3: Implement Node Script (converter.js) Using docx — Headings, Paragraphs, Code, Tables, Images

### Refined Acceptance Criteria

- **AC5.3.1** A **Node.js script** (e.g. `converter.js`) reads **structure.json** (path as first CLI arg) and writes **output.docx** (path as second CLI arg). Script uses the **docx** npm package (docx-js) to build the document. Exit code 0 on success; non-zero and stderr message on failure (ARCHITECTURE §4.7).
- **AC5.3.2** Script maps section types to docx elements: **heading1–3** → Paragraph with HeadingLevel.HEADING_1/2/3; **paragraph** → Paragraph with TextRun(s); **code_block** → one or more Paragraphs with Code style (e.g. Courier New, shading); **table** → Table with header row and data rows; **image** → ImageRun from file path (path resolved relative to cwd or passed absolute). Document has default styles and page setup (e.g. US Letter) per ARCHITECTURE §4.7.
- **AC5.3.3** **Image path** resolution: script receives paths that are either session-relative (e.g. `./assets/fig.png`) or absolute. When running from Python, cwd SHALL be session dir so relative paths work; or Python passes absolute paths in structure.json. Image load failure (missing file) SHALL be caught and reported (stderr, exit 1) rather than crashing.
- **AC5.3.4** **package.json** lists **docx** dependency; script is invocable as `node converter.js <jsonPath> <docxPath>`. No hardcoded paths; paths from argv only. Code blocks SHALL be monospaced and visually distinct (style "Code" or equivalent).
- **AC5.3.5** Script is **deterministic** for same input (no timestamps inside doc content that change between runs); metadata (e.g. created) may come from JSON.
- **AC5.3.6** Script SHALL use **async entry** (top-level await or async main) and **await Packer.toBuffer(doc)**; write output synchronously after await. **JSON parse failure** (malformed structure.json) → try/catch, stderr message, exit 1. **Empty inputs:** sections=[] or missing → minimal document; code_block with code "" → one empty Code paragraph; table with rows=[] → header row only. **Style id "Code"** is the canonical identifier for code blocks (QualityValidator in 5.5 checks by this id/name). **docx** version pinned in package.json; **Node 18+** required (document in README or package.json engines).

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Create Node project (package.json) and add docx dependency | Dev | 0.5 SP | npm init if needed; npm install docx; pin version. |
| 2 | Implement CLI: read argv[1] (jsonPath), argv[2] (docxPath) | Dev | 1 SP | fs.readFileSync(jsonPath); parse JSON; validate presence of sections. |
| 3 | Map heading1–3 to Paragraph with HeadingLevel | Dev | 1 SP | Loop sections; emit Paragraph with heading: HeadingLevel.HEADING_1 etc. |
| 4 | Map paragraph to Paragraph with TextRun | Dev | 1 SP | section.text → TextRun; handle empty. |
| 5 | Map code_block to Code-style paragraphs (Courier New, optional shading) | Dev | 2 SP | Split code by newline; one Paragraph per line with style "Code"; document styles. |
| 6 | Map table to docx Table (header row + data rows) | Dev | 3 SP | Table with TableRow/TableCell; header styling (e.g. bold, shading). |
| 7 | Map image to ImageRun; resolve path; handle missing file → stderr + exit 1 | Dev | 2 SP | fs.readFileSync(path); if path relative, resolve from cwd; catch and report. |
| 8 | Build Document with default styles and page setup; Packer.toBuffer → writeFile | Dev | 2 SP | Single section; margins, page size; **use async and await Packer.toBuffer**; write docx to argv[2]. |
| 9 | Add document styles (Code block) in Document options | Dev | 0.5 SP | paragraphStyles with id "Code", font Courier New. |
| 10 | Unit/test script: run with sample structure.json; assert output.docx exists and opens | QA/Dev | 2 SP | Node test or Python subprocess; minimal JSON fixture. |
| 11 | Test with all section types (heading, paragraph, code, table, image) | QA/Dev | 2 SP | Fixture with one of each; visual or programmatic check. |
| 12 | Test image missing → exit 1 and stderr | QA/Dev | 1 SP | Fixture with bad image path. |
| 13 | Document cwd requirement (session dir) or absolute path contract for Python caller | Dev | 0.5 SP | DoD and ARCHITECTURE §4.7. |
| 14 | Use async entry and await Packer.toBuffer; handle rejections | Dev | 1 SP | Top-level await or async main(); exit 1 on catch. |
| 15 | JSON parse try/catch; stderr + exit 1 on invalid JSON | Dev | 0.5 SP | try/catch around JSON.parse. |
| 16 | Handle empty sections, empty code, empty table rows per DoD | Dev | 1 SP | sections=[] → minimal doc; code="" → one empty Code para; rows=[] → header only. |
| 17 | Pin docx version in package.json; document Node 18+ requirement | Dev | 0.5 SP | package.json engines or README. |

### Technical Risks & Dependencies

- **Risk:** docx API changes; pin docx version in package.json and document. Packer.toBuffer is async — script must use async/await (Node 18+).
- **Dependency:** Story 5.1 (schema); Story 5.2 (structure.json format). Python (Story 5.4) will set cwd or paths. Story 5.5 QualityValidator uses style "Code" — same contract.

### Definition of Done

- [ ] converter.js reads structure.json and writes output.docx; all section types implemented; **async entry and await Packer.toBuffer**; JSON parse failure and image load failure → exit 1 and stderr.
- [ ] **Empty sections/code/table** behavior documented and implemented. **Style id "Code"** documented for QualityValidator (5.5) alignment. docx version pinned; Node 18+ documented.
- [ ] Image path resolution documented; missing image → exit 1 and stderr. Script tested; deterministic output. **Contract:** Invocation `node converter.js <jsonPath> <docxPath>` with cwd = session dir; exit 0 on success, 1 on failure.

---

## Story 5.4: Python Conversion Node — Call Node Script, Timeout (e.g. 120s), Map Success/Failure to State

### Refined Acceptance Criteria

- **AC5.4.1** A **convert_to_docx** (or convert_with_docxjs) **graph node** invokes the Node script: `node converter.js <structure_json_path> <output_docx_path>`. Paths SHALL be absolute or relative such that the script and session files are found; **working directory** for subprocess SHALL be session directory (SessionManager.get_path(session_id)) so relative paths in structure.json resolve (ARCHITECTURE §4.7, §5.3).
- **AC5.4.2** **Timeout** SHALL be enforced (e.g. 120s); on **subprocess.TimeoutExpired** the node sets conversion_success=False and last_error to a clear message (e.g. "Conversion timeout (120s exceeded)"). On non-zero exit, conversion_success=False and last_error=stderr (or stdout if stderr empty). On success (exit 0), conversion_success=True and output_docx_path set in state.
- **AC5.4.3** Node SHALL **not** throw unhandled exceptions: missing Node, missing converter.js, missing structure.json, or permission errors SHALL be caught and mapped to state (conversion_success=False, last_error descriptive). conversion_attempts SHALL be incremented when conversion is attempted (success or failure).
- **AC5.4.4** **State updates:** conversion_success (bool), output_docx_path (str, when success), last_error (str, when failure), conversion_attempts (incremented). Status transition: to "quality_checking" on success, to "error_handling" on failure (per ARCHITECTURE §5.2).
- **AC5.4.5** **Short-circuit:** If **structure_json_path** is missing or the file does not exist (e.g. parse node failed), convert_docx SHALL **not** invoke Node; set conversion_success=False, last_error="No structure.json", increment conversion_attempts, and return state so conditional edge routes to error_handler. **Node executable:** Resolve via NODE_PATH env or shutil.which('node'); if not found, set conversion_success=False, last_error="Node.js not found". **Converter script path:** CONVERTER_JS_PATH env; if relative, resolve relative to project root. **Timeout** 120s; optional env CONVERSION_TIMEOUT_SECONDS for override. Update ARCHITECTURE §4.7 to 120s (example shows 60s). Structured logging: log event (conversion_started, attempt, timeout); conversion_success or conversion_failed (with error summary); FC015.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement convert_with_docxjs node: subprocess.run(node, converter.js, jsonPath, docxPath) | Dev | 3 SP | Resolve paths; cwd=session dir; capture_output=True, text=True. |
| 2 | Set subprocess timeout (e.g. 120s); handle TimeoutExpired → state | Dev | 1 SP | timeout=120 (or CONVERSION_TIMEOUT_SECONDS); except TimeoutExpired: conversion_success=False, last_error message. |
| 3 | Map returncode and stderr to conversion_success and last_error | Dev | 1 SP | returncode 0 → success, set output_docx_path; else failure, last_error=stderr or stdout. |
| 4 | Catch FileNotFoundError, PermissionError, other OSErrors → state | Dev | 1 SP | No unhandled exception; set conversion_success=False, last_error. Resolve Node via NODE_PATH or shutil.which('node'); "Node.js not found" if missing. |
| 5 | Increment conversion_attempts on each run (success or fail) | Dev | 0.5 SP | state["conversion_attempts"] + 1 in returned state. |
| 6 | Add output_docx_path to DocumentState; set on success | Dev | 0.5 SP | state.py or graph state; output_docx_path = str(session_path / "output.docx"). |
| 7 | Wire conditional edge: convert_docx → quality_check (success) or error_handler (fail) | Dev | 1 SP | add_conditional_edges("convert_docx", lambda s: "quality_check" if s.get("conversion_success") else "error_handler", ...). |
| 8 | Make converter script path configurable (env CONVERTER_JS_PATH or default) | Dev | 0.5 SP | Default ./converter.js or project root; resolve relative to project when path is relative. |
| 9 | Structured logging (conversion_started, conversion_success/failed, attempt) | Dev | 0.5 SP | FC015. |
| 10 | Unit tests: mock subprocess — success path (returncode 0) → state has conversion_success True | QA/Dev | 2 SP | Patch subprocess.run; assert state. |
| 11 | Unit tests: timeout path → conversion_success False, last_error contains timeout | QA/Dev | 1 SP | Mock TimeoutExpired. |
| 12 | Unit tests: non-zero exit → conversion_success False, last_error from stderr | QA/Dev | 1 SP | Mock returncode 1, stderr. |
| 13 | Integration test: run node with real converter.js and sample structure.json (if Node available) | QA/Dev | 2 SP | Optional skip if no Node; assert output.docx created and state. |
| 14 | Short-circuit: if structure_json_path missing or file not exists, skip subprocess, set failure state | Dev | 1 SP | Check at start of node; return failure state and increment conversion_attempts. |
| 15 | Resolve Node executable (NODE_PATH or shutil.which); document Windows | Dev | 0.5 SP | which('node'); if None, last_error "Node.js not found". |
| 16 | Resolve CONVERTER_JS_PATH relative to project root when path is relative | Dev | 0.5 SP | If not absolute, resolve from project root. |

### Technical Risks & Dependencies

- **Risk:** Node not installed or wrong version; document requirement (Node 18+ or LTS) and fail gracefully in node (task 4).
- **Dependency:** Story 5.2 (structure_json_path set; convert_docx short-circuits when missing); Story 5.3 (converter.js); Epic 6 (error_handler node and retry/route). DocumentState must include conversion_success, last_error, conversion_attempts, output_docx_path.

### Definition of Done

- [ ] convert_with_docxjs node implemented; **short-circuits** when structure.json missing or not readable; invokes Node script with cwd=session dir; timeout 120s (optional CONVERSION_TIMEOUT_SECONDS); success/failure mapped to state.
- [ ] Node executable from NODE_PATH or PATH; converter script path configurable and resolved from project root when relative. No unhandled exceptions; conversion_attempts incremented; conditional edge to quality_check or error_handler.
- [ ] ARCHITECTURE §4.7 updated to 120s. Converter path configurable; structured logging; unit tests. **Contract:** Node invoked with cwd=session dir; arguments = absolute json path, absolute output path; state always updated; conversion_attempts incremented on every attempt.

---

## Story 5.5: Quality Validator — Load DOCX (python-docx), Implement FC011 Checks; Set quality_passed and Issue List; Route Pass/Fail

### Refined Acceptance Criteria

- **AC5.5.1** A **QualityValidator** (e.g. validators/docx_validator.py or quality_validator.py) loads the generated DOCX using **python-docx** and runs **FC011** checks: (1) **Heading hierarchy** — no skipped levels (H1→H2→H3), (2) **Image rendering** — image parts load (no broken refs), (3) **Code block formatting** — code paragraphs use monospaced font (e.g. Courier New, Consolas), (4) **Table structure** — tables have at least one row and consistent column counts across rows (ARCHITECTURE §4.9).
- **AC5.5.2** Validator returns a **result dict** with keys **"pass"** (bool), **"issues"** (list of strings), and **"score"** (e.g. max(0, 100 - 10*len(issues))). The **quality_check** node maps result["pass"] → state **quality_passed**, result["issues"] → state **quality_issues**. quality_passed SHALL be True only when issues is empty.
- **AC5.5.3** A **quality_check** graph node loads state (output_docx_path), runs QualityValidator.validate(docx_path), and updates state: **quality_passed** = result["pass"], **quality_issues** = result["issues"], and status. If quality_passed: route to **save_results** (or "complete"); if not: route to **error_handling** with last_error set to summary of issues (ARCHITECTURE §5.2–5.3). **Code style check:** Use style id or name **"Code"** (same as converter.js) per converter contract; document in DoD.
- **AC5.5.4** If **output_docx_path is missing** or file does not exist (e.g. conversion was skipped), quality_check SHALL set quality_passed=False and a single issue "No DOCX output to validate"; route to error_handling.
- **AC5.5.5** Structured logging: log event (quality_check_completed, passed, issue_count, issues summary); FC015. Validator SHALL not raise unhandled exceptions; malformed DOCX (e.g. python-docx load error) → pass=False, issue "Failed to load DOCX: &lt;reason&gt;". **Empty document:** No headings or no tables → all checks pass (no spurious issues). **python-docx** version pinned in pyproject.toml; image check and Code style check implementation documented.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement QualityValidator class with validate(docx_path: Path) -> dict | Dev | 2 SP | Load Document(docx_path); run all checks; return {pass, issues, score}. |
| 2 | Implement _check_headings: iterate paragraphs; detect Heading 1/2/3; assert no skip | Dev | 2 SP | prev_level; if style Heading N and N > prev_level+1 → add issue. |
| 3 | Implement _check_images: verify image parts are loadable (rel.target_part.blob or similar) | Dev | 2 SP | doc.part.rels; filter image type; try load blob; on exception add issue. |
| 4 | Implement _check_code_blocks: paragraphs with style "Code" have monospaced font | Dev | 1 SP | Check by style id or name "Code" (converter contract); font Courier New, Consolas, Monaco allowed. |
| 5 | Implement _check_tables: non-empty tables, consistent column count per row | Dev | 1 SP | For each table: rows length; len(row.cells) consistent. |
| 6 | Handle missing file or invalid DOCX (load error) → pass=False, single issue | Dev | 1 SP | Try/except in validate(); no raise. |
| 7 | Implement quality_check node: call validator, set quality_passed and quality_issues in state | Dev | 2 SP | quality_passed = result["pass"], quality_issues = result["issues"]; if output_docx_path missing → pass=False. |
| 8 | Add quality_passed and quality_issues to DocumentState | Dev | 0.5 SP | state definition. |
| 9 | Wire conditional edge: quality_check → save_results (pass) or error_handler (fail) | Dev | 1 SP | add_conditional_edges("quality_check", lambda s: "save_results" if s.get("quality_passed") else "error_handler", ...). |
| 10 | Set last_error when routing to error_handler (summary of quality_issues) | Dev | 0.5 SP | So error_handler can classify and possibly retry. |
| 11 | Structured logging (quality_check_completed, passed, issue_count) | Dev | 0.5 SP | FC015. |
| 12 | Unit tests: validator with valid DOCX (headings, code, table) → pass True, issues=[] | QA/Dev | 2 SP | Create minimal docx (python-docx) or use fixture. |
| 13 | Unit tests: validator with skipped heading level → pass False, issue in list | QA/Dev | 1 SP | Fixture with H1 then H3. |
| 14 | Unit tests: validator with broken image or wrong code font → issues | QA/Dev | 2 SP | Fixtures. |
| 15 | Unit tests: quality_check node (missing path, load error) → pass False | QA/Dev | 1 SP | Mock or temp. |
| 16 | Document FC011 check list and result schema in DoD and ARCHITECTURE §4.9 | Dev | 0.5 SP | Align with ARCHITECTURE. |
| 17 | Align validator return key "pass" and state "quality_passed" in DoD | Dev | 0.5 SP | result["pass"] → state["quality_passed"]; document. |
| 18 | Implement image check using python-docx rels API; pin python-docx version | Dev | 1 SP | Iterate rels; filter image; try blob; pin version in pyproject.toml. |
| 19 | Code style check: use style id or name "Code" per converter contract | Dev | 0.5 SP | Check style_id or name; document "Code". |
| 20 | Define empty-document behavior (no headings/tables → pass) | Dev | 0.5 SP | DoD. |

### Technical Risks & Dependencies

- **Risk:** python-docx API differences for image/rels; use stable APIs and pin version.
- **Dependency:** Story 5.4 (output_docx_path set on conversion success); Epic 6 (error_handler and optional retry from quality fail). Story 5.3 converter uses style id "Code" — same contract. DocumentState must include quality_passed and quality_issues.

### Definition of Done

- [ ] QualityValidator implements all FC011 checks (heading hierarchy, images, code blocks, tables); returns **{"pass", "issues", "score"}**; node sets quality_passed = result["pass"], quality_issues = result["issues"].
- [ ] python-docx version pinned; image check and **Code** style check (id or name) implementation documented. **Empty document** passes all checks.
- [ ] quality_check node updates state and routes to save_results (pass) or error_handler (fail); missing/invalid DOCX handled. quality_passed and quality_issues in DocumentState; structured logging; unit tests. **Contract:** quality_passed True iff issues list is empty; error_handler receives last_error with quality summary when failing.

---

## Epic 5 — Summary

| Story | Focus | Key Deliverables |
|-------|--------|-------------------|
| 5.1 | JSON schema for docx-js | Schema file (oneOf, edge cases, version), spec, ARCHITECTURE update |
| 5.2 | MD→JSON parser + parse node | parsers/md_to_json, structure.json in session, parse node; parse failure → conversion_success=False; UTF-8, image path security |
| 5.3 | Node converter.js | converter.js (async, Packer.toBuffer), docx mapping, empty-input handling, style "Code", package.json (docx pinned, Node 18+) |
| 5.4 | Python conversion node | convert_with_docxjs node, short-circuit when no structure.json, timeout 120s, Node/converter path resolution |
| 5.5 | Quality validator + node | QualityValidator FC011 (pass → quality_passed), quality_check node, routing; python-docx pinned, Code style contract |

**Suggested implementation order:** 5.1 → 5.2 & 5.3 (parallel where possible) → 5.4 → 5.5.  
**Total effort (planning poker):** ~55–65 SP (story-level after technical review); adjust per task table for sprint planning.

**DoD (Epic-level):** All Epic 5 state keys (structure_json_path, output_docx_path, conversion_success, conversion_attempts, last_error, quality_passed, quality_issues) added to DocumentState; graph edges parse_to_json → convert_docx → quality_check and conditional edges to error_handler/save_results implemented and tested. Optional: one E2E test (temp_output.md → parse → convert → quality_check → pass).
