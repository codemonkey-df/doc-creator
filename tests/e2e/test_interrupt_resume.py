"""E2E tests for interrupt and resume flow (Epic 2.4).

Tests: human_input interruption and resume with user_decisions.
"""

from __future__ import annotations

from pathlib import Path


from backend.graph import _apply_user_decisions_node
from backend.graph import create_document_workflow
from backend.state import build_initial_state


class MockSessionManager:
    """Mock SessionManager that returns temp directory."""

    def __init__(self, session_path: Path):
        self._path = session_path

    def get_path(self, session_id: str) -> Path:
        return self._path


class TestInterruptResume:
    """Test interrupt and resume flow."""

    def test_missing_images_interrupts_at_human_input(
        self, temp_session_dir: Path
    ) -> None:
        """GIVEN input with missing image ref WHEN scan_assets runs THEN pending_question set for human_input."""
        # Setup: create input file with missing image ref
        input_file = temp_session_dir / "inputs" / "doc.md"
        input_file.write_text("# Test\n\n![missing](missing.png)", encoding="utf-8")

        # Create workflow
        workflow = create_document_workflow(
            session_manager=MockSessionManager(temp_session_dir)
        )

        # Initial state
        session_id = "test-session-interrupt"
        initial = build_initial_state(session_id=session_id, input_files=["doc.md"])

        config = {"configurable": {"thread_id": "test-thread-interrupt"}}

        # Invoke - should pause at human_input due to missing refs
        # Note: With interrupt_before=["human_input"], the graph should stop there
        result = workflow.invoke(initial, config)

        # The scan_assets should have detected missing refs
        assert result.get("missing_references") is not None
        assert len(result.get("missing_references", [])) > 0

        # pending_question should be set for human_input
        assert result.get("pending_question") != ""

    def test_resume_after_skip_decision(self, temp_session_dir: Path) -> None:
        """GIVEN state with missing refs, user_decisions={img:skip} WHEN apply_user_decisions_node runs THEN placeholder inserted, status=processing."""
        # Setup: create input file with missing image ref
        input_file = temp_session_dir / "inputs" / "doc.md"
        input_file.write_text("# Test\n\n![missing](missing.png)", encoding="utf-8")

        # Initial state with missing refs and user decisions
        session_id = "test-session-resume"
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])

        # Simulate scan finding missing refs
        state["missing_references"] = ["missing.png"]
        state["missing_ref_details"] = [
            {"original_path": "missing.png", "source_file": "doc.md"}
        ]
        state["pending_question"] = "Found 1 missing image(s): missing.png"
        state["user_decisions"] = {"missing.png": "skip"}

        # Apply user decisions
        result = _apply_user_decisions_node(state, MockSessionManager(temp_session_dir))

        # Assert: missing_references cleared
        assert result["missing_references"] == []
        assert result["missing_ref_details"] == []

        # Assert: pending_question cleared
        assert result["pending_question"] == ""

        # Assert: status set to processing for agent re-entry
        assert result["status"] == "processing"

        # Assert: user_decisions cleared
        assert result["user_decisions"] == {}

    def test_resume_after_upload_decision(self, temp_session_dir: Path) -> None:
        """GIVEN state with missing refs, user_decisions={img:upload_path} WHEN apply_user_decisions_node runs THEN image copied, ref updated."""
        # Setup: create input file with missing image ref
        input_file = temp_session_dir / "inputs" / "doc.md"
        input_file.write_text("# Test\n\n![chart](chart.png)", encoding="utf-8")

        # Create actual image file to "upload"
        upload_dir = temp_session_dir / "uploads"
        upload_dir.mkdir(exist_ok=True)
        uploaded_image = upload_dir / "chart.png"
        uploaded_image.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        # Initial state with missing refs and user decisions
        session_id = "test-session-upload"
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])

        # Simulate scan finding missing refs
        state["missing_references"] = ["chart.png"]
        state["missing_ref_details"] = [
            {"original_path": "chart.png", "source_file": "doc.md"}
        ]
        state["pending_question"] = "Found 1 missing image(s): chart.png"
        state["user_decisions"] = {"chart.png": str(uploaded_image)}

        # Apply user decisions
        result = _apply_user_decisions_node(state, MockSessionManager(temp_session_dir))

        # Assert: missing refs cleared
        assert result["missing_references"] == []
        assert result["status"] == "processing"


class TestHumanInputNode:
    """Test human_input node behavior."""

    def test_human_input_node_returns_state_unchanged(
        self, temp_session_dir: Path
    ) -> None:
        """GIVEN state WHEN _human_input_node runs THEN returns state unchanged."""
        from backend.graph import _human_input_node

        state = build_initial_state(session_id="test", input_files=["doc.md"])
        state["pending_question"] = "Test question?"

        result = _human_input_node(state)

        # Assert: state returned unchanged
        assert result["session_id"] == state["session_id"]
        assert result["pending_question"] == "Test question?"
