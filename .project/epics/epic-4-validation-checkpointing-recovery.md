# Epic 4: Validation, Checkpointing & Recovery

## Brief Description

Ensure intermediate markdown is valid before conversion and support rollback on failure via checkpoints.

## Business Value

- Catches syntax/structure issues early (before docx-js).
- Enables retry from last good state instead of full restart.

## Acceptance Criteria

- **FC009:** Save checkpoint after each successful chapter (e.g. `{timestamp}_{label}.md`); support rollback to checkpoint.
- **FC010:** Run markdownlint before conversion; return structured issues (e.g. line numbers) to agent for fixes.
- Validation triggers after "chapter done"; failed validation routes back to agent with issue payload.

## High-Level Stories (4)

1. Checkpoint tool and node: create checkpoint from `temp_output.md`, rollback to chosen checkpoint.
2. Markdown validator node: run markdownlint (CLI/JSON), map output to state (e.g. `validation_passed`, issues list).
3. Conditional edges: after tools → validate when chapter complete; validate → agent (fix) or continue.
4. Error-handling path can trigger rollback to last checkpoint before retry (handshake with Epic 6).

## Dependencies

- Epic 2: AI-Powered Content Generation Pipeline (agent/tools and "chapter done" semantics).

## Priority

| Value | Effort | Note             |
|-------|--------|------------------|
| High  | Medium | Quality and retry. |
