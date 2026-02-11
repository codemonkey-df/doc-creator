"""Unit tests for DocumentState and build_initial_state (Story 2.1). GIVEN-WHEN-THEN."""

from __future__ import annotations

from backend.state import build_initial_state


# Keys that build_initial_state must set (all keys the graph expects when scan_assets runs).
REQUIRED_STATE_KEYS = (
    "session_id",
    "input_files",
    "current_file_index",
    "current_chapter",
    "temp_md_path",
    "structure_json_path",
    "output_docx_path",
    "last_checkpoint_id",
    "document_outline",
    "conversion_attempts",
    "last_error",
    "error_type",
    "retry_count",
    "missing_references",
    "user_decisions",
    "pending_question",
    "status",
    "messages",
    "validation_passed",
    "validation_issues",
    "generation_complete",
)


def test_build_initial_state_returns_all_document_state_keys() -> None:
    """GIVEN session_id and input_files / WHEN build_initial_state / THEN returned dict has every DocumentState key."""
    state = build_initial_state("sid-123", ["a.txt", "b.md"])

    for key in REQUIRED_STATE_KEYS:
        assert key in state, f"Missing key: {key}"


def test_build_initial_state_value_types() -> None:
    """GIVEN session_id and input_files / WHEN build_initial_state / THEN all values have correct types."""
    state = build_initial_state("sid-456", ["f.txt"])

    assert state["session_id"] == "sid-456"
    assert isinstance(state["input_files"], list)
    assert all(isinstance(x, str) for x in state["input_files"])
    assert isinstance(state["current_file_index"], int)
    assert isinstance(state["current_chapter"], int)
    assert isinstance(state["temp_md_path"], str)
    assert isinstance(state["structure_json_path"], str)
    assert isinstance(state["output_docx_path"], str)
    assert isinstance(state["last_checkpoint_id"], str)
    assert isinstance(state["document_outline"], list)
    assert isinstance(state["conversion_attempts"], int)
    assert isinstance(state["last_error"], str)
    assert isinstance(state["error_type"], str)
    assert isinstance(state["retry_count"], int)
    assert isinstance(state["missing_references"], list)
    assert isinstance(state["user_decisions"], dict)
    assert isinstance(state["pending_question"], str)
    assert isinstance(state["status"], str)
    assert isinstance(state["messages"], list)
    assert isinstance(state["validation_passed"], bool)
    assert isinstance(state["validation_issues"], list)
    assert isinstance(state["generation_complete"], bool)


def test_build_initial_state_defaults_and_status() -> None:
    """GIVEN session_id and input_files / WHEN build_initial_state / THEN status is scanning_assets and defaults are set."""
    state = build_initial_state("sid-789", [])

    assert state["status"] == "scanning_assets"
    assert state["current_file_index"] == 0
    assert state["current_chapter"] == 0
    assert state["conversion_attempts"] == 0
    assert state["retry_count"] == 0
    assert state["last_checkpoint_id"] == ""
    assert state["document_outline"] == []
    assert state["missing_references"] == []
    assert state["user_decisions"] == {}
    assert state["pending_question"] == ""
    assert state["messages"] == []
    assert state["temp_md_path"] == ""
    assert state["structure_json_path"] == ""
    assert state["output_docx_path"] == ""
    assert state["last_error"] == ""
    assert state["error_type"] == ""
    assert state["validation_passed"] is False
    assert state["validation_issues"] == []
    assert state["generation_complete"] is False
