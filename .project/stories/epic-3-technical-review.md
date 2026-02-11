# Epic 3: Asset & Reference Management — Technical Review

**Reviewer role:** Senior Software Architect / Agile Team Lead  
**Scope:** Technical deep-dive audit of decomposed stories; data models, APIs, feasibility, security, MECE, DoD.  
**Context:** Parent Epic 3, ARCHITECTURE.md (Agentic Document Generator), Epic 1 (session/inputs), Epic 2 (scan_assets, human-in-the-loop).

---

## Parent Epic Technical Context

### Architecture Assumptions

- **Orchestration:** LangGraph with graph starting at `scan_assets` (per Epic 1/2). Entry creates session and copies files; no session create inside graph. Epic 3 **enhances** the existing `scan_assets` node (minimal version in Epic 2.1) with full image parsing, path resolution, copy, and rewrite.
- **Tech stack:** Python 3.13, uv, pathlib, LangGraph. No DB; asset metadata is in-memory (state) and on-disk (session `inputs/`, `assets/`). Config via env; no new services or queues.
- **State model:** DocumentState already has `missing_references: Annotated[List[str], operator.add]`, `user_decisions: dict`, `pending_question: str`. Epic 3 consumes these; no new state keys are mandated, but **found refs** (for copy/rewrite) must be passed from 3.1 to 3.2 — either in state or as internal scan output (see gap below).
- **Human-in-the-loop:** Epic 2 defines interrupt before `human_input`, resume with updated state. Epic 3 uses this for missing refs: prompt user, collect `user_decisions`, then apply placeholders or handle upload and re-enter.

### Relevant ARCHITECTURE References

- **§3.1 Flow:** FileDiscovery → **ImageScan** → (missing? → HumanInput) → Agent. ImageScan = scan_assets node.
- **§4.4 copy_image tool:** `copy_image(source_path, session_id) -> str`; returns `./assets/{name}` or placeholder text if missing.
- **§4.8 AssetHandler:** `insert_placeholder(session_id, image_name) -> str`; replaces image markdown in **temp_output.md** with `**[Image Missing: image_name]**`. ARCHITECTURE uses exact match `![...]({image_name})` — fragile for varying alt text or path format.
- **§5.2–5.3 scan_assets_node:** ARCHITECTURE sample uses `Path(img_path).resolve()` (CWD-relative); **stories correctly specify resolution relative to input file directory** — alignment fix.
- **§5.1 DocumentState:** `missing_references` (reducer), `user_decisions`, `pending_question`. No explicit key for "found refs" or "asset scan result"; 3.1→3.2 handoff needs design.

### Cross-Epic Dependencies

- **Epic 1:** Session layout (`inputs/`, `assets/`), SessionManager.get_path, entry-owned create/copy. Base path for absolute refs should align with Epic 1 input base.
- **Epic 2:** DocumentState shape, scan_assets as first node, human_input node, interrupt/resume, `user_decisions` and `pending_question` semantics. Epic 3 must not change state schema in a breaking way; can extend (e.g. optional `asset_scan_result`).

---

## Story-by-Story Technical Audit

---

### Story 3.1: Asset Scan Node — Parse Inputs for Image Refs, Resolve Paths, Detect Missing

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Logic is clear; data handoff to 3.2 and path-resolution schema need definition. |
| Data Model | Needs Design Work | `missing_references` is specified; "found paths for downstream copy" is not in state — no schema for scan result. |
| API/Integration | Sound | Node reads state, updates state; no external API. |
| Technical Feasibility | Sound | Regex, path resolution, file existence are standard; task breakdown is realistic. |
| Vertical Slice | Partial | Scan only; copy/rewrite in 3.2. |
| Security/Compliance | Sound | Path escape and allowed base are tasked; logging (FC015) is in scope. |
| Dependencies & Risks | Low | Epic 1, 2.1; ARCHITECTURE sample resolves relative to CWD — stories fix to input-file dir. |
| MECE | Sound | Discovery/classification only; no overlap with 3.2–3.4. |
| DoD Technical | Needs Design Work | Add scan result schema and handoff contract; performance (large files) not specified. |

#### Strengths

- Explicit resolution order: URL skip → relative (to input file dir) → absolute (under base) → existence check.
- Security: no path escape; absolute paths restricted to allowed base.
- Extraction helper and unit tests for regex edge cases (nested brackets, spaces).
- Structured logging per file and per ref.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Scan result not in state:** Story says "found paths are recorded for downstream copy (Story 3.2)" but does not define where. DocumentState has no `found_references` or `asset_scan_result`. Options: (a) add state key e.g. `found_image_refs: List[Tuple[str, Path]]` (original path + resolved path), or (b) scan_assets does copy+rewrite in the same node (so 3.1 and 3.2 merge in one node). Recommendation: **add a state key** or an internal return structure so 3.2 has a defined input (see Proposed Designs).
2. **Reducer vs replace for missing_references:** State uses `Annotated[List[str], operator.add]`. Scan_assets typically **replaces** the list for the current run (new scan = new list), not appends. So either: (i) scan_assets sets `missing_references` by **replacing** (LangGraph may require special handling to replace rather than add), or (ii) clear then append. Document intended semantics; if reducer always appends, a "scan result" key might hold the current scan and missing_references could be cumulative (unusual). Recommendation: **document that for scan_assets, missing_references is set by full replacement** (e.g. node returns state with missing_references = current list); confirm LangGraph reducer allows overwrite for this key or use a non-reducer key for "current missing."
3. **Path resolution base for absolute paths:** "Allowed base" for absolute paths is not defined. Should match Epic 1 input base (e.g. same as `base_dir` in validate_requested_files) or session root. Propose: **AssetScanSettings** (or reuse entry base_dir) with `allowed_base_path: Path`; document in story.
4. **Image ref regex edge cases:** Markdown allows spaces in URL/path and optional title: `![alt](url "title")`. Regex `!\[.*?\]\((.*?)\)` may capture `url "title"` or break on spaces. Propose: capture group for path only; strip optional `"title"`; document supported markdown image syntax.

#### Proposed Technical Designs

**1. Scan result schema (state or internal)**

Option A — add to DocumentState (recommended for clarity):

```python
# In state.py / DocumentState
# Optional; set by scan_assets, read by copy/rewrite step
found_image_refs: List[Tuple[str, str]]  # (original_path_as_in_md, resolved_absolute_path_str)
# Or a small TypedDict:
class ImageRefResult(TypedDict):
    original_path: str   # as in markdown
    resolved_path: str  # absolute, validated
    source_file: str    # input filename where ref was found
found_image_refs: List[ImageRefResult]
```

Option B — same node does scan + copy + rewrite (3.1+3.2 in one node): no new key; "found" refs are processed inside the node and never stored. Then 3.2 becomes "extract copy+rewrite into reusable helpers and call from scan_assets."

Recommendation: **Option A** with `found_image_refs` (or `asset_scan_result`) so 3.2 can be a separate node or a clear sub-step, and so tests can assert on scan output without running copy.

**2. missing_references semantics**

- For scan_assets: output state should set "current scan" missing list. If reducer appends, either use a different key for "current missing" (e.g. `current_missing_references`) and copy to `missing_references` for human_input, or document that this node **replaces** (e.g. by returning state where this key is the new list — LangGraph reducers typically merge; need to verify). If replace is not supported, add `current_missing_references: List[str]` (no reducer) set by scan_assets; conditional edge uses that; when sending to human_input, copy to `missing_references` or use `current_missing_references` in the prompt.
- DoD: document whether scan_assets replaces or appends to `missing_references` and how human_input gets the list.

**3. Path resolution config**

```python
# config or scan_assets_node
class AssetScanSettings(BaseSettings):
    allowed_base_path: Optional[Path] = None  # for absolute path validation; default = session inputs parent or entry base
    model_config = {"env_prefix": "ASSET_", "extra": "ignore"}
```

**4. Image syntax and regex**

- Support: `![alt](path)` and `![alt](path "title")`. Regex: capture path only; strip trailing `"title"` if present. Document: "We support path and optional title; URL query params are preserved in path."
- Unit test: `![x](a/b.png "t")` → path `a/b.png` (or `a/b.png "t"` then strip title).

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 10 | Define scan result schema (found_image_refs or asset_scan_result) and set in state | Dev | 2 SP | Add key to DocumentState; scan_assets populates it for found refs (original path, resolved path, source file). |
| 11 | Document missing_references replace vs append; ensure conditional edge uses correct key | Dev | 1 SP | If reducer appends, introduce current_missing_references for scan output; document in DoD. |
| 12 | Define allowed base for absolute paths (config or Epic 1 base_dir) | Dev | 1 SP | AssetScanSettings or pass base from entry; document in story. |
| 13 | Extend regex/tests for optional title in image syntax | Dev/QA | 0.5 SP | Support `](path "title")`; strip title from path; add test. |

#### Revised Story (Technical Specs)

- **DoD addition:** Scan result schema (found_image_refs / asset_scan_result) defined and set by scan_assets; missing_references (or current_missing_references) semantics documented; allowed base for absolute paths configured; image syntax (optional title) and regex documented and tested.
- **Contract:** scan_assets reads `session_id`, `input_files`; writes `missing_references` (or current), `pending_question`, `status`, and **found_image_refs** (or equivalent); conditional edge uses missing list for human_input vs continue.

---

### Story 3.2: Copy Available Images to Session `assets/` and Rewrite Refs to Relative Paths

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Copy and rewrite logic is clear; input contract from 3.1 and in-place vs view decision need specification. |
| Data Model | Needs Design Work | No explicit schema for "which refs to copy" (depends on 3.1 handoff); rewrite target (file path or key) undefined. |
| API/Integration | Sound | Same node or sub-step as 3.1; no new endpoints. |
| Technical Feasibility | Sound | shutil.copy and string replace are standard; encoding and idempotency are called out. |
| Vertical Slice | Partial | Depends on 3.1 output. |
| Security/Compliance | Sound | Writes only to session/assets; no path escape. |
| Dependencies & Risks | Medium | 3.1 must expose found refs; in-place rewrite can corrupt if replace is wrong. |
| MECE | Sound | Copy + rewrite only; 3.1 = classify, 3.2 = apply. |
| DoD Technical | Needs Design Work | Idempotency and rollback not specified; test for encoding preservation. |

#### Strengths

- Collision policy (last-copy-wins or indexed) and logging are in scope.
- Rewrite only the path inside `](...)`; preserve alt text.
- Explicit choice: in-place rewrite of inputs/ vs resolved view; ARCHITECTURE suggests in-place.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Input contract from 3.1:** 3.2 assumes "found refs from Story 3.1" — must consume `found_image_refs` (or equivalent) from state. Add AC: "Copy step reads found_image_refs (or asset_scan_result) from state; each entry has original_path and resolved_path (and optionally source_file)."
2. **Rewrite target and matching:** Rewrite is "replace original path with ./assets/basename" in "source content." If same file has two refs to the same resolved path, both should become the same `./assets/basename`. If two different original paths (e.g. `./img/a.png` and `../other/a.png`) resolve to the same file, last-copy-wins means one file in assets; both refs in content should be replaced with that same path. **Matching:** replace each occurrence of the **original_path** (as it appeared in markdown) with `./assets/basename` — but original_path might have been normalized (e.g. `./x` vs `x`). Define: replace by **exact string** of original path as captured by regex, or normalize before replace. Recommendation: use the exact string from the regex capture so that replace is deterministic and no accidental double-replace.
3. **In-place rewrite and encoding:** Story says "use same encoding (UTF-8)" and "replace only the path part." Add task: "Ensure file read and write use UTF-8; verify no BOM or line-ending change."
4. **Idempotency:** If scan_assets + copy/rewrite is run again (e.g. after user upload), running copy again should be safe (overwrite same assets/ file). Document: "Copy and rewrite are idempotent for the same scan result."

#### Proposed Technical Designs

**1. Copy input (from state)**

- Read `state["found_image_refs"]` (or `asset_scan_result`). Each item: `original_path`, `resolved_path`, `source_file`. For each item: copy `resolved_path` → `session_path / "assets" / basename(resolved_path)`; then in content of `source_file`, replace substring `](original_path)` with `](./assets/basename)` (preserve `![alt]` part). If multiple refs to same resolved path, copy once; replace all matching original_path strings in the relevant file(s).

**2. Replace strategy**

- Use **exact** original path string from regex capture for replace (no normalization). So if markdown has `](./a.png)` and `](a.png)`, treat as two refs if both exist; replace each with same `./assets/a.png` if they resolve to same file.
- Regex for replace: to avoid replacing in non-image context, replace only inside image syntax: e.g. find `!\[.*?\]\((original_path_escaped)\)` and replace with `![same_alt](./assets/basename)` (preserve alt). So replacement is per-ref, not global string replace.

**3. File to rewrite**

- "Source content" = content of each input file in `inputs/`. After all copies, for each input file that had refs, read file, apply replacements, write back. Order: can process per source_file; for each ref in that file, replace; write once per file.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 10 | Consume found_image_refs from state; document input contract | Dev | 1 SP | AC: copy step reads state["found_image_refs"]; handle empty list. |
| 11 | Implement replace using exact original path and image-pattern scope | Dev | 1 SP | Replace only within image syntax; preserve alt; use escaped original_path. |
| 12 | Add test: UTF-8 and line endings preserved after rewrite | QA/Dev | 1 SP | Fixture with UTF-8 and CRLF/LF; assert no corruption. |
| 13 | Document idempotency of copy+rewrite for same scan result | Dev | 0.5 SP | DoD: idempotent when run again with same found refs. |

#### Revised Story (Technical Specs)

- **DoD addition:** Copy reads `found_image_refs` from state; replace uses exact original path within image syntax; UTF-8 and line-ending test; idempotency documented.
- **Contract:** Copy step is either same node as scan (scan_assets does classify + copy + rewrite) or a dedicated node that runs after scan and reads `found_image_refs`; output is updated files in inputs/ and files in assets/.

---

### Story 3.3: Add `copy_image` Tool and Integrate with Agent for On-Demand Asset Handling

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Architecturally Sound** | Tool contract and path validation are clear; minor schema and allowed-base details. |
| Data Model | Sound | No persistent model; tool I/O is path in, path or placeholder out. |
| API/Integration | Sound | get_tools(session_id) and tool factory pattern from Epic 2.2. |
| Technical Feasibility | Sound | Realistic; reuses same path resolution as 3.1 for consistency. |
| Vertical Slice | Partial | Tool only; agent prompt update is in scope. |
| Security/Compliance | Sound | Path validation and allowed base are tasked; agent cannot pass session_id. |
| Dependencies & Risks | Low | Epic 1, 2.2; shared path-resolution logic with 3.1 reduces drift. |
| MECE | Sound | On-demand tool only; 3.2 is batch at scan time. |
| DoD Technical | Sound | Unit and integration tests; add allowed-base alignment with 3.1. |

#### Strengths

- Session_id from tool factory (no agent-passed session_id); path validation (no traversal).
- Placeholder return instead of exception (FC014); tool description for LLM.
- Agent prompt update to mention copy_image.

#### Critical Gaps (Data Model, APIs, Infra)

1. **Allowed base for source_path:** "Resolve relative to session inputs/ or configured base" — should match 3.1 (same allowed_base_path or entry base). Propose: copy_image uses the same resolution helper as scan_assets (relative to session inputs dir for relative paths; absolute must be under same allowed base). Add task: "Reuse or align path resolution with scan_assets allowed base."
2. **Placeholder format consistency:** Story uses `[PLACEHOLDER: filename]`; Story 3.4 uses `**[Image Missing: identifier]**`. For agent-inserted content (3.3), placeholder should be recognizable by downstream (e.g. MD→JSON or quality check). Recommend: **single canonical format** (e.g. `[Image Missing: {name}]`) and use it in both copy_image return and AssetHandler.insert_placeholder; document in Epic DoD.
3. **Basename extraction for placeholder:** When file is missing, "filename" could be the full path the agent passed. Use basename for placeholder text so it's short and consistent (e.g. `[Image Missing: diagram.png]`).

#### Proposed Technical Designs

**1. Path resolution reuse**

- Extract from 3.1 a shared helper: `resolve_image_path(path: str, base_dir: Path) -> Path | None` (returns None if invalid or outside base). copy_image calls it with base_dir = session_path / "inputs" (or allowed_base_path). Ensures 3.1 and 3.3 use same rules.

**2. Placeholder format (Epic-wide)**

- Standard: `[Image Missing: {basename}]` (or `**[Image Missing: {basename}]**` for visibility in markdown). copy_image returns that string when file missing; AssetHandler.insert_placeholder writes the same. Document in Epic 3 DoD.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 9 | Align copy_image path resolution with scan_assets (reuse helper or same allowed base) | Dev | 1 SP | Use same resolve_image_path or config; document. |
| 10 | Use canonical placeholder format; use basename in placeholder text | Dev | 0.5 SP | e.g. [Image Missing: {basename}]; document in Epic 3. |

#### Revised Story (Technical Specs)

- **DoD addition:** copy_image path resolution aligned with 3.1; placeholder format is canonical and uses basename; document in ARCHITECTURE.
- **Contract:** copy_image(source_path) [session_id from factory]; returns `./assets/basename` or canonical placeholder string; path validated against same base as scan_assets.

---

### Story 3.4: Placeholder Insertion for Missing Images and Optional Human-in-the-Loop (Epic 2 Interrupt)

| Dimension | Score | Notes |
|-----------|--------|--------|
| **Overall** | **Needs Design Work** | Flow and AssetHandler are specified; user_decisions schema, target file for placeholders, and re-entry routing need design. |
| Data Model | Needs Design Work | user_decisions structure (per-ref key, "skip" vs path value) and where placeholders are applied (inputs vs temp_output) are underspecified. |
| API/Integration | Needs Design Work | human_input payload and resume payload (how user sends decisions) not defined; Epic 2 interrupt contract must align. |
| Technical Feasibility | Sound | Placeholder replace and conditional routing are standard. |
| Vertical Slice | Sound | Full slice: scan → interrupt → decisions → placeholders/upload → agent. |
| Security/Compliance | Needs Design Work | Upload path must be validated (Epic 1 sanitizer or session-bound); audit of user decision not tasked. |
| Dependencies & Risks | Medium | Epic 2 human_input contract; matching ref to placeholder (identifier consistency). |
| MECE | Sound | Missing-ref handling only; 3.3 is on-demand tool. |
| DoD Technical | Needs Design Work | user_decisions schema and re-entry flow in DoD; test for upload path validation. |

#### Strengths

- AssetHandler.insert_placeholder and human-in-the-loop flow are in scope.
- Skip → placeholders, upload → copy and update refs; optional auto-placeholder config.
- Integration test for skip path.

#### Critical Gaps (Data Model, APIs, Infra)

1. **user_decisions schema:** Story says "dict mapping ref or path to 'skip' or path string." Keys must be stable: use the same identifier as in `missing_references` (e.g. resolved path string or display path). Value: "skip" | "<uploaded_path>". Schema: `user_decisions: Dict[str, Literal["skip"] | str]`; key = missing ref identifier (as in missing_references); value = "skip" or absolute path to uploaded file. Document so Epic 2 human_input can produce this structure.
2. **Where to insert placeholders:** ARCHITECTURE AssetHandler writes to **temp_output.md**. But missing refs are in **input files** (not yet in temp_output when scan runs). So: (a) placeholders for "skip" go into **input files** (so when agent reads input, it sees placeholder), or (b) go into temp_output only (then only refs that agent has already written to temp_output get placeholders — refs only in inputs would never get replaced). Recommendation: **apply placeholders to input files** for refs that were in inputs and user chose skip; AssetHandler.insert_placeholder should accept target: "inputs" (and which file) or "temp_output". So either two modes or two calls (per input file). Design: `insert_placeholder(session_id, image_identifier, target_file: str)` where target_file is relative to session (e.g. `inputs/doc.md` or `temp_output.md`). For scan-time skip: call for each input file that had missing refs, target = that input file.
3. **Matching ref to placeholder:** "Corresponding image markdown" — match by identifier. Options: (i) replace **all** refs in the file that match this path (e.g. same original path string), or (ii) replace by position if we stored line/offset (complex). Use (i): for each skipped ref, in the file where it appeared, replace `![*](identifier)` (or original path as in content) with placeholder. Identifier must match what's in the file: use **original path as in markdown** (from scan result). So store in missing_references the original path string (or a key that maps 1:1); user_decisions key is same; insert_placeholder finds that string in the target file and replaces.
4. **Upload path validation:** When user sends a path for "upload," validate with InputSanitizer (or at least path under allowed base, file exists, allowed type). Copy to session assets and update ref in content (same as 3.2 rewrite). Add task: "Validate uploaded path; copy to assets; update ref in input file."
5. **Re-entry after human_input:** After applying skip (placeholders) and upload (copy + update), clear `missing_references` (or set to []), set `pending_question` to None, then route to **agent** (not back to scan_assets unless we want to re-scan). If we re-scan after upload, we could discover more missing; simpler is: apply decisions → clear missing_references → go to agent. Document in story.
6. **Reducer and missing_references clear:** If missing_references uses reducer (append), "clearing" requires returning state that sets it to [] — reducer may not support that. Use a non-reducer key for "current missing" (see 3.1) and set that to [] after processing; or document LangGraph pattern for "reset list."

#### Proposed Technical Designs

**1. user_decisions schema**

```python
# user_decisions: Dict[str, Union[Literal["skip"], str]]
# Key = identifier of missing ref (same as in missing_references list)
# Value = "skip" or absolute path to uploaded file
# Example: {"../images/a.png": "skip", "/allowed/base/new.png": "/allowed/base/new.png"}
```

**2. insert_placeholder API**

```python
def insert_placeholder(
    session_id: str,
    image_identifier: str,  # original path as in markdown (or key from missing_references)
    target_file: str        # "temp_output.md" or "inputs/<filename>"
) -> str:
    """Replace image markdown matching identifier in target file with placeholder."""
    path = session_path / target_file
    content = path.read_text(encoding="utf-8")
    # Replace ![...](identifier) with placeholder (regex to preserve alt)
    new_content = replace_image_ref_with_placeholder(content, image_identifier)
    path.write_text(new_content, encoding="utf-8")
    return f"Inserted placeholder for {image_identifier}"
```

**3. Post-decision flow (node or subgraph)**

- Input: state with user_decisions and current_missing_references (or missing_references).
- For each (ref_id, decision) in user_decisions:
  - if "skip": call insert_placeholder(session_id, ref_id, target_file_for_ref(ref_id)) — target = input file where ref was found (from scan result; need source_file in missing ref record).
  - if path: validate path; copy to assets; find ref_id in content of source file, replace with ./assets/basename.
- Set missing_references = [] (or current_missing_references = []), pending_question = None.
- Return state; conditional edge routes to agent.

**4. missing_references content for matching**

- Store in missing_references either (a) original path string as in markdown, or (b) a stable id. Recommendation: **original path string** so we can match in content and use as user_decisions key. When applying skip, we need to know **which input file** the ref was in — so scan result should store (original_path, source_file). So missing_references could be `List[str]` (original paths) and we look up source file from scan result; or missing_references is `List[Tuple[str, str]]` (original_path, source_file). Propose: **extend to List[dict]** or keep two parallel lists: missing_ref_identifiers and missing_ref_source_files. Simpler: store in state `missing_ref_details: List[{original_path, source_file}]` and use that for both prompt and placeholder application.

#### Missing Tasks (Add to Breakdown)

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 10 | Define user_decisions schema (key = ref id, value = "skip" | path) and document for Epic 2 | Dev | 1 SP | TypedDict or doc; align with human_input output. |
| 11 | Extend insert_placeholder to accept target_file (inputs/x or temp_output.md) | Dev | 2 SP | Implement; for skip, call per (ref, source_file). |
| 12 | Store source_file with each missing ref (missing_ref_details or parallel list) | Dev | 1 SP | Scan produces (original_path, source_file) for missing; use when applying placeholder. |
| 13 | Validate upload path (sanitizer or allowed base); copy to assets and update ref | Dev | 2 SP | Reuse InputSanitizer or path check; copy; rewrite in input file. |
| 14 | Document re-entry: after apply, clear missing_references, route to agent | Dev | 0.5 SP | DoD and story. |
| 15 | Unit test: upload path validation (reject path escape) | QA/Dev | 1 SP | Assert invalid upload path rejected. |

#### Revised Story (Technical Specs)

- **DoD addition:** user_decisions schema and target_file for insert_placeholder; missing ref includes source_file; upload path validated and copied; re-entry to agent documented; security test for upload path.
- **Contract:** human_input returns state with user_decisions populated; post-decision node applies skip (insert_placeholder per ref in correct input file) and upload (validate, copy, rewrite); then route to agent with missing_references cleared.

---

## Overall Technical Roadmap

### Missing Foundational Work

1. **State schema for asset scan:** Add `found_image_refs` (or `asset_scan_result`) and clarify `missing_references` replace vs append; consider `current_missing_references` and/or `missing_ref_details` (with source_file) for 3.4. **Decision:** Product/tech lead to approve one state shape and document in ARCHITECTURE.
2. **Path resolution shared module:** Extract `resolve_image_path(path, base_dir)` (and allowed-base config) used by both scan_assets and copy_image; document allowed base (Epic 1 base_dir or session inputs).
3. **Placeholder format:** Canonical format `[Image Missing: {basename}]` (or with bold) used by copy_image and AssetHandler; document in Epic 3 and ARCHITECTURE.

### Schema Proposals Summary

| Item | Proposal |
|------|----------|
| found_image_refs | `List[ImageRefResult]` with original_path, resolved_path, source_file; set by scan_assets. |
| missing_references / current_missing | Document replace vs append; optionally current_missing_references (no reducer) for scan output. |
| missing_ref_details | If needed for 3.4: list of {original_path, source_file} for missing refs. |
| user_decisions | `Dict[str, Literal["skip"] \| str]`; key = ref identifier, value = "skip" or upload path. |
| insert_placeholder | (session_id, image_identifier, target_file: str); target_file = "inputs/f" or "temp_output.md". |
| AssetScanSettings | allowed_base_path for absolute refs; env prefix ASSET_. |

### Architecture Decisions Needed

1. **Scan and copy in one node vs two:** Option A: single scan_assets node does classify + copy + rewrite (3.1+3.2); Option B: scan_assets only classifies and writes found_image_refs; separate node or sub-step does copy+rewrite. Recommendation: **Option B** (separate) for testability and single responsibility; add one "apply_assets" or keep copy+rewrite inside scan_assets as second phase in same node — decide and document.
2. **Reducer for missing_references:** If LangGraph reducer only appends, introduce a non-reducer key (e.g. current_missing_references) for "this scan's missing list" and use it for conditional edge and for 3.4; optionally copy to missing_references for logging. Confirm with LangGraph 1.x behavior.
3. **Human_input contract (Epic 2):** Epic 2 must define how human_input receives and returns state (e.g. interrupt returns state with user_decisions filled). Epic 3 must consume that; align key names and schema in Epic 2 technical review or joint backlog.

### Cross-Story Consistency

- **3.1 and 3.3:** Same path resolution and allowed base; shared helper recommended.
- **3.1 and 3.2:** Clear handoff via found_image_refs; 3.2 reads it and writes assets/ and inputs/.
- **3.3 and 3.4:** Same placeholder format; 3.4 applies to inputs (and optionally temp_output) with same text.
- **3.4 and Epic 2:** user_decisions schema and re-entry flow; human_input node output shape.

### DoD Additions (Epic Level)

- Placeholder format is canonical and documented.
- Path resolution (relative to input file dir; absolute under base; URL skip) is documented and tested.
- Upload path in 3.4 is validated (no path escape; allowed base).
- Scan result and missing-ref semantics (replace/append, current_missing) documented.

---

## Summary Scores

| Story | Technical Score | Main Gaps |
|-------|-----------------|-----------|
| 3.1 | Needs Design Work | Scan result schema; missing_references semantics; allowed base; regex for title |
| 3.2 | Needs Design Work | Input from 3.1 (found_image_refs); replace strategy; UTF-8 test; idempotency |
| 3.3 | Architecturally Sound | Align path resolution and placeholder format with 3.1/3.4 |
| 3.4 | Needs Design Work | user_decisions schema; insert_placeholder target_file; missing ref + source_file; upload validation; re-entry |

**Recommendation:** Implement schema and path-resolution decisions (state keys, shared helper, placeholder format) before or in parallel with 3.1; add the missing tasks to each story and align with Epic 2 human_input contract.
