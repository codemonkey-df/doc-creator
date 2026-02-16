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

logger = logging.getLogger(__name__)


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


def parse_to_json_node(state: DocumentState) -> DocumentState:
    """Convert temp_output.md to structure.json stub (AC2.5.4).

    Reads markdown file, parses basic structure (headings, paragraphs, code blocks),
    writes minimal JSON structure for docx-js converter.

    Sets state[structure_json_path] pointing to created structure.json file
    in session root. This enables the conversion epic (Epic 4) to consume the
    structured format.

    Args:
        state: DocumentState with session_id and optionally temp_md_path.

    Returns:
        Updated DocumentState with structure_json_path set.
    """
    session_id = state.get("session_id", "")
    sm = SessionManager()
    session_path = sm.get_path(session_id)

    # Use provided temp_md_path or default
    temp_md_path = state.get("temp_md_path") or str(session_path / "temp_output.md")
    temp_md_file = Path(temp_md_path)

    structure_json_path = session_path / "structure.json"

    # Read markdown (handle missing file gracefully)
    if not temp_md_file.exists():
        logger.warning(
            "temp_output.md not found at %s, creating empty structure", temp_md_path
        )
        md_content = ""
    else:
        try:
            md_content = temp_md_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("Failed to read %s: %s", temp_md_path, e)
            md_content = ""

    # Parse markdown into sections
    sections = _parse_markdown_to_sections(md_content)

    # Build structure JSON (minimal stub for conversion epic)
    structure = {
        "metadata": {
            "title": "Generated Document",
            "author": "AI Agent",
            "created": _get_iso_timestamp(),
        },
        "sections": sections,
    }

    # Write structure.json
    try:
        structure_json_path.write_text(
            json.dumps(structure, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "Created structure.json for session %s with %d sections",
            session_id,
            len(sections),
        )
    except Exception as e:
        logger.error(
            "Failed to write structure.json for session %s: %s",
            session_id,
            e,
        )
        # Still return state with path, conversion epic can handle missing file

    return cast(
        DocumentState,
        {
            **state,
            "structure_json_path": str(structure_json_path),
        },
    )


def _parse_markdown_to_sections(content: str) -> list[dict[str, Any]]:
    """Parse markdown content into sections (headings, paragraphs, code blocks).

    Simple regex-based parsing to extract:
    - Headings (# → ###) → heading1/heading2/heading3
    - Code blocks (```language ... ```) → code_block
    - Paragraphs → paragraph

    Returns list of section dicts compatible with structure.json schema.
    """
    sections: list[dict[str, Any]] = []

    if not content.strip():
        return sections

    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Parse heading
        if line.startswith("#"):
            level = len(line.split()[0])  # Count # chars
            if 1 <= level <= 3:
                text = line[level:].strip()
                sections.append(
                    {
                        "type": f"heading{level}",
                        "text": text,
                    }
                )
            i += 1
            continue

        # Parse code block
        if line.strip().startswith("```"):
            language = line[3:].strip() or "text"
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # Skip closing ```

            code_content = "\n".join(code_lines).rstrip()
            if code_content:  # Only add if non-empty
                sections.append(
                    {
                        "type": "code_block",
                        "language": language,
                        "code": code_content,
                    }
                )
            continue

        # Skip empty lines
        if not line.strip():
            i += 1
            continue

        # Parse paragraph
        para_lines = []
        while i < len(lines) and lines[i].strip():
            if lines[i].startswith("#") or lines[i].strip().startswith("```"):
                break
            para_lines.append(lines[i])
            i += 1

        para_text = " ".join([line.strip() for line in para_lines]).strip()
        if para_text:
            sections.append(
                {
                    "type": "paragraph",
                    "text": para_text,
                }
            )

    return sections


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
