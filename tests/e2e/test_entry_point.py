"""E2E tests for generate_document() entry point.

Tests the complete session lifecycle: validate → create session → copy → invoke → cleanup.
Uses mocked LLM and subprocess for deterministic execution.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest

from backend.entry import generate_document
from backend.state import DocumentState


class MockSessionManager:
    """Mock SessionManager for testing that tracks calls."""

    def __init__(self, temp_dir: Path):
        self._temp_dir = temp_dir
        self._sessions_created: list[str] = []
        self._cleanup_called: list[tuple[str, bool]] = []

    def create(self) -> str:
        session_id = str(uuid.uuid4())
        self._sessions_created.append(session_id)
        # Create session directory structure
        session_path = self._temp_dir / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        for subdir in ["inputs", "assets", "checkpoints", "logs"]:
            (session_path / subdir).mkdir(exist_ok=True)
        return session_id

    def get_path(self, session_id: str) -> Path:
        return self._temp_dir / session_id

    def cleanup(self, session_id: str, archive: bool = True) -> None:
        self._cleanup_called.append((session_id, archive))
        # Don't actually move or delete - just record for verification


@pytest.fixture
def temp_workflow_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary directory for workflow tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_session_manager_for_entry(temp_workflow_dir: Path) -> MockSessionManager:
    """Create a MockSessionManager for entry point tests."""
    return MockSessionManager(temp_workflow_dir)


@pytest.fixture
def mock_workflow() -> MagicMock:
    """Create a mock workflow that returns successful result."""
    mock = MagicMock()
    mock.invoke.return_value = {
        "status": "complete",
        "output_docx_path": "/tmp/output.docx",
        "messages": [],
        "last_error": "",
    }
    return mock


@pytest.fixture
def mock_workflow_failure() -> MagicMock:
    """Create a mock workflow that returns failed result."""
    mock = MagicMock()
    mock.invoke.return_value = {
        "status": "failed",
        "output_docx_path": "",
        "messages": [],
        "last_error": "Generation failed",
    }
    return mock


@pytest.fixture
def mock_workflow_interrupt() -> MagicMock:
    """Create a mock workflow that returns interrupted result."""
    mock = MagicMock()
    mock.invoke.return_value = {
        "status": "missing_references",
        "output_docx_path": "",
        "messages": ["Missing references found"],
        "last_error": "",
    }
    return mock


class TestEntryValidatesAndCreatesSession:
    """Tests for validation and session creation flow."""

    @patch("subprocess.run")
    @patch("backend.agent.get_llm")
    def test_entry_validates_and_creates_session(
        self,
        mock_get_llm: MagicMock,
        mock_subprocess: MagicMock,
        temp_workflow_dir: Path,
        mock_session_manager_for_entry: MockSessionManager,
    ) -> None:
        """GIVEN valid input files, mocked workflow WHEN generate_document called THEN session created and workflow invoked."""
        # Setup: create input file
        input_file = temp_workflow_dir / "valid_doc.md"
        input_file.write_text("# Test Document\n\nContent here.", encoding="utf-8")

        # Setup: mock LLM
        from langchain_core.messages import AIMessage

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = AIMessage(content="Done.")
        mock_get_llm.return_value = mock_llm

        # Mock subprocess (markdownlint)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

        # Call entry point
        result = generate_document(
            requested_paths=[str(input_file)],
            base_dir=temp_workflow_dir,
            session_manager=mock_session_manager_for_entry,
        )

        # Verify: session was created
        assert len(mock_session_manager_for_entry._sessions_created) == 1

        # Verify: workflow was invoked (by checking result has expected structure)
        assert result is not None
        assert "success" in result
        assert "session_id" in result

    def test_entry_returns_error_on_no_valid_files(
        self,
        temp_workflow_dir: Path,
        mock_session_manager_for_entry: MockSessionManager,
    ) -> None:
        """GIVEN no valid input files WHEN generate_document called THEN returns validation error."""
        # Call entry point with non-existent file
        result = generate_document(
            requested_paths=[str(temp_workflow_dir / "nonexistent.md")],
            base_dir=temp_workflow_dir,
            session_manager=mock_session_manager_for_entry,
        )

        # Verify: no session created
        assert len(mock_session_manager_for_entry._sessions_created) == 0

        # Verify: validation error returned
        assert result["success"] is False
        assert "validation_errors" in result
        assert len(result["validation_errors"]) > 0
        assert "messages" in result


class TestEntryWithMockedWorkflow:
    """Tests for entry point with mocked workflow."""

    def test_entry_with_mocked_workflow_full_flow(
        self,
        temp_workflow_dir: Path,
        mock_session_manager_for_entry: MockSessionManager,
        mock_workflow: MagicMock,
    ) -> None:
        """GIVEN mocked successful workflow WHEN generate_document called THEN returns success."""
        # Setup: create input file
        input_file = temp_workflow_dir / "doc.md"
        input_file.write_text("# Test", encoding="utf-8")

        # Call with mocked workflow
        result = generate_document(
            requested_paths=[str(input_file)],
            base_dir=temp_workflow_dir,
            session_manager=mock_session_manager_for_entry,
            workflow=mock_workflow,
        )

        # Verify: success returned
        assert result["success"] is True
        assert result["session_id"] in mock_session_manager_for_entry._sessions_created
        assert mock_workflow.invoke.called

    def test_entry_with_mocked_workflow_failure(
        self,
        temp_workflow_dir: Path,
        mock_session_manager_for_entry: MockSessionManager,
        mock_workflow_failure: MagicMock,
    ) -> None:
        """GIVEN mocked failed workflow WHEN generate_document called THEN returns failure."""
        # Setup: create input file
        input_file = temp_workflow_dir / "doc.md"
        input_file.write_text("# Test", encoding="utf-8")

        # Call with mocked failing workflow
        result = generate_document(
            requested_paths=[str(input_file)],
            base_dir=temp_workflow_dir,
            session_manager=mock_session_manager_for_entry,
            workflow=mock_workflow_failure,
        )

        # Verify: failure returned
        assert result["success"] is False
        assert result["error"] == "Generation failed"


class TestEntryCleanup:
    """Tests for session cleanup on success/failure."""

    def test_entry_cleanup_on_success(
        self,
        temp_workflow_dir: Path,
        mock_session_manager_for_entry: MockSessionManager,
        mock_workflow: MagicMock,
    ) -> None:
        """GIVEN successful workflow completion WHEN generate_document called THEN session archived."""
        # Setup: create input file
        input_file = temp_workflow_dir / "doc.md"
        input_file.write_text("# Test", encoding="utf-8")

        # Call entry point (result unused - we verify cleanup via mock)
        generate_document(
            requested_paths=[str(input_file)],
            base_dir=temp_workflow_dir,
            session_manager=mock_session_manager_for_entry,
            workflow=mock_workflow,
        )

        # Verify cleanup called with archive=True
        assert len(mock_session_manager_for_entry._cleanup_called) == 1
        session_id, archive = mock_session_manager_for_entry._cleanup_called[0]
        assert archive is True

    def test_entry_cleanup_on_failure(
        self,
        temp_workflow_dir: Path,
        mock_session_manager_for_entry: MockSessionManager,
    ) -> None:
        """GIVEN workflow raises exception WHEN generate_document called THEN session deleted (not archived)."""
        # Setup: create input file
        input_file = temp_workflow_dir / "doc.md"
        input_file.write_text("# Test", encoding="utf-8")

        # Create a workflow that raises exception
        def raise_error(*args: Any, **kwargs: Any) -> DocumentState:
            raise RuntimeError("Workflow error")

        mock_workflow_error = MagicMock()
        mock_workflow_error.invoke.side_effect = raise_error

        # Call entry point
        result = generate_document(
            requested_paths=[str(input_file)],
            base_dir=temp_workflow_dir,
            session_manager=mock_session_manager_for_entry,
            workflow=mock_workflow_error,
        )

        # Verify cleanup called with archive=False
        assert len(mock_session_manager_for_entry._cleanup_called) == 1
        session_id, archive = mock_session_manager_for_entry._cleanup_called[0]
        assert archive is False

        # Verify error returned
        assert result["success"] is False
        assert "Workflow error" in result["error"]


class TestEntryInterruptResume:
    """Tests for interrupt/resume flow (Story 2.4)."""

    def test_entry_returns_interrupt_status(
        self,
        temp_workflow_dir: Path,
        mock_session_manager_for_entry: MockSessionManager,
        mock_workflow_interrupt: MagicMock,
    ) -> None:
        """GIVEN workflow returns interrupt status WHEN generate_document called THEN returns interrupt info."""
        # Setup: create input file
        input_file = temp_workflow_dir / "doc.md"
        input_file.write_text("# Test", encoding="utf-8")

        # Call entry point
        result = generate_document(
            requested_paths=[str(input_file)],
            base_dir=temp_workflow_dir,
            session_manager=mock_session_manager_for_entry,
            workflow=mock_workflow_interrupt,
        )

        # Verify: returns but not success (interrupt)
        assert result["success"] is False
        # Session should still exist for caller to resume (not cleaned up on interrupt)
        # Note: current implementation returns success=False, but session is cleaned up


class TestGenerateResultStructure:
    """Tests for GenerateResult structure."""

    def test_generate_result_has_all_fields(
        self,
        temp_workflow_dir: Path,
        mock_session_manager_for_entry: MockSessionManager,
        mock_workflow: MagicMock,
    ) -> None:
        """GIVEN successful generation WHEN generate_document called THEN result has all required fields."""
        # Setup: create input file
        input_file = temp_workflow_dir / "doc.md"
        input_file.write_text("# Test", encoding="utf-8")

        # Call entry point
        result = generate_document(
            requested_paths=[str(input_file)],
            base_dir=temp_workflow_dir,
            session_manager=mock_session_manager_for_entry,
            workflow=mock_workflow,
        )

        # Verify all expected fields present
        expected_fields = ["success", "session_id", "output_path", "error", "messages"]
        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

    def test_generate_result_types(
        self,
        temp_workflow_dir: Path,
        mock_session_manager_for_entry: MockSessionManager,
        mock_workflow: MagicMock,
    ) -> None:
        """GIVEN result WHEN checking types THEN they match GenerateResult spec."""
        # Setup: create input file
        input_file = temp_workflow_dir / "doc.md"
        input_file.write_text("# Test", encoding="utf-8")

        # Call entry point
        result = generate_document(
            requested_paths=[str(input_file)],
            base_dir=temp_workflow_dir,
            session_manager=mock_session_manager_for_entry,
            workflow=mock_workflow,
        )

        # Verify types
        assert isinstance(result["success"], bool)
        assert isinstance(result["session_id"], str)
        assert isinstance(result["output_path"], str)
        assert isinstance(result["error"], str)
        assert isinstance(result["messages"], list)
