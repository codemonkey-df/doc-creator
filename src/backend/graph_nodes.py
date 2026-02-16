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
    """Handle errors and decide retry vs complete (Story 4.4).

    Called when an error occurs during agent execution. Checks for last_error
    and decides whether to retry (restore from checkpoint) or complete (fail gracefully).

    The actual routing decision is made by route_after_error in routing.py.

    Args:
        state: DocumentState with last_error, error_type set

    Returns:
        State unchanged (routing decision made by route_after_error)
    """
    session_id = state.get("session_id", "")
    last_error = state.get("last_error", "")
    error_type = state.get("error_type", "")

    if last_error:
        logger.info(
            "error_handler_triggered",
            extra={
                "session_id": session_id,
                "error_type": error_type,
                "error": last_error[:200] if last_error else "",
            },
        )

    return state


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
