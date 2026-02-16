"""Unit tests for rollback_node and restore_from_checkpoint (Story 4.4). GIVEN-WHEN-THEN."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.graph_nodes import rollback_node
from backend.state import DocumentState
from backend.utils.checkpoint import restore_from_checkpoint
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


# --- Tests for restore_from_checkpoint ---


def test_restore_from_checkpoint_success(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: checkpoint file exists in checkpoints/
    WHEN: restore_from_checkpoint is called
    THEN: copies checkpoint content to temp_output.md, returns True
    """
    # Create checkpoint file
    checkpoints_dir = temp_session_dir / "checkpoints"
    checkpoint_file = checkpoints_dir / "20240215_120000_chapter_1.md"
    checkpoint_file.write_text("# Checkpoint Content\n\nSaved state.", encoding="utf-8")

    # Create different temp_output.md
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Different Content\n\nOld state.", encoding="utf-8")

    # Restore
    result = restore_from_checkpoint(
        "test-session", "20240215_120000_chapter_1.md", mock_session_manager
    )

    assert result is True, "Should return True on success"
    content = temp_md.read_text(encoding="utf-8")
    assert "# Checkpoint Content" in content, (
        "temp_output.md should have checkpoint content"
    )


def test_restore_from_checkpoint_missing_file(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: checkpoint file does NOT exist
    WHEN: restore_from_checkpoint is called
    THEN: returns False, no crash
    """
    # No checkpoint file created
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Original\n", encoding="utf-8")

    result = restore_from_checkpoint(
        "test-session", "nonexistent_checkpoint.md", mock_session_manager
    )

    assert result is False, "Should return False when checkpoint missing"


def test_restore_from_checkpoint_invalid_id(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: checkpoint_id with path traversal
    WHEN: restore_from_checkpoint is called
    THEN: returns False, no crash
    """
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Original\n", encoding="utf-8")

    # Try path traversal
    result = restore_from_checkpoint(
        "test-session", "../../../etc/passwd", mock_session_manager
    )

    assert result is False, "Should return False for invalid checkpoint_id"


def test_restore_from_checkpoint_path_separator(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: checkpoint_id with path separator
    WHEN: restore_from_checkpoint is called
    THEN: returns False, no crash
    """
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Original\n", encoding="utf-8")

    result = restore_from_checkpoint(
        "test-session", "foo/bar/baz.md", mock_session_manager
    )

    assert result is False, "Should return False for path separator in checkpoint_id"


# --- Tests for rollback_node ---


def test_rollback_node_performs_rollback(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: state with last_checkpoint_id set and checkpoint exists
    WHEN: rollback_node runs
    THEN: restores temp_output.md from checkpoint, logs rollback_performed, routes to agent
    """
    # Create checkpoint file
    checkpoints_dir = temp_session_dir / "checkpoints"
    checkpoint_file = checkpoints_dir / "20240215_120000_chapter_1.md"
    checkpoint_file.write_text(
        "# Checkpoint Content\n\nChapter 1 saved.", encoding="utf-8"
    )

    # Create different temp_output.md
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Current Content\n\nBroken content.", encoding="utf-8")

    # Use a valid UUID for session_id
    state: DocumentState = {
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "last_checkpoint_id": "20240215_120000_chapter_1.md",
    }

    # Patch SessionManager in both places where it's imported
    with patch(
        "backend.utils.session_manager.SessionManager",
        return_value=mock_session_manager,
    ):
        with patch(
            "backend.utils.checkpoint.SessionManager", return_value=mock_session_manager
        ):
            result = rollback_node(state)

    # Verify restoration
    content = temp_md.read_text(encoding="utf-8")
    assert "# Checkpoint Content" in content, (
        "temp_output.md should be restored from checkpoint"
    )
    assert "last_checkpoint_id" in result


def test_rollback_node_skips_when_no_checkpoint_id(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: state with empty last_checkpoint_id
    WHEN: rollback_node runs
    THEN: logs rollback_skipped, returns state unchanged
    """
    # Create temp_output.md
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Original Content\n", encoding="utf-8")

    state: DocumentState = {
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "last_checkpoint_id": "",
    }

    with patch(
        "backend.utils.session_manager.SessionManager",
        return_value=mock_session_manager,
    ):
        result = rollback_node(state)

    # Verify state unchanged (no restoration attempted)
    content = temp_md.read_text(encoding="utf-8")
    assert "# Original Content" in content, "temp_output.md should be unchanged"
    assert "last_checkpoint_id" in result


def test_rollback_node_skips_when_checkpoint_missing(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: state with last_checkpoint_id but file doesn't exist
    WHEN: rollback_node runs
    THEN: logs rollback_skipped, returns state unchanged
    """
    # Create temp_output.md
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Original Content\n", encoding="utf-8")

    # Note: no checkpoint file created
    state: DocumentState = {
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "last_checkpoint_id": "nonexistent_checkpoint.md",
    }

    with patch(
        "backend.utils.session_manager.SessionManager",
        return_value=mock_session_manager,
    ):
        with patch(
            "backend.utils.checkpoint.SessionManager", return_value=mock_session_manager
        ):
            _ = rollback_node(state)

    # Verify state unchanged (no restoration attempted)
    content = temp_md.read_text(encoding="utf-8")
    assert "# Original Content" in content, "temp_output.md should be unchanged"


def test_rollback_node_always_returns_state(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: valid state
    WHEN: rollback_node runs (success or failure)
    THEN: returns DocumentState (never raises)
    """
    # No checkpoint, should skip gracefully
    state: DocumentState = {
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "last_checkpoint_id": "",
    }

    with patch(
        "backend.utils.session_manager.SessionManager",
        return_value=mock_session_manager,
    ):
        result = rollback_node(state)

    assert isinstance(result, dict), "Should return state dict"
    assert "session_id" in result
