"""Integration test for error → rollback → retry flow (Epic 4).

Tests the flow: error_handler → (retry) → rollback → agent
"""

from __future__ import annotations

import uuid
from pathlib import Path


from backend.graph_nodes import error_handler_node, rollback_node
from backend.routing import route_after_error
from backend.state import DocumentState


class TestErrorRecoveryFlow:
    """Test error handling and rollback functionality."""

    def test_route_after_error_routes_to_rollback_when_checkpoint_exists(
        self,
    ) -> None:
        """GIVEN state with error and checkpoint WHEN route_after_error THEN routes to rollback."""
        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "last_error": "Conversion failed",
            "error_type": "conversion_error",
            "last_checkpoint_id": "20240215_120000_chapter_1.md",
            "retry_count": 0,
        }

        result = route_after_error(state)

        assert result == "rollback"

    def test_route_after_error_routes_to_complete_when_no_checkpoint(
        self,
    ) -> None:
        """GIVEN state with error but no checkpoint WHEN route_after_error THEN routes to complete."""
        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "last_error": "Conversion failed",
            "error_type": "conversion_error",
            "last_checkpoint_id": "",
            "retry_count": 0,
        }

        result = route_after_error(state)

        assert result == "complete"

    def test_route_after_error_routes_to_complete_when_max_retries(
        self,
    ) -> None:
        """GIVEN state with error and max retries exceeded WHEN route_after_error THEN routes to complete."""
        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "last_error": "Conversion failed",
            "error_type": "conversion_error",
            "last_checkpoint_id": "20240215_120000_chapter_1.md",
            "retry_count": 3,  # MAX_RETRY_ATTEMPTS = 3
        }

        result = route_after_error(state)

        assert result == "complete"

    def test_rollback_node_skips_when_no_checkpoint(
        self, temp_session_dir: Path
    ) -> None:
        """GIVEN no checkpoint_id WHEN rollback_node runs THEN no restore, state unchanged."""
        # Setup
        session_id = str(uuid.uuid4())
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text("Content before", encoding="utf-8")

        state: DocumentState = {
            "session_id": session_id,
            "last_checkpoint_id": "",
        }

        # Execute rollback_node (will skip since no checkpoint_id)
        rollback_node(state)

        # Verify - content unchanged
        content = temp_output.read_text(encoding="utf-8")
        assert content == "Content before"

    def test_error_handler_node_returns_state(self, temp_session_dir: Path) -> None:
        """GIVEN state with error WHEN error_handler_node runs THEN returns state."""
        state: DocumentState = {
            "session_id": str(uuid.uuid4()),
            "last_error": "Test error",
            "error_type": "test_error",
        }

        result = error_handler_node(state)

        assert result["session_id"] == state["session_id"]
        assert result["last_error"] == "Test error"
