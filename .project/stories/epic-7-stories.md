# Epic 7: Interactive CLI Workflow Configuration — Story Decomposition

**Epic ID:** 7  
**Epic Goal:** Provide a rich TUI (using `rich`) so users can start a session, see detected source files, map them to a document structure (Introduction, Chapters), and trigger the generation agent.  
**Business Value:** Reduces friction when setting up generation jobs; lets users visually organize inputs and get immediate feedback; developer-friendly.  
**Epic Acceptance Criteria (Reference):** FC020 (Dashboard: Live view with Detected Sources + Document Configuration); FC021 (Ingestion: CLI args or drop into `inputs/`, UI updates in real time); FC022 (Mapping: assign files to Introduction/Chapters via commands or menus); FC023 (Handoff: validate config and pass to Agent Core).

**Dependencies:** Epic 1 (Session Manager, session layout, `inputs/`); Epic 2 (Agent Execution Engine); Epic 4 (Validation, Checkpointing — downstream); Epic 5 (DOCX Conversion — downstream). Asset Discovery and entry-point contract (session create, copy to inputs, invoke workflow) must be respected.

**Architecture alignment:** ARCHITECTURE §5.0 (entry owns session lifecycle: validate → create session → copy to inputs → build initial state → workflow.invoke → cleanup). Epic 7 adds an **alternative entry path**: TUI "Configuration Mode" produces a structured config (document title, outline: intro + chapters with file paths and optional titles) that is validated, saved to `session/config.json`, and then passed to the same entry flow. **Prompt alignment:** The user’s layout (title, intro file, chapter order, optional chapter titles) MUST be reflected in the agent’s prompts (`src/backend/prompts.py`) so the LLM formats the entire markdown according to that setup (Story 7.5). State and `build_user_prompt` (and system prompt if needed) are extended to accept and inject this structure.

---

## Story 7.1: TUI Dashboard & Real-time File Discovery

### Refined Acceptance Criteria

- **AC7.1.1** Application can launch in a **"Configuration Mode"** using `rich.layout`. A single entry point or flag (e.g. `--config` or default when no args) enters this mode.
- **AC7.1.2** The screen is split into two main panels (matching target UI): (1) **Left/Top — Detected Sources:** list of files in the session `inputs/` directory; (2) **Right/Bottom — Workflow Preview:** current Document Title (default "Untitled") and Outline (Introduction + Chapters).
- **AC7.1.3** A **background file watcher** (using `watchdog`) monitors the session `inputs/` directory. When files are added or removed (e.g. user copies a file into the folder), the "Detected Sources" list updates within 2 seconds without blocking the UI.
- **AC7.1.4** Each detected file has a **stable visual ID or index** (e.g. `[1] architecture.md`) for use in slash commands and selection.
- **AC7.1.5** A **command prompt** is shown below the panels and accepts user input without blocking the UI refresh loop (non-blocking input or dedicated input area).

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Setup rich Layout and Live display | Dev | 3 SP | Create Layout (Header, Columns for Sources + Outline, Footer for Prompt). Implement render loop with `rich.live.Live`. |
| 2 | Implement FileWatcher service | Dev | 3 SP | Use `watchdog` to observe `session/inputs/` (or SessionManager.get_path(session_id) / "inputs"); emit events on file create/delete. |
| 3 | Connect watcher to UI state | Dev | 2 SP | On watcher event, update `detected_sources` (or ConfigState) and trigger UI refresh. Watcher runs in a separate thread. |
| 4 | CLI argument ingestion on startup | Dev | 2 SP | Parse startup args (e.g. `main.py file1.md file2.md`). Create session, copy files to `inputs/` so they appear in TUI at launch. |
| 5 | Unit test: FileWatcher | QA/Dev | 2 SP | Add a file to a temp inputs dir; assert state callback is invoked. |
| 6 | Smoke test: UI render | Dev | 1 SP | Verify layout renders on minimal terminal size (e.g. 80x24). |

### Technical Risks & Dependencies

- **Risk:** TUI flicker on refresh. *Mitigation:* Use `rich.live.Live` with `refresh_per_second` and avoid unnecessary full redraws.
- **Risk:** File watcher blocking main loop. *Mitigation:* Run watcher in a separate `threading.Thread`.
- **Dependency:** Epic 1 (SessionManager, session layout). Session must exist and have `inputs/` before TUI runs; entry or TUI creates session when entering config mode.

### Definition of Done

- [ ] UI launches in Configuration Mode and shows Sources list + Outline panels.
- [ ] Files passed via CLI args appear in Detected Sources at startup.
- [ ] Files added to `inputs/` at runtime appear in Detected Sources within 2 seconds.
- [ ] Command prompt accepts input without freezing the UI.

---

## Story 7.2: Interactive Structure Mapping (Slash Commands)

### Refined Acceptance Criteria

- **AC7.2.1** User can set **Document Title** with a command, e.g. `/title "My Project Docs"`. The Workflow Preview panel updates immediately.
- **AC7.2.2** User can assign a source file to **Introduction**: `/intro <file_id>` or `/intro` with interactive selection. Only one file can be the Introduction; reassigning replaces the previous choice.
- **AC7.2.3** User can add **Chapters**: `/chapter <file_id>` or `/chapter` with selection; optionally `/chapter <file_id> "Custom Chapter Title"`. Chapters are ordered.
- **AC7.2.4** The UI shows **mapping state**: Detected Sources indicates which files are used (e.g. dimmed or checkmark via `rich` styling); Outline shows Introduction and ordered chapters.
- **AC7.2.5** User can **remove or reset** mappings: e.g. `/remove <chapter_index>` or `/reset` to clear intro/chapters (document title may be kept or reset per product decision).

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Implement command parser | Dev | 3 SP | Parse input like `/cmd arg1 "arg 2"`. Handle `/help` and list available commands. |
| 2 | Implement `/title` | Dev | 1 SP | Update ConfigState `document_title`; refresh Workflow Preview panel. |
| 3 | Implement `/intro` | Dev | 2 SP | Validate file ID exists in detected_sources; set outline.introduction to selected file path; refresh UI. |
| 4 | Implement `/chapter` | Dev | 3 SP | Validate file ID; append to outline.chapters (path + optional title); refresh UI. |
| 5 | Visual feedback for used/unused files | Dev | 2 SP | In Detected Sources render, apply style (e.g. dim or green check) for files that are intro or in chapters. |
| 6 | Unit tests: command parsing | Dev | 2 SP | Test quoted args, ID resolution, invalid ID handling. |

### Technical Risks & Dependencies

- **Risk:** File ID changes if list is re-sorted. *Mitigation:* Use stable IDs (e.g. index by sorted filename) or allow partial filename match (e.g. `/intro arch` → `architecture.md`).
- **Dependency:** Story 7.1 (ConfigState, detected_sources, UI panels).

### Definition of Done

- [ ] `/title` updates the document title in the UI.
- [ ] `/intro` assigns one file to Introduction; UI shows it in Outline.
- [ ] `/chapter` adds files to chapters with optional custom title.
- [ ] Invalid file IDs are rejected with a clear message.

---

## Story 7.3: Smart "Claude Style" Interaction (Q&A & Suggestions)

### Refined Acceptance Criteria

- **AC7.3.1** If the user types a **natural-language-style** request that is not a slash command (e.g. "Add server.ts as the first chapter"), a **lightweight router** (regex or simple keyword/NLP heuristic) maps intent to a structured action and executes it (e.g. equivalent to `/chapter server.ts` or similar).
- **AC7.3.2** If the user types **`/add`** (or equivalent) without arguments, an **interactive selection menu** (arrow keys) is shown to pick a file from Detected Sources (e.g. for intro or chapter).
- **AC7.3.3** **Detected Sources** remains visible during menu selection (menu overlays or appears in footer so the list is still in view).
- **AC7.3.4** **Errors** are shown in a dedicated **status bar** (e.g. red text, transient message) without crashing the UI.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Interactive select menu | Dev | 3 SP | Use `rich.prompt` or `questionary` for arrow-key file selection. |
| 2 | Natural-language router (basic) | Dev | 3 SP | Keywords ("add", "intro", "remove", etc.) map to slash commands or structured actions. |
| 3 | Status bar for errors | Dev | 1 SP | Dedicated area in rich Layout for success/error messages; red for errors, clear after delay or next action. |
| 4 | Integration test: selection flow | QA | 2 SP | Select a file from menu and assert it is mapped to outline. |

### Technical Risks & Dependencies

- **Risk:** Arrow keys conflicting with normal text input. *Mitigation:* Enter a distinct "Menu Mode" for key handling, then return to "Command Mode" after selection.
- **Dependency:** Story 7.2 (slash commands, outline state).

### Definition of Done

- [ ] Interactive selection works for Intro and Chapters.
- [ ] Simple natural-language commands perform the expected mapping actions.
- [ ] Error messages appear in the status bar, in red, and are transient.

---

## Story 7.4: Workflow Validation & Agent Handoff

### Refined Acceptance Criteria

- **AC7.4.1** A **`/generate` or `/run`** command triggers "Initialize Agent" (same as current entry flow): validate config, then hand off to the workflow.
- **AC7.4.2** **Validation rules:** (1) Error if Document Title is empty. (2) Warning if no chapters are defined. (3) Error if Introduction is required by product rules and missing.
- **AC7.4.3** On validation success, build the **workflow config** (e.g. title, outline with intro + chapters and file paths) and save to **`session/config.json`** for reproducibility.
- **AC7.4.4** **State transition:** Stop the file watcher, leave or clear the Config screen, and show **Agent Execution** view (spinner and/or log stream).
- **AC7.4.5** The **entry flow** is invoked with the config: create or reuse session, ensure mapped files are in `inputs/`, build initial_state from config (including document structure for prompts — see Story 7.5), call `workflow.invoke(initial_state)`, then cleanup per ARCHITECTURE §5.0.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Validation logic | Dev | 2 SP | Check outline (title, intro, chapters); return list of errors and warnings. |
| 2 | Config serializer | Dev | 1 SP | Write current config (title, outline) to `session/config.json`. |
| 3 | `/run` transition | Dev | 2 SP | Stop TUI loop and watcher; build config; call entry (session + copy files + build initial_state + workflow.invoke). |
| 4 | Stream agent logs to console | Dev | 3 SP | Subscribe to workflow/graph events and print progress (spinners, logs) with `rich` console. |
| 5 | E2E test: config → execution | QA | 3 SP | Configure via TUI, run `/generate`, assert agent starts and processes. |

### Technical Risks & Dependencies

- **Risk:** Logs lost when switching from TUI to agent stream. *Mitigation:* Use a shared `rich.Console` or clean handoff so agent output is visible.
- **Dependency:** Story 7.2 (outline state). Story 7.5 (document structure in state and prompts). Epic 1 (SessionManager). Epic 2 (workflow.invoke). Entry contract (validate → create session → copy to inputs → invoke).

### Definition of Done

- [ ] `/run` (or `/generate`) runs validation and, if valid, saves config and starts the agent.
- [ ] Valid config is written to `session/config.json`.
- [ ] UI hands off to the Agent execution stream and user sees progress.

---

## Story 7.5: Document Structure in Agent Prompts (Backend)

### Refined Acceptance Criteria

- **AC7.5.1** When the run is started with a **user-defined document layout** (from TUI config or from `session/config.json`), the **initial state** (or state passed to the agent) SHALL include: **document_title** (str), and a **document outline** that specifies which file is Introduction and the ordered list of chapters, each with filename and optional custom title (e.g. `introduction_file: str | None`, `chapters: list[dict]` with `file` and optional `title`). Existing `document_outline` in state may be extended or a new key added; contract is documented.
- **AC7.5.2** **`build_user_prompt(state)`** in `src/backend/prompts.py` SHALL inject the user’s layout into the user prompt when present. The LLM MUST be explicitly told: (1) the **document title** to use for the final document; (2) which **file is the Introduction** (and that its content should be formatted as introduction, not as "Chapter 1"); (3) the **order of chapters** and, for each, the **filename** and **optional chapter title** (e.g. "Chapter 1: &lt;title&gt; — source file: X"). This guides the LLM to format the entire markdown according to the user’s setup.
- **AC7.5.3** Optionally, a **system-prompt fragment** or a dedicated "DOCUMENT LAYOUT" block (in system or user prompt) MAY be added so the agent always sees the layout rules first (e.g. "You are building a document with this structure: Title: X. Introduction: file A. Chapter 1 (title): file B. Chapter 2: file C. Use exactly this order and these titles."). Implementation choice: inject in user prompt only, or also extend system prompt when layout is present.
- **AC7.5.4** When **no user-defined layout** is present (e.g. non-TUI entry with only a list of files), behavior remains backward compatible: prompts do not require document_title or outline; the agent may infer structure as today.

### Task Breakdown

| # | Task | Owner | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Define state contract for document layout | Dev | 1 SP | document_title (str), introduction_file (str \| None), chapters (list of {file, title?}); or extend document_outline; document in state.py. |
| 2 | Extend build_initial_state or entry to accept layout | Dev | 1 SP | When config has title/outline, set state["document_title"] and outline fields from config. |
| 3 | Inject layout into build_user_prompt | Dev | 3 SP | If state has document_title/outline, add a "DOCUMENT LAYOUT" section to user prompt: title, intro file, chapter list with titles. |
| 4 | Optional: add system-prompt fragment when layout present | Dev | 1 SP | Or keep layout only in user prompt; document choice. |
| 5 | Unit test: build_user_prompt with/without layout | QA/Dev | 2 SP | With layout → prompt contains title, intro, chapter order; without → unchanged from current. |

### Technical Risks & Dependencies

- **Risk:** Prompt length grows with many chapters; keep outline section concise (e.g. bullet list).
- **Dependency:** Epic 2 (prompts.py, agent). Story 7.4 (config produced by TUI and passed to entry/state). State schema (Epic 1 / state.py).

### Definition of Done

- [ ] State carries document_title and document outline (intro file + ordered chapters with optional titles) when run is started from TUI config.
- [ ] `build_user_prompt(state)` includes the user’s layout in the prompt when present, so the LLM is guided to format the document with that title, intro, and chapter order/titles.
- [ ] Backward compatibility: when no layout is in state, prompts behave as today. Unit tests for both cases.

---

## Epic 7 Summary: Prioritization and Estimates

| Story | Summary | Story Points | Priority | Dependencies |
|-------|---------|--------------|----------|--------------|
| 7.1 | TUI Dashboard & File Discovery | 13 | P0 | Epic 1 (Session) |
| 7.2 | Interactive Mapping (Slash Commands) | 11 | P0 | 7.1 |
| 7.3 | Smart Interaction (Menus, NL) | 9 | P1 | 7.2 |
| 7.4 | Validation & Agent Handoff | 11 | P0 | 7.2, Epic 1, 2 |
| 7.5 | Document structure in prompts (backend) | 8 | P0 | 7.4 / Epic 2 |

**Total Epic 7:** ~52 SP

**Suggested order:** 7.1 → 7.2 → 7.5 (prompt contract and injection) → 7.4 (handoff uses it); 7.3 can follow 7.2 for better UX. Story 7.5 can be implemented in parallel with 7.4 once 7.2 is done (contract: config includes title + outline; entry passes to state; prompts consume state).
