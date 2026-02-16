"""Document workflow state and initial state builder (Story 1.4, 2.1).

DocumentState is the TypedDict used by the LangGraph workflow. After entry,
input_files holds filenames in session inputs/ (not full paths). build_initial_state
produces the initial slice with all required keys and defaults so no key is
missing when scan_assets runs.

Required at entry (set by build_initial_state): session_id, input_files,
current_file_index, current_chapter, conversion_attempts, retry_count,
last_checkpoint_id, document_outline, missing_references, user_decisions,
pending_question, status, messages, plus defaults for all optional keys below.

Optional / set by graph nodes: temp_md_path, structure_json_path, output_docx_path,
last_error, error_type, validation_passed, validation_issues, generation_complete.

Reducer semantics: messages and missing_references use Annotated[list, operator.add]
so nodes can append without overwriting (LangGraph merges updates with reducer).
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage


class ImageRefResult(TypedDict):
    """Result of scanning a single image reference from markdown.

    Attributes:
        original_path: Path as it appeared in markdown (before resolution).
        resolved_path: Absolute resolved path if file exists, or resolved attempt if missing.
        source_file: Input filename where the reference was found.
    """

    original_path: str
    resolved_path: str
    source_file: str


class MissingRefDetail(TypedDict):
    """Detail of a missing image reference for placeholder insertion (Story 3.4).

    Used to track which input file contains each missing reference, so that
    insert_placeholder() can target the correct file when user chooses "skip".

    Attributes:
        original_path: Path as it appeared in markdown.
        source_file: Input filename where the reference was found.
    """

    original_path: str
    source_file: str


class ValidationIssue(TypedDict, total=False):
    """A single markdown validation issue from markdownlint."""

    line_number: int
    rule: str
    rule_description: str
    message: str
    error_detail: str


class DocumentState(TypedDict, total=False):
    """State passed through the document generation workflow.

    All keys are set by build_initial_state with defaults so the graph never
    sees a missing key. messages and missing_references are append-only (reducer).
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
    found_image_refs: list[ImageRefResult]
    missing_references: Annotated[list[str], operator.add]
    missing_ref_details: list[MissingRefDetail]
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
    messages: Annotated[list[BaseMessage], operator.add]
    validation_passed: bool
    validation_issues: list[ValidationIssue]
    generation_complete: bool


def build_initial_state(session_id: str, input_files: list[str]) -> DocumentState:
    """Build the initial DocumentState for workflow invocation.

    Entry calls this after copying validated files into session inputs/.
    All keys the graph expects are set (no key missing when scan_assets runs).
    Defaults: current_file_index=0, current_chapter=0, conversion_attempts=0,
    retry_count=0, last_checkpoint_id="", document_outline=[], found_image_refs=[],
    missing_references=[], missing_ref_details=[], user_decisions={}, pending_question="",
    status="scanning_assets", messages=[], temp_md_path="", structure_json_path="",
    output_docx_path="", last_error="", error_type="", validation_passed=False,
    validation_issues=[], generation_complete=False.

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
        "temp_md_path": "",
        "structure_json_path": "",
        "output_docx_path": "",
        "last_checkpoint_id": "",
        "document_outline": [],
        "conversion_attempts": 0,
        "last_error": "",
        "error_type": "",
        "retry_count": 0,
        "found_image_refs": [],
        "missing_references": [],
        "missing_ref_details": [],
        "user_decisions": {},
        "pending_question": "",
        "status": "scanning_assets",
        "messages": [],
        "validation_passed": False,
        "validation_issues": [],
        "generation_complete": False,
    }
