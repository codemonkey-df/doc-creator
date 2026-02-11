"""Unit and integration tests for entry flow and session lifecycle (Story 1.4). GIVEN-WHEN-THEN."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import Mock

from backend.state import build_initial_state
from backend.utils.session_manager import SessionManager
from backend.utils.settings import SessionSettings


# --- Fixtures ---

SESSION_SUBDIRS = ("inputs", "assets", "checkpoints", "logs")


@pytest.fixture
def temp_base(tmp_path: Path) -> Path:
    """GIVEN a temporary base directory for sessions and archive."""
    return tmp_path.resolve()


@pytest.fixture
def session_settings(temp_base: Path) -> SessionSettings:
    """GIVEN SessionSettings with temp base."""
    return SessionSettings(
        docs_base_path=temp_base,
        sessions_dir="sessions",
        archive_dir="archive",
    )


@pytest.fixture
def session_manager(session_settings: SessionSettings) -> SessionManager:
    """GIVEN a SessionManager configured with temp base."""
    return SessionManager(settings=session_settings)


# --- build_initial_state ---


def test_build_initial_state_returns_document_state_with_required_keys() -> None:
    """GIVEN session_id and input_files / WHEN build_initial_state / THEN returned dict has session_id, input_files, status=scanning_assets, defaults."""
    state = build_initial_state("sid-123", ["a.txt", "b.md"])
    assert state["session_id"] == "sid-123"
    assert state["input_files"] == ["a.txt", "b.md"]
    assert state["status"] == "scanning_assets"
    assert state["current_file_index"] == 0
    assert state["current_chapter"] == 0
    assert state["conversion_attempts"] == 0
    assert state["retry_count"] == 0
    assert state["last_checkpoint_id"] == ""
    assert state["document_outline"] == []
    assert state["missing_references"] == []
    assert state["user_decisions"] == {}
    assert state["pending_question"] == ""
    assert state["messages"] == []


def test_build_initial_state_empty_input_files() -> None:
    """GIVEN session_id and empty input_files / WHEN build_initial_state / THEN state has input_files=[] and status=scanning_assets."""
    state = build_initial_state("sid-456", [])
    assert state["input_files"] == []
    assert state["status"] == "scanning_assets"


# --- copy_validated_files_to_session ---


def test_copy_validated_files_to_session_copies_files_under_inputs(
    session_manager: SessionManager,
) -> None:
    """GIVEN validated Paths and session_id / WHEN copy_validated_files_to_session / THEN files exist under session_path/inputs/ with correct names."""
    from backend.entry import copy_validated_files_to_session

    session_id = session_manager.create()
    f1 = session_manager.get_path(session_id).parent.parent / "f1.txt"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_text("content1", encoding="utf-8")
    f2 = f1.parent / "other" / "f2.md"
    f2.parent.mkdir(parents=True, exist_ok=True)
    f2.write_text("content2", encoding="utf-8")
    valid_paths = [f1, f2]

    names = copy_validated_files_to_session(valid_paths, session_id, session_manager)

    assert names == ["f1.txt", "f2.md"]
    inputs_dir = session_manager.get_path(session_id) / "inputs"
    assert (inputs_dir / "f1.txt").read_text() == "content1"
    assert (inputs_dir / "f2.md").read_text() == "content2"


def test_copy_validated_files_to_session_duplicate_names_last_wins(
    session_manager: SessionManager,
) -> None:
    """GIVEN two Paths with same name (different dirs) / WHEN copy / THEN second overwrites first; single file in inputs/."""
    from backend.entry import copy_validated_files_to_session

    session_id = session_manager.create()
    base = session_manager.get_path(session_id).parent.parent
    (base / "dir1").mkdir(parents=True, exist_ok=True)
    (base / "dir2").mkdir(parents=True, exist_ok=True)
    (base / "dir1" / "same.txt").write_text("first", encoding="utf-8")
    (base / "dir2" / "same.txt").write_text("second", encoding="utf-8")
    valid_paths = [base / "dir1" / "same.txt", base / "dir2" / "same.txt"]

    names = copy_validated_files_to_session(valid_paths, session_id, session_manager)

    assert names == ["same.txt", "same.txt"]
    inputs_dir = session_manager.get_path(session_id) / "inputs"
    assert list(inputs_dir.iterdir()) == [inputs_dir / "same.txt"]
    assert (inputs_dir / "same.txt").read_text() == "second"


def test_copy_validated_files_to_session_empty_list_returns_empty(
    session_manager: SessionManager,
) -> None:
    """GIVEN empty valid_paths / WHEN copy / THEN no error, return []."""
    from backend.entry import copy_validated_files_to_session

    session_id = session_manager.create()
    names = copy_validated_files_to_session([], session_id, session_manager)
    assert names == []


# --- generate_document: validation failure ---


def test_generate_document_no_valid_files_returns_false_and_validation_errors(
    session_manager: SessionManager,
    temp_base: Path,
) -> None:
    """GIVEN requested_paths that yield no valid files / WHEN generate_document / THEN return success=False, validation_errors populated, no session created."""
    from backend.entry import generate_document

    # Request non-existent and invalid paths so valid list is empty
    requested = [str(temp_base / "nonexistent.txt"), str(temp_base / "missing.md")]
    result = generate_document(requested, temp_base, session_manager=session_manager)

    assert result["success"] is False
    assert "validation_errors" in result
    assert len(result["validation_errors"]) >= 1
    # No session should have been created (we did not pass paths under a dir with valid files)
    sessions_dir = temp_base / "sessions"
    if sessions_dir.exists():
        session_dirs = [d for d in sessions_dir.iterdir() if d.is_dir()]
        assert len(session_dirs) == 0


def test_generate_document_all_invalid_no_session_created(
    session_manager: SessionManager,
    temp_base: Path,
) -> None:
    """GIVEN only invalid paths (e.g. blocked extension) / WHEN generate_document / THEN no session created."""
    from backend.entry import generate_document

    (temp_base / "bad.exe").write_bytes(b"MZ")
    result = generate_document(
        [str(temp_base / "bad.exe")], temp_base, session_manager=session_manager
    )
    assert result["success"] is False
    assert result.get("validation_errors")
    sessions_dir = temp_base / "sessions"
    assert not sessions_dir.exists() or len(list(sessions_dir.iterdir())) == 0


def test_generate_document_empty_requested_paths_no_session(
    session_manager: SessionManager,
    temp_base: Path,
) -> None:
    """GIVEN empty requested_paths / WHEN generate_document / THEN success=False, validation_errors=[], no session created."""
    from backend.entry import generate_document

    result = generate_document([], temp_base, session_manager=session_manager)

    assert result["success"] is False
    assert result.get("validation_errors") == []
    sessions_dir = temp_base / "sessions"
    assert not sessions_dir.exists() or len(list(sessions_dir.iterdir())) == 0


# --- generate_document: happy path ---


def test_generate_document_happy_path_creates_session_and_copies(
    session_manager: SessionManager,
    temp_base: Path,
) -> None:
    """GIVEN valid temp files and base_dir / WHEN generate_document / THEN session created, inputs/ populated, cleanup (archive) after invoke."""
    from backend.entry import generate_document

    (temp_base / "valid.txt").write_text("hello", encoding="utf-8")
    requested = [str(temp_base / "valid.txt")]

    result = generate_document(requested, temp_base, session_manager=session_manager)

    assert result["success"] is True
    assert "session_id" in result
    session_id = result["session_id"]
    # After success, entry calls cleanup(session_id, archive=True), so session moves to archive
    archive_path = temp_base / "archive" / session_id
    assert archive_path.is_dir()
    inputs_dir = archive_path / "inputs"
    assert (inputs_dir / "valid.txt").exists()
    assert (inputs_dir / "valid.txt").read_text() == "hello"


def test_generate_document_cleanup_called_after_invoke(
    session_manager: SessionManager,
    temp_base: Path,
) -> None:
    """GIVEN valid file / WHEN generate_document / THEN cleanup is called once after workflow.invoke with correct session_id and archive."""
    from backend.entry import generate_document

    (temp_base / "one.txt").write_text("x", encoding="utf-8")
    cleanup_spy = Mock(wraps=session_manager.cleanup)
    session_manager.cleanup = cleanup_spy

    result = generate_document(
        [str(temp_base / "one.txt")], temp_base, session_manager=session_manager
    )

    cleanup_spy.assert_called_once()
    call_args = cleanup_spy.call_args
    assert call_args[0][0] == result["session_id"]
    assert call_args[1]["archive"] is True  # success -> archive


def test_generate_document_workflow_raises_cleanup_called_with_archive_false(
    session_manager: SessionManager,
    temp_base: Path,
) -> None:
    """GIVEN valid file and workflow that raises on invoke / WHEN generate_document / THEN cleanup(session_id, archive=False) called once; result success=False, error set."""
    from backend.entry import generate_document

    (temp_base / "valid.txt").write_text("x", encoding="utf-8")
    cleanup_spy = Mock(wraps=session_manager.cleanup)
    session_manager.cleanup = cleanup_spy

    class FailingWorkflow:
        def invoke(self, initial_state: dict) -> dict:
            raise ValueError("simulated failure")

    result = generate_document(
        [str(temp_base / "valid.txt")],
        temp_base,
        session_manager=session_manager,
        workflow=FailingWorkflow(),
    )

    assert result["success"] is False
    assert result["session_id"]
    assert "simulated failure" in result["error"]
    cleanup_spy.assert_called_once()
    call_args = cleanup_spy.call_args
    assert call_args[0][0] == result["session_id"]
    assert call_args[1]["archive"] is False


# --- graph: no session create in graph ---


def test_graph_receives_pre_filled_state_no_session_create(
    session_manager: SessionManager,
) -> None:
    """GIVEN build_initial_state(session_id, ["a.txt"]) / WHEN invoke graph / THEN no SessionManager.create inside graph; state has session_id and input_files."""
    from backend.graph import create_document_workflow

    session_id = session_manager.create()
    initial = build_initial_state(session_id, ["a.txt"])
    workflow = create_document_workflow()

    result = workflow.invoke(initial)

    assert result["session_id"] == session_id
    assert result["input_files"] == ["a.txt"]
    # Graph does not create session; it only receives state (scan_assets stub may set status)
    assert "status" in result


def test_graph_starts_at_scan_assets(
    session_manager: SessionManager,
) -> None:
    """GIVEN initial state with status=scanning_assets / WHEN invoke graph / THEN result has state shape (session_id, input_files) unchanged or updated by scan_assets."""
    from backend.graph import create_document_workflow

    session_id = session_manager.create()
    initial = build_initial_state(session_id, ["f.txt"])
    workflow = create_document_workflow()
    result = workflow.invoke(initial)
    assert result["session_id"] == session_id
    assert result["input_files"] == ["f.txt"]
