"""Minimal LangGraph workflow for Story 1.4, 2.1: START → scan_assets → human_input | agent → END.

Session is not created in the graph; entry provides state with session_id and
input_files. scan_assets reads from state only (session_id, input_files) and
uses SessionManager.get_path for session root; no SessionManager.create in graph.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.state import DocumentState
from backend.utils.session_manager import SessionManager

logger = logging.getLogger(__name__)

# Markdown image syntax: ![alt](path)
IMAGE_REF_PATTERN = re.compile(r"!\[.*?\]\((.*?)\)")


def _scan_assets_impl(
    state: DocumentState, session_manager: SessionManager
) -> DocumentState:
    """Read input files, detect image refs (regex), set missing_references and pending_question or status=processing.

    Uses only state["session_id"] and state["input_files"]; does not create session.
    """
    session_id = state["session_id"]
    input_files = state["input_files"]
    session_path = session_manager.get_path(session_id)
    inputs_dir = session_path / "inputs"

    missing_refs: list[str] = []

    for filename in input_files:
        file_path = inputs_dir / filename
        if not file_path.exists():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Skipping file %s: %s", file_path, e)
            continue
        for match in IMAGE_REF_PATTERN.finditer(content):
            ref = match.group(1).strip()
            if ref.startswith("http"):
                continue
            # Resolve in order: inputs dir, session root, then absolute path
            candidate = (inputs_dir / ref).resolve()
            if not candidate.exists():
                candidate = (session_path / ref).resolve()
            if not candidate.exists():
                try:
                    candidate = Path(ref).resolve()
                except (OSError, ValueError):
                    pass
            if not candidate.exists():
                missing_refs.append(ref)

    if missing_refs:
        return {
            **state,
            "missing_references": missing_refs,
            "pending_question": f"Missing images: {', '.join(missing_refs)}. Upload or skip?",
            "status": "scanning_assets",
        }
    return {
        **state,
        "status": "processing",
    }


def _human_input_node(state: DocumentState) -> DocumentState:
    """Stub: return state unchanged. After resume, entry injects user_decisions."""
    return state


def _agent_node(state: DocumentState) -> DocumentState:
    """Stub: return state with status 'complete' so minimal workflow signals success to entry.

    Agent loop will be implemented in later stories; for 2.1 we only route here when
    no missing refs, then end the graph so entry can cleanup and report success.
    """
    return {**state, "status": "complete"}


def create_document_workflow(
    session_manager: SessionManager | None = None,
) -> Any:
    """Build and compile the document workflow. Graph starts at scan_assets.

    Entry injects session_manager so scan_assets can resolve session path.
    """
    sm = session_manager if session_manager is not None else SessionManager()

    def scan_assets_node(state: DocumentState) -> DocumentState:
        return _scan_assets_impl(state, sm)

    workflow = StateGraph(DocumentState)
    workflow.add_node("scan_assets", scan_assets_node)
    workflow.add_node("human_input", _human_input_node)
    workflow.add_node("agent", _agent_node)

    workflow.add_edge(START, "scan_assets")
    workflow.add_conditional_edges(
        "scan_assets",
        lambda s: "human_input" if s.get("missing_references") else "agent",
        {"human_input": "human_input", "agent": "agent"},
    )
    workflow.add_edge("human_input", END)
    workflow.add_edge("agent", END)

    return workflow.compile()
