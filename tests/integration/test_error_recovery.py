"""Integration tests for error recovery flow (Epic 4).

Tests: error_handler → rollback → agent retry with mocked externals.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.graph_nodes import error_handler_node, rollback_node
from backend.routing import route_after_error
from backend.state import DocumentState


class TestErrorRecoveryFlow:
    """Test error handling and rollback functionality."""

    def test_error_with_checkpoint_routes_to_rollback(
        self, sample_state: DocumentState
    ) -> None:
        """GIVEN state with error and checkpoint WHEN route_after_error THEN routes to rollback."""
        state = sample_state.copy()
        state["last_error"] = "Conversion failed"
        state["error_type"] = "conversion_error"
        state["last_checkpoint_id"] = "20240215_120000_chapter_1.md"
        state["retry_count"] = 0

        result = route_after_error(state)

        assert result == "rollback"

    def test_error_without_checkpoint_routes_to_complete(
        self, sample_state: DocumentState
    ) -> None:
        """GIVEN state with error but no checkpoint WHEN route_after_error THEN routes to complete."""
        state = sample_state.copy()
        state["last_error"] = "Conversion failed"
        state["error_type"] = "conversion_error"
        state["last_checkpoint_id"] = ""
        state["retry_count"] = 0

        result = route_after_error(state)

        assert result == "complete"

    def test_error_max_retries_routes_to_complete(
        self, sample_state: DocumentState
    ) -> None:
        """GIVEN state with error and retry_count=3 (max) WHEN route_after_error THEN routes to complete."""
        state = sample_state.copy()
        state["last_error"] = "Conversion failed"
        state["error_type"] = "conversion_error"
        state["last_checkpoint_id"] = "20240215_120000_chapter_1.md"
        state["retry_count"] = 3  # MAX_RETRY_ATTEMPTS = 3

        result = route_after_error(state)

        assert result == "complete"

    def test_error_handler_node_returns_state(
        self, sample_state: DocumentState
    ) -> None:
        """GIVEN state with error WHEN error_handler_node runs THEN returns state unchanged."""
        state = sample_state.copy()
        state["last_error"] = "Test error"
        state["error_type"] = "test_error"

        result = error_handler_node(state)

        assert result["session_id"] == state["session_id"]
        assert result["last_error"] == "Test error"

    @patch("backend.graph_nodes.SessionManager")
    @patch("backend.utils.checkpoint.SessionManager")
    def test_full_error_recovery_cycle(
        self,
        mock_checkpoint_sm: MagicMock,
        mock_graph_sm: MagicMock,
        temp_session_dir: Path,
        session_with_temp_output: tuple[Path, DocumentState],
    ) -> None:
        """GIVEN error occurs, checkpoint exists WHEN error_handler → rollback THEN content restored, ready for agent retry."""
        temp_session_dir, initial_state = session_with_temp_output

        # Mock SessionManager for graph_nodes
        mock_graph_sm_instance = MagicMock()
        mock_graph_sm_instance.get_path.return_value = temp_session_dir
        mock_graph_sm.return_value = mock_graph_sm_instance

        # Mock SessionManager for checkpoint utils
        mock_checkpoint_sm_instance = MagicMock()
        mock_checkpoint_sm_instance.get_path.return_value = temp_session_dir
        mock_checkpoint_sm.return_value = mock_checkpoint_sm_instance

        # Step 1: Create a checkpoint
        from backend.graph_nodes import checkpoint_node

        temp_output = temp_session_dir / "temp_output.md"
        original_content = temp_output.read_text(encoding="utf-8")

        checkpoint_result = checkpoint_node(initial_state)
        checkpoint_id = checkpoint_result["last_checkpoint_id"]
        assert checkpoint_id != ""

        # Step 2: Simulate error - modify temp_output
        temp_output.write_text("Broken content after error", encoding="utf-8")

        # Step 3: Error handler sets error state
        error_state = initial_state.copy()
        error_state["last_error"] = "Test error"
        error_state["error_type"] = "test_error"
        error_state["last_checkpoint_id"] = checkpoint_id
        error_state["retry_count"] = 0

        error_handler_node(error_state)

        # Step 4: Route after error should go to rollback
        route = route_after_error(error_state)
        assert route == "rollback"

        # Step 5: Rollback should restore content
        rollback_result = rollback_node(error_state)

        restored_content = temp_output.read_text(encoding="utf-8")
        assert restored_content == original_content
        assert rollback_result.get("last_checkpoint_id") == ""


class TestRollbackNode:
    """Test rollback_node behavior."""

    @patch("backend.graph_nodes.SessionManager")
    @patch("backend.utils.checkpoint.SessionManager")
    def test_rollback_restores_from_checkpoint(
        self,
        mock_checkpoint_sm: MagicMock,
        mock_graph_sm: MagicMock,
        temp_session_dir: Path,
        session_with_temp_output: tuple[Path, DocumentState],
    ) -> None:
        """GIVEN checkpoint exists WHEN rollback_node runs THEN temp_output.md restored."""
        temp_session_dir, initial_state = session_with_temp_output

        # Mock SessionManager for graph_nodes
        mock_graph_sm_instance = MagicMock()
        mock_graph_sm_instance.get_path.return_value = temp_session_dir
        mock_graph_sm.return_value = mock_graph_sm_instance

        # Mock SessionManager for checkpoint utils
        mock_checkpoint_sm_instance = MagicMock()
        mock_checkpoint_sm_instance.get_path.return_value = temp_session_dir
        mock_checkpoint_sm.return_value = mock_checkpoint_sm_instance

        # Create checkpoint
        from backend.graph_nodes import checkpoint_node

        temp_output = temp_session_dir / "temp_output.md"
        original_content = temp_output.read_text(encoding="utf-8")

        checkpoint_result = checkpoint_node(initial_state)
        checkpoint_id = checkpoint_result["last_checkpoint_id"]

        # Modify content
        temp_output.write_text("Modified", encoding="utf-8")

        # Rollback
        state = initial_state.copy()
        state["last_checkpoint_id"] = checkpoint_id
        rollback_node(state)

        # Assert: restored
        assert temp_output.read_text(encoding="utf-8") == original_content

    @patch("backend.graph_nodes.SessionManager")
    def test_rollback_skips_gracefully_no_checkpoint(
        self,
        mock_sm_class: MagicMock,
        temp_session_dir: Path,
        sample_state: DocumentState,
    ) -> None:
        """GIVEN no checkpoint_id WHEN rollback_node runs THEN no crash, content unchanged."""
        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("Original", encoding="utf-8")

        state = sample_state.copy()
        state["last_checkpoint_id"] = ""

        rollback_node(state)

        assert temp_output.read_text(encoding="utf-8") == "Original"

    @patch("backend.graph_nodes.SessionManager")
    def test_rollback_skips_gracefully_missing_checkpoint_file(
        self,
        mock_sm_class: MagicMock,
        temp_session_dir: Path,
        sample_state: DocumentState,
    ) -> None:
        """GIVEN checkpoint_id but file missing WHEN rollback_node runs THEN no crash, content unchanged."""
        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("Original", encoding="utf-8")

        state = sample_state.copy()
        state["last_checkpoint_id"] = "nonexistent.md"

        rollback_node(state)

        assert temp_output.read_text(encoding="utf-8") == "Original"
