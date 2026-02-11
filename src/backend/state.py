"""Document workflow state and initial state builder (Story 1.4).

DocumentState is the TypedDict used by the LangGraph workflow. After entry,
input_files holds filenames in session inputs/ (not full paths). build_initial_state
produces the initial slice with all required keys and defaults.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict


class DocumentState(TypedDict, total=False):
    """State passed through the document generation workflow.

    Required keys for initial state (set by build_initial_state):
    session_id, input_files, current_file_index, current_chapter,
    conversion_attempts, retry_count, last_checkpoint_id, document_outline,
    missing_references, user_decisions, pending_question, status, messages.

    Optional keys (set by graph nodes): temp_md_path, structure_json_path,
    output_docx_path, last_error, error_type.
    """

    session_id: str
    input_files: list[str]
    current_file_index: int
    current_chapter: int
    temp_md_path: str
    structure_json_path: str
    output_docx_path: str
    last_checkpoint_id: str
    document_outline: list[str]
    conversion_attempts: int
    last_error: str
    error_type: str
    retry_count: int
    missing_references: Annotated[list[str], operator.add]
    user_decisions: dict[str, str]
    pending_question: str
    status: Literal[
        "initializing",
        "scanning_assets",
        "processing",
        "validating",
        "converting",
        "quality_checking",
        "error_handling",
        "complete",
        "failed",
    ]
    messages: Annotated[list[str], operator.add]


def build_initial_state(session_id: str, input_files: list[str]) -> DocumentState:
    """Build the initial DocumentState for workflow invocation.

    Entry calls this after copying validated files into session inputs/.
    Required keys and defaults:
    - session_id, input_files: as passed
    - current_file_index: 0
    - current_chapter: 0
    - conversion_attempts: 0
    - retry_count: 0
    - last_checkpoint_id: ""
    - document_outline: []
    - missing_references: []
    - user_decisions: {}
    - pending_question: ""
    - status: "scanning_assets" (graph starts at scan_assets node)
    - messages: []

    Args:
        session_id: UUID from SessionManager.create().
        input_files: Filenames in session inputs/ (path.name of copied files).

    Returns:
        DocumentState ready for workflow.invoke().
    """
    return {
        "session_id": session_id,
        "input_files": input_files,
        "current_file_index": 0,
        "current_chapter": 0,
        "conversion_attempts": 0,
        "retry_count": 0,
        "last_checkpoint_id": "",
        "document_outline": [],
        "missing_references": [],
        "user_decisions": {},
        "pending_question": "",
        "status": "scanning_assets",
        "messages": [],
    }
