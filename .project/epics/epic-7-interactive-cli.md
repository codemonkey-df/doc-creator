# Epic 7: Interactive CLI Workflow Configuration

## Brief Description

Provide a rich Terminal User Interface (TUI) using the `rich` Python library so users can start a session, see detected source files, map them to a document structure (Introduction, Chapters), and trigger the generation agent—without editing JSON by hand.

## Business Value

- Reduces friction when setting up generation jobs.
- Lets users visually organize complex inputs and get immediate feedback on file detection in a developer-friendly environment.

## Acceptance Criteria

- **FC020 (Dashboard):** CLI shows a persistent "Live" view with "Detected Sources" and "Document Configuration" (Title/Outline).
- **FC021 (Ingestion):** Users can supply files via CLI args or by dropping them into the session `inputs/` folder; the UI updates in real time.
- **FC022 (Mapping):** Users can assign files to "Introduction" or "New Chapter" via interactive commands or selection menus.
- **FC023 (Handoff):** Configuration is validated and passed to the Agent Core to start generation.

- **Prompt alignment:** The user’s setup (document title, which file is Introduction, chapter order and optional chapter titles) MUST be passed into the agent’s prompts (`src/backend/prompts.py`) so the LLM is explicitly guided to format the entire markdown according to that layout (intro vs chapters, order, and titles). Without this, the agent would infer structure on its own and ignore the TUI configuration.

## High-Level Stories (5)

1. TUI dashboard and real-time file discovery: rich Layout/Live, two panels (Detected Sources, Workflow Preview), watchdog on `inputs/`, CLI-arg ingestion.
2. Interactive structure mapping: slash commands (`/title`, `/intro`, `/chapter`, `/remove`, `/reset`); visual feedback for used/unused files.
3. Smart interaction: natural-language-style routing for simple intents, interactive selection menus (e.g. `/add`), status bar for errors.
4. Workflow validation and agent handoff: `/generate` or `/run`, validation rules, persist config to `session/config.json`, transition to Agent execution and stream logs.
5. Document structure in prompts (backend): state carries document title and outline (intro file + ordered chapters with optional titles); `build_user_prompt` (and system prompt if needed) inject this so the LLM formats the document according to the user’s layout.

## Dependencies

- Epic 1: Secure Input & Session Foundation (Session Manager, session layout, `inputs/`).
- Epic 2: AI-Powered Content Generation Pipeline (Agent Execution Engine).
- Epic 4: Validation, Checkpointing & Recovery (optional; checkpoints after generation).
- Epic 5: DOCX Conversion & Output Quality (downstream pipeline).
- Asset Discovery (file listing) and entry-point contract (session create, copy to inputs, invoke workflow).

## Priority

| Value     | Effort | Note                                      |
|-----------|--------|-------------------------------------------|
| High      | High   | New entry path; depends on Epics 1, 2, 4, 5. |

## Architecture Notes

- **Stack:** `rich` (Layout, Live, Panel) for TUI; `watchdog` for file system monitoring.
- **State:** Single `ConfigState` (e.g. detected_files, doc_title, intro_file, chapters); output is a structured config (e.g. GenerationConfig/WorkflowConfig) consumed by the existing entry.
- **Concurrency:** File watcher in a background thread; main thread runs UI render loop and input handling (non-blocking or asyncio as needed).
- **Backend touchpoint:** The user’s document layout (title, intro file, chapter order/titles) must flow from config → entry → `DocumentState` → **`src/backend/prompts.py`** (`build_user_prompt` and optionally system prompt) so the LLM is explicitly guided to format the markdown accordingly (Story 7.5).
