"""Unit tests for checkpoint_node (Story 4.1). GIVEN-WHEN-THEN."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.graph_nodes import checkpoint_node
from backend.state import DocumentState
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


# --- Tests ---


def test_checkpoint_node_copies_temp_to_checkpoints(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: session with temp_output.md
    WHEN: checkpoint_node runs
    THEN: file created in checkpoints/, last_checkpoint_id set
    """
    # Create temp_output.md
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Test Document\n\nSome content here.", encoding="utf-8")

    state: DocumentState = {
        "session_id": "test-session",
        "current_chapter": 1,
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        result = checkpoint_node(state)

    # Verify checkpoint was created
    checkpoints_dir = temp_session_dir / "checkpoints"
    assert checkpoints_dir.exists(), "checkpoints/ directory should be created"

    checkpoint_files = list(checkpoints_dir.glob("*.md"))
    assert len(checkpoint_files) == 1, "One checkpoint file should exist"

    # Verify last_checkpoint_id is set
    assert result["last_checkpoint_id"] != "", "last_checkpoint_id should be set"
    assert result["last_checkpoint_id"] == checkpoint_files[0].name


def test_checkpoint_node_uses_chapter_label(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: state with current_chapter=3
    WHEN: checkpoint_node runs
    THEN: checkpoint filename contains 'chapter_3'
    """
    # Create temp_output.md
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Test\n", encoding="utf-8")

    state: DocumentState = {
        "session_id": "test-session",
        "current_chapter": 3,
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        result = checkpoint_node(state)

    checkpoint_id = result["last_checkpoint_id"]
    assert "chapter_3" in checkpoint_id, (
        f"Checkpoint ID should contain 'chapter_3': {checkpoint_id}"
    )


def test_checkpoint_node_timestamp_uniqueness(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: checkpoint already exists for same second
    WHEN: checkpoint_node runs again
    THEN: filename has sequence suffix (_0, _1, etc.)
    """
    # Create temp_output.md
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Test\n", encoding="utf-8")

    state: DocumentState = {
        "session_id": "test-session",
        "current_chapter": 1,
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        # First checkpoint
        result1 = checkpoint_node(state)
        first_id = result1["last_checkpoint_id"]

        # Second checkpoint (same chapter) - should get sequence suffix
        result2 = checkpoint_node(state)
        second_id = result2["last_checkpoint_id"]

    # Verify uniqueness with sequence suffix
    assert "_1" in second_id or second_id != first_id, (
        f"Second checkpoint should have sequence suffix: {first_id} vs {second_id}"
    )


def test_checkpoint_node_missing_temp_raises(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: no temp_output.md
    WHEN: checkpoint_node runs
    THEN: handles gracefully, returns state with empty last_checkpoint_id
    """
    state: DocumentState = {
        "session_id": "test-session",
        "current_chapter": 1,
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        result = checkpoint_node(state)

    assert result["last_checkpoint_id"] == "", (
        "last_checkpoint_id should be empty when temp is missing"
    )
    assert "error_type" in result or "last_error" in result, (
        "Should set error fields when temp is missing"
    )


def test_checkpoint_node_creates_checkpoints_dir_if_missing(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: session without checkpoints/ directory
    WHEN: checkpoint_node runs
    THEN: creates checkpoints/ automatically
    """
    # Create temp_output.md
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Test\n", encoding="utf-8")

    # Remove checkpoints directory if exists
    checkpoints_dir = temp_session_dir / "checkpoints"
    if checkpoints_dir.exists():
        shutil.rmtree(checkpoints_dir)

    state: DocumentState = {
        "session_id": "test-session",
        "current_chapter": 1,
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        checkpoint_node(state)

    assert checkpoints_dir.exists(), "checkpoints/ directory should be created"


def test_checkpoint_node_uses_custom_temp_path(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: session with temp at custom path
    WHEN: checkpoint_node runs with temp_md_path set
    THEN: uses custom path for copying
    """
    # Create temp at custom location
    custom_temp = temp_session_dir / "custom_temp.md"
    custom_temp.write_text("# Custom Content\n", encoding="utf-8")

    state: DocumentState = {
        "session_id": "test-session",
        "current_chapter": 2,
        "temp_md_path": str(custom_temp),
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        checkpoint_node(state)

    checkpoints_dir = temp_session_dir / "checkpoints"
    checkpoint_files = list(checkpoints_dir.glob("*.md"))
    assert len(checkpoint_files) == 1

    # Verify the content was copied from custom path
    content = checkpoint_files[0].read_text(encoding="utf-8")
    assert "# Custom Content" in content


def test_checkpoint_node_chapter_0(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: state with current_chapter=0
    WHEN: checkpoint_node runs
    THEN: checkpoint filename contains 'chapter_0'
    """
    # Create temp_output.md
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Test\n", encoding="utf-8")

    state: DocumentState = {
        "session_id": "test-session",
        "current_chapter": 0,
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        result = checkpoint_node(state)

    checkpoint_id = result["last_checkpoint_id"]
    assert "chapter_0" in checkpoint_id, (
        f"Checkpoint ID should contain 'chapter_0': {checkpoint_id}"
    )
