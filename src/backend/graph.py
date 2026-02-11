"""Minimal LangGraph workflow for Story 1.4: START → scan_assets → END.

Session is not created in the graph; entry provides state with session_id and
input_files. Cleanup is entry-owned, not in the graph.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.state import DocumentState


def scan_assets_node(state: DocumentState) -> DocumentState:
    """Stub: receive pre-filled state, return state with status 'complete'.

    Does not create session or call SessionManager. Entry has already
    created the session and copied files; this node only updates state
    for the minimal workflow (e.g. set status to complete for tests).
    """
    return {
        **state,
        "status": "complete",
    }


def create_document_workflow() -> Any:
    """Build and compile the document workflow. Graph starts at scan_assets."""
    workflow = StateGraph(DocumentState)
    workflow.add_node("scan_assets", scan_assets_node)
    workflow.add_edge(START, "scan_assets")
    workflow.add_edge("scan_assets", END)
    return workflow.compile()
