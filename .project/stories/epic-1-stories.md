# Epic 1: Secure Input & Session Foundation — Story Decomposition

**Epic ID:** 1  
**Epic Goal:** Implement secure, multi-format input handling and per-request session isolation so every conversion runs in a dedicated, safe environment.  
**Business Value:** Prevents path traversal, executable uploads, and oversized files; enables concurrent runs without file clashes and clear audit per request.  
**Epic Acceptance Criteria (Reference):** FC001, FC007, FC012, FC016.

**Technical Review:** This backlog was updated with findings from the technical audit. See `.project/stories/epic-1-technical-review.md` for full detail. Key decisions: (1) Session creation and copy happen at **entry**; graph starts at `scan_assets` (no session create in graph). (2) Cleanup is **entry-owned** (after `workflow.invoke`). (3) Shared exception/config schemas and entry response type (`GenerateResult`) are part of the stories below.

---

## Story 1.1: Implement InputSanitizer (Path Resolution, Extensions, Size, Boundary)

### Refined Acceptance Criteria

- **AC1.1.1** Given a user-provided path, the sanitizer resolves it to an absolute path and rejects any path that escapes the allowed base directory (no `../` or symlinks outside base).
- **AC1.1.2** Only `.txt`, `.log`, `.md` are accepted (whitelist); `.exe`, `.dll`, `.so`, `.bin`, `.sh`, `.bat` (and any extension in a configurable blocklist) are rejected with a clear error.
- **AC1.1.3** Files over 100MB (configurable via constant/env) are rejected before any read.
- **AC1.1.4** UTF-8 readability is verified (or validation attempted) for allowed files; non-UTF-8 or binary detection leads to rejection.
- **AC1.1.5** All validation failures raise specific exceptions: `SecurityError` (path escape/symlink), `ValidationError` with code (extension/size/encoding), or `FileNotFoundError`; no generic bare exceptions.
- **AC1.1.6** Public API: `validate(path: str, base_dir: Path) -> Path` returning resolved, validated path; docstrings and type hints present. Config via `SanitizerSettings` (Pydantic) from env.
- **AC1.1.7** Validation order (enforced): resolve path → exists → under base_dir → extension (blocklist then whitelist) → size (`stat()` only, no full read) → UTF-8 check.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Design InputSanitizer interface and constants | Dev | 2 SP | Define `InputSanitizer` class, `ALLOWED_EXTS`, `BLOCKED_EXTS`, `MAX_FILE_SIZE`; document contract and error types in docstrings. |
| 2 | Implement path resolution and directory-boundary check | Dev | 3 SP | Resolve path with `Path.resolve()`, ensure `is_relative_to(base_dir)` (or equivalent); raise `SecurityError` if outside base; handle symlinks. |
| 3 | Implement extension whitelist and blocklist checks | Dev | 2 SP | Reject blocklist extensions; accept only whitelist; raise `ValidationError` with code (e.g. EXTENSION_BLOCKED) and clear message. |
| 4 | Implement file size limit and file-exists check | Dev | 2 SP | After path checks, `stat().st_size` vs `MAX_FILE_SIZE`; raise if over limit or file missing. Never read full file for size. |
| 5 | Add UTF-8 / binary sniff validation | Dev | 2 SP | After size check: attempt read with `encoding='utf-8'` or sample; reject binary/illegal UTF-8. |
| 6 | Unit tests: path traversal, extensions, size, encoding | QA/Dev | 3 SP | Tests for `../`, blocklist exts, oversized file, invalid UTF-8; fixtures for temp files; tag security tests e.g. `@pytest.mark.security`. |
| 7 | Integrate config (Pydantic/env) for limits and lists | Dev | 2 SP | Load via `SanitizerSettings`: allowed_extensions, blocked_extensions, max_file_size_bytes; env prefix e.g. INPUT_; keep ARCHITECTURE defaults. |
| 8 | Define shared exception types and error codes | Dev | 1 SP | Add `SecurityError` and `ValidationError(message, code)`; codes e.g. PATH_ESCAPE, EXTENSION_BLOCKED, FILE_TOO_LARGE, INVALID_UTF8; document in sanitizer contract. |
| 9 | Define Pydantic SanitizerSettings model | Dev | 1 SP | SanitizerSettings with allowed_extensions, blocked_extensions, max_file_size_bytes; load from env; use in InputSanitizer. |
| 10 | Document validation order and security test tag in DoD | Dev/QA | 1 SP | DoD: validation order (resolve→exists→base_dir→extension→size→UTF-8) documented; security-related tests tagged. |

### Technical Risks & Dependencies

- **Risk:** Symlinks may resolve outside `base_dir`; must use `resolve()` and then check containment.
- **Risk:** Very large file size check via `stat()` is cheap; avoid reading whole file for size.
- **Dependency:** None (foundation). Python 3.12+ `Path.is_relative_to`; for older Python, use `Path.resolve().relative_to(base_dir.resolve())` with try/except.

### Definition of Done

- [ ] `InputSanitizer` in `utils/sanitizer.py` (or agreed path) with full type hints and docstrings.
- [ ] All acceptance criteria verified by unit tests; >80% coverage for sanitizer module; security-related tests tagged (e.g. `@pytest.mark.security`).
- [ ] Validation order documented and implemented: resolve → exists → base_dir → extension → size → UTF-8; size via `stat()` only.
- [ ] `uv run ruff check .` and `uv run mypy src/` pass; no secrets hardcoded.
- [ ] SecurityError and ValidationError (with code) used consistently; no bare `except`. Config via SanitizerSettings from env.

---

## Story 1.2: Implement SessionManager (Create UUID Dirs, Cleanup/Archive)

### Refined Acceptance Criteria

- **AC1.2.1** `create()` generates a new UUID (e.g. uuid4), creates session root under configurable base (e.g. `./docs/sessions/{uuid}`), and creates subdirs: `inputs/`, `assets/`, `checkpoints/`, `logs/`.
- **AC1.2.2** `get_path(session_id: str) -> Path` returns the session root path; **does not check existence** (callers ensure session_id was created by this manager). Optional `exists(session_id) -> bool` if needed.
- **AC1.2.3** `cleanup(session_id: str, archive: bool = True)` either moves session to archive (e.g. `./docs/archive/{uuid}`) or deletes the tree; **archive parent directory created if missing**; cleanup failure policy (log vs raise) documented; no partial state left.
- **AC1.2.4** Directory layout matches ARCHITECTURE: exactly `inputs`, `assets`, `checkpoints`, `logs` under session root.
- **AC1.2.5** Creation is atomic enough that concurrent `create()` calls do not collide (UUID guarantees uniqueness); cleanup is idempotent or clearly documented.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define SessionManager interface and directory contract | Dev | 1 SP | Class API: `create() -> str`, `get_path(session_id) -> Path`, `cleanup(session_id, archive)`; document layout. |
| 2 | Implement create(): UUID generation and directory creation | Dev | 3 SP | Generate UUID, create base path, create all four subdirs with `mkdir(parents=True)`; return session_id. |
| 3 | Implement get_path() and session existence check | Dev | 1 SP | Return `Path(base / session_id)`; optional `exists()` check or documented behavior if missing. |
| 4 | Implement cleanup(): archive vs delete | Dev | 3 SP | If archive: ensure archive dir exists, move session tree; else rmtree; handle missing session gracefully. |
| 5 | Configuration for base path (sessions + archive) | Dev | 2 SP | Load via `SessionSettings` (Pydantic): base_path, sessions_dir, archive_dir; env e.g. DOCS_BASE_PATH, SESSIONS_DIR, ARCHIVE_DIR. |
| 6 | Unit tests: create layout, get_path, cleanup archive/delete | QA/Dev | 3 SP | Temp dir for tests; verify structure; verify archive and delete behavior. |
| 7 | Error handling and logging for cleanup failures | Dev | 1 SP | Log failures; document cleanup failure policy (log vs raise for archive/rmtree). |
| 8 | Define get_path contract and optional exists(session_id) | Dev | 1 SP | Document that get_path returns path without existence check; add exists(session_id) -> bool if needed. |
| 9 | Ensure archive parent exists before move; document cleanup failure policy | Dev | 1 SP | mkdir(archive_parent, parents=True) before move; document log vs raise for failures in DoD. |
| 10 | Add SessionSettings (Pydantic) for base_path, sessions_dir, archive_dir | Dev | 1 SP | Load from env; use in create() and cleanup(). |

### Technical Risks & Dependencies

- **Risk:** Cleanup while workflow still using session — lifecycle ownership must be clear (workflow finishes before cleanup, or cleanup is only called from known points).
- **Dependency:** None. Use standard library `uuid`, `pathlib`, `shutil`.

### Definition of Done

- [ ] `SessionManager` in `utils/session_manager.py` (or agreed path); type hints and docstrings.
- [ ] get_path contract documented (no existence check); cleanup failure policy and archive parent creation documented.
- [ ] Unit tests for create, get_path, cleanup (archive and delete); tests use temp directories.
- [ ] Lint and type-check pass; no hardcoded paths (SessionSettings from env).
- [ ] Directory layout matches ARCHITECTURE exactly.

---

## Story 1.3: File Discovery — List and Validate Requested Files Before Workflow Start

### Refined Acceptance Criteria

- **AC1.3.1** Given an allowed input directory (base path), the system lists all files in that directory that are valid for processing (by extension and sanitizer rules).
- **AC1.3.2** Given a user request (list of requested paths or names), the system validates each requested file against the filesystem (exists, within base, passes InputSanitizer) and returns a clear result: valid list + list of errors (missing, invalid type, too large, etc.).
- **AC1.3.3** No workflow step starts until file discovery and validation complete; "file not found" and similar errors are prevented before processing (FC007).
- **AC1.3.4** API: `list_available_files(base_dir: Path) -> list[Path]` (flat, non-recursive; allowed extension only); `validate_requested_files(requested: list[str], base_dir: Path) -> tuple[list[Path], list[FileValidationError]]` with errors as path + message + code (e.g. MISSING, EXTENSION_BLOCKED, FILE_TOO_LARGE, INVALID_UTF8, PATH_ESCAPE).
- **AC1.3.5** base_dir is the single allowed input root (absolute, resolved); document that it must be set to a dedicated input directory.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define file discovery API and integration with InputSanitizer | Dev | 2 SP | Design `list_available_files(base_dir)` and `validate_requested_files(requested, base_dir)`; reuse InputSanitizer; define return types. |
| 2 | Implement list_available_files | Dev | 2 SP | Iterate base_dir (non-recursive); filter by allowed extensions; return `list[Path]` (resolved under base_dir). |
| 3 | Implement validate_requested_files with per-file errors | Dev | 3 SP | For each requested path, run sanitizer.validate; collect valid Paths and list of FileValidationError (path, message, code). |
| 4 | Ensure base_dir is validated and safe | Dev | 1 SP | base_dir must be absolute, resolved; document as single allowed input root. |
| 5 | Unit tests: list only allowed exts; validate missing, invalid ext, oversized | QA/Dev | 3 SP | Fixtures: temp dir with .txt, .md, .exe; test validation outcomes and error structure. |
| 6 | Integration test: discovery + sanitizer together | QA/Dev | 2 SP | One test that lists and validates and asserts no workflow is started on invalid set. |
| 7 | Define FileValidationError (path, message, code) and return structure | Dev | 1 SP | TypedDict or dataclass; align codes with sanitizer (MISSING, EXTENSION_BLOCKED, FILE_TOO_LARGE, INVALID_UTF8, PATH_ESCAPE). |
| 8 | Document list_available_files return list[Path] and non-recursive behavior | Dev | 1 SP | Docstring and DoD: flat directory only; return resolved Paths. |
| 9 | Document base_dir as single allowed root | Dev | 0.5 SP | In docstring and DoD. |

### Technical Risks & Dependencies

- **Risk:** Large directories: listing is O(n); consider iteration without loading full list if scale required later.
- **Dependency:** Depends on Story 1.1 (InputSanitizer) being done.

### Definition of Done

- [ ] File discovery module (e.g. `utils/file_discovery.py`) with clear API; uses InputSanitizer; `list_available_files` returns `list[Path]`, `validate_requested_files` returns errors as `list[FileValidationError]`.
- [ ] base_dir contract and non-recursive behavior documented.
- [ ] Unit and integration tests; validation returns both valid list and structured error list (path, message, code).
- [ ] FC007 satisfied: validation against filesystem before workflow start; no "file not found" after discovery.
- [ ] Lint and type-check pass.

---

## Story 1.4: Copy Validated Inputs into Session `inputs/` and Wire Session Lifecycle into Workflow Entry

### Architecture Decision (from Technical Review)

- **Entry owns session lifecycle:** Session is created at entry (after validation); graph **does not** create session — graph starts at `scan_assets` (or a thin "session_ready" node). Cleanup is **entry-owned**: entry calls `SessionManager.cleanup(session_id, archive=success)` after `workflow.invoke` returns. Update ARCHITECTURE and graph so START → scan_assets (no initialize node that creates session).

### Refined Acceptance Criteria

- **AC1.4.1** After validation (Story 1.3), validated files are copied into the session’s `inputs/` directory (e.g. `session_path / "inputs" / path.name`); no path traversal in destination names. **Duplicate destination filenames:** last copy wins (documented).
- **AC1.4.2** Entry flow: validate_requested_files → [if no valid files return GenerateResult(success=False, validation_errors=...)] → SessionManager.create() → copy valid Paths to session inputs/ → build_initial_state(session_id, input_filenames) → workflow.invoke(initial_state) → SessionManager.cleanup(session_id, archive=(status=="complete")) → return GenerateResult.
- **AC1.4.3** Entry returns typed result: `GenerateResult` (success, session_id, output_path, error, validation_errors, messages). Initial state shape is documented and built via `build_initial_state(session_id, input_files: list[str])` with all required DocumentState keys and defaults.
- **AC1.4.4** If validation fails (no valid files), no session is created; return GenerateResult with validation_errors and success=False.
- **AC1.4.5** Cleanup runs in exactly one place (entry, after invoke); no other code path deletes or archives the session.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define workflow entry signature and state shape for session + inputs | Dev | 2 SP | Entry accepts list of paths; state includes session_id, input_files (names in session inputs/); document in ARCHITECTURE or graph.py. |
| 2 | Implement copy validated files into session inputs/ | Dev | 2 SP | Given list of validated Paths and session_id, copy each to `get_path(session_id) / "inputs" / path.name`; use shutil.copy. |
| 3 | Implement entry flow: create session → validate → copy → pass to graph | Dev | 5 SP | In entry (e.g. main or graph): create session; validate_requested_files; if any valid, copy into session inputs; set state; invoke graph; else cleanup and return error. |
| 4 | Wire session_id and input file list into first workflow node | Dev | 2 SP | Graph starts at scan_assets (no session create in graph); first node receives state with session_id and input_files; tools use session_id. |
| 5 | Integrate cleanup in entry after workflow.invoke | Dev | 3 SP | Entry calls SessionManager.cleanup(session_id, archive=(result["status"]=="complete")) after invoke; single cleanup owner; no cleanup in graph. |
| 6 | Error handling: validation failure and partial failure | Dev | 2 SP | If no valid files: return GenerateResult(success=False, validation_errors=...); no session created; log which files failed and why. |
| 7 | Integration test: full entry flow with temp files and session layout | QA/Dev | 3 SP | Invoke entry with mixed valid/invalid paths; assert session created, inputs/ populated, workflow receives correct data; assert cleanup after invoke. |
| 8 | Architecture decision: document entry-owned create+copy; graph starts at scan_assets | Dev/Arch | 1 SP | Document flow; update graph to remove session creation from initialize or remove initialize node; align ARCHITECTURE. |
| 9 | Define build_initial_state(session_id, input_files) and DocumentState defaults | Dev | 2 SP | Return DocumentState with session_id, input_files, current_file_index=0, status="scanning_assets", conversion_attempts=0, retry_count=0, etc.; document required keys. |
| 10 | Define GenerateResult TypedDict and entry return contract | Dev | 1 SP | success, session_id, output_path, error, validation_errors (list[FileValidationError]), messages; return on validation failure vs workflow failure vs success. |
| 11 | Document cleanup ownership and duplicate-filename policy | Dev | 1 SP | DoD: cleanup only in entry after invoke; duplicate destination names = last wins, documented. |
| 12 | Integration test: graph receives pre-filled state; no session create in graph | QA/Dev | 2 SP | Assert no session create inside graph; assert cleanup after invoke; state shape correct. |

### Technical Risks & Dependencies

- **Risk:** Race between cleanup and still-running tools: ensure cleanup is called only after workflow has finished using the session.
- **Dependency:** Stories 1.1 (InputSanitizer), 1.2 (SessionManager), 1.3 (File discovery) must be done.
- **Risk:** Duplicate filenames from different directories: copy with same name may overwrite; document or derive unique names if needed.

### Definition of Done

- [ ] Entry flow implemented: validate → create session → copy → build_initial_state → workflow.invoke → cleanup (entry-owned); graph starts at scan_assets with no session create in graph.
- [ ] GenerateResult and build_initial_state defined; initial state shape and cleanup ownership documented.
- [ ] Duplicate destination filenames policy documented (last wins).
- [ ] Integration tests: happy path, validation failure (no session created), and graph receives pre-filled state with no double-create; cleanup after invoke verified.
- [ ] FC012 and FC007 satisfied; session isolation and file discovery integrated.
- [ ] Lint and type-check pass; logging at key steps (session created, files copied, cleanup).

---

## Epic 1 Summary: Prioritization and Estimates

| Story | Summary | Story Points | Priority | Dependencies |
|-------|---------|--------------|----------|--------------|
| 1.1 | InputSanitizer | 19 | P0 | None |
| 1.2 | SessionManager | 17 | P0 | None |
| 1.3 | File discovery | 16 | P1 | 1.1 |
| 1.4 | Copy inputs + wire session lifecycle | 26 | P1 | 1.1, 1.2, 1.3 |

**Suggested sprint order:** 1.1 and 1.2 in parallel (or 1.1 first); then 1.3; then 1.4.  
**Total Epic 1:** ~78 SP (includes technical review additions; adjust to team scale).

---

## Architecture Decisions (from Technical Review)

- **Session creation:** Entry only. Graph does not create session; it starts at `scan_assets` with state already containing session_id and input_files.
- **Cleanup:** Entry-owned. Entry calls `SessionManager.cleanup(session_id, archive=...)` after `workflow.invoke` returns. No cleanup inside graph.
- **Schemas:** SanitizerSettings and SessionSettings (Pydantic) for config; SecurityError and ValidationError (with code) for sanitizer; FileValidationError for discovery; GenerateResult for entry return; build_initial_state() for DocumentState initial slice.
- **Config:** Env-loaded (e.g. INPUT_*, DOCS_BASE_PATH, SESSIONS_DIR, ARCHIVE_DIR); no hardcoded paths.

---

## MECE & Vertical Slice Check

- **MECE:** Input (sanitizer + discovery) vs Session (manager + lifecycle) vs Integration (copy + wire) are non-overlapping and cover all Epic 1 scope. Shared exception/config schemas are defined in 1.1 and consumed by 1.3/1.4.
- **Vertical slice:** Story 1.4 delivers an end-to-end slice: request in → validate → create session → copy → invoke graph (scan_assets…) → cleanup → return GenerateResult; 1.1–1.3 are enabling pieces.
- **Epic alignment:** FC001 (input validation), FC007 (file discovery), FC012 (session isolation), FC016 (path sanitization) are fully covered by the four stories above.
