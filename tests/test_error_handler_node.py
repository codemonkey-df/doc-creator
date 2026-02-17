"""Unit tests for error_handler_node (Story 6.3).

Tests the full error handling flow:
- Classify error using the classifier
- Rollback from checkpoint if available
- Invoke handler based on error_type
- Increment retry_count
- Return updated state
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path
import uuid

from backend.state import build_initial_state
from backend.graph_nodes import error_handler_node


class TestErrorHandlerNode:
    """Test error_handler_node with mocked classifier and handlers."""

    def test_classifies_error_and_sets_error_type(self, tmp_path: Path) -> None:
        """GIVEN generic error message WHEN error_handler_node runs THEN classifies as unknown."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Something went wrong"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "unknown"
        assert result["retry_count"] == 1

    def test_classifies_syntax_error(self, tmp_path: Path) -> None:
        """GIVEN syntax error message WHEN error_handler_node runs THEN classifies as syntax."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Unclosed code block at line 42"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "syntax"
        assert result["retry_count"] == 1

    def test_classifies_encoding_error(self, tmp_path: Path) -> None:
        """GIVEN encoding error message WHEN error_handler_node runs THEN classifies as encoding."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Invalid UTF-8 encoding at line 10"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "encoding"
        assert result["retry_count"] == 1

    def test_classifies_asset_error(self, tmp_path: Path) -> None:
        """GIVEN asset error message WHEN error_handler_node runs THEN classifies as asset."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Image file not found: diagram.png"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "asset"
        assert result["retry_count"] == 1

    def test_classifies_structural_error(self, tmp_path: Path) -> None:
        """GIVEN structural error message WHEN error_handler_node runs THEN classifies as structural."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Heading hierarchy skip detected: H1 to H3"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "structural"
        assert result["retry_count"] == 1

    def test_increments_retry_count(self, tmp_path: Path) -> None:
        """GIVEN retry_count=2 WHEN error_handler_node runs THEN returns retry_count=3."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Test error"
        state["retry_count"] = 2

        result = error_handler_node(state)

        assert result["retry_count"] == 3

    def test_sets_handler_outcome(self, tmp_path: Path) -> None:
        """GIVEN state with error WHEN error_handler_node runs THEN sets handler_outcome."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Test error"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert "handler_outcome" in result

    @patch("backend.utils.checkpoint.restore_from_checkpoint")
    def test_rollback_performed_when_checkpoint_exists(
        self, mock_restore: MagicMock, tmp_path: Path
    ) -> None:
        """GIVEN state with checkpoint_id WHEN error_handler_node runs THEN restores from checkpoint."""
        mock_restore.return_value = True

        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Test error"
        state["last_checkpoint_id"] = "20240215_120000_chapter_1.md"
        state["retry_count"] = 0

        error_handler_node(state)

        mock_restore.assert_called_once_with(session_id, "20240215_120000_chapter_1.md")

    @patch("backend.utils.checkpoint.restore_from_checkpoint")
    def test_no_rollback_when_checkpoint_id_empty(
        self, mock_restore: MagicMock, tmp_path: Path
    ) -> None:
        """GIVEN state without checkpoint_id WHEN error_handler_node runs THEN skips rollback."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Test error"
        state["last_checkpoint_id"] = ""
        state["retry_count"] = 0

        error_handler_node(state)

        mock_restore.assert_not_called()

    def test_syntax_error_sets_handler_outcome(self, tmp_path: Path) -> None:
        """GIVEN syntax error WHEN error_handler_node runs THEN sets appropriate handler_outcome."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Unclosed code block at line 5"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "syntax"
        assert "handler_outcome" in result

    def test_encoding_error_sets_handler_outcome(self, tmp_path: Path) -> None:
        """GIVEN encoding error WHEN error_handler_node runs THEN sets appropriate handler_outcome."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Invalid UTF-8 encoding"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "encoding"
        assert "handler_outcome" in result

    def test_asset_error_sets_handler_outcome(self, tmp_path: Path) -> None:
        """GIVEN asset error WHEN error_handler_node runs THEN sets appropriate handler_outcome."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Image not found: diagram.png"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "asset"
        assert "handler_outcome" in result

    def test_structural_error_sets_handler_outcome(self, tmp_path: Path) -> None:
        """GIVEN structural error WHEN error_handler_node runs THEN sets appropriate handler_outcome."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Heading hierarchy issue"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "structural"
        assert "handler_outcome" in result

    def test_unknown_error_sets_appropriate_message(self, tmp_path: Path) -> None:
        """GIVEN unknown error type WHEN error_handler_node runs THEN sets appropriate message."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Some unknown error"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["error_type"] == "unknown"
        assert result["handler_outcome"] == "Unknown error - no fix applied"

    def test_sets_status_to_error_handling(self, tmp_path: Path) -> None:
        """GIVEN state with error WHEN error_handler_node runs THEN sets status to error_handling."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Test error"
        state["status"] = "processing"
        state["retry_count"] = 0

        result = error_handler_node(state)

        assert result["status"] == "error_handling"

    def test_preserves_other_state_keys(self, tmp_path: Path) -> None:
        """GIVEN state with other keys WHEN error_handler_node runs THEN preserves them."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Test error"
        state["retry_count"] = 0
        state["custom_field"] = "custom_value"
        state["messages"] = ["message1", "message2"]

        result = error_handler_node(state)

        assert result["custom_field"] == "custom_value"
        assert result["messages"] == ["message1", "message2"]
        assert result["session_id"] == session_id
        assert result["input_files"] == ["doc.md"]
