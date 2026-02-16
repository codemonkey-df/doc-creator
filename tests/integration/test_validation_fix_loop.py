"""Integration tests for validation → fix loop flow (Epic 2.5).

Tests multi-node flows: validate_md → agent (fix) or checkpoint with mocked subprocess.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from backend.graph_nodes import checkpoint_node, validate_md_node
from backend.routing import route_after_validation
from backend.state import DocumentState


class TestValidationFixLoop:
    """Test validation → fix loop with mocked markdownlint."""

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_valid_md_routes_to_checkpoint(
        self,
        mock_sm_class: MagicMock,
        mock_run: MagicMock,
        session_with_temp_output: tuple[Path, DocumentState],
    ) -> None:
        """GIVEN valid markdown WHEN validate_md runs THEN validation_passed=True, routes to checkpoint."""
        temp_session_dir, initial_state = session_with_temp_output

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        # Mock markdownlint returning success (returncode=0, no issues)
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

        # Execute validate_md_node
        result = validate_md_node(initial_state)

        # Assert: validation passed
        assert result["validation_passed"] is True
        assert len(result["validation_issues"]) == 0

        # Assert: routing would go to checkpoint
        routing = route_after_validation(result)
        assert routing == "checkpoint"

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_invalid_md_under_max_attempts_routes_to_agent(
        self,
        mock_sm_class: MagicMock,
        mock_run: MagicMock,
        session_with_temp_output: tuple[Path, DocumentState],
    ) -> None:
        """GIVEN invalid markdown, fix_attempts=1 WHEN validate_md runs THEN routes to agent for fix."""
        temp_session_dir, initial_state = session_with_temp_output

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

        # Set fix_attempts to 1 (under max)
        initial_state["fix_attempts"] = 1

        # Execute validate_md_node
        result = validate_md_node(initial_state)

        # Assert: validation failed
        assert result["validation_passed"] is False
        assert len(result["validation_issues"]) > 0

        # Assert: routing would go to agent for fix
        routing = route_after_validation(result)
        assert routing == "agent"

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_invalid_md_at_max_attempts_routes_to_complete(
        self,
        mock_sm_class: MagicMock,
        mock_run: MagicMock,
        session_with_temp_output: tuple[Path, DocumentState],
    ) -> None:
        """GIVEN invalid markdown, fix_attempts=3 (max) WHEN validate_md runs THEN routes to complete."""
        temp_session_dir, initial_state = session_with_temp_output

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

        # Set fix_attempts to MAX_FIX_ATTEMPTS (3)
        initial_state["fix_attempts"] = 3

        # Execute validate_md_node
        result = validate_md_node(initial_state)

        # Assert: validation failed
        assert result["validation_passed"] is False

        # Assert: routing would go to complete (stop fix loop)
        routing = route_after_validation(result)
        assert routing == "complete"

    @patch("subprocess.run")
    @patch("backend.graph_nodes.SessionManager")
    def test_checkpoint_after_validation_creates_file(
        self,
        mock_sm_class: MagicMock,
        mock_run: MagicMock,
        session_with_temp_output: tuple[Path, DocumentState],
    ) -> None:
        """GIVEN validation passed WHEN checkpoint_node runs THEN checkpoint file created in checkpoints/."""
        temp_session_dir, initial_state = session_with_temp_output

        # Mock SessionManager
        mock_sm = MagicMock()
        mock_sm.get_path.return_value = temp_session_dir
        mock_sm_class.return_value = mock_sm

        # Mock markdownlint returning success
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

        # First validate
        validated = validate_md_node(initial_state)
        assert validated["validation_passed"] is True

        # Execute checkpoint_node
        result = checkpoint_node(validated)

        # Assert: checkpoint created
        assert result["last_checkpoint_id"] != ""
        checkpoint_file = (
            temp_session_dir / "checkpoints" / result["last_checkpoint_id"]
        )
        assert checkpoint_file.exists(), (
            f"Checkpoint file should exist at {checkpoint_file}"
        )

        # Verify content matches temp_output.md
        temp_output = temp_session_dir / "temp_output.md"
        assert checkpoint_file.read_text(encoding="utf-8") == temp_output.read_text(
            encoding="utf-8"
        )


class TestValidationRouting:
    """Test routing decisions after validation."""

    def test_validation_pass_routes_to_checkpoint(
        self, sample_state: DocumentState
    ) -> None:
        """GIVEN validation_passed=True WHEN route_after_validation THEN routes to checkpoint."""
        state = sample_state.copy()
        state["validation_passed"] = True

        result = route_after_validation(state)
        assert result == "checkpoint"

    def test_validation_fail_under_max_routes_to_agent(
        self, sample_state: DocumentState
    ) -> None:
        """GIVEN validation_passed=False, fix_attempts=1 WHEN route_after_validation THEN routes to agent."""
        state = sample_state.copy()
        state["validation_passed"] = False
        state["fix_attempts"] = 1

        result = route_after_validation(state)
        assert result == "agent"

    def test_validation_fail_at_max_routes_to_complete(
        self, sample_state: DocumentState
    ) -> None:
        """GIVEN validation_passed=False, fix_attempts=3 WHEN route_after_validation THEN routes to complete."""
        state = sample_state.copy()
        state["validation_passed"] = False
        state["fix_attempts"] = 3

        result = route_after_validation(state)
        assert result == "complete"
