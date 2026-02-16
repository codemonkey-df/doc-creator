"""E2E tests for error paths in workflow (Epic 4).

Tests: error handling at various points in the workflow.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from backend.graph_nodes import error_handler_node
from backend.routing import route_after_error
from backend.state import build_initial_state
import uuid


class MockSessionManager:
    """Mock SessionManager that returns temp directory."""

    def __init__(self, session_path: Path):
        self._path = session_path

    def get_path(self, session_id: str) -> Path:
        return self._path


class TestErrorPaths:
    """Test error handling paths in the workflow."""

    def test_error_handler_node_sets_error_state(self, temp_session_dir: Path) -> None:
        """GIVEN state with error WHEN error_handler_node runs THEN logs and returns state."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Test error message"
        state["error_type"] = "test_error"

        result = error_handler_node(state)

        # Assert: state returned with error
        assert result["last_error"] == "Test error message"
        assert result["error_type"] == "test_error"


class TestErrorRouting:
    """Test routing after errors."""

    def test_error_with_checkpoint_routes_to_rollback(
        self, temp_session_dir: Path
    ) -> None:
        """GIVEN error with checkpoint_id, retry_count=0 WHEN route_after_error THEN routes to rollback."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Conversion failed"
        state["error_type"] = "conversion_error"
        state["last_checkpoint_id"] = "20240215_120000_chapter_1.md"
        state["retry_count"] = 0

        result = route_after_error(state)

        assert result == "rollback"

    def test_error_without_checkpoint_routes_to_complete(
        self, temp_session_dir: Path
    ) -> None:
        """GIVEN error without checkpoint_id WHEN route_after_error THEN routes to complete."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Conversion failed"
        state["error_type"] = "conversion_error"
        state["last_checkpoint_id"] = ""
        state["retry_count"] = 0

        result = route_after_error(state)

        assert result == "complete"

    def test_error_max_retries_routes_to_complete(self, temp_session_dir: Path) -> None:
        """GIVEN error with retry_count=3 (max) WHEN route_after_error THEN routes to complete."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Conversion failed"
        state["error_type"] = "conversion_error"
        state["last_checkpoint_id"] = "20240215_120000_chapter_1.md"
        state["retry_count"] = 3  # MAX_RETRY_ATTEMPTS = 3

        result = route_after_error(state)

        assert result == "complete"

    def test_error_under_max_retries_routes_to_rollback(
        self, temp_session_dir: Path
    ) -> None:
        """GIVEN error with retry_count=2 (under max) WHEN route_after_error THEN routes to rollback."""
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["last_error"] = "Conversion failed"
        state["error_type"] = "conversion_error"
        state["last_checkpoint_id"] = "20240215_120000_chapter_1.md"
        state["retry_count"] = 2

        result = route_after_error(state)

        assert result == "rollback"


class TestConversionErrorPath:
    """Test conversion failure error path."""

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_conversion_failure_triggers_error_handler(
        self,
        mock_sm_class: MagicMock,
        mock_subprocess: MagicMock,
        temp_session_dir: Path,
    ) -> None:
        """GIVEN parse_to_json succeeds, convert fails (mock) WHEN convert_with_docxjs_node runs THEN routes to error_handler."""
        from backend.graph_nodes import convert_with_docxjs_node, parse_to_json_node

        # Setup: create temp_output.md
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("# Test\n\nContent", encoding="utf-8")

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        # Parse first
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        parse_result = parse_to_json_node(state)

        # Mock Node.js converter to fail
        mock_subprocess.return_value = MagicMock(
            returncode=1, stdout="", stderr="Conversion failed: invalid JSON"
        )

        # Execute convert
        result = convert_with_docxjs_node(parse_result)

        # Assert: conversion failed, routes to error_handler
        assert result["conversion_success"] is False
        assert result["status"] == "error_handling"
        assert result["last_error"] != ""
