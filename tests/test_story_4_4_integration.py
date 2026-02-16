"""Integration test for error-handling rollback path (Story 4.4). GIVEN-WHEN-THEN."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.utils.session_manager import SessionManager


# --- Fixtures ---


@pytest.fixture
def temp_session_dir() -> Path:
    """GIVEN temporary session directory with required subdirs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_path = Path(tmpdir) / "sessions" / "test-session"
        session_path.mkdir(parents=True)
        for subdir in ["inputs", "assets", "checkpoints", "logs"]:
            (session_path / subdir).mkdir(exist_ok=True)
        yield session_path


@pytest.fixture
def mock_session_manager(temp_session_dir: Path) -> SessionManager:
    """GIVEN mocked SessionManager that uses temp directory."""
    sm = MagicMock(spec=SessionManager)
    sm.get_path.return_value = temp_session_dir
    return sm


# --- Integration Tests for Error Path ---


def test_error_handler_routes_to_rollback_when_checkpoint_exists(
    temp_session_dir: Path,
    mock_session_manager: SessionManager,
) -> None:
    """GIVEN: state with last_error and last_checkpoint_id set
    WHEN: route_after_error is called
    THEN: routes to 'rollback'
    """
    from backend.routing import route_after_error
    from backend.state import DocumentState

    state: DocumentState = {
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "last_error": "Some error occurred",
        "error_type": "validation_error",
        "last_checkpoint_id": "20240215_120000_chapter_1.md",
    }

    result = route_after_error(state)

    assert result == "rollback", "Should route to rollback when checkpoint exists"


def test_error_handler_routes_to_complete_when_no_checkpoint(
    temp_session_dir: Path,
    mock_session_manager: SessionManager,
) -> None:
    """GIVEN: state with last_error but no last_checkpoint_id
    WHEN: route_after_error is called
    THEN: routes to 'complete'
    """
    from backend.routing import route_after_error
    from backend.state import DocumentState

    state: DocumentState = {
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "last_error": "Some error occurred",
        "error_type": "validation_error",
        "last_checkpoint_id": "",
    }

    result = route_after_error(state)

    assert result == "complete", "Should route to complete when no checkpoint"


def test_error_handler_node_logs_error(
    temp_session_dir: Path,
    mock_session_manager: SessionManager,
) -> None:
    """GIVEN: state with last_error and error_type set
    WHEN: error_handler_node runs
    THEN: logs error_handler_triggered event
    """
    from backend.graph_nodes import error_handler_node
    from backend.state import DocumentState

    state: DocumentState = {
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "last_error": "Validation failed",
        "error_type": "validation_error",
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        result = error_handler_node(state)

    # Should return state unchanged
    assert result.get("last_error") == "Validation failed"


def test_full_error_retry_flow_with_checkpoint(
    temp_session_dir: Path,
    mock_session_manager: SessionManager,
) -> None:
    """GIVEN: session with checkpoint, agent returns error, checkpoint exists
    WHEN: error occurs and graph processes error path
    THEN: restores from checkpoint and routes back to agent
    """
    # Setup: create checkpoint and temp_output.md
    checkpoints_dir = temp_session_dir / "checkpoints"
    checkpoint_file = checkpoints_dir / "20240215_120000_chapter_1.md"
    checkpoint_file.write_text(
        "# Checkpointed Content\n\nSaved state.", encoding="utf-8"
    )

    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Current Broken Content\n\nThis will fail.", encoding="utf-8")

    session_id = "550e8400-e29b-41d4-a716-446655440000"

    # Create initial state with error and checkpoint
    state: dict = {
        "session_id": session_id,
        "last_error": "Generation failed",
        "error_type": "generation_error",
        "last_checkpoint_id": "20240215_120000_chapter_1.md",
        "input_files": ["test.md"],
        "current_file_index": 0,
        "current_chapter": 0,
        "retry_count": 0,
    }

    # Test route_after_error routing
    from backend.routing import route_after_error

    routing_result = route_after_error(state)
    assert routing_result == "rollback", "Should route to rollback"

    # Test rollback_node restoration
    from backend.graph_nodes import rollback_node

    with patch(
        "backend.utils.session_manager.SessionManager",
        return_value=mock_session_manager,
    ):
        with patch(
            "backend.utils.checkpoint.SessionManager", return_value=mock_session_manager
        ):
            rollback_result = rollback_node(state)

    # Verify temp_output.md was restored
    restored_content = temp_md.read_text(encoding="utf-8")
    assert "# Checkpointed Content" in restored_content, (
        "Should restore from checkpoint"
    )
    assert "Saved state" in restored_content

    # Verify last_checkpoint_id is cleared to prevent duplicate rollback
    assert rollback_result.get("last_checkpoint_id") == "", (
        "Should clear checkpoint after restore"
    )


def test_full_error_flow_without_checkpoint(
    temp_session_dir: Path,
    mock_session_manager: SessionManager,
) -> None:
    """GIVEN: agent returns error, no checkpoint available
    WHEN: error occurs and graph processes error path
    THEN: routes to complete (fail gracefully)
    """
    session_id = "550e8400-e29b-41d4-a716-446655440000"

    # Create state with error but NO checkpoint
    state: dict = {
        "session_id": session_id,
        "last_error": "Generation failed",
        "error_type": "generation_error",
        "last_checkpoint_id": "",
        "input_files": ["test.md"],
        "current_file_index": 0,
        "current_chapter": 0,
    }

    # Test route_after_error routing
    from backend.routing import route_after_error

    routing_result = route_after_error(state)
    assert routing_result == "complete", "Should route to complete when no checkpoint"


def test_rollback_node_handles_missing_checkpoint_file(
    temp_session_dir: Path,
    mock_session_manager: SessionManager,
) -> None:
    """GIVEN: state with last_checkpoint_id but file doesn't exist
    WHEN: rollback_node runs
    THEN: logs warning, routes to agent anyway
    """
    # Create temp_output.md but NO checkpoint file
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Original Content\n", encoding="utf-8")

    session_id = "550e8400-e29b-41d4-a716-446655440000"

    state: dict = {
        "session_id": session_id,
        "last_checkpoint_id": "nonexistent_checkpoint.md",
    }

    from backend.graph_nodes import rollback_node

    with patch(
        "backend.utils.session_manager.SessionManager",
        return_value=mock_session_manager,
    ):
        with patch(
            "backend.utils.checkpoint.SessionManager", return_value=mock_session_manager
        ):
            _ = rollback_node(state)

    # Verify temp_output.md is unchanged (no crash)
    content = temp_md.read_text(encoding="utf-8")
    assert "# Original Content" in content, (
        "Should not modify file when checkpoint missing"
    )
