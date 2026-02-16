"""Integration tests for checkpoint → rollback flow (Epic 4).

Tests checkpoint creation and rollback restoration with real file operations.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.graph_nodes import checkpoint_node, rollback_node
from backend.state import DocumentState


class TestCheckpointRollbackFlow:
    """Test checkpoint save and restore flow."""

    @patch("backend.graph_nodes.SessionManager")
    @patch("backend.utils.checkpoint.SessionManager")
    def test_checkpoint_then_rollback_restores_content(
        self,
        mock_checkpoint_sm: MagicMock,
        mock_graph_sm: MagicMock,
        session_with_temp_output: tuple[Path, DocumentState],
    ) -> None:
        """GIVEN checkpoint saved, temp_output modified WHEN rollback_node runs THEN original content restored."""
        temp_session_dir, initial_state = session_with_temp_output

        # Mock SessionManager for graph_nodes
        mock_graph_sm_instance = MagicMock()
        mock_graph_sm_instance.get_path.return_value = temp_session_dir
        mock_graph_sm.return_value = mock_graph_sm_instance

        # Mock SessionManager for checkpoint utils
        mock_checkpoint_sm_instance = MagicMock()
        mock_checkpoint_sm_instance.get_path.return_value = temp_session_dir
        mock_checkpoint_sm.return_value = mock_checkpoint_sm_instance

        # Get original content
        temp_output = temp_session_dir / "temp_output.md"
        original_content = temp_output.read_text(encoding="utf-8")

        # Create checkpoint
        checkpoint_result = checkpoint_node(initial_state)
        checkpoint_id = checkpoint_result["last_checkpoint_id"]
        assert checkpoint_id != ""

        # Modify temp_output.md (simulate failed generation)
        temp_output.write_text(
            "Modified content after failed generation", encoding="utf-8"
        )
        assert temp_output.read_text(encoding="utf-8") != original_content

        # Execute rollback
        rollback_state = initial_state.copy()
        rollback_state["last_checkpoint_id"] = checkpoint_id
        rollback_result = rollback_node(rollback_state)

        # Assert: content restored
        restored_content = temp_output.read_text(encoding="utf-8")
        assert restored_content == original_content, (
            "Content should be restored from checkpoint"
        )

        # Assert: checkpoint_id cleared after restore
        assert rollback_result.get("last_checkpoint_id") == ""

    @patch("backend.graph_nodes.SessionManager")
    def test_rollback_with_missing_checkpoint_skips_gracefully(
        self,
        mock_sm_class: MagicMock,
        temp_session_dir: Path,
        sample_state: DocumentState,
    ) -> None:
        """GIVEN nonexistent checkpoint_id WHEN rollback_node runs THEN no crash, state unchanged."""
        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("Some content", encoding="utf-8")

        # State with non-existent checkpoint
        state = sample_state.copy()
        state["last_checkpoint_id"] = "nonexistent_checkpoint.md"

        # Execute rollback (should not crash)
        rollback_node(state)

        # Assert: original content unchanged
        content = temp_output.read_text(encoding="utf-8")
        assert content == "Some content"

    @patch("backend.graph_nodes.SessionManager")
    def test_rollback_with_empty_checkpoint_id_skips(
        self,
        mock_sm_class: MagicMock,
        temp_session_dir: Path,
        sample_state: DocumentState,
    ) -> None:
        """GIVEN empty checkpoint_id WHEN rollback_node runs THEN state unchanged."""
        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("Some content", encoding="utf-8")

        # State with empty checkpoint
        state = sample_state.copy()
        state["last_checkpoint_id"] = ""

        # Execute rollback
        rollback_node(state)

        # Assert: content unchanged
        content = temp_output.read_text(encoding="utf-8")
        assert content == "Some content"


class TestCheckpointCreation:
    """Test checkpoint file creation."""

    @patch("backend.graph_nodes.SessionManager")
    def test_checkpoint_creates_file_in_checkpoints_dir(
        self,
        mock_sm_class: MagicMock,
        session_with_temp_output: tuple[Path, DocumentState],
    ) -> None:
        """GIVEN temp_output.md exists WHEN checkpoint_node runs THEN file created in checkpoints/."""
        temp_session_dir, initial_state = session_with_temp_output

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        # Verify checkpoints dir exists
        checkpoints_dir = temp_session_dir / "checkpoints"
        assert checkpoints_dir.exists()

        # Execute checkpoint
        result = checkpoint_node(initial_state)

        # Assert: checkpoint created
        checkpoint_id = result["last_checkpoint_id"]
        assert checkpoint_id != ""
        assert (checkpoints_dir / checkpoint_id).exists()

    @patch("backend.graph_nodes.SessionManager")
    def test_checkpoint_includes_chapter_in_filename(
        self,
        mock_sm_class: MagicMock,
        session_with_temp_output: tuple[Path, DocumentState],
    ) -> None:
        """GIVEN current_chapter=1 WHEN checkpoint_node runs THEN filename includes chapter_1."""
        temp_session_dir, initial_state = session_with_temp_output

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        initial_state["current_chapter"] = 1

        result = checkpoint_node(initial_state)

        checkpoint_id = result["last_checkpoint_id"]
        assert "chapter_1" in checkpoint_id, (
            f"Checkpoint ID should include chapter_1: {checkpoint_id}"
        )
