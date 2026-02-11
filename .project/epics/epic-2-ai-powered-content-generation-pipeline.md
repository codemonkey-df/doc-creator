# Epic 2: AI-Powered Content Generation Pipeline

## Brief Description

Deliver the core agent loop: LLM reads source files, maintains context, and produces structured markdown (chapters/sections/subsections) with strict fidelity and human-in-the-loop for missing refs.

## Business Value

- Core product value: raw files become structured, narrative document content.
- Quality and safety: no summarization of technical content, and user can resolve missing references.

## Acceptance Criteria

- **FC002:** Content organized as Chapters → Sections → Subsections; valid heading hierarchy (no skips).
- **FC003:** Agent reads current document state (e.g. last 100 lines + outline) before appending.
- **FC004:** Code/logs in fenced blocks verbatim; no summarization; formatting preserved.
- **FC006:** On detected missing external file reference, pause and prompt user (upload/skip); resume after decision.
- Agent has correct system prompt and tool access; tools used per spec (read file, read generated file, append, etc.).

## High-Level Stories (5)

1. Define LangGraph `DocumentState` and integrate SessionManager/sanitizer with workflow start.
2. Implement Tool Node: `list_files`, `read_file`, `read_generated_file`, `append_to_markdown`, `edit_markdown_line`, plus checkpoint tools (create/rollback).
3. Implement Agent node: system prompt (structure, fidelity, no summarization, when to interrupt), tool binding, and state updates.
4. Implement human-in-the-loop: interrupt on missing reference, inject user decision into state, resume to agent or asset handling.
5. Wire agent ↔ tools loop and routing (when to validate, when to go to conversion, when to ask user).

## Dependencies

- Epic 1: Secure Input & Session Foundation.

## Priority

| Value     | Effort | Note                    |
|-----------|--------|-------------------------|
| Very High | High   | Core product; most complexity. |
