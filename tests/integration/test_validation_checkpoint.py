"""Integration test for validation → checkpoint flow (Epic 4).

Tests the flow: validate_md → (valid) → checkpoint → agent
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


from backend.graph_nodes import validate_md_node, checkpoint_node
from backend.state import DocumentState


class TestValidationCheckpointFlow:
    """Test validation passes and checkpoint is created."""

    def test_validate_md_passes_with_valid_markdown(
        self, temp_session_dir: Path, sample_markdown_content: str
    ) -> None:
        """GIVEN valid markdown in temp_output.md WHEN validate_md_node runs THEN validation_passed=True."""
        # Setup
        session_id = str(uuid.uuid4())
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text(sample_markdown_content, encoding="utf-8")

        state: DocumentState = {
            "session_id": session_id,
            "temp_md_path": str(temp_output),
        }

        # Mock subprocess.run to return valid markdownlint result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[]"

        with patch("subprocess.run", return_value=mock_result):
            result = validate_md_node(state)

        # Verify
        assert result["validation_passed"] is True
        assert result["validation_issues"] == []

    def test_validate_md_fails_with_invalid_markdown(
        self, temp_session_dir: Path, sample_markdown_with_invalid: str
    ) -> None:
        """GIVEN invalid markdown (unclosed fence) WHEN validate_md_node runs THEN validation_passed=False with issues."""
        # Setup
        session_id = str(uuid.uuid4())
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text(sample_markdown_with_invalid, encoding="utf-8")

        state: DocumentState = {
            "session_id": session_id,
            "temp_md_path": str(temp_output),
        }

        # Mock subprocess.run to return lint error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = '[{"lineNumber": 1, "ruleNames": ["MD047"], "ruleDescription": "Single trailing newline", "errorDetail": "File should end with a single newline character"}]'

        with patch("subprocess.run", return_value=mock_result):
            result = validate_md_node(state)

        # Verify
        assert result["validation_passed"] is False
        assert len(result["validation_issues"]) > 0

    def test_checkpoint_node_requires_temp_file(self, temp_session_dir: Path) -> None:
        """GIVEN temp_output.md does not exist WHEN checkpoint_node runs THEN last_checkpoint_id is empty."""
        session_id = str(uuid.uuid4())
        state: DocumentState = {
            "session_id": session_id,
            "current_chapter": 1,
            "temp_md_path": str(temp_session_dir / "nonexistent.md"),
        }

        result = checkpoint_node(state)

        assert result["last_checkpoint_id"] == ""

    def test_checkpoint_generates_unique_id(
        self, temp_session_dir: Path, sample_markdown_content: str
    ) -> None:
        """GIVEN valid markdown WHEN checkpoint_node runs THEN generates unique checkpoint_id."""
        session_id = str(uuid.uuid4())
        temp_output = temp_session_dir / "temp_output.md"
        temp_output.write_text(sample_markdown_content, encoding="utf-8")

        state: DocumentState = {
            "session_id": session_id,
            "current_chapter": 1,
            "temp_md_path": str(temp_output),
        }

        result = checkpoint_node(state)

        # Verify checkpoint_id format: timestamp_chapter_N.md
        assert result["last_checkpoint_id"] != ""
        assert "_chapter_1.md" in result["last_checkpoint_id"]
