"""Workflow entry: validate, create session, copy inputs, invoke graph, cleanup (Story 1.4).

Entry owns session lifecycle. Flow: validate_requested_files → if no valid return
GenerateResult(success=False) → SessionManager.create() → copy to session inputs/
→ build_initial_state → workflow.invoke → SessionManager.cleanup → return GenerateResult.
Cleanup runs only in entry after invoke. Duplicate destination filenames: last copy wins.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Protocol, TypedDict

from backend.state import DocumentState, build_initial_state
from backend.utils.file_discovery import (
    FileValidationError,
    validate_requested_files,
)
from backend.utils.sanitizer import InputSanitizer
from backend.utils.session_manager import SessionManager

logger = logging.getLogger(__name__)


class GenerateResult(TypedDict, total=False):
    """Return type of generate_document.

    success: True if workflow completed with status 'complete'.
    session_id: Set when a session was created.
    output_path: Set on success (path to output docx).
    error: Set on workflow or entry failure.
    validation_errors: Set when validation failed (no valid files).
    messages: List of status messages from workflow or entry.
    """

    success: bool
    session_id: str
    output_path: str
    error: str
    validation_errors: list[FileValidationError]
    messages: list[str]


def copy_validated_files_to_session(
    valid_paths: list[Path],
    session_id: str,
    session_manager: SessionManager,
) -> list[str]:
    """Copy validated files into session inputs/ directory.

    Each file is copied to session_manager.get_path(session_id) / "inputs" / path.name.
    No path traversal in destination: only path.name is used (AC1.4.1).
    Duplicate destination filenames: last copy wins (overwrites).

    Args:
        valid_paths: Resolved, validated Paths to copy.
        session_id: UUID from SessionManager.create().
        session_manager: SessionManager instance.

    Returns:
        List of filenames (path.name) in copy order.
    """
    if not valid_paths:
        return []
    inputs_dir = session_manager.get_path(session_id) / "inputs"
    names: list[str] = []
    for p in valid_paths:
        dest = inputs_dir / p.name
        shutil.copy(p, dest)
        names.append(p.name)
    logger.info(
        "Files copied to session inputs: session_id=%s count=%s", session_id, len(names)
    )
    return names


class _WorkflowProtocol(Protocol):
    """Protocol for workflow invocation. Used for dependency injection in generate_document."""

    def invoke(self, initial_state: DocumentState) -> DocumentState: ...


def generate_document(
    requested_paths: list[str],
    base_dir: Path,
    *,
    session_manager: SessionManager | None = None,
    sanitizer: InputSanitizer | None = None,
    workflow: _WorkflowProtocol | None = None,
) -> GenerateResult:
    """Entry point: validate, create session, copy, invoke workflow, cleanup.

    Path validation (and thus path traversal prevention) is done by
    validate_requested_files(..., sanitizer) before any session create or copy.

    If no valid files, returns GenerateResult(success=False, validation_errors=...)
    and does not create a session. Otherwise creates session, copies files,
    invokes workflow with initial state, then calls SessionManager.cleanup
    (archive=success). Cleanup is the only place that deletes/archives the session.

    Args:
        requested_paths: User-requested file paths (strings).
        base_dir: Allowed input root (resolved).
        session_manager: Optional; default from env.
        sanitizer: Optional; default from env.
        workflow: Optional; default create_document_workflow().

    Returns:
        GenerateResult with success, session_id, output_path, error,
        validation_errors, messages as appropriate.
    """
    base_resolved = base_dir.resolve()
    sm = session_manager if session_manager is not None else SessionManager()
    san = sanitizer if sanitizer is not None else InputSanitizer()
    wf = workflow
    if wf is None:
        from backend.graph import create_document_workflow

        wf = create_document_workflow(session_manager=sm)

    valid_paths, errors = validate_requested_files(
        requested_paths, base_resolved, sanitizer=san
    )

    if not valid_paths:
        for e in errors:
            logger.warning(
                "Validation failed: path=%s code=%s message=%s",
                e.path,
                e.code,
                e.message,
            )
        return {
            "success": False,
            "validation_errors": errors,
            "messages": [f"No valid files: {len(errors)} error(s)"],
        }

    session_id = sm.create()
    try:
        input_filenames = copy_validated_files_to_session(valid_paths, session_id, sm)
        initial_state = build_initial_state(session_id, input_filenames)
        result = wf.invoke(initial_state)
        status = result.get("status", "")
        archive = status == "complete"
        sm.cleanup(session_id, archive=archive)
        return {
            "success": status == "complete",
            "session_id": session_id,
            "output_path": result.get("output_docx_path", "") or "",
            "error": result.get("last_error", "") or "",
            "messages": result.get("messages", []) or [],
        }
    except Exception as e:
        logger.exception("Workflow failed: session_id=%s", session_id)
        try:
            sm.cleanup(session_id, archive=False)
        except Exception:
            logger.exception("Cleanup after failure failed: session_id=%s", session_id)
        return {
            "success": False,
            "session_id": session_id,
            "error": str(e),
            "messages": [f"Fatal error: {e}"],
        }
