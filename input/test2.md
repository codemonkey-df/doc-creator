# DocForge — EPICs & Stories

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

