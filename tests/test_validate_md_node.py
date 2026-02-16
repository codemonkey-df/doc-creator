"""Unit tests for validate_md_node and normalize_markdownlint_issue (Story 4.2). GIVEN-WHEN-THEN."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.graph_nodes import normalize_markdownlint_issue, validate_md_node
from backend.utils.session_manager import SessionManager
from backend.state import DocumentState


# --- Fixtures ---


@pytest.fixture
def temp_session_dir() -> Path:
    """GIVEN temporary session directory with required subdirs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_path = Path(tmpdir) / "sessions" / "test-session"
        session_path.mkdir(parents=True)
        for subdir in ["inputs", "assets", "checkpoints", "logs"]:
            (session_path / subdir).mkdir(exist_ok=True)
        yield session_path


@pytest.fixture
def mock_session_manager(temp_session_dir: Path) -> SessionManager:
    """GIVEN mocked SessionManager that uses temp directory."""
    sm = MagicMock(spec=SessionManager)
    sm.get_path.return_value = temp_session_dir
    return sm


# --- normalize_markdownlint_issue tests ---


def test_normalize_markdownlint_issue() -> None:
    """GIVEN: raw markdownlint JSON issue
    WHEN: normalize_markdownlint_issue is called
    THEN: returns ValidationIssue with snake_case keys
    """
    raw_issue = {
        "lineNumber": 10,
        "ruleNames": ["MD001", "heading-increment"],
        "ruleDescription": "Heading levels should only increment by one level at a time",
        "errorDetail": "This level 2 heading jumps from level 1",
    }

    result = normalize_markdownlint_issue(raw_issue)

    assert isinstance(result, dict)
    assert result["line_number"] == 10
    assert result["rule"] == "MD001"
    assert (
        result["rule_description"]
        == "Heading levels should only increment by one level at a time"
    )
    assert (
        result["message"]
        == "Heading levels should only increment by one level at a time (line 10)"
    )
    assert result["error_detail"] == "This level 2 heading jumps from level 1"


def test_normalize_markdownlint_issue_missing_fields() -> None:
    """GIVEN: raw issue with missing optional fields
    WHEN: normalize_markdownlint_issue is called
    THEN: returns ValidationIssue with default values
    """
    raw_issue = {
        "lineNumber": 5,
    }

    result = normalize_markdownlint_issue(raw_issue)

    assert result["line_number"] == 5
    assert result["rule"] == ""
    assert result["rule_description"] == ""
    assert result["message"] == " (line 5)"
    assert result["error_detail"] == ""


# --- validate_md_node tests ---


def test_validate_md_node_with_valid_markdown(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: valid markdown file with no lint errors
    WHEN: validate_md_node runs
    THEN: validation_passed=True, issues=[], structured log emitted
    """
    # Create valid markdown
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Valid Document\n\nSome content here.\n", encoding="utf-8")

    state: DocumentState = {
        "session_id": "test-session",
    }

    # Mock subprocess to return success (returncode=0)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = validate_md_node(state)

    assert result["validation_passed"] is True
    assert result["validation_issues"] == []
    mock_run.assert_called_once()


def test_validate_md_node_with_invalid_markdown_returns_normalized_issues(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: markdown file with lint errors
    WHEN: validate_md_node runs
    THEN: returns normalized issues with snake_case keys
    """
    # Create markdown with heading issue
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Title\n\n## Subtitle\n\n# Jump to H1\n", encoding="utf-8")

    # Mock markdownlint returning JSON errors
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = json.dumps(
        [
            {
                "lineNumber": 4,
                "ruleNames": ["MD001", "heading-increment"],
                "ruleDescription": "Heading levels should only increment by one level at a time",
                "errorDetail": "This level 1 heading jumps from level 2",
            }
        ]
    )
    mock_result.stderr = ""

    state: DocumentState = {
        "session_id": "test-session",
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        with patch("subprocess.run", return_value=mock_result):
            result = validate_md_node(state)

    assert result["validation_passed"] is False
    issues = result["validation_issues"]
    assert len(issues) == 1

    # Verify snake_case keys
    issue = issues[0]
    assert "line_number" in issue
    assert "rule" in issue
    assert "rule_description" in issue
    assert "message" in issue
    assert "error_detail" in issue

    assert issue["line_number"] == 4
    assert issue["rule"] == "MD001"
    assert "Heading levels should only increment" in issue["rule_description"]


def test_validate_md_node_missing_markdownlint_cli(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: markdownlint CLI not installed
    WHEN: validate_md_node runs
    THEN: returns synthetic issue with rule="markdownlint"
    """
    # Create any markdown file
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Test\n", encoding="utf-8")

    state: DocumentState = {
        "session_id": "test-session",
    }

    # Mock FileNotFoundError for missing CLI
    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        with patch(
            "subprocess.run", side_effect=FileNotFoundError("markdownlint not found")
        ):
            result = validate_md_node(state)

    assert result["validation_passed"] is False
    issues = result["validation_issues"]
    assert len(issues) == 1
    assert issues[0]["rule"] == "markdownlint"
    assert (
        "not installed" in issues[0]["message"].lower()
        or "not found" in issues[0]["message"].lower()
    )


def test_validate_md_node_timeout(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: markdownlint takes longer than 30 seconds
    WHEN: validate_md_node runs
    THEN: returns synthetic issue with "Validation timeout"
    """
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Test\n", encoding="utf-8")

    state: DocumentState = {
        "session_id": "test-session",
    }

    import subprocess

    # Mock TimeoutExpired
    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            result = validate_md_node(state)

    assert result["validation_passed"] is False
    issues = result["validation_issues"]
    assert len(issues) == 1
    assert "timeout" in issues[0]["rule_description"].lower()


def test_validate_md_node_json_parse_failure(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: markdownlint returns invalid JSON
    WHEN: validate_md_node runs
    THEN: returns synthetic issue for JSON parse error
    """
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Test\n", encoding="utf-8")

    # Mock subprocess returning non-JSON output
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "This is not JSON output"
    mock_result.stderr = ""

    state: DocumentState = {
        "session_id": "test-session",
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        with patch("subprocess.run", return_value=mock_result):
            result = validate_md_node(state)

    assert result["validation_passed"] is False
    issues = result["validation_issues"]
    assert len(issues) == 1
    assert (
        "json" in issues[0]["rule_description"].lower()
        or "parse" in issues[0]["rule_description"].lower()
    )


def test_validate_md_node_missing_temp_file(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: temp_output.md does not exist
    WHEN: validate_md_node runs
    THEN: returns validation_passed=False, preserves existing state
    """
    state: DocumentState = {
        "session_id": "test-session",
        "input_files": ["doc1.md"],
        "current_file_index": 0,
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        result = validate_md_node(state)

    assert result["validation_passed"] is False
    issues = result["validation_issues"]
    assert len(issues) == 1
    # Verify state is preserved
    assert result["input_files"] == ["doc1.md"]
    assert result["current_file_index"] == 0


def test_validate_md_node_preserves_other_state(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: state with various fields populated
    WHEN: validate_md_node runs
    THEN: other state fields are preserved
    """
    # Create valid markdown
    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Valid\n", encoding="utf-8")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    state: DocumentState = {
        "session_id": "test-session",
        "input_files": ["a.md", "b.md"],
        "current_file_index": 1,
        "current_chapter": 2,
        "messages": [],
        "user_decisions": {"key": "value"},
    }

    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        with patch("subprocess.run", return_value=mock_result):
            result = validate_md_node(state)

    # Verify all original fields preserved
    assert result["input_files"] == ["a.md", "b.md"]
    assert result["current_file_index"] == 1
    assert result["current_chapter"] == 2
    assert result["user_decisions"] == {"key": "value"}
    # validation fields updated
    assert result["validation_passed"] is True
    assert result["validation_issues"] == []


def test_validate_md_node_structured_logging(
    temp_session_dir: Path, mock_session_manager: SessionManager
) -> None:
    """GIVEN: valid markdown file
    WHEN: validate_md_node runs
    THEN: emits validation_ran log event with passed/issue_count
    """

    temp_md = temp_session_dir / "temp_output.md"
    temp_md.write_text("# Valid\n", encoding="utf-8")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    state: DocumentState = {
        "session_id": "test-session",
    }

    # Capture log events
    with patch("backend.graph_nodes.SessionManager", return_value=mock_session_manager):
        with patch("subprocess.run", return_value=mock_result):
            with patch("backend.graph_nodes.logger") as mock_logger:
                validate_md_node(state)

                # Verify structured logging was called
                mock_logger.info.assert_called()
                call_args = mock_logger.info.call_args
                # First positional arg should be "validation_ran"
                assert call_args[0][0] == "validation_ran"
                # Extra dict should have passed and issue_count
                extra = call_args[1].get("extra", {})
                assert extra.get("passed") is True
                assert extra.get("issue_count") == 0
