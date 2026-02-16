"""Routing logic for agent ↔ tools loop (Story 2.5).

AC2.5.2: route_after_tools(state) determines next node after tools execute.
Priority (human_input > validate > complete > agent):
  1. if pending_question → "human_input" (user must decide on missing ref)
  2. if last_checkpoint_id → "validate" (validate chapter after checkpoint)
  3. if generation_complete → "complete" (move to parse_to_json for conversion)
  4. else → "agent" (continue processing)

Routing enables the agent ↔ tools loop: agent calls tools → tools node updates
state with last_checkpoint_id and pending_question → routing decides next step.
"""

from __future__ import annotations

from backend.state import DocumentState

MAX_FIX_ATTEMPTS = 3


def route_after_tools(state: DocumentState) -> str:
    """Route after tools execute: agent | validate | human_input | complete.

    Priority order (AC2.5.2):
    1. pending_question (human-in-the-loop) → "human_input"
    2. last_checkpoint_id (chapter complete, needs validation) → "validate"
    3. generation_complete (all files processed) → "complete"
    4. else → "agent" (continue processing)

    Args:
        state: DocumentState after tools have run.

    Returns:
        One of: "human_input", "validate", "complete", "agent"
    """
    # Check 1: User needs to decide on missing reference
    if state.get("pending_question") and str(state["pending_question"]).strip():
        return "human_input"

    # Check 2: Chapter complete, needs validation before next chapter
    if state.get("last_checkpoint_id") and str(state["last_checkpoint_id"]).strip():
        return "validate"

    # Check 3: All content generated, move to conversion pipeline
    if state.get("generation_complete"):
        return "complete"

    # Check 4: Continue processing
    return "agent"


def route_after_validation(state: DocumentState) -> str:
    """Route after validation: checkpoint | agent (fix) | complete (max fixes exceeded).

    Priority:
    1. validation_passed=True → "checkpoint"
    2. validation_passed=False AND fix_attempts < MAX_FIX_ATTEMPTS → "agent" (fix path)
    3. validation_passed=False AND fix_attempts >= MAX_FIX_ATTEMPTS → "complete" (stop fix loop)

    Also increments fix_attempts when routing to agent (fix).
    """
    if state.get("validation_passed"):
        return "checkpoint"

    fix_attempts = state.get("fix_attempts", 0)
    if fix_attempts >= MAX_FIX_ATTEMPTS:
        return "complete"  # Stop infinite fix loop

    # Route to agent for fix
    return "agent"


def route_after_error(state: DocumentState) -> str:
    """Route after error handler decides to retry or fail (Story 4.4).

    Priority:
    1. Has checkpoint AND retry_count < MAX_RETRY_ATTEMPTS → "rollback" (restore checkpoint, retry)
    2. Otherwise → "complete" (fail gracefully)

    Args:
        state: DocumentState with last_error, error_type, last_checkpoint_id, retry_count

    Returns:
        One of: "rollback", "complete"
    """
    retry_count = state.get("retry_count", 0)
    last_checkpoint_id = state.get("last_checkpoint_id", "")

    # Route to rollback only if there's a checkpoint AND we haven't exceeded retry limit
    if (
        last_checkpoint_id
        and last_checkpoint_id.strip()
        and retry_count < MAX_RETRY_ATTEMPTS
    ):
        return "rollback"

    # No checkpoint or max retries exceeded - proceed to complete (fail gracefully)
    return "complete"


# Max retry attempts for error handling
MAX_RETRY_ATTEMPTS = 3
