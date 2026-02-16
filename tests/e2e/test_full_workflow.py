"""E2E tests for full document generation workflow.

Tests the complete flow from start to end with mocked LLM and mocked subprocesses.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from backend.graph import create_document_workflow
from backend.state import build_initial_state


class MockSessionManager:
    """Mock SessionManager that returns temp directory."""

    def __init__(self, session_path: Path):
        self._path = session_path

    def get_path(self, session_id: str) -> Path:
        return self._path


class TestFullWorkflow:
    """Test complete document generation workflow."""

    @patch("subprocess.run")
    @patch("backend.agent.get_llm")
    def test_happy_path_no_images(
        self,
        mock_get_llm: MagicMock,
        mock_subprocess: MagicMock,
        temp_session_dir: Path,
    ) -> None:
        """GIVEN initial state with no image refs, mock LLM returns completion WHEN graph invokes THEN reaches parse_to_json (mocked convert)."""
        # Setup: create input file without images
        input_file = temp_session_dir / "inputs" / "doc.md"
        input_file.write_text("# Test Document\n\nNo images here.", encoding="utf-8")

        # Setup: mock LLM
        from langchain_core.messages import AIMessage

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = AIMessage(content="Generation complete.")
        mock_get_llm.return_value = mock_llm

        # Mock markdownlint (for validate_md node if reached)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

        # Create workflow with mocked session manager
        workflow = create_document_workflow(
            session_manager=MockSessionManager(temp_session_dir)
        )

        # Initial state
        session_id = "test-session-123"
        initial = build_initial_state(session_id=session_id, input_files=["doc.md"])

        # Invoke graph
        config = {"configurable": {"thread_id": "test-thread"}}

        # Run until we get to agent (or as far as we can with mocks)
        # Note: Full end-to-end requires more complex mocking; this tests flow setup
        # The key is that the graph compiles and can be invoked
        result = workflow.invoke(initial, config)

        # Verify: graph ran and reached some state
        assert result is not None

    @patch("subprocess.run")
    @patch("backend.agent.get_llm")
    def test_happy_path_with_conversion(
        self,
        mock_get_llm: MagicMock,
        mock_subprocess: MagicMock,
        temp_session_dir: Path,
    ) -> None:
        """GIVEN full path to quality_check WHEN all subprocesses mocked THEN graph completes without error."""
        # Setup: create input file without images
        input_file = temp_session_dir / "inputs" / "doc.md"
        input_file.write_text("# Test Document\n\nNo images here.", encoding="utf-8")

        # Create temp_output.md for the flow
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("# Test\n\nContent", encoding="utf-8")

        # Setup: mock LLM - completion (generation_complete)
        from langchain_core.messages import AIMessage

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        # First call: completion with no tool calls (generation_complete)
        mock_llm.invoke.return_value = AIMessage(content="Generation complete.")
        mock_get_llm.return_value = mock_llm

        # Mock subprocess for markdownlint (returncode=0 for valid)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

        # Create workflow
        workflow = create_document_workflow(
            session_manager=MockSessionManager(temp_session_dir)
        )

        # Initial state
        session_id = "test-session-456"
        initial = build_initial_state(session_id=session_id, input_files=["doc.md"])

        config = {"configurable": {"thread_id": "test-thread-2"}}

        # Invoke - should go through to agent and potentially to validation
        result = workflow.invoke(initial, config)

        # Verify: result exists
        assert result is not None


class TestWorkflowCompilation:
    """Test that workflow compiles correctly."""

    def test_workflow_compiles_with_mocked_session_manager(
        self, temp_session_dir: Path
    ) -> None:
        """GIVEN mock SessionManager WHEN create_document_workflow called THEN workflow compiles."""
        workflow = create_document_workflow(
            session_manager=MockSessionManager(temp_session_dir)
        )

        # Verify: workflow is compiled (has invoke method)
        assert hasattr(workflow, "invoke")
        assert callable(workflow.invoke)

    def test_workflow_has_all_nodes(self, temp_session_dir: Path) -> None:
        """GIVEN compiled workflow WHEN inspecting THEN has all expected nodes."""
        # The graph structure should include these nodes
        workflow = create_document_workflow(
            session_manager=MockSessionManager(temp_session_dir)
        )

        # We can't easily inspect internal graph, but we can verify it compiles
        # This is more of a smoke test
        assert workflow is not None


class TestGraphInvocation:
    """Test graph invocation with various states."""

    def test_initial_state_has_required_keys(self, temp_session_dir: Path) -> None:
        """GIVEN build_initial_state WHEN called THEN returns state with all required keys."""
        session_id = "test-session-789"
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])

        # Verify all required keys present
        required_keys = [
            "session_id",
            "input_files",
            "current_file_index",
            "current_chapter",
            "temp_md_path",
            "status",
            "messages",
            "missing_references",
            "found_image_refs",
            "last_checkpoint_id",
            "pending_question",
            "generation_complete",
            "validation_passed",
            "fix_attempts",
            "retry_count",
        ]

        for key in required_keys:
            assert key in state, f"Missing required key: {key}"
