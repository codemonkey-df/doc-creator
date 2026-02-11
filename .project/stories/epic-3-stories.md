# Epic 3: Asset & Reference Management — Story Decomposition

**Epic ID:** 3  
**Epic Goal:** Resolve image and path references: discover references in inputs, copy images into session assets, and handle missing files (placeholders or user resolution).  
**Business Value:** Documents with images and external refs work reliably; fewer conversion failures and clear handling of missing assets.  
**Epic Acceptance Criteria (Reference):** FC008 (image/path resolution), FC014 (validate existence, copy to assets, placeholder when missing). Scan runs after initialization; missing refs can trigger human-in-the-loop (Epic 2).

**Dependencies:** Epic 1 (Secure Input & Session Foundation — session with `inputs/`, `assets/`). Integrates with Epic 2 (human-in-the-loop interrupt for missing refs; scan_assets node and conditional edges).

**Architecture alignment:** ARCHITECTURE §3.1 (ImageScan after File Discovery), §4.4 (copy_image tool), §4.8 (AssetHandler), §5.2–5.3 (scan_assets_node, conditional edges to human_input).

**Technical Review:** This backlog was updated with findings from the technical audit. See `.project/stories/epic-3-technical-review.md` for full detail. Key decisions: (1) State key `found_image_refs` (List[ImageRefResult]: original_path, resolved_path, source_file) for 3.1→3.2 handoff; (2) `missing_references` replace vs append documented; optional `current_missing_references` if reducer does not support replace; (3) AssetScanSettings / allowed_base_path for absolute paths; (4) Canonical placeholder format `[Image Missing: {basename}]` used by copy_image and AssetHandler; (5) insert_placeholder(session_id, image_identifier, target_file) for inputs or temp_output; (6) user_decisions schema and upload path validation; (7) Shared path-resolution helper for 3.1 and 3.3.

---

## Story 3.1: Asset Scan Node — Parse Inputs for Image Refs, Resolve Paths, Detect Missing

### Refined Acceptance Criteria

- **AC3.1.1** The scan_assets node reads all files in `state["input_files"]` from the session `inputs/` directory and parses each for markdown image syntax: `![alt](path)` (regex or equivalent); captures the path (group) from every match.
- **AC3.1.2** For each extracted path: (a) if it is a URL (starts with `http://` or `https://`), skip (no copy, no missing); (b) if relative, resolve relative to the directory of the current input file (session `inputs/` dir); (c) if absolute, use as-is; then check existence.
- **AC3.1.3** Each path is classified as **found** (file exists) or **missing** (file not found). Missing paths are collected in `state["missing_references"]` (or `current_missing_references` if reducer does not support replace); found paths are recorded in **state["found_image_refs"]** for downstream copy (Story 3.2). Each found/missing record includes **source_file** (input filename) for rewrite and placeholder targeting.
- **AC3.1.4** Path resolution respects security: resolved paths must not escape session or allowed input base. Absolute paths from markdown are validated against an **allowed base** (AssetScanSettings.allowed_base_path or Epic 1 base_dir); treat outside base as missing; document policy.
- **AC3.1.5** scan_assets node output: state updated with `missing_references` (or current_missing_references), `pending_question` when non-empty, `status`, and **found_image_refs** (List[ImageRefResult]: original_path, resolved_path, source_file). Semantics for replace vs append of missing_references are documented; conditional edge uses the missing list for human_input vs continue. No modification of input file content in this story.
- **AC3.1.6** Image syntax: support `![alt](path)` and optional title `![alt](path "title")`; capture path only, strip title if present. Structured logging: log event per input file (refs found), and per ref (resolved path, found/missing); use session logger (FC015).

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define image-ref regex and extraction helper | Dev | 2 SP | Regex for `![...](path)`; function `extract_image_refs(content: str) -> list[str]` returning paths; unit tests for edge cases (nested brackets, spaces). |
| 2 | Implement path resolution (relative to input file dir) | Dev | 3 SP | Given input file path (under session/inputs), resolve relative image path; handle `.`, `..` within allowed base; return resolved Path or None if invalid. |
| 3 | Implement absolute path validation against allowed base | Dev | 2 SP | If path is absolute, check under configured base (e.g. session or input root); treat outside base as missing; document policy. |
| 4 | Implement URL detection and skip for http(s) refs | Dev | 1 SP | Skip copy and missing for URLs; do not add to missing_references. |
| 5 | Wire scan_assets node: read inputs, extract refs, classify found/missing | Dev | 3 SP | For each input file, read content, extract refs, resolve, check exists; populate missing_references and internal list of found refs for Story 3.2. |
| 6 | Update state (missing_references, pending_question, status) and logging | Dev | 2 SP | Set state for conditional edge; log per file and per ref (found/missing). |
| 7 | Unit tests: extract_image_refs, resolve relative/absolute, URL skip | QA/Dev | 3 SP | Fixtures with sample markdown; test resolution from different input dirs; test absolute outside base. |
| 8 | Integration test: scan_assets with mixed found/missing refs | QA/Dev | 2 SP | Invoke node with state; assert missing_references and state shape for human_input vs continue. |
| 9 | Document resolution order and security (no escape from base) | Dev | 1 SP | Docstring and DoD: relative → input file dir; absolute → allowed base; URLs skipped. |
| 10 | Define scan result schema (found_image_refs) and set in state | Dev | 2 SP | Add ImageRefResult (original_path, resolved_path, source_file); scan_assets populates found_image_refs; DocumentState key. |
| 11 | Document missing_references replace vs append; ensure conditional edge uses correct key | Dev | 1 SP | If reducer appends, introduce current_missing_references for scan output; document in DoD. |
| 12 | Define allowed base for absolute paths (AssetScanSettings or Epic 1 base_dir) | Dev | 1 SP | AssetScanSettings with allowed_base_path; env prefix ASSET_; document in story. |
| 13 | Extend regex/tests for optional title in image syntax | Dev/QA | 0.5 SP | Support `](path "title")`; strip title from path; add test. |

### Technical Risks & Dependencies

- **Risk:** Relative paths in markdown are ambiguous (relative to file vs CWD); standard is relative to the markdown file’s directory — use session `inputs/` + current filename to derive directory.
- **Risk:** Absolute paths in user content could point anywhere; restrict to same base as inputs or treat as missing and document.
- **Dependency:** Epic 1 (session layout, `inputs/`); Story 2.1 (scan_assets node exists in minimal form — this story enhances it with full parsing and classification).

### Definition of Done

- [ ] Image ref extraction and path resolution implemented; regex and helpers unit tested; optional title in image syntax supported and tested.
- [ ] Scan result schema (found_image_refs with original_path, resolved_path, source_file) defined and set by scan_assets; missing_references (or current_missing_references) semantics documented.
- [ ] Allowed base for absolute paths configured (AssetScanSettings or Epic 1 base_dir); path resolution and security documented (relative → input file dir; absolute under base); no path escape.
- [ ] Unit and integration tests; structured logging for refs; lint and type-check pass.

---

## Story 3.2: Copy Available Images to Session `assets/` and Rewrite Refs to Relative Paths

### Refined Acceptance Criteria

- **AC3.2.1** Copy step reads **state["found_image_refs"]** from Story 3.1; each entry has original_path, resolved_path, source_file. For every entry, copy the file to the session `assets/` directory; destination filename is the source file’s name (basename); if multiple refs map to the same basename, last copy wins (documented).
- **AC3.2.2** After copying, rewrite using **exact original path** (as captured by regex) within image syntax only: replace `![alt](original_path)` with `![alt](./assets/basename)`; preserve alt. Apply to content of each input file in `inputs/`; write back in-place (UTF-8).
- **AC3.2.3** Rewriting is deterministic; refs in different input files that point to the same resolved file both become `./assets/basename`. Copy and rewrite are **idempotent** for the same scan result (re-run safe).
- **AC3.2.4** Implementation: (a) in-place rewrite of files in `inputs/` after copy, or (b) build a “resolved” view (e.g. temp or in-memory) and have read_file serve that when asset scan has run — document choice; ARCHITECTURE suggests copy + update refs.
- **AC3.2.5** scan_assets node (or a dedicated sub-step) performs copy and rewrite so that when the graph proceeds to the agent, input files already contain session-local image paths for existing images; missing refs are not rewritten here (handled in Story 3.4).
- **AC3.2.6** Log each copy (source → assets/basename) and any collision; do not overwrite session-critical files outside `assets/`. UTF-8 and line endings preserved on read/write.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Design copy destination and collision policy | Dev | 1 SP | Destination: session_path/assets/basename; document last-copy-wins or indexed names; ensure assets/ exists (SessionManager). |
| 2 | Implement copy found images to session assets/ | Dev | 3 SP | For each found ref from scan, copy resolved path to assets/basename; use shutil.copy; handle read errors. |
| 3 | Implement ref rewrite: replace original path with ./assets/basename in content | Dev | 3 SP | For each rewritten ref, replace the markdown path (in content string) with ./assets/basename; preserve alt text. |
| 4 | Integrate copy + rewrite into scan_assets flow | Dev | 3 SP | After classifying found/missing, run copy for found refs, then rewrite input file content and write back to inputs/ (or apply via read_file override); document in-place vs view. |
| 5 | Handle duplicate basenames from different source paths | Dev | 2 SP | Same basename → same destination; last copy wins; log when overwriting. |
| 6 | Unit tests: copy to assets, rewrite refs in sample markdown | QA/Dev | 3 SP | Temp session; create image file; run copy+rewrite; assert file in assets/ and content updated. |
| 7 | Integration test: full scan_assets with copy and rewrite, then read_file | QA/Dev | 2 SP | Run scan_assets (with found refs); assert assets/ populated and read_file returns content with ./assets/ paths. |
| 8 | Logging for copy and rewrite steps | Dev | 1 SP | Log each copy (source, dest); log rewrite count per file. |
| 9 | Document in-place rewrite vs resolved-view decision in DoD | Dev | 0.5 SP | DoD: chosen approach and where refs are updated (inputs/ files vs derived view). |
| 10 | Consume found_image_refs from state; document input contract | Dev | 1 SP | Copy step reads state["found_image_refs"]; handle empty list; document in AC. |
| 11 | Implement replace using exact original path and image-pattern scope | Dev | 1 SP | Replace only within image syntax; preserve alt; use exact original_path from capture. |
| 12 | Add test: UTF-8 and line endings preserved after rewrite | QA/Dev | 1 SP | Fixture with UTF-8 and CRLF/LF; assert no corruption. |
| 13 | Document idempotency of copy+rewrite for same scan result | Dev | 0.5 SP | DoD: idempotent when run again with same found refs. |

### Technical Risks & Dependencies

- **Risk:** Rewriting markdown in place can corrupt encoding or structure; use same encoding (UTF-8) and replace only the path part inside image syntax.
- **Dependency:** Story 3.1 (found_image_refs in state with original_path, resolved_path, source_file).

### Definition of Done

- [ ] Copy reads found_image_refs from state; all found images copied to `session/assets/`; refs rewritten using exact original path within image syntax.
- [ ] Collision policy and idempotency documented; logging for copy and rewrite; UTF-8 and line-ending test.
- [ ] Unit and integration tests; agent sees session-local paths when reading input files after scan.
- [ ] Lint and type-check pass; no writes outside session/assets.

---

## Story 3.3: Add `copy_image` Tool and Integrate with Agent for On-Demand Asset Handling

### Refined Acceptance Criteria

- **AC3.3.1** A new tool `copy_image(source_path: str, session_id: str)` is available: given a source path (file path or basename), it copies the file to `{session}/assets/` and returns the relative path string (e.g. `./assets/filename.png`) for the agent to use in markdown. Session ID is **injected via tool factory** (not passed by agent); tool signature may be `copy_image(source_path)` when bound with session_id.
- **AC3.3.2** If the source file does not exist, the tool returns the **canonical placeholder** `[Image Missing: {basename}]` (basename only) so the agent can insert it; no exception that stops the agent (FC014). Same format as AssetHandler.insert_placeholder (Epic-wide).
- **AC3.3.3** Path validation: same rules as scan_assets — **reuse shared** `resolve_image_path(path, base_dir)` or same allowed_base_path; relative resolve to session `inputs/`; absolute under allowed base; reject invalid paths with clear error.
- **AC3.3.4** Tool is registered in `get_tools(session_id)` and described so the agent knows when to use it.
- **AC3.3.5** Agent system prompt (Epic 2) is updated to mention copy_image; path resolution and placeholder format documented in ARCHITECTURE.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement copy_image logic: resolve path, copy to assets, return path or placeholder | Dev | 3 SP | Resolve source_path (relative to session inputs or base); if exists, copy to assets/basename, return "./assets/basename"; else return "[PLACEHOLDER: basename]". |
| 2 | Add path validation for source_path (no traversal, allowed base) | Dev | 2 SP | Reject .. and path escape; resolve and ensure under allowed directory; raise ValueError with message if invalid. |
| 3 | Expose copy_image via get_tools(session_id) with session_id bound | Dev | 2 SP | Tool factory returns copy_image bound to current session_id; agent only passes source_path. |
| 4 | Write tool description for LLM (when to use, args, return value) | Dev | 1 SP | Docstring and tool schema: copy image to assets, return path or placeholder. |
| 5 | Unit tests: copy_image success, missing file (placeholder), path validation | QA/Dev | 3 SP | Temp session; valid path → copy and return path; missing → placeholder; "../" → rejected. |
| 6 | Update agent system prompt to mention copy_image | Dev | 1 SP | Add line: when referencing images, use copy_image to copy to assets and use returned path in markdown. |
| 7 | Integration test: agent invokes copy_image and uses returned path in append_to_markdown | QA/Dev | 2 SP | Simulate or run agent with content containing image ref; assert copy_image called and markdown contains ./assets/ path. |
| 8 | Document copy_image in ARCHITECTURE or tools section | Dev | 0.5 SP | FC014; signature, placeholder behavior, path rules. |
| 9 | Align copy_image path resolution with scan_assets (reuse helper or same allowed base) | Dev | 1 SP | Use same resolve_image_path or config; document. |
| 10 | Use canonical placeholder format; use basename in placeholder text | Dev | 0.5 SP | `[Image Missing: {basename}]`; document in Epic 3 DoD. |

### Technical Risks & Dependencies

- **Risk:** Agent may pass arbitrary paths; validation must restrict to allowed base (session inputs or same base as entry).
- **Dependency:** Epic 1 (SessionManager, assets/); Story 2.2 (get_tools, tool factory). Shared path-resolution helper from 3.1.

### Definition of Done

- [ ] `copy_image` implemented; path validation aligned with scan_assets; returns path or canonical placeholder `[Image Missing: {basename}]`; session_id from factory.
- [ ] Tool in get_tools(session_id); agent prompt updated; unit and integration tests.
- [ ] FC014 satisfied for on-demand copy and placeholder; lint and type-check pass.

---

## Story 3.4: Placeholder Insertion for Missing Images and Optional Human-in-the-Loop (Epic 2 Interrupt)

### Refined Acceptance Criteria

- **AC3.4.1** When an image ref is **missing** (from scan_assets), the system inserts the **canonical placeholder** `[Image Missing: {basename}]` (same as Story 3.3) so the document still generates and the user sees what was missing (FC014).
- **AC3.4.2** Placeholders for skip are applied to **input files** (so agent never sees the broken ref). AssetHandler also supports **temp_output.md** for error-pipeline use. Story 3.3 covers agent-inserted placeholder via copy_image return.
- **AC3.4.3** AssetHandler.insert_placeholder(session_id, image_identifier, target_file) exists: given session and image identifier, it finds and replaces the corresponding image markdown in target_file (e.g. inputs/doc.md or temp_output.md) with the canonical placeholder; used when we choose “skip” for missing refs or when applying placeholders after user decision (ARCHITECTURE §4.8).
- **AC3.4.4** **user_decisions** schema: key = missing ref identifier (same as in missing_references), value = "skip" or absolute path to uploaded file. Align with Epic 2 human_input output. Missing refs trigger human-in-the-loop; on skip insert placeholders; on upload validate path, copy to assets, update ref in input file.
- **AC3.4.5** After applying decisions: clear missing_references, set pending_question to None, **route to agent** (not back to scan_assets). Store **source_file** with each missing ref (from 3.1) so insert_placeholder targets the correct input file. Document re-entry flow.
- **AC3.4.6** Upload path must be **validated** (InputSanitizer or allowed base; no path escape). Optional: config/flag to auto-apply placeholders without human prompt; document behavior.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement AssetHandler.insert_placeholder(session_id, image_identifier, target_file) | Dev | 3 SP | Replace image markdown matching identifier with canonical placeholder in target_file (inputs/x or temp_output.md); return confirmation. |
| 2 | Define where placeholders are applied (input files vs temp_output) | Dev | 1 SP | For skip: apply to input files (target = source_file from scan); document; support temp_output for error pipeline. |
| 3 | Wire human_input: prompt message from pending_question, collect user_decisions | Dev | 2 SP | When routing to human_input, show missing_references; user returns user_decisions (key = ref id, value = "skip" or upload path); update state. |
| 4 | Implement post-decision flow: apply placeholders for "skip", handle "upload" | Dev | 4 SP | For each (ref_id, decision): if skip → insert_placeholder(session_id, ref_id, target_file_for_ref); if upload → validate path, copy to assets, update ref in input file. Clear missing_references, pending_question = None; route to agent. |
| 5 | State updates: user_decisions schema and clearing missing_references | Dev | 2 SP | user_decisions: key = ref id, value = "skip" or path; after applying, set missing_references = []; set pending_question = None; document for Epic 2. |
| 6 | Unit tests: AssetHandler.insert_placeholder | QA/Dev | 2 SP | Temp file with image ref; call insert_placeholder with target_file; assert content updated. |
| 7 | Integration test: scan_assets → human_input → skip → placeholders → agent | QA/Dev | 3 SP | Mock or real human input returning "skip" for all; assert placeholders in content and graph proceeds to agent. |
| 8 | Optional: config/flag to auto-apply placeholders without human prompt | Dev | 2 SP | If configured, skip human_input and call insert_placeholder for all missing; document in DoD. |
| 9 | Document interrupt flow and user_decisions in ARCHITECTURE | Dev | 1 SP | Epic 2 integration: when missing_references, interrupt; user_decisions format; re-entry to agent. |
| 10 | Define user_decisions schema and document for Epic 2 human_input | Dev | 1 SP | TypedDict or doc; key = ref id, value = "skip" or upload path; align with human_input output. |
| 11 | Store source_file with each missing ref (missing_ref_details or from scan) | Dev | 1 SP | Use (original_path, source_file) for missing refs so insert_placeholder knows target file. |
| 12 | Validate upload path (sanitizer or allowed base); copy to assets and update ref | Dev | 2 SP | Reuse InputSanitizer or path check; copy; rewrite in input file. |
| 13 | Document re-entry: after apply, clear missing_references, route to agent | Dev | 0.5 SP | DoD and story. |
| 14 | Unit test: upload path validation (reject path escape) | QA/Dev | 1 SP | Assert invalid upload path rejected. |

### Technical Risks & Dependencies

- **Risk:** Matching "the same" ref in content when applying placeholder (multiple refs to same path, or same filename from different dirs); use consistent identifier (resolved path or display path) in missing_references and insert_placeholder.
- **Dependency:** Epic 2 (human_input node, interrupt_before, state shape for pending_question and user_decisions); Story 3.1 (missing_references list).

### Definition of Done

- [ ] AssetHandler.insert_placeholder(session_id, image_identifier, target_file) implemented; canonical placeholder format; unit tested.
- [ ] user_decisions schema defined and documented for Epic 2; insert_placeholder targets input files (and temp_output) using source_file from scan.
- [ ] Human-in-the-loop wired: missing refs → human_input → user_decisions → placeholders for skip (with target_file), validate+copy for upload → clear missing_references → route to agent.
- [ ] Upload path validated; re-entry flow documented; integration test for skip path; security test for upload path; FC014 and FC006 satisfied; lint and type-check pass.

---

## Epic 3 Summary: Prioritization and Estimates

| Story | Summary | Story Points | Priority | Dependencies |
|-------|---------|--------------|----------|--------------|
| 3.1 | Asset scan: parse refs, resolve paths, detect missing | 19 | P0 | Epic 1, Epic 2.1 (minimal scan_assets) |
| 3.2 | Copy images to assets/, rewrite refs to relative | 19 | P1 | 3.1 |
| 3.3 | copy_image tool + agent integration | 15 | P1 | Epic 1, 2.2 |
| 3.4 | Placeholder insertion + human-in-the-loop | 24 | P1 | 3.1, Epic 2 |

**Suggested sprint order:** 3.1 first (full scan and classification); then 3.2 (copy and rewrite) and 3.3 (copy_image tool) can be parallel or 3.2 then 3.3; then 3.4 (placeholders and interrupt).  
**Total Epic 3:** ~77 SP (includes technical review tasks).

---

## Architecture Decisions (from Technical Review)

- **State:** `found_image_refs`: List[ImageRefResult] (original_path, resolved_path, source_file); set by scan_assets. `missing_references` replace vs append documented; optional `current_missing_references` if reducer does not support replace. For 3.4, missing refs include source_file (from scan or missing_ref_details).
- **Placeholder format:** Canonical `[Image Missing: {basename}]` used by copy_image and AssetHandler; document in ARCHITECTURE.
- **Path resolution:** Shared `resolve_image_path(path, base_dir)` and AssetScanSettings (allowed_base_path); env prefix ASSET_; same rules for scan_assets and copy_image.
- **user_decisions:** Dict[str, Literal["skip"] | str]; key = ref identifier, value = "skip" or upload path; align with Epic 2 human_input output.
- **insert_placeholder:** (session_id, image_identifier, target_file); target_file = "inputs/filename" or "temp_output.md".

---

## Technical Risks & Dependencies (Epic Level)

- **Path resolution:** Relative refs are resolved relative to the input file’s directory (session `inputs/`); absolute refs restricted to allowed base; URLs skipped. Document clearly to avoid security issues.
- **Epic 2 coupling:** Human-in-the-loop (interrupt, user_decisions) is defined in Epic 2; Epic 3 consumes it for missing refs. Ensure state shape and node contracts align.
- **Ordering:** Scan must run after session creation and file copy (Epic 1.4); graph starts at scan_assets (Epic 2.1). Epic 3 enhances scan_assets and adds copy_image and placeholder flow.

---

## MECE & Vertical Slice Check

- **MECE:** (1) Discovery and classification (3.1), (2) Copy and rewrite for found refs (3.2), (3) On-demand agent tool (3.3), (4) Missing ref handling and human-in-the-loop (3.4) are non-overlapping and cover FC008 and FC014.
- **Vertical slice:** Story 3.4 delivers the full slice for missing refs (scan → interrupt → user decision → placeholder or upload → continue). Stories 3.1–3.3 deliver the slice for existing refs (scan → copy → rewrite → agent can use copy_image).
- **Epic alignment:** FC008 (detect, resolve, copy, update refs) and FC014 (validate existence, copy to assets, placeholder when missing) are fully covered. Scan runs after initialization; missing refs trigger human-in-the-loop per Epic 2.
