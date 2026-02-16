"""E2E tests for full document generation workflow.

Tests the complete flow from start to end with mocked LLM.
"""

from __future__ import annotations

import uuid
from pathlib import Path




class TestFullWorkflow:
    """Test complete document generation workflow."""

    def test_routing_from_tools_to_validate(
        self, temp_session_dir: Path, sample_input_files: list[str]
    ) -> None:
        """GIVEN state with last_checkpoint_id WHEN route_after_tools THEN routes to validate."""
        from backend.routing import route_after_tools
        from backend.state import DocumentState

        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "input_files": sample_input_files,
            "last_checkpoint_id": "20240215_120000_chapter_1.md",
            "pending_question": "",
            "generation_complete": False,
        }

        result = route_after_tools(state)

        assert result == "validate"

    def test_routing_from_tools_to_complete(
        self, temp_session_dir: Path, sample_input_files: list[str]
    ) -> None:
        """GIVEN state with generation_complete WHEN route_after_tools THEN routes to complete."""
        from backend.routing import route_after_tools
        from backend.state import DocumentState

        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "input_files": sample_input_files,
            "last_checkpoint_id": "",
            "pending_question": "",
            "generation_complete": True,
        }

        result = route_after_tools(state)

        assert result == "complete"

    def test_routing_from_tools_to_human_input(
        self, temp_session_dir: Path, sample_input_files: list[str]
    ) -> None:
        """GIVEN state with pending_question WHEN route_after_tools THEN routes to human_input."""
        from backend.routing import route_after_tools
        from backend.state import DocumentState

        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "input_files": sample_input_files,
            "last_checkpoint_id": "",
            "pending_question": "Should I include this image?",
            "generation_complete": False,
        }

        result = route_after_tools(state)

        assert result == "human_input"

    def test_routing_from_tools_to_agent(
        self, temp_session_dir: Path, sample_input_files: list[str]
    ) -> None:
        """GIVEN state without checkpoint, question, or complete WHEN route_after_tools THEN routes to agent."""
        from backend.routing import route_after_tools
        from backend.state import DocumentState

        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "input_files": sample_input_files,
            "last_checkpoint_id": "",
            "pending_question": "",
            "generation_complete": False,
        }

        result = route_after_tools(state)

        assert result == "agent"


class TestWorkflowVariants:
    """Test different workflow paths."""

    def test_validation_failure_triggers_fix_path(self, temp_session_dir: Path) -> None:
        """GIVEN validation fails WHEN route_after_validation THEN routes to agent for fix."""
        from backend.routing import route_after_validation
        from backend.state import DocumentState

        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "validation_passed": False,
            "fix_attempts": 0,
        }

        result = route_after_validation(state)

        assert result == "agent"

    def test_max_fix_attempts_stops_fix_loop(self, temp_session_dir: Path) -> None:
        """GIVEN fix_attempts >= MAX_FIX_ATTEMPTS WHEN route_after_validation THEN routes to complete."""
        from backend.routing import route_after_validation
        from backend.state import DocumentState

        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "validation_passed": False,
            "fix_attempts": 3,  # MAX_FIX_ATTEMPTS = 3
        }

        result = route_after_validation(state)

        assert result == "complete"

    def test_validation_success_routes_to_checkpoint(
        self, temp_session_dir: Path
    ) -> None:
        """GIVEN validation passes WHEN route_after_validation THEN routes to checkpoint."""
        from backend.routing import route_after_validation
        from backend.state import DocumentState

        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "validation_passed": True,
            "fix_attempts": 0,
        }

        result = route_after_validation(state)

        assert result == "checkpoint"
