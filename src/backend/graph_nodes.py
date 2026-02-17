"""Graph nodes for Story 2.5: validate_md, parse_to_json, tools_node, checkpoint_node.

AC2.5.3: validate_md node runs markdown validation (markdownlint) and sets
validation_passed and validation_issues. Routes back to agent for fixes.

AC2.5.4: parse_to_json stub reads temp_output.md, writes minimal structure.json,
sets structure_json_path for downstream conversion epic.

Story 4.1: checkpoint_node runs after validation passes, copies temp_output.md
to checkpoints/{timestamp}_chapter_{n}.md with timestamp uniqueness.

Custom tools_node updates state from tool results: sets last_checkpoint_id from
create_checkpoint tool and pending_question from request_human_input tool.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from backend.state import DocumentState, ValidationIssue
from backend.tools import get_tools
from backend.utils.session_manager import SessionManager
from backend.utils.checkpoint import restore_from_checkpoint
from backend.utils.md_to_json_parser import parse_md_to_structure
from backend.utils.quality_validator import QualityValidator


def normalize_markdownlint_issue(raw_issue: dict[str, Any]) -> ValidationIssue:
    """Normalize markdownlint JSON to ValidationIssue."""
    line_number = raw_issue.get("lineNumber", 0)
    rule_names = raw_issue.get("ruleNames", [])
    rule = rule_names[0] if rule_names else ""
    rule_description = raw_issue.get("ruleDescription", "")
    error_detail = raw_issue.get("errorDetail", "")

    return ValidationIssue(
        line_number=line_number,
        rule=rule,
        rule_description=rule_description,
        message=f"{rule_description} (line {line_number})",
        error_detail=error_detail,
    )


def validate_md_node(state: DocumentState) -> DocumentState:
    """Run markdown validation on temp_output.md (AC2.5.3).

    Runs markdownlint on session temp_output.md, parses JSON issues,
    sets state[validation_passed] and state[validation_issues].

    Returns state with updated validation fields. On error, logs warning
    and returns state with validation_passed=False.

    Args:
        state: DocumentState with session_id and optionally temp_md_path.

    Returns:
        Updated DocumentState with validation_passed and validation_issues.
    """
    session_id = state.get("session_id", "")
    sm = SessionManager()
    session_path = sm.get_path(session_id)

    # Use provided temp_md_path or default
    temp_md_path = state.get("temp_md_path") or str(session_path / "temp_output.md")
    temp_md_file = Path(temp_md_path)

    if not temp_md_file.exists():
        logger.warning("temp_output.md not found at %s", temp_md_path)
        return cast(
            DocumentState,
            {
                **state,
                "validation_passed": False,
                "validation_issues": [
                    ValidationIssue(
                        line_number=0,
                        rule="markdownlint",
                        rule_description="File not found",
                        message=f"temp_output.md not found at {temp_md_path}",
                        error_detail=f"temp_output.md not found at {temp_md_path}",
                    )
                ],
            },
        )

    try:
        # Run markdownlint on the file
        result = subprocess.run(
            ["markdownlint", str(temp_md_file), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            # No errors
            logger.info(
                "validation_ran",
                extra={
                    "session_id": session_id,
                    "passed": True,
                    "issue_count": 0,
                },
            )
            return cast(
                DocumentState,
                {
                    **state,
                    "validation_passed": True,
                    "validation_issues": [],
                },
            )

        # Parse JSON output for issues
        try:
            issues = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse markdownlint JSON output: %s", result.stdout
            )
            logger.info(
                "validation_ran",
                extra={
                    "session_id": session_id,
                    "passed": False,
                    "issue_count": 1,
                },
            )
            return cast(
                DocumentState,
                {
                    **state,
                    "validation_passed": False,
                    "validation_issues": [
                        ValidationIssue(
                            line_number=0,
                            rule="markdownlint",
                            rule_description="JSON parse error",
                            message="Failed to parse markdownlint output",
                            error_detail=result.stdout[:500] if result.stdout else "",
                        )
                    ],
                },
            )

        # Normalize issue format using the normalizer function
        normalized_issues: list[ValidationIssue] = []
        for issue in issues:
            if isinstance(issue, dict):
                normalized_issues.append(normalize_markdownlint_issue(issue))

        logger.info(
            "validation_ran",
            extra={
                "session_id": session_id,
                "passed": False,
                "issue_count": len(normalized_issues),
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "validation_passed": False,
                "validation_issues": normalized_issues,
            },
        )

    except FileNotFoundError:
        logger.error("markdownlint CLI not found for session %s", session_id)
        logger.info(
            "validation_ran",
            extra={
                "session_id": session_id,
                "passed": False,
                "issue_count": 1,
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "validation_passed": False,
                "validation_issues": [
                    ValidationIssue(
                        line_number=0,
                        rule="markdownlint",
                        rule_description="CLI not found",
                        message="markdownlint CLI not installed",
                        error_detail="Please install markdownlint: npm install -g markdownlint-cli",
                    )
                ],
            },
        )
    except subprocess.TimeoutExpired:
        logger.error("Markdown validation timeout for session %s", session_id)
        logger.info(
            "validation_ran",
            extra={
                "session_id": session_id,
                "passed": False,
                "issue_count": 1,
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "validation_passed": False,
                "validation_issues": [
                    ValidationIssue(
                        line_number=0,
                        rule="markdownlint",
                        rule_description="Validation timeout",
                        message="Validation timeout after 30 seconds",
                        error_detail="The markdown file took too long to validate",
                    )
                ],
            },
        )
    except subprocess.SubprocessError as e:
        logger.error(
            "Markdown validation subprocess error for session %s: %s",
            session_id,
            e,
        )
        logger.info(
            "validation_ran",
            extra={
                "session_id": session_id,
                "passed": False,
                "issue_count": 1,
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "validation_passed": False,
                "validation_issues": [
                    ValidationIssue(
                        line_number=0,
                        rule="markdownlint",
                        rule_description="Validation error",
                        message=f"Validation error: {str(e)}",
                        error_detail=str(e),
                    )
                ],
            },
        )
    except Exception as e:
        logger.exception(
            "Unexpected error validating markdown for session %s",
            session_id,
        )
        logger.info(
            "validation_ran",
            extra={
                "session_id": session_id,
                "passed": False,
                "issue_count": 1,
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "validation_passed": False,
                "validation_issues": [
                    ValidationIssue(
                        line_number=0,
                        rule="markdownlint",
                        rule_description="Unexpected error",
                        message=f"Unexpected error: {str(e)}",
                        error_detail=str(e),
                    )
                ],
            },
        )


logger = logging.getLogger(__name__)


def parse_to_json_node(state: DocumentState) -> DocumentState:
    """Convert temp_output.md to structure.json (AC5.2).

    Uses parse_md_to_structure to parse markdown with support for:
    - Headings (H1-H3)
    - Paragraphs
    - Fenced code blocks
    - Tables
    - Images

    Sets state[structure_json_path] on success.
    On failure: sets conversion_success=False, last_error, does NOT write structure.json.

    Args:
        state: DocumentState with session_id and optionally temp_md_path.

    Returns:
        Updated DocumentState with structure_json_path set (on success),
        or conversion_success=False and last_error (on failure).
    """
    session_id = state.get("session_id", "")
    sm = SessionManager()
    session_path = sm.get_path(session_id)

    # Use provided temp_md_path or default
    temp_md_path = state.get("temp_md_path") or str(session_path / "temp_output.md")
    temp_md_file = Path(temp_md_path)

    structure_json_path = session_path / "structure.json"

    # Handle missing file gracefully - create empty structure with defaults
    if not temp_md_file.exists():
        logger.warning(
            "temp_output.md not found at %s, creating empty structure", temp_md_path
        )
        structure = {
            "metadata": {
                "title": "Generated Document",
                "author": "AI Agent",
                "created": _get_iso_timestamp(),
            },
            "sections": [],
        }
        try:
            structure_json_path.write_text(
                json.dumps(structure, indent=2),
                encoding="utf-8",
            )
            logger.info(
                "parse_completed",
                extra={
                    "session_id": session_id,
                    "section_count": 0,
                },
            )
        except Exception as e:
            logger.error("Failed to write structure.json: %s", e)

        return cast(
            DocumentState,
            {
                **state,
                "structure_json_path": str(structure_json_path),
            },
        )

    # Parse markdown using the new parser
    try:
        structure = parse_md_to_structure(temp_md_file, session_path)

        # Write structure.json
        structure_json_path.write_text(
            json.dumps(structure, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "parse_completed",
            extra={
                "session_id": session_id,
                "section_count": len(structure["sections"]),
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "structure_json_path": str(structure_json_path),
            },
        )

    except UnicodeDecodeError as e:
        logger.error("Failed to read %s: %s", temp_md_path, e)
        return cast(
            DocumentState,
            {
                **state,
                "conversion_success": False,
                "last_error": f"Parse error: Unicode decode error - {str(e)}",
            },
        )
    except ValueError as e:
        # Path traversal or other validation error
        logger.error("Parse validation error for %s: %s", temp_md_path, e)
        return cast(
            DocumentState,
            {
                **state,
                "conversion_success": False,
                "last_error": f"Parse error: {str(e)}",
            },
        )
    except Exception as e:
        logger.exception("Unexpected error parsing markdown for session %s", session_id)
        return cast(
            DocumentState,
            {
                **state,
                "conversion_success": False,
                "last_error": f"Parse error: {str(e)}",
            },
        )


def _get_iso_timestamp() -> str:
    """Return current timestamp in ISO format."""
    from datetime import datetime

    return datetime.now().isoformat()


def tools_node(state: DocumentState) -> DocumentState:
    """Execute tools and update state from results (AC2.5.1, AC2.5.2).

    Workflow:
    1. Extract session_id and messages from state
    2. Invoke LangGraph ToolNode with tools from get_tools(session_id)
    3. Execute all tool calls from agent's last AIMessage
    4. Parse returned ToolMessages to extract special tool results:
       - create_checkpoint: set state["last_checkpoint_id"] = content
       - request_human_input: set state["pending_question"] = content
    5. Return merged state with updated messages and extracted fields

    AC2.5.1: Completes agent → tools → routing loop
    AC2.5.2: Updates state fields used by route_after_tools for routing decisions

    Args:
        state: DocumentState with agent-generated messages containing tool_calls.

    Returns:
        Updated DocumentState with:
        - messages: appended with ToolMessages (via reducer operator.add)
        - last_checkpoint_id: set if create_checkpoint was called
        - pending_question: set if request_human_input was called
    """
    from langgraph.prebuilt import ToolNode
    from langchain_core.messages import ToolMessage

    session_id = state.get("session_id", "")
    messages = state.get("messages", [])

    # Get tools for this session
    tools = get_tools(session_id)

    # Create and invoke ToolNode
    tool_node = ToolNode(tools)
    try:
        tool_result = tool_node.invoke({"messages": messages})
    except Exception as e:
        logger.error("ToolNode invocation failed: %s", e)
        # Return state unchanged on error (graceful fallback)
        return cast(
            DocumentState,
            {
                **state,
                "last_error": f"Tool execution error: {str(e)}",
                "error_type": "tool_execution",
            },
        )

    # Extract tool results from ToolMessages
    extracted_checkpoint_id = state.get("last_checkpoint_id", "")
    extracted_pending_question = state.get("pending_question", "")

    new_messages = tool_result.get("messages", [])
    for msg in new_messages:
        if isinstance(msg, ToolMessage):
            # Extract checkpoint_id from create_checkpoint result
            if msg.name == "create_checkpoint" and msg.content:
                extracted_checkpoint_id = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )

            # Extract pending_question from request_human_input result
            elif msg.name == "request_human_input" and msg.content:
                # Don't overwrite if agent already set it
                if not extracted_pending_question:
                    extracted_pending_question = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )

    # Merge and return updated state
    return cast(
        DocumentState,
        {
            **state,
            "messages": new_messages,  # Reducer will append via operator.add
            "last_checkpoint_id": extracted_checkpoint_id,
            "pending_question": extracted_pending_question,
        },
    )


def _generate_checkpoint_filename(label: str, checkpoints_dir: Path) -> str:
    """Generate unique checkpoint filename with timestamp + sequence.

    If the base filename already exists, appends _0, _1, etc. until unique.

    Args:
        label: Sanitized label (e.g., "chapter_1")
        checkpoints_dir: Path to checkpoints directory

    Returns:
        Unique filename: {timestamp}_{label}.md or {timestamp}_{label}_{n}.md
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = f"{timestamp}_{label}.md"

    if not (checkpoints_dir / basename).exists():
        return basename

    # Sequence suffix if exists
    seq = 0
    while (checkpoints_dir / f"{timestamp}_{label}_{seq}.md").exists():
        seq += 1
    return f"{timestamp}_{label}_{seq}.md"


def checkpoint_node(state: DocumentState) -> DocumentState:
    """Create checkpoint after validation passes (Story 4.1).

    Copies temp_output.md to checkpoints/{timestamp}_chapter_{n}.md.
    Updates state['last_checkpoint_id'] with the checkpoint basename.
    Uses timestamp uniqueness: appends _0, _1, etc. if file exists.

    Args:
        state: DocumentState with session_id, current_chapter, temp_md_path

    Returns:
        Updated state with last_checkpoint_id set
    """
    session_id = state.get("session_id", "")
    current_chapter = state.get("current_chapter", 0)

    sm = SessionManager()
    session_path = sm.get_path(session_id)

    # Get temp_output.md path
    temp_md_path = state.get("temp_md_path") or str(session_path / "temp_output.md")
    temp_md_file = Path(temp_md_path)

    if not temp_md_file.exists():
        logger.warning("checkpoint_node: temp_output.md not found at %s", temp_md_path)
        return cast(
            DocumentState,
            {
                **state,
                "last_checkpoint_id": "",
                "last_error": f"temp_output.md not found at {temp_md_path}",
                "error_type": "checkpoint_failed",
            },
        )

    # Create checkpoints directory if missing
    checkpoints_dir = session_path / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    # Generate label from state (chapter_{n})
    label = f"chapter_{current_chapter}"

    # Generate unique filename with timestamp + sequence
    checkpoint_filename = _generate_checkpoint_filename(label, checkpoints_dir)
    dest_path = checkpoints_dir / checkpoint_filename

    try:
        shutil.copy2(temp_md_file, dest_path)
        logger.info(
            "checkpoint_saved",
            extra={
                "session_id": session_id,
                "checkpoint_id": checkpoint_filename,
                "chapter": current_chapter,
            },
        )
    except Exception as e:
        logger.error(
            "Failed to create checkpoint for session %s: %s",
            session_id,
            e,
            exc_info=True,
        )
        return cast(
            DocumentState,
            {
                **state,
                "last_checkpoint_id": "",
                "last_error": f"Checkpoint failed: {str(e)}",
                "error_type": "checkpoint_failed",
            },
        )

    return cast(
        DocumentState,
        {
            **state,
            "last_checkpoint_id": checkpoint_filename,
        },
    )


def error_handler_node(state: DocumentState) -> DocumentState:
    """Handle errors with classification, rollback, handler invocation, and retry logic (Story 6.3).

    Flow:
    1. Get session info (session_id, last_error, last_checkpoint_id, retry_count)
    2. Classify error using ErrorClassifier
    3. Log state transition to error_handling
    4. Log error_classified event
    5. Rollback if checkpoint available (restore_from_checkpoint)
    6. Invoke handler based on error_type (syntax/encoding/asset/structural)
    7. Log handler result
    8. Increment retry_count
    9. Log retry_count and routing decision (retry vs fail)

    Note: The actual routing to retry or fail is done by should_retry_conversion in routing.py.

    Args:
        state: DocumentState with last_error, last_checkpoint_id, retry_count

    Returns:
        Updated state with error_type, retry_count incremented, handler_outcome set
    """
    from backend.error_handlers import (
        ErrorType,
        classify,
        fix_heading_hierarchy,
        fix_invalid_utf8,
        fix_unclosed_code_block,
        insert_placeholder,
    )
    from backend.utils.checkpoint import restore_from_checkpoint

    # Step 1: Get session info
    session_id = state.get("session_id", "")
    last_error = state.get("last_error", "")
    last_checkpoint_id = state.get("last_checkpoint_id", "")
    current_retry_count = state.get("retry_count", 0)

    # Step 2: Classify error
    error_type, metadata = classify(last_error)

    # Step 3: Log state transition to error_handling
    logger.info(
        "state_transition",
        extra={
            "session_id": session_id,
            "from_status": state.get("status", ""),
            "to_status": "error_handling",
        },
    )

    # Step 4: Log error_classified
    logger.info(
        "error_classified",
        extra={
            "session_id": session_id,
            "error_type": error_type.value,
            "line_number": metadata.get("line_number"),
            "asset_ref": metadata.get("asset_ref"),
        },
    )

    # Step 5: Rollback if checkpoint available
    rollback_success = False
    if last_checkpoint_id and last_checkpoint_id.strip():
        rollback_success = restore_from_checkpoint(session_id, last_checkpoint_id)
        if rollback_success:
            logger.info(
                "rollback_performed",
                extra={
                    "session_id": session_id,
                    "checkpoint_id": last_checkpoint_id,
                },
            )
        else:
            logger.info(
                "rollback_skipped",
                extra={
                    "session_id": session_id,
                    "checkpoint_id": last_checkpoint_id,
                    "reason": "restore_failed",
                },
            )

    # Step 6: Invoke handler based on error_type
    handler_outcome = ""
    if error_type == ErrorType.SYNTAX:
        handler_outcome = fix_unclosed_code_block(
            session_id, metadata.get("line_number")
        )
    elif error_type == ErrorType.ENCODING:
        handler_outcome = fix_invalid_utf8(session_id)
    elif error_type == ErrorType.ASSET:
        handler_outcome = insert_placeholder(session_id, metadata.get("asset_ref"))
    elif error_type == ErrorType.STRUCTURAL:
        handler_outcome = fix_heading_hierarchy(session_id)
    else:
        # Unknown error - no handler applied
        handler_outcome = "Unknown error - no fix applied"
        logger.info(
            "error_fix_skipped",
            extra={
                "session_id": session_id,
                "reason": "unknown_error_type",
            },
        )

    # Step 7: Log handler result
    logger.info(
        "error_fix_attempted",
        extra={
            "session_id": session_id,
            "error_type": error_type.value,
            "handler_outcome": handler_outcome[:200] if handler_outcome else "",
        },
    )

    # Step 8: Increment retry_count
    new_retry_count = current_retry_count + 1

    # Step 9: Log retry_count and routing decision
    route = "retry" if new_retry_count < 3 else "fail"
    logger.info(
        "error_handler_complete",
        extra={
            "session_id": session_id,
            "retry_count": new_retry_count,
            "route": route,
        },
    )

    # Step 10: Return updated state
    return cast(
        DocumentState,
        {
            **state,
            "error_type": error_type.value,
            "retry_count": new_retry_count,
            "handler_outcome": handler_outcome,
            "status": "error_handling",
        },
    )


def rollback_node(state: DocumentState) -> DocumentState:
    """Restore temp_output.md from last_checkpoint_id before retry (Story 4.4).

    Checks state['last_checkpoint_id'] and attempts to restore temp_output.md
    from the checkpoint file. Logs rollback_performed on success or
    rollback_skipped if no checkpoint or file missing.

    Args:
        state: DocumentState with session_id and last_checkpoint_id

    Returns:
        Updated state (last_checkpoint_id cleared after restore to prevent
        duplicate rollback on subsequent retries)
    """
    session_id = state.get("session_id", "")
    checkpoint_id = state.get("last_checkpoint_id", "")

    # No checkpoint ID - skip rollback
    if not checkpoint_id or not checkpoint_id.strip():
        logger.info(
            "rollback_skipped",
            extra={
                "session_id": session_id,
                "reason": "no_checkpoint_id",
            },
        )
        return cast(DocumentState, {**state})

    # Attempt restore using shared helper
    success = restore_from_checkpoint(session_id, checkpoint_id)

    if success:
        logger.info(
            "rollback_performed",
            extra={
                "session_id": session_id,
                "checkpoint_id": checkpoint_id,
            },
        )
        # Clear last_checkpoint_id after restore to prevent duplicate rollback
        return cast(DocumentState, {**state, "last_checkpoint_id": ""})
    else:
        # Checkpoint file missing - skip rollback, log warning
        logger.warning(
            "rollback_skipped",
            extra={
                "session_id": session_id,
                "checkpoint_id": checkpoint_id,
                "reason": "checkpoint_file_missing",
            },
        )
        return cast(DocumentState, {**state})


def convert_with_docxjs_node(state: DocumentState) -> DocumentState:
    """Convert structure.json to output.docx using Node.js converter.js (Story 5.4).

    Executes the converter.js script with structure.json as input and writes
    output.docx. Uses 120s timeout by default (configurable via CONVERSION_TIMEOUT_SECONDS).

    Short-circuits on missing inputs (structure.json, Node.js, converter.js).
    Increments conversion_attempts on every run.

    Args:
        state: DocumentState with session_id, optionally structure_json_path

    Returns:
        Updated DocumentState with:
        - conversion_success: True if conversion completed, False otherwise
        - output_docx_path: Set on success
        - last_error: Set on failure
        - status: "quality_checking" on success, "error_handling" on failure
        - conversion_attempts: Incremented
    """
    import os
    import shutil

    session_id = state.get("session_id", "")
    sm = SessionManager()
    session_path = sm.get_path(session_id)

    # Get structure.json path from state or derive
    structure_json_path = state.get("structure_json_path") or str(
        session_path / "structure.json"
    )
    structure_json_file = Path(structure_json_path)

    # Prepare output path
    output_docx_path = state.get("output_docx_path") or str(
        session_path / "output.docx"
    )

    # Increment conversion_attempts
    current_attempts = state.get("conversion_attempts", 0)

    # Step 1: Short-circuit if structure.json missing
    if not structure_json_file.exists():
        logger.warning(
            "conversion_failed_no_json",
            extra={
                "session_id": session_id,
                "attempt": current_attempts + 1,
                "reason": "No structure.json",
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "conversion_success": False,
                "last_error": "No structure.json",
                "status": "error_handling",
                "conversion_attempts": current_attempts + 1,
            },
        )

    # Step 2: Resolve Node executable
    node_exe = os.environ.get("NODE_PATH") or shutil.which("node")
    if not node_exe:
        logger.warning(
            "conversion_failed_no_node",
            extra={
                "session_id": session_id,
                "attempt": current_attempts + 1,
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "conversion_success": False,
                "last_error": "Node.js not found",
                "status": "error_handling",
                "conversion_attempts": current_attempts + 1,
            },
        )

    # Step 3: Resolve converter.js path
    converter_js_path = os.environ.get("CONVERTER_JS_PATH")
    if converter_js_path:
        converter_script = Path(converter_js_path)
        if not converter_script.is_absolute():
            # Resolve relative to project root (assuming project root is parent of src/backend)
            project_root = Path(__file__).parent.parent.parent
            converter_script = project_root / converter_js_path
    else:
        # Default: ./src/node/converter.js relative to project root
        project_root = Path(__file__).parent.parent.parent
        converter_script = project_root / "src" / "node" / "converter.js"

    if not converter_script.exists():
        logger.warning(
            "conversion_failed_no_converter",
            extra={
                "session_id": session_id,
                "attempt": current_attempts + 1,
                "converter_path": str(converter_script),
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "conversion_success": False,
                "last_error": "converter.js not found",
                "status": "error_handling",
                "conversion_attempts": current_attempts + 1,
            },
        )

    # Get timeout from env or default to 120s
    timeout_seconds = int(os.environ.get("CONVERSION_TIMEOUT_SECONDS", "120"))

    logger.info(
        "conversion_started",
        extra={
            "session_id": session_id,
            "attempt": current_attempts + 1,
            "json_path": str(structure_json_file),
            "docx_path": output_docx_path,
            "timeout": timeout_seconds,
        },
    )

    # Step 4: Execute Node script
    try:
        result = subprocess.run(
            [
                node_exe,
                str(converter_script),
                str(structure_json_file),
                output_docx_path,
            ],
            cwd=str(session_path),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        logger.error(
            "conversion_timeout",
            extra={
                "session_id": session_id,
                "timeout": timeout_seconds,
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "conversion_success": False,
                "last_error": f"Conversion timeout ({timeout_seconds}s exceeded)",
                "status": "error_handling",
                "conversion_attempts": current_attempts + 1,
            },
        )

    # Step 5: Handle results
    if result.returncode == 0:
        logger.info(
            "conversion_success",
            extra={
                "session_id": session_id,
                "output_docx_path": output_docx_path,
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "conversion_success": True,
                "output_docx_path": output_docx_path,
                "status": "quality_checking",
                "conversion_attempts": current_attempts + 1,
            },
        )
    else:
        # Non-zero exit: use stderr, fallback to stdout
        error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        logger.warning(
            "conversion_failed",
            extra={
                "session_id": session_id,
                "error": error_msg[:200],
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "conversion_success": False,
                "last_error": error_msg,
                "status": "error_handling",
                "conversion_attempts": current_attempts + 1,
            },
        )


def quality_check_node(state: DocumentState) -> DocumentState:
    """Validate generated DOCX quality (Story 5.5).

    Loads the generated DOCX file and validates against FC011 criteria:
    - Heading hierarchy (no skipped levels)
    - Image rendering (no broken images)
    - Code block formatting (monospace fonts)
    - Table structure (consistent column counts)

    Args:
        state: DocumentState with session_id and output_docx_path

    Returns:
        Updated state with quality_passed, quality_issues, and status:
        - "complete" if quality passes
        - "error_handling" if quality fails
    """
    session_id = state.get("session_id", "")
    output_docx_path = state.get("output_docx_path", "")

    # Handle missing DOCX path
    if not output_docx_path:
        logger.warning(
            "quality_check_skipped",
            extra={
                "session_id": session_id,
                "reason": "No DOCX output to validate",
            },
        )
        return cast(
            DocumentState,
            {
                **state,
                "quality_passed": False,
                "quality_issues": ["No DOCX output to validate"],
                "last_error": "No DOCX output to validate",
                "status": "error_handling",
            },
        )

    # Validate the DOCX
    validator = QualityValidator()
    result = validator.validate(Path(output_docx_path))

    quality_passed = result.get("passed", False)
    quality_issues = result.get("issues", [])

    # Log quality check results
    logger.info(
        "quality_check_completed",
        extra={
            "session_id": session_id,
            "passed": quality_passed,
            "issue_count": len(quality_issues),
            "issues": quality_issues,
            "score": result.get("score", 0),
        },
    )

    # Set status based on result
    if quality_passed:
        return cast(
            DocumentState,
            {
                **state,
                "quality_passed": True,
                "quality_issues": quality_issues,
                "status": "complete",
            },
        )
    else:
        # Summarize issues for last_error
        issue_summary = "; ".join(quality_issues[:3])
        if len(quality_issues) > 3:
            issue_summary += f" (+{len(quality_issues) - 3} more)"
        return cast(
            DocumentState,
            {
                **state,
                "quality_passed": False,
                "quality_issues": quality_issues,
                "last_error": f"Quality check failed: {issue_summary}",
                "status": "error_handling",
            },
        )


def save_results_node(state: DocumentState) -> DocumentState:
    """Handle final results: success path (archive session) or failure path (write error files).

    Story 6.4 DoD - Handles both success and failure paths:

    Failure branch: (retry_count >= MAX_RETRY_ATTEMPTS) or (status == "failed")
      - Write FAILED_conversion.md with error summary
      - Write ERROR_REPORT.txt with full error details
      - Set status="failed"

    Success branch: conversion succeeded and passed quality check
      - Archive session (cleanup temp files, mark complete)
      - Set status="complete"

    Always routes to END.

    Args:
        state: DocumentState with conversion_success, retry_count, status, etc.

    Returns:
        Updated state with status="complete" or status="failed"
    """
    from datetime import datetime
    from backend.routing import MAX_RETRY_ATTEMPTS
    from backend.utils.session_manager import SessionManager

    session_id = state.get("session_id", "")
    sm = SessionManager()
    session_path = sm.get_path(session_id)

    retry_count = state.get("retry_count", 0)
    current_status = state.get("status", "")
    last_error = state.get("last_error", "")

    # Determine failure: max retries exceeded OR explicitly failed status
    is_failure = (retry_count >= MAX_RETRY_ATTEMPTS) or (current_status == "failed")

    if is_failure:
        # Failure path: write error files
        error_msg = last_error or "Unknown error"

        # Write FAILED_conversion.md
        failed_md_path = session_path / "FAILED_conversion.md"
        failed_content = f"""# Conversion Failed

**Session ID**: {session_id}
**Timestamp**: {datetime.now().isoformat()}
**Retry Count**: {retry_count}/{MAX_RETRY_ATTEMPTS}

## Error Summary

{error_msg[:500]}

## Details

- Status: {current_status}
- Error Type: {state.get("error_type", "unknown")}
- Handler Outcome: {str(state.get("handler_outcome", "N/A"))[:200]}
"""
        try:
            failed_md_path.write_text(failed_content, encoding="utf-8")
            logger.info(
                "failure_report_written",
                extra={
                    "session_id": session_id,
                    "path": str(failed_md_path),
                },
            )
        except Exception as e:
            logger.error(
                "Failed to write FAILED_conversion.md: %s",
                e,
                exc_info=True,
            )

        # Write ERROR_REPORT.txt
        error_report_path = session_path / "ERROR_REPORT.txt"
        error_report_content = f"""Error Report
===========
Session ID: {session_id}
Timestamp: {datetime.now().isoformat()}
Retry Count: {retry_count}/{MAX_RETRY_ATTEMPTS}

Status: {current_status}
Error Type: {state.get("error_type", "unknown")}

Error Message:
--------------
{error_msg}

Handler Outcome:
----------------
{state.get("handler_outcome", "N/A")}

State Summary:
--------------
conversion_success: {state.get("conversion_success", False)}
quality_passed: {state.get("quality_passed", False)}
validation_passed: {state.get("validation_passed", False)}
generation_complete: {state.get("generation_complete", False)}
"""
        try:
            error_report_path.write_text(error_report_content, encoding="utf-8")
            logger.info(
                "error_report_written",
                extra={
                    "session_id": session_id,
                    "path": str(error_report_path),
                },
            )
        except Exception as e:
            logger.error(
                "Failed to write ERROR_REPORT.txt: %s",
                e,
                exc_info=True,
            )

        logger.info(
            "save_results_failure",
            extra={
                "session_id": session_id,
                "retry_count": retry_count,
                "max_retries": MAX_RETRY_ATTEMPTS,
            },
        )

        return cast(
            DocumentState,
            {
                **state,
                "status": "failed",
            },
        )
    else:
        # Success path: archive session (mark complete)
        logger.info(
            "save_results_success",
            extra={
                "session_id": session_id,
            },
        )

        return cast(
            DocumentState,
            {
                **state,
                "status": "complete",
            },
        )
