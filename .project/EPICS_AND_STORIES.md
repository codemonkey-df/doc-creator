# DocForge — EPICs & Stories

> Work decomposition aligned with ARCHITECTURE.md phases.
> Each EPIC = one milestone. Each Story = one workable unit (1–2 days max).

---

## EPIC 1 — Core TUI Foundation
**Milestone:** App launches, shows files, accepts slash commands, state updates in real time.
**Goal:** Developer can run `uv run main.py`, see detected `.md` files, map them to intro/chapters via commands, and see the outline update live.
**Done when:** All commands work, UI renders correctly, no pipeline yet needed.

---

### Story 1.1 — Project Scaffold & Entry Point

**Description**
Set up the `uv` project, folder structure, and `main.py` so the app can be launched with `uv run main.py` or `uv run main.py --input /path`.

**Tasks**
- [ ] Init `uv` project with `pyproject.toml` (deps: `rich`, `watchdog`, `litellm`, `pydantic`)
- [ ] Create directory skeleton: `src/tui/`, `src/scanner/`, `src/llm/`, `src/pipeline/`, `src/converter/`, `converter/`, `input/`
- [ ] `main.py` parses `--input <folder>` (default: `./input`) and list of positional file args
- [ ] If files passed as args, copy them into `input/` folder
- [ ] Placeholder `AppState` dataclass in `src/tui/state.py` with `title`, `intro_file`, `chapters`, `detected_files`, `log_lines`
- [ ] `main.py` prints "DocForge starting..." and exits cleanly

**Acceptance Criteria**
- `uv run main.py` runs without error
- `uv run main.py --input ./docs` sets input folder to `./docs`
- `uv run main.py file1.md file2.md` copies both files to `input/` and resolves them
- `AppState` instantiates with correct defaults

**Definition of Done**
- [ ] Project installs cleanly with `uv sync`
- [ ] `main.py` accepts all three invocation styles
- [ ] `AppState` and `ChapterEntry` dataclasses exist and have correct fields
- [ ] No runtime errors on startup

---

### Story 1.2 — TUI Layout & Live Render

**Description**
Build the two-panel `rich` layout: Sources (left), Outline (right), Log (bottom), Command prompt (footer). The layout renders and refreshes via `rich.live.Live`.

**Tasks**
- [ ] `src/tui/app.py`: create `DocForgeApp` class with `rich.layout.Layout` and `rich.live.Live`
- [ ] `src/tui/panels.py`: implement `render_sources(state)`, `render_outline(state)`, `render_log(state)` — each returns a `rich.panel.Panel`
- [ ] Layout splits: top 70% = two columns (Sources | Outline), bottom 20% = Log, footer = prompt line
- [ ] `DocForgeApp.run()` starts the Live loop with `refresh_per_second=4`
- [ ] Prompt line shows `> ` and current partial input (read from shared input buffer)
- [ ] Sources panel lists `[1] filename.md` for each detected file
- [ ] Outline panel shows Title, Intro, and numbered chapters

**Acceptance Criteria**
- UI renders without errors on 80×24 terminal
- Sources panel shows file list with numeric IDs
- Outline panel shows default `Title: Untitled`, `Intro: (none)`, `Chapters: (none)`
- Log panel shows last N log lines
- Layout does not flicker on refresh

**Definition of Done**
- [ ] `DocForgeApp.run()` renders all 4 panels
- [ ] Manual test: resize terminal, UI adapts without crash
- [ ] Sources/Outline/Log all update when `AppState` changes

---

### Story 1.3 — File Detection from Input Folder

**Description**
On startup, scan the input folder for `.md` files and populate `AppState.detected_files`. Use `watchdog` to watch for files added/removed at runtime and refresh the UI within 2 seconds.

**Tasks**
- [ ] On startup: scan input folder with `Path.glob("*.md")`, populate `state.detected_files`
- [ ] `src/tui/watcher.py`: `FileWatcher` class using `watchdog.observers.Observer`
- [ ] `FileWatcher` takes a callback; fires `on_created` / `on_deleted` events
- [ ] On event: update `state.detected_files`, append log message, trigger UI refresh
- [ ] `FileWatcher` runs in a daemon `threading.Thread` so it doesn't block the main loop
- [ ] Assign stable numeric IDs: sorted by filename, re-indexed on change

**Acceptance Criteria**
- Files in `input/` at startup appear in Sources panel immediately
- Dropping a new `.md` into `input/` at runtime appears within 2 seconds
- Removing a file removes it from the list within 2 seconds
- IDs are reassigned after removal (no gaps)

**Definition of Done**
- [ ] Unit test: create temp dir, create file, assert callback fires within 2s
- [ ] Unit test: delete file, assert callback fires
- [ ] Manual test: drop file into `input/` while app runs — UI updates

---

### Story 1.4 — Slash Command Parser & Handlers

**Description**
Implement the command input loop and all slash commands: `/title`, `/intro`, `/chapter`, `/remove`, `/reset`, `/help`, `/quit`.

**Tasks**
- [ ] `src/tui/commands.py`: `parse_command(raw: str) -> Command | None` — splits `/cmd arg1 "quoted arg"`
- [ ] Command input loop: read line from stdin without blocking `Live`; use `threading.Thread` for input
- [ ] `/title "My Doc"` — sets `state.title`, logs confirmation
- [ ] `/intro <id>` — validates ID exists, sets `state.intro_file`, marks file as used in Sources panel
- [ ] `/chapter <id>` — appends to `state.chapters`; `/chapter <id> "Custom Title"` sets `custom_title`
- [ ] `/remove <chapter_index>` — removes chapter at 1-based index from `state.chapters`
- [ ] `/reset` — clears `intro_file` and `chapters`
- [ ] `/help` — prints command list to log panel
- [ ] `/quit` — stops Live loop and exits
- [ ] Invalid ID → log error message in red; do not crash
- [ ] Used files in Sources panel get a `✓` marker (green)

**Acceptance Criteria**
- All 8 commands execute without error
- `/intro 99` with no file 99 logs `"Error: no file with ID 99"` and does nothing
- `/chapter 1 "My Chapter"` sets custom title visible in Outline panel
- `/reset` clears intro and chapters; `✓` markers disappear
- UI updates immediately after each command

**Definition of Done**
- [ ] Unit tests: `parse_command` handles quoted strings, missing args, unknown commands
- [ ] Unit tests: each handler mutates `AppState` correctly
- [ ] Manual test: run all commands in sequence, verify UI

---

## EPIC 2 — Reference Scanner
**Milestone:** Before generation, the system detects all image/path/URL references in selected files and classifies them.
**Goal:** `ref_scanner.scan_files(paths)` returns a typed list of every reference found, with status `found / missing / external`. No user interaction yet.
**Done when:** Scanner works correctly on all reference types with full unit test coverage.

---

### Story 2.1 — Ref Dataclass & Image/Path Scanner

**Description**
Create the `Ref` dataclass and implement regex detection for image refs (`![alt](path)`) and path refs (`[text](path)`), with path resolution relative to the source file.

**Tasks**
- [ ] `src/scanner/ref_scanner.py`: define `Ref` dataclass with `type`, `original`, `resolved_path`, `status`, `source_file`, `line_number`
- [ ] `PATTERN_IMAGE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')`
- [ ] `PATTERN_PATH = re.compile(r'(?<!!)\[([^\]]*)\]\(([^)#\s]+)\)')` (exclude images, anchors)
- [ ] `scan_file(path: Path) -> list[Ref]`: reads file, applies both patterns line by line
- [ ] For each match: resolve path relative to source file's directory; set `status` to `found` or `missing`
- [ ] Skip URL-like paths in path scanner (those starting with `http`)
- [ ] `scan_files(paths: list[Path]) -> list[Ref]`: calls `scan_file` for each, returns combined list

**Acceptance Criteria**
- `![diagram](./images/d.png)` → `Ref(type="image", status="missing")` when file absent
- `![diagram](./images/d.png)` → `Ref(type="image", status="found")` when file exists
- `[see spec](./spec.md)` → `Ref(type="path", status="missing")` when file absent
- `[click here](https://example.com)` → NOT matched by path scanner (filtered out)

**Definition of Done**
- [ ] Unit tests: 6+ fixture `.md` files covering each case
- [ ] All tests pass with `uv run pytest`
- [ ] `scan_files([])` returns `[]` without error

---

### Story 2.2 — URL Scanner & Deduplication

**Description**
Add URL detection to the scanner and deduplicate refs so the same URL/path isn't listed twice across files.

**Tasks**
- [ ] `PATTERN_URL = re.compile(r'https?://[^\s\)\"<>]+')`
- [ ] Add URL scanning to `scan_file`; create `Ref(type="url", status="external")`
- [ ] `deduplicate_refs(refs: list[Ref]) -> list[Ref]`: keep first occurrence of each unique `original` value
- [ ] `scan_files` calls `deduplicate_refs` before returning
- [ ] Add `ref_count_by_type(refs)` helper: returns `{"image": N, "path": N, "url": N}`

**Acceptance Criteria**
- `https://github.com/x` appearing in 2 files → deduplicated to 1 `Ref`
- `ref_count_by_type` returns correct counts
- URL refs always have `status="external"` and `resolved_path=None`

**Definition of Done**
- [ ] Unit tests for URL pattern, deduplication, count helper
- [ ] All existing Story 2.1 tests still pass
- [ ] `scan_files` on 3 fixture files returns expected deduped list

---

## EPIC 3 — LLM Generation & Pipeline
**Milestone:** `/forge` runs the full pipeline: validate → scan → LLM calls → write `temp_output.md`.
**Goal:** Given a configured `AppState`, the pipeline produces a valid, well-structured `temp_output.md` ready for DOCX conversion.
**Done when:** `temp_output.md` is written with title block, TOC, intro summary, and structured chapters.

---

### Story 3.1 — LiteLLM Client & Prompt Templates

**Description**
Build the thin LiteLLM wrapper and define the 4 prompt templates (intro summary, chapter structuring, TOC generation, self-heal).

**Tasks**
- [ ] `src/llm/client.py`: `call_llm(system: str, user: str, model: str = "gpt-4o") -> str`
- [ ] Read `DOCFORGE_MODEL` env var to override default model
- [ ] On `litellm.exceptions.APIError`: raise `LLMError(stage, message)` with clear message
- [ ] `src/llm/prompts.py`: define 4 functions returning `(system, user)` tuples:
  - `prompt_summarize_intro(content: str) -> tuple[str, str]`
  - `prompt_structure_chapter(content: str, title: str) -> tuple[str, str]`
  - `prompt_generate_toc(doc_title: str, chapter_list: list[str]) -> tuple[str, str]`
  - `prompt_self_heal(markdown: str) -> tuple[str, str]`
- [ ] Each prompt instructs LLM to return only valid Markdown, no prose wrapping

**Acceptance Criteria**
- `call_llm` returns the text content from LLM response
- `call_llm` with invalid API key raises `LLMError` with useful message
- All 4 prompt functions return non-empty `(system, user)` tuples
- `prompt_structure_chapter` injects the chapter title into the user message

**Definition of Done**
- [ ] Unit tests: mock `litellm.completion`, assert correct messages passed
- [ ] Unit tests: `APIError` → `LLMError` re-raise
- [ ] Manual test: `call_llm` with real API key returns coherent markdown

---

### Story 3.2 — Content Generator

**Description**
Implement `generate_content(state, resolved_context)` which calls the LLM for each file and assembles `temp_output.md`.

**Tasks**
- [ ] `src/llm/generator.py`: `generate_content(state: AppState, resolved: ResolvedContext) -> str`
- [ ] Step 1: call `prompt_summarize_intro` on `state.intro_file` content → `intro_md`
- [ ] Step 2: for each chapter in `state.chapters`: call `prompt_structure_chapter` → `chapter_md`
- [ ] Step 3: collect all chapter headings from structured output → call `prompt_generate_toc` → `toc_md`
- [ ] Assemble: `title_block + "\n\n" + toc_md + "\n\n" + intro_md + "\n\n" + "\n\n".join(chapter_mds)`
- [ ] Title block: `# {state.title}\n\n---` (simple, converter handles page break)
- [ ] Log each step to `state.log_lines` with progress messages
- [ ] Inject any `to_summarize` content from `resolved` into the relevant chapter prompt

**Acceptance Criteria**
- Output starts with `# {title}`
- Output contains `## Table of Contents` section
- Output contains `## Introduction` section
- Output contains one `## Chapter N` section per chapter
- Code blocks from source files are preserved in output

**Definition of Done**
- [ ] Unit tests: mock `call_llm`, assert assembly order is correct
- [ ] Unit test: `to_summarize` refs injected into correct chapter prompt
- [ ] Integration test: run with 2 real fixture `.md` files, inspect output structure

---

### Story 3.3 — Sequential Pipeline

**Description**
Implement `pipeline.py` that wires all stages together: validate → scan → (resolve placeholder) → generate → write `temp_output.md`.

**Tasks**
- [ ] `src/pipeline/pipeline.py`: `run_pipeline(state: AppState) -> Path`
- [ ] `validate_config(state)`: raises `PipelineError("validate", msg)` if title is "Untitled" or empty, no intro, or no chapters
- [ ] `scan_references(state) -> list[Ref]`: calls `ref_scanner.scan_files` on intro + all chapters
- [ ] `resolve_references(refs, state) -> ResolvedContext`: for now, returns `ResolvedContext(skipped=all_refs)` (resolution UI in EPIC 5)
- [ ] `write_output(markdown: str, state: AppState) -> Path`: writes to `output/{title_slug}.md`; creates `output/` dir if needed
- [ ] Each stage logs start/end to `state.log_lines`
- [ ] `PipelineError` carries `stage: str` and `message: str`; caught in TUI to show red log message

**Acceptance Criteria**
- `/forge` with no title set → log shows `"Error [validate]: Document title required"`
- `/forge` with no intro set → log shows `"Error [validate]: Introduction file required"`
- Successful run writes `output/<title>.md` to disk
- `state.log_lines` shows progress: "Scanning...", "Generating...", "Done."

**Definition of Done**
- [ ] Unit tests: each `PipelineError` case tested
- [ ] Unit test: `write_output` creates file at correct path
- [ ] Integration test: full `run_pipeline` with fixture state produces `.md` file
- [ ] `/forge` command in TUI calls `run_pipeline` in a background thread

---

### Story 3.4 — Self-Heal Pass

**Description**
After content generation, run the self-heal LLM call if the generated markdown has detectable issues (unmatched code fences, broken headings).

**Tasks**
- [ ] `src/llm/healer.py`: `needs_healing(markdown: str) -> bool`
  - Checks: unmatched ` ``` ` count (odd = broken), headings without blank lines before them
- [ ] `heal_markdown(markdown: str) -> str`: calls `call_llm(*prompt_self_heal(markdown))`
- [ ] Integrate into pipeline after `generate_content`: if `needs_healing(md)` → `md = heal_markdown(md)`
- [ ] Log "Self-healing markdown..." if triggered

**Acceptance Criteria**
- `needs_healing("```\ncode\n```")` → `False` (matched)
- `needs_healing("```\ncode\n")` → `True` (unmatched)
- `heal_markdown` called only when `needs_healing` is `True`
- Log shows "Self-healing..." when triggered

**Definition of Done**
- [ ] Unit tests for `needs_healing` with 4+ cases
- [ ] Unit test: `heal_markdown` mocks LLM and returns fixed content
- [ ] Manual test: intentionally broken fixture triggers heal

---

## EPIC 4 — DOCX Converter
**Milestone:** `temp_output.md` is converted to a properly structured `output.docx` with title page, TOC, and formatted sections.
**Goal:** Running `node converter/convert.js temp.md --title "X"` produces a valid `.docx` file with correct structure.
**Done when:** DOCX opens in Word/LibreOffice with title page, TOC page, introduction, and chapters in order, with code blocks and tables rendered correctly.

---

### Story 4.1 — Node.js Project & Markdown Parser

**Description**
Set up the `converter/` Node.js project and implement `md_parser.js` that converts a markdown string into a list of typed block objects consumable by `convert.js`.

**Tasks**
- [ ] `converter/package.json`: deps `docx ^8.0`, `minimist`
- [ ] `npm install` produces `node_modules/`
- [ ] `converter/md_parser.js`: `parseMarkdown(text) -> Block[]`
- [ ] Block types: `heading(level, text)`, `paragraph(text)`, `code(lang, content)`, `bullet_list(items)`, `numbered_list(items)`, `table(headers, rows)`, `blockquote(text)`, `placeholder(text)`
- [ ] Parser handles `# H1` through `### H3`, ` ``` ` fenced code, `- ` and `* ` bullets, `1. ` numbered, `> ` blockquotes, `| table |` rows, `[Image: x]` and `[External: x]` placeholders
- [ ] Inline bold (`**text**`) and inline code (`` `code` ``) parsed within paragraph text

**Acceptance Criteria**
- `parseMarkdown("# Title\n\nParagraph")` → `[{type:"heading",level:1,text:"Title"},{type:"paragraph",text:"Paragraph"}]`
- Fenced code block with lang tag → `{type:"code",lang:"python",content:"..."}`
- `[Image: diagram.png]` → `{type:"placeholder",text:"[Image: diagram.png]"}`
- Table rows parsed into `headers` array and `rows` array

**Definition of Done**
- [ ] `node md_parser.test.js` (or Jest) passes for all block types
- [ ] Parser handles empty input gracefully
- [ ] Parser handles consecutive blocks of same type

---

### Story 4.2 — DOCX Builder (Title, TOC, Sections)

**Description**
Implement `convert.js` that takes the parsed blocks and builds the DOCX document with title page, TOC page, and content sections using the `docx` npm library.

**Tasks**
- [ ] `converter/convert.js`: reads args `<input.md>`, `--title "X"`, `--output <out.docx>` (default: `output.docx`)
- [ ] Build `Document` with styles: Heading1 (bold, 24pt), Heading2 (bold, 18pt), Heading3 (bold, 14pt), Body (12pt Arial)
- [ ] **Section 1 (title page):** centered `TextRun` with title, large font (36pt), page break after
- [ ] **Section 2 (TOC):** `TableOfContents` element + page break after
- [ ] **Section 3+ (content):** map each `Block` to docx element:
  - `heading` → `Paragraph` with `HeadingLevel.HEADING_N` and `outlineLevel`
  - `paragraph` → `Paragraph` with `TextRun` (handle `**bold**` and `` `code` `` inline)
  - `code` → `Paragraph` with shaded background, monospace font
  - `bullet_list` → `Paragraph` with `LevelFormat.BULLET` numbering
  - `numbered_list` → `Paragraph` with `LevelFormat.DECIMAL` numbering
  - `table` → `Table` with `WidthType.DXA`, dual widths (table + cells)
  - `blockquote` → `Paragraph` with left indent
  - `placeholder` → `Paragraph` with italic `TextRun`
- [ ] Write buffer to output file; log path on success

**Acceptance Criteria**
- Running `node convert.js temp.md --title "Test"` produces `output.docx` without error
- DOCX opens in Word without repair warnings
- Page 1 has centered title text
- Page 2 has a Table of Contents field
- Headings appear in TOC when updated in Word
- Code blocks have monospace font and grey background
- Tables render with visible borders

**Definition of Done**
- [ ] `node convert.js` runs end-to-end on fixture `temp.md`
- [ ] Output DOCX passes `python -c "import zipfile; zipfile.ZipFile('output.docx')"` (valid zip)
- [ ] Manual review: open in Word or LibreOffice, verify visual structure

---

### Story 4.3 — Python Subprocess Wrapper

**Description**
Implement `src/converter/run_converter.py` that calls `convert.js` via subprocess and integrates with the pipeline.

**Tasks**
- [ ] `src/converter/run_converter.py`: `convert_to_docx(markdown_path: Path, title: str, output_path: Path) -> Path`
- [ ] Builds command: `["node", "converter/convert.js", str(markdown_path), "--title", title, "--output", str(output_path)]`
- [ ] Uses `subprocess.run(..., capture_output=True, text=True)`
- [ ] On non-zero exit code: raise `PipelineError("convert", stderr_text)`
- [ ] Resolve `converter/` path relative to this file's location (not cwd)
- [ ] Add `convert_to_docx` call as final step in `pipeline.py`
- [ ] Log "Converting to DOCX..." and "✓ Output: {path}" on success

**Acceptance Criteria**
- `convert_to_docx(fixture_md, "Test", output_path)` produces `.docx` at `output_path`
- Non-zero Node.js exit → `PipelineError` with stderr message in TUI log
- `node` not installed → clear error message (not a Python traceback)
- Output path returned from `run_pipeline` is the final `.docx`

**Definition of Done**
- [ ] Unit test: mock `subprocess.run`, assert correct command assembled
- [ ] Unit test: non-zero returncode → `PipelineError` raised
- [ ] Integration test: full `run_pipeline` with fixture produces `.docx`

---

## EPIC 5 — Reference Resolution UI
**Milestone:** When refs are found, user is shown an interactive resolution screen before generation proceeds.
**Goal:** User can skip, provide a file path, or request LLM summarization for each detected reference. Choices are reflected in the final document.
**Done when:** All three resolution actions work; batch-skip works; placeholders appear in output for skipped refs.

---

### Story 5.1 — Resolution Screen & Skip Action

**Description**
After `/forge` triggers the scan, if refs are found, pause the pipeline and show a resolution screen in the TUI. Implement the "skip" action which inserts a placeholder.

**Tasks**
- [ ] `src/resolver/ref_resolver.py`: `resolve_refs(refs: list[Ref], state: AppState) -> ResolvedContext`
- [ ] Temporarily replace the main layout with a "Reference Resolution" panel listing all refs
- [ ] Each ref shows: index, type badge, original path/url, status badge
- [ ] Prompt: `> Choice for [1] (s=skip, p=provide path, r=read & summarize):`
- [ ] `s` (skip): add to `ResolvedContext.skipped`; insert placeholder text in source file's resolved content
- [ ] Placeholder format: `[Image: {filename}]`, `[External URL: {url}]`, `[External Path: {path}]`
- [ ] `> Skip all [image] refs? (y/n):` batch option shown after individual choices
- [ ] After all refs resolved: restore main layout, continue pipeline

**Acceptance Criteria**
- Resolution screen shows all refs with correct type and status
- `s` for an image ref → `[Image: diagram.png]` appears in generated markdown
- Batch skip for images → all image refs skipped without individual prompts
- After resolution, main layout and log panel restored

**Definition of Done**
- [ ] Unit test: `resolve_refs` with all-skip input returns `ResolvedContext(skipped=all_refs)`
- [ ] Unit test: placeholder text correctly formatted for each type
- [ ] Manual test: trigger `/forge` with fixture containing 1 image ref, choose skip

---

### Story 5.2 — Provide Path & Read/Summarize Actions

**Description**
Implement the "provide path" action (copy file to session and update ref) and "read & summarize" action (pass content to LLM and inject summary).

**Tasks**
- [ ] `p` (provide path): prompt `> Enter file path:`, validate exists, copy to `input/`, update `Ref.resolved_path`, mark as `found`
- [ ] `r` (read & summarize): read file at `Ref.resolved_path` or provided path; add to `ResolvedContext.to_summarize` with the ref's context (which chapter it's in)
- [ ] In `generate_content`: for each chapter, inject `to_summarize` entries as additional context in the chapter prompt
- [ ] If file not found after `p`: show error, re-prompt (don't crash)
- [ ] URL refs with `r`: show message "URL fetching not supported; use (s) to skip or (p) to provide a local copy"

**Acceptance Criteria**
- `p` then valid path → file copied to `input/`, ref marked `found`, no placeholder inserted
- `p` then invalid path → error shown, user re-prompted
- `r` → content of referenced file appears as context in the corresponding chapter's LLM call
- URL + `r` → informative message, user re-prompted with `s` or `p` options only

**Definition of Done**
- [ ] Unit test: `p` action updates `ResolvedContext.provided`
- [ ] Unit test: `r` action adds entry to `ResolvedContext.to_summarize`
- [ ] Integration test: `r` ref content appears in chapter LLM prompt
- [ ] Manual test: all three actions on a fixture with 3 refs (one of each type)

---

## Summary Table

| EPIC | Stories | Milestone | Est. Days |
|------|---------|-----------|-----------|
| 1 — Core TUI | 1.1, 1.2, 1.3, 1.4 | App runs, commands work, live UI | 3 |
| 2 — Reference Scanner | 2.1, 2.2 | Scanner returns typed refs with status | 1 |
| 3 — LLM + Pipeline | 3.1, 3.2, 3.3, 3.4 | `/forge` produces `temp_output.md` | 2–3 |
| 4 — DOCX Converter | 4.1, 4.2, 4.3 | `output.docx` with correct structure | 2 |
| 5 — Ref Resolution UI | 5.1, 5.2 | Interactive resolution before generation | 1–2 |

**Recommended delivery order:** EPIC 1 → EPIC 4 → EPIC 2 → EPIC 3 → EPIC 5

> Deliver EPIC 4 early (Node converter) so it can be tested independently with handwritten markdown fixtures before the LLM pipeline is complete.
