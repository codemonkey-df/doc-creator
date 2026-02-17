"""Unit tests for save_results_node (Story 6.4).

Tests the save_results_node function that handles both success and failure paths:
- Success: Archive session, set status="complete", set output_docx_path to archive path
- Failure: Write FAILED_conversion.md and ERROR_REPORT.txt, set status="failed"
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.state import build_initial_state
from backend.graph_nodes import save_results_node


def _create_mock_sm(temp_docs_base: Path, session_path: Path) -> MagicMock:
    """Create a mock SessionManager with settings."""
    mock_settings = MagicMock()
    mock_settings.docs_base_path = temp_docs_base
    mock_settings.archive_dir = "archive"
    mock_settings.sessions_dir = "sessions"

    mock_sm = MagicMock()
    mock_sm.get_path.return_value = session_path
    mock_sm._settings = mock_settings
    return mock_sm


# Patch target - must patch where it's imported, i.e., in the module that imports it
_SESSION_MANAGER_PATCH = "backend.utils.session_manager.SessionManager"


class TestSaveResultsNode:
    """Tests for save_results_node."""

    @pytest.fixture
    def temp_docs_base(self, tmp_path: Path) -> Path:
        """Create a temp docs base with sessions and archive directories."""
        docs_base = tmp_path / "docs"
        sessions_dir = docs_base / "sessions"
        archive_dir = docs_base / "archive"
        sessions_dir.mkdir(parents=True)
        archive_dir.mkdir(parents=True)
        return docs_base

    def _build_session(self, docs_base: Path, session_id: str) -> Path:
        """Create a session directory with necessary files."""
        session_path = docs_base / "sessions" / session_id
        session_path.mkdir(parents=True)
        # Create temp_output.md
        (session_path / "temp_output.md").write_text(
            "# Test Document\n\nContent here", encoding="utf-8"
        )
        return session_path

    # ==================== Success Path Tests ====================

    def test_success_path_calls_cleanup(self, temp_docs_base: Path) -> None:
        """GIVEN state with retry_count < MAX_RETRY_ATTEMPTS and status != 'failed' WHEN save_results_node runs THEN SessionManager.cleanup(archive=True) is called."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 0
            state["status"] = "processing"
            save_results_node(state)

        mock_sm.cleanup.assert_called_once_with(session_id, archive=True)

    def test_success_path_sets_status_complete(self, temp_docs_base: Path) -> None:
        """GIVEN success state WHEN save_results_node runs THEN status='complete' is returned."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 0
            state["status"] = "processing"
            result = save_results_node(state)

        assert result["status"] == "complete"

    def test_success_path_sets_output_docx_path_to_archive(
        self, temp_docs_base: Path
    ) -> None:
        """GIVEN success state WHEN save_results_node runs THEN output_docx_path points to archive location."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 0
            state["status"] = "processing"
            result = save_results_node(state)

        expected_archive_path = temp_docs_base / "archive" / session_id / "output.docx"
        assert result.get("output_docx_path") == str(expected_archive_path)

    # ==================== Failure Path Tests ====================

    def test_failure_path_copies_temp_output_to_failed_md(
        self, temp_docs_base: Path
    ) -> None:
        """GIVEN temp_output.md exists WHEN failure THEN it's copied to FAILED_conversion.md."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        # Verify temp_output.md exists
        assert (session_path / "temp_output.md").exists()

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 3  # Max retries
            state["status"] = "failed"
            state["last_error"] = "Conversion failed"
            save_results_node(state)

        failed_md_path = session_path / "FAILED_conversion.md"
        assert failed_md_path.exists()
        # Should contain content from temp_output.md
        content = failed_md_path.read_text(encoding="utf-8")
        assert "Test Document" in content

    def test_failure_path_handles_missing_temp_output(
        self, temp_docs_base: Path
    ) -> None:
        """GIVEN temp_output.md missing WHEN failure THEN FAILED_conversion.md is created with placeholder."""
        session_id = str(uuid.uuid4())
        session_path = temp_docs_base / "sessions" / session_id
        session_path.mkdir(parents=True)
        # Don't create temp_output.md

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 3
            state["status"] = "failed"
            state["last_error"] = "Conversion failed"
            save_results_node(state)

        failed_md_path = session_path / "FAILED_conversion.md"
        assert failed_md_path.exists()
        content = failed_md_path.read_text(encoding="utf-8")
        # Should have some content even without temp_output.md
        assert len(content) > 0

    def test_failure_path_writes_error_report(self, temp_docs_base: Path) -> None:
        """GIVEN failure state WHEN save_results_node runs THEN ERROR_REPORT.txt has correct schema."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 3
            state["status"] = "failed"
            state["last_error"] = "Test error message"
            state["error_type"] = "syntax"
            state["handler_outcome"] = "Fix applied"
            state["conversion_success"] = False
            state["quality_passed"] = False
            state["validation_passed"] = False
            state["generation_complete"] = True
            save_results_node(state)

        error_report_path = session_path / "ERROR_REPORT.txt"
        assert error_report_path.exists()
        content = error_report_path.read_text(encoding="utf-8")
        # Check required sections
        assert "Session ID:" in content
        assert "Timestamp:" in content
        assert "Retry Count:" in content
        assert "Status:" in content
        assert "Error Type:" in content
        assert "Error Message:" in content
        assert "Test error message" in content
        assert "Handler Outcome:" in content

    def test_failure_path_truncates_error_to_1000_chars(
        self, temp_docs_base: Path
    ) -> None:
        """GIVEN long last_error WHEN failure THEN it's truncated to 1000 chars."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        long_error = "A" * 2000  # 2000 character error
        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 3
            state["status"] = "failed"
            state["last_error"] = long_error
            state["error_type"] = "unknown"
            state["handler_outcome"] = "N/A"
            save_results_node(state)

        error_report_path = session_path / "ERROR_REPORT.txt"
        content = error_report_path.read_text(encoding="utf-8")
        # The error in the report should be truncated to 1000 chars
        assert len(long_error) == 2000
        # The content in the file should have truncated error (1000 chars max)
        assert content.count("A" * 1000) <= 1  # At most one occurrence of 1000 As

    def test_failure_path_sets_status_failed(self, temp_docs_base: Path) -> None:
        """GIVEN failure state WHEN save_results_node runs THEN status='failed' is returned."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 3
            state["status"] = "failed"
            state["last_error"] = "Test error"
            result = save_results_node(state)

        assert result["status"] == "failed"

    def test_failure_path_does_not_archive_session(self, temp_docs_base: Path) -> None:
        """GIVEN failure state WHEN save_results_node runs THEN session is NOT archived."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 3
            state["status"] = "failed"
            state["last_error"] = "Test error"
            save_results_node(state)

        # cleanup should NOT be called with archive=True on failure
        mock_sm.cleanup.assert_not_called()

    # ==================== Branch Condition Tests ====================

    def test_failure_when_retry_count_at_max(self, temp_docs_base: Path) -> None:
        """GIVEN retry_count >= MAX_RETRY_ATTEMPTS WHEN save_results_node runs THEN failure path taken."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 3  # MAX_RETRY_ATTEMPTS is 3
            state["status"] = "processing"  # Not failed, but max retries reached
            result = save_results_node(state)

        assert result["status"] == "failed"

    def test_failure_when_status_failed(self, temp_docs_base: Path) -> None:
        """GIVEN status='failed' WHEN save_results_node runs THEN failure path taken."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 1  # Under max
            state["status"] = "failed"
            result = save_results_node(state)

        assert result["status"] == "failed"

    def test_success_when_under_max_retries_and_not_failed(
        self, temp_docs_base: Path
    ) -> None:
        """GIVEN retry_count < MAX and status != 'failed' WHEN save_results_node runs THEN success path."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 1  # Under MAX_RETRY_ATTEMPTS (3)
            state["status"] = "processing"  # Not failed
            result = save_results_node(state)

        assert result["status"] == "complete"

    # ==================== Structured Logging Tests ====================

    @patch("backend.graph_nodes.logger")
    def test_logs_session_completed_on_success(
        self, mock_logger: MagicMock, temp_docs_base: Path
    ) -> None:
        """GIVEN success state WHEN save_results_node runs THEN structured log event 'session_completed' is emitted."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 0
            state["status"] = "processing"
            save_results_node(state)

        # Check for session_completed event
        calls = mock_logger.info.call_args_list
        event_names = [call[0][0] for call in calls]
        assert "session_completed" in event_names

    @patch("backend.graph_nodes.logger")
    def test_logs_session_failed_on_failure(
        self, mock_logger: MagicMock, temp_docs_base: Path
    ) -> None:
        """GIVEN failure state WHEN save_results_node runs THEN structured log event 'session_failed' is emitted."""
        session_id = str(uuid.uuid4())
        session_path = self._build_session(temp_docs_base, session_id)

        mock_sm = _create_mock_sm(temp_docs_base, session_path)

        with patch(_SESSION_MANAGER_PATCH, return_value=mock_sm):
            state = build_initial_state(session_id=session_id, input_files=["doc.md"])
            state["retry_count"] = 3
            state["status"] = "failed"
            state["last_error"] = "Test error"
            save_results_node(state)

        # Check for session_failed event
        calls = mock_logger.info.call_args_list
        event_names = [call[0][0] for call in calls]
        assert "session_failed" in event_names
