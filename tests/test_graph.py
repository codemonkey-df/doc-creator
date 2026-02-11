"""Integration tests for document workflow graph (Story 2.1). GIVEN-WHEN-THEN."""

from __future__ import annotations

import pytest
from pathlib import Path

from backend.state import build_initial_state
from backend.utils.session_manager import SessionManager
from backend.utils.settings import SessionSettings


# --- Fixtures ---


@pytest.fixture
def temp_base(tmp_path: Path) -> Path:
    """GIVEN a temporary base directory for sessions."""
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


# --- Task 8: Graph receives state and first node runs ---


def test_graph_invoke_scan_assets_runs_and_uses_session_id_input_files(
    session_manager: SessionManager,
) -> None:
    """GIVEN build_initial_state(session_id, ['a.txt']) and session with that file under inputs / WHEN invoke graph with session_manager / THEN scan_assets runs; result has session_id and input_files; flow goes to agent (status ends 'complete' from agent stub)."""
    from backend.graph import create_document_workflow

    session_id = session_manager.create()
    session_path = session_manager.get_path(session_id)
    (session_path / "inputs").mkdir(parents=True, exist_ok=True)
    (session_path / "inputs" / "a.txt").write_text(
        "Plain text, no images.", encoding="utf-8"
    )

    initial = build_initial_state(session_id, ["a.txt"])
    workflow = create_document_workflow(session_manager=session_manager)
    result = workflow.invoke(initial)

    assert result["session_id"] == session_id
    assert result["input_files"] == ["a.txt"]
    # No missing refs → agent path → agent stub sets status complete for entry
    assert result["status"] == "complete"


# --- Task 12: scan_assets routes to human_input vs agent ---


def test_scan_assets_no_missing_refs_routes_to_agent_status_processing(
    session_manager: SessionManager,
) -> None:
    """GIVEN session with input file that has no image refs / WHEN invoke graph / THEN flow goes to agent: no pending_question, no missing_references, status 'complete' (agent stub)."""
    from backend.graph import create_document_workflow

    session_id = session_manager.create()
    session_path = session_manager.get_path(session_id)
    (session_path / "inputs").mkdir(parents=True, exist_ok=True)
    (session_path / "inputs" / "doc.md").write_text(
        "# Doc\n\nNo images here.", encoding="utf-8"
    )

    initial = build_initial_state(session_id, ["doc.md"])
    workflow = create_document_workflow(session_manager=session_manager)
    result = workflow.invoke(initial)

    assert not result.get("pending_question", "").strip()
    assert result.get("missing_references", []) == []
    assert result["status"] == "complete"


def test_scan_assets_with_missing_refs_routes_to_human_input(
    session_manager: SessionManager,
) -> None:
    """GIVEN session with input file containing image ref ![](missing.png) (file missing) / WHEN invoke graph / THEN missing_references non-empty, pending_question set (human_input path)."""
    from backend.graph import create_document_workflow

    session_id = session_manager.create()
    session_path = session_manager.get_path(session_id)
    (session_path / "inputs").mkdir(parents=True, exist_ok=True)
    (session_path / "inputs" / "with_img.md").write_text(
        "Text and ![alt](missing.png) reference.",
        encoding="utf-8",
    )

    initial = build_initial_state(session_id, ["with_img.md"])
    workflow = create_document_workflow(session_manager=session_manager)
    result = workflow.invoke(initial)

    assert len(result.get("missing_references", [])) > 0
    assert result.get("pending_question", "").strip() != ""
