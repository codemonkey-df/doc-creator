"""E2E tests for validation loop flow (Epic 2.5).

Tests: validation failure -> agent fix -> validation success flow.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


from backend.graph_nodes import validate_md_node
from backend.routing import route_after_validation
from backend.state import build_initial_state


class TestValidationLoop:
    """Test validation failure -> fix loop."""

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_validation_failure_loops_back_to_agent(
        self, mock_sm_class: MagicMock, mock_run: MagicMock, temp_session_dir: Path
    ) -> None:
        """GIVEN validation fails (markdownlint returns issues) WHEN route_after_validation THEN routes to agent for fix."""
        # Setup: create temp_output.md
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("# Test\n\nContent", encoding="utf-8")

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        # Mock markdownlint returning failure
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='[{"lineNumber": 1, "ruleNames": ["MD041"], "ruleDescription": "First line should be a heading"}]',
            stderr="",
        )

        # Initial state
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["fix_attempts"] = 0

        # First validation - should fail
        result = validate_md_node(state)

        # Assert: validation failed
        assert result["validation_passed"] is False
        assert len(result["validation_issues"]) > 0

        # Assert: routing would go to agent for fix
        routing = route_after_validation(result)
        assert routing == "agent"

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_validation_then_fix_then_pass(
        self, mock_sm_class: MagicMock, mock_run: MagicMock, temp_session_dir: Path
    ) -> None:
        """GIVEN validation fails first, then passes (after agent fix) WHEN route_after_validation THEN routes to checkpoint."""
        # Setup: create temp_output.md
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("# Test\n\nContent", encoding="utf-8")

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        # Initial state
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["fix_attempts"] = 0

        # First validation - fails
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='[{"lineNumber": 1, "ruleNames": ["MD041"], "ruleDescription": "First line should be a heading"}]',
            stderr="",
        )
        result1 = validate_md_node(state)
        assert result1["validation_passed"] is False
        assert route_after_validation(result1) == "agent"

        # Second validation - passes (after agent fixes the content)
        # Simulate agent fixed the content
        temp_output.write_text("# Fixed Heading\n\nContent", encoding="utf-8")

        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        result2 = validate_md_node(result1)
        assert result2["validation_passed"] is True
        assert route_after_validation(result2) == "checkpoint"

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_max_fix_attempts_stops_loop(
        self, mock_sm_class: MagicMock, mock_run: MagicMock, temp_session_dir: Path
    ) -> None:
        """GIVEN validation fails 3 times (max) WHEN route_after_validation THEN routes to complete, stops fix loop."""
        # Setup: create temp_output.md
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("# Test\n\nContent", encoding="utf-8")

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        # Mock markdownlint always failing
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='[{"lineNumber": 1, "ruleNames": ["MD041"], "ruleDescription": "First line should be a heading"}]',
            stderr="",
        )

        # Initial state with max fix attempts already used
        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])
        state["fix_attempts"] = 3  # Already at max

        # Validation - should fail
        result = validate_md_node(state)

        # Assert: validation failed
        assert result["validation_passed"] is False

        # Assert: routing goes to complete (stop fix loop)
        routing = route_after_validation(result)
        assert routing == "complete"


class TestValidationNodeBehavior:
    """Test validate_md_node behavior."""

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_validate_md_with_valid_markdown(
        self, mock_sm_class: MagicMock, mock_run: MagicMock, temp_session_dir: Path
    ) -> None:
        """GIVEN valid markdown WHEN validate_md_node runs THEN validation_passed=True."""
        # Setup
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("# Valid Heading\n\nSome content.", encoding="utf-8")

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])

        result = validate_md_node(state)

        assert result["validation_passed"] is True
        assert len(result["validation_issues"]) == 0

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_validate_md_with_invalid_markdown(
        self, mock_sm_class: MagicMock, mock_run: MagicMock, temp_session_dir: Path
    ) -> None:
        """GIVEN invalid markdown (unclosed fence) WHEN validate_md_node runs THEN validation_passed=False."""
        # Setup
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text(
            "# Heading\n\n```python\nprint('hello')", encoding="utf-8"
        )  # Unclosed fence

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='[{"lineNumber": 3, "ruleNames": ["MD014"], "ruleDescription": "Code fence"}]',
            stderr="",
        )

        session_id = str(uuid.uuid4())
        state = build_initial_state(session_id=session_id, input_files=["doc.md"])

        result = validate_md_node(state)

        assert result["validation_passed"] is False
        assert len(result["validation_issues"]) > 0
