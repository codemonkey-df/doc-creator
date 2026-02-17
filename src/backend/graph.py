"""LangGraph workflow for document generation (Stories 1.4, 2.1-2.5, 3.1-3.2).

Story 1.4, 2.1: START → scan_assets → agent → END
  Session not created in graph; entry provides session_id and input_files.
  scan_assets detects missing image refs and routes to human_input if needed.

Story 2.4: Add checkpointer, interrupt_before, and human_input node for HITL.
  Two interrupt points:
  1. scan_assets → human_input (missing refs detected)
  2. agent → human_input (pending_question set during generation)

Story 2.5: Wire agent ↔ tools loop with routing.
  agent → tools → route_after_tools → (agent | validate | human_input | complete)
  - validate_md: run markdownlint, return to agent if issues
  - parse_to_json: write structure.json stub for conversion epic
  - route_after_tools: priority (pending_question > checkpoint > complete > agent)

Story 3.1, 3.2: scan_assets extracts and classifies image refs, then copies found images
  to assets/ and rewrites refs in input files to use ./assets/basename paths (in-place).
  Missing refs trigger human_input for resolution (Story 3.4).
"""

from __future__ import annotations

import logging
from typing import Any, cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.agent import agent_node as agent_node_impl
from backend.graph_nodes import (
    checkpoint_node,
    convert_with_docxjs_node,
    error_handler_node,
    parse_to_json_node,
    quality_check_node,
    rollback_node,
    save_results_node,
    tools_node,
    validate_md_node,
)
from backend.routing import (
    route_after_tools,
    route_after_validation,
    should_retry_conversion,
)
from backend.state import DocumentState, ImageRefResult, MissingRefDetail
from backend.utils.asset_handler import apply_asset_scan_results
from backend.utils.image_scanner import extract_image_refs, resolve_image_path
from backend.utils.session_manager import SessionManager
from backend.utils.settings import AssetScanSettings

logger = logging.getLogger(__name__)


def _scan_assets_impl(
    state: DocumentState, session_manager: SessionManager
) -> DocumentState:
    """Scan input files for image references, resolve paths, and classify found/missing (Story 3.1).

    Then copy found images to session assets/ and rewrite refs in input files (Story 3.2).

    Story 3.1 - Implements AC3.1.1-3.1.6:
    1. Extract markdown image refs: ![alt](path)
    2. Classify each path: URL (skip), relative (resolve to input dir), absolute (validate under base)
    3. Check existence: found vs missing
    4. Track source_file for each ref (for Story 3.4 placeholder targeting)
    5. Populate state: found_image_refs, missing_references, pending_question, status
    6. Log per-file and per-ref events

    Story 3.2 - Implements AC3.2.1-3.2.6:
    - Copy found images to session/assets/ (destination = basename; last-copy-wins on collisions)
    - Rewrite refs in input files: ![alt](original_path) → ![alt](./assets/basename); in-place
    - Preserve UTF-8 encoding and line endings (CRLF/LF)
    - Log all copy and rewrite operations

    Args:
        state: DocumentState with session_id and input_files
        session_manager: SessionManager for path resolution

    Returns:
        Updated state with found_image_refs, missing_references, and routing decision
    """
    session_id = state["session_id"]
    input_files = state["input_files"]
    session_path = session_manager.get_path(session_id)
    inputs_dir = session_path / "inputs"

    # Load asset scan settings (allowed_base_path, etc.)
    settings = AssetScanSettings()
    allowed_base = (
        settings.allowed_base_path if settings.allowed_base_path else inputs_dir
    )

    found_refs: list[ImageRefResult] = []
    missing_refs: list[str] = []
    missing_ref_details: list[MissingRefDetail] = []  # For Story 3.4: track source_file

    # Scan each input file
    for filename in input_files:
        file_path = inputs_dir / filename
        if not file_path.exists():
            logger.warning("Input file not found: %s", file_path)
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Skipping file %s: %s", file_path, e)
            continue

        # Extract all image refs from this file
        refs = extract_image_refs(content)
        logger.info(
            "refs_scanned",
            extra={
                "session_id": session_id,
                "filename": filename,
                "ref_count": len(refs),
            },
        )

        # Classify each ref
        found_count = 0
        missing_count = 0
        for original_path in refs:
            # Resolve path (URL/relative/absolute)
            resolved = resolve_image_path(
                original_path,
                inputs_dir,
                allowed_base,
            )

            if resolved is None:
                # URL or missing
                missing_refs.append(original_path)
                missing_ref_details.append(
                    {"original_path": original_path, "source_file": filename}
                )
                missing_count += 1
                logger.info(
                    "image_ref_missing",
                    extra={
                        "session_id": session_id,
                        "filename": filename,
                        "original_path": original_path,
                    },
                )
            else:
                # Found
                found_refs.append(
                    {
                        "original_path": original_path,
                        "resolved_path": str(resolved),
                        "source_file": filename,
                    }
                )
                found_count += 1
                logger.info(
                    "image_ref_found",
                    extra={
                        "session_id": session_id,
                        "filename": filename,
                        "original_path": original_path,
                        "resolved_path": str(resolved),
                    },
                )

        logger.info(
            "file_scan_complete",
            extra={
                "session_id": session_id,
                "filename": filename,
                "found": found_count,
                "missing": missing_count,
            },
        )

    # Step 2: Copy found images to assets/ and rewrite refs in input files (Story 3.2)
    # AC3.2.1-3.2.6: Copy images, rewrite refs to ./assets/basename in input files (in-place)
    if found_refs:
        try:
            asset_results = apply_asset_scan_results(session_path, found_refs)
            logger.info(
                "asset_scan_results_applied",
                extra={
                    "session_id": session_id,
                    "copied": asset_results.get("copied", 0),
                    "rewritten": asset_results.get("rewritten", 0),
                },
            )
        except Exception as e:
            logger.error(
                "Failed to apply asset scan results: %s",
                e,
                exc_info=True,
            )
            # Continue anyway; refs might not have been copied but scan can continue

    # Update state
    new_state: DocumentState = {
        **state,
        "found_image_refs": found_refs,
        "missing_references": missing_refs,
        "missing_ref_details": missing_ref_details,
    }

    if missing_refs:
        # Route to human_input for missing ref resolution
        new_state["pending_question"] = (
            f"Found {len(missing_refs)} missing image(s): "
            f"{', '.join(missing_refs[:3])}{'...' if len(missing_refs) > 3 else ''}. "
            "Upload files or skip?"
        )
        new_state["status"] = "scanning_assets"
    else:
        # No missing refs; proceed to agent
        new_state["status"] = "processing"
        new_state["pending_question"] = ""

    logger.info(
        "scan_assets_complete",
        extra={
            "session_id": session_id,
            "found_count": len(found_refs),
            "missing_count": len(missing_refs),
            "has_missing": len(missing_refs) > 0,
        },
    )

    return new_state


def _human_input_node(state: DocumentState) -> DocumentState:
    """Stub: return state unchanged. After resume, entry injects user_decisions."""
    return state


def _apply_user_decisions_node(
    state: DocumentState, session_manager: SessionManager | None = None
) -> DocumentState:
    """Apply user decisions for missing image references (Story 3.4).

    After human-in-the-loop interruption, processes user_decisions:
    - "skip": Inserts canonical placeholder `**[Image Missing: {basename}]**` in input file
    - upload path: Copies uploaded file to session assets, updates markdown ref

    AC3.4.4-3.4.5: Skip → placeholder, Upload → copy+update, clear missing_references,
    set status="processing", route to agent.

    Args:
        state: DocumentState with user_decisions populated by entry (or caller)
        session_manager: Optional SessionManager for DI

    Returns:
        Updated state with decisions applied, missing_references cleared, pending_question cleared
    """
    sm = session_manager if session_manager is not None else SessionManager()

    session_id = state.get("session_id")
    if not session_id:
        logger.warning("No session_id in state for apply_user_decisions_node")
        return state

    session_path = sm.get_path(session_id)
    user_decisions = state.get("user_decisions", {})
    missing_ref_details = state.get("missing_ref_details", [])

    if not user_decisions:
        logger.debug("No user_decisions to apply, returning state unchanged")
        return state

    from backend.utils.asset_handler import handle_upload_decision, insert_placeholder

    # Build a map of original_path → source_file for quick lookup
    ref_details_map = {
        detail["original_path"]: detail["source_file"] for detail in missing_ref_details
    }

    # Process each decision
    for original_path, decision in user_decisions.items():
        # Find source_file for this ref
        source_file = ref_details_map.get(original_path)

        if decision == "skip":
            # Insert placeholder for skipped image
            try:
                if source_file:
                    target_file = f"inputs/{source_file}"
                else:
                    # Fallback: try all input files (less efficient but handles missing metadata)
                    logger.warning(
                        "No source_file found for %s, skipping placeholder insertion",
                        original_path,
                    )
                    continue

                insert_placeholder(session_path, original_path, target_file)
                logger.info(
                    "Placeholder inserted for %s in %s",
                    original_path,
                    target_file,
                )

            except Exception as e:
                logger.warning(
                    "Failed to insert placeholder for %s: %s",
                    original_path,
                    e,
                )
                continue

        else:
            # Upload decision: decision value is the upload path
            try:
                if not source_file:
                    logger.warning(
                        "No source_file found for uploaded ref %s",
                        original_path,
                    )
                    continue

                target_file = f"inputs/{source_file}"

                handle_upload_decision(
                    session_path,
                    decision,
                    original_path,
                    target_file,
                    allowed_base_path=None,
                )
                logger.info(
                    "Uploaded file processed for %s in %s",
                    original_path,
                    target_file,
                )

            except Exception as e:
                logger.warning(
                    "Failed to handle upload decision for %s: %s",
                    original_path,
                    e,
                )
                continue

    # Clear decision state and set status for agent re-entry
    new_state: DocumentState = cast(
        DocumentState,
        {
            **state,
            "missing_references": [],
            "missing_ref_details": [],
            "pending_question": "",
            "user_decisions": {},
            "status": "processing",
        },
    )

    logger.info(
        "User decisions applied: processed %d decisions, status set to processing",
        len(user_decisions),
    )

    return new_state


def _agent_node(state: DocumentState) -> DocumentState:
    """Single-step agent node (Story 2.3). One LLM invoke; returns state with messages, generation_complete, pending_question."""
    return agent_node_impl(state)


def create_document_workflow(
    session_manager: SessionManager | None = None,
) -> Any:
    """Build and compile the document workflow (Stories 1.4, 2.1, 2.4, 2.5).

    Graph structure:
      scan_assets → (agent ↔ tools) → route_after_tools → (agent | validate_md | human_input | parse_to_json) → END

    Story 2.5 additions:
    - tools node executes tool calls and updates state (last_checkpoint_id, pending_question)
    - route_after_tools conditional routing (priority: pending_question > checkpoint > complete > agent)
    - validate_md node runs markdownlint, routes back to agent on issues
    - parse_to_json stub writes structure.json for conversion epic
    - Conditional edges wire the loop

    Args:
        session_manager: Optional SessionManager for dependency injection (test/mock friendly).

    Returns:
        Compiled graph with checkpointer, interrupt_before, and full routing support.
    """
    sm = session_manager if session_manager is not None else SessionManager()

    def scan_assets_node(state: DocumentState) -> DocumentState:
        return _scan_assets_impl(state, sm)

    workflow = StateGraph(DocumentState)

    # Add all nodes
    workflow.add_node("scan_assets", scan_assets_node)
    workflow.add_node("human_input", _human_input_node)
    workflow.add_node(
        "apply_user_decisions",
        lambda state: _apply_user_decisions_node(state, sm),
    )
    workflow.add_node("agent", _agent_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("validate_md", validate_md_node)
    workflow.add_node("checkpoint", checkpoint_node)
    workflow.add_node("rollback", rollback_node)
    workflow.add_node("error_handler", error_handler_node)
    workflow.add_node("parse_to_json", parse_to_json_node)
    workflow.add_node("convert_docx", convert_with_docxjs_node)
    workflow.add_node("quality_check", quality_check_node)
    workflow.add_node("save_results", save_results_node)

    # Entry point
    workflow.add_edge(START, "scan_assets")

    # Conditional edge 1: scan_assets → agent | human_input (interrupt point 1)
    # If missing_references detected, pause at human_input
    workflow.add_conditional_edges(
        "scan_assets",
        lambda s: "human_input" if s.get("missing_references") else "agent",
        {"human_input": "human_input", "agent": "agent"},
    )

    # Edge: human_input → apply_user_decisions (after interrupt resolved, process decisions)
    workflow.add_edge("human_input", "apply_user_decisions")

    # Edge: apply_user_decisions → agent (after decisions applied, resume to agent)
    workflow.add_edge("apply_user_decisions", "agent")

    # Conditional edge 2: agent → human_input | tools | error_handler (interrupt point 2)
    # Route to tools if agent generated tool_calls, otherwise route to human_input if pending_question set
    def agent_routing(s: DocumentState) -> str:
        """Route from agent: prioritize human_input, then error, then check for tool_calls to route to tools."""
        # Check 1: Agent set pending_question (from content analysis)
        if s.get("pending_question") and str(s["pending_question"]).strip():
            return "human_input"

        # Check 2: Agent returned an error (last_error set by tools_node or agent)
        if s.get("last_error") and str(s["last_error"]).strip():
            return "error_handler"

        # Check 3: Agent generated tool_calls
        messages = s.get("messages", [])
        if messages:
            from langchain_core.messages import AIMessage

            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage) and getattr(
                last_msg, "tool_calls", None
            ):
                return "tools"

        # Fallback (shouldn't happen in normal flow, but default to human_input to prevent silent failures)
        return "human_input"

    workflow.add_conditional_edges(
        "agent",
        agent_routing,
        {
            "human_input": "human_input",
            "tools": "tools",
            "error_handler": "error_handler",
        },
    )

    # Conditional edge 3: tools → human_input | validate_md | parse_to_json | agent
    # Route after tools are executed, using route_after_tools
    workflow.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "human_input": "human_input",
            "validate": "validate_md",
            "complete": "parse_to_json",
            "agent": "agent",
        },
    )

    # Node to increment fix_attempts before routing
    def increment_fix_attempts_node(state: DocumentState) -> DocumentState:
        """Increment fix_attempts counter when routing back to agent for fixes."""
        if not state.get("validation_passed"):
            current_attempts = state.get("fix_attempts", 0)
            return {"fix_attempts": current_attempts + 1}
        return {}

    # Add the increment node
    workflow.add_node("increment_fix_attempts", increment_fix_attempts_node)

    # Edge: validate_md → increment_fix_attempts
    workflow.add_edge("validate_md", "increment_fix_attempts")

    # Conditional edge: increment_fix_attempts → checkpoint | agent | complete
    # Uses route_after_validation which checks fix_attempts cap
    workflow.add_conditional_edges(
        "increment_fix_attempts",
        route_after_validation,
        {
            "checkpoint": "checkpoint",
            "agent": "agent",
            "complete": "parse_to_json",
        },
    )

    # Edge: checkpoint → agent (after checkpoint saved, continue to next chapter)
    workflow.add_edge("checkpoint", "agent")

    # Conditional edge: error_handler → retry | fail
    # Uses should_retry_conversion to decide whether to retry or fail (Story 6.3)
    # Note: rollback is now handled inside error_handler_node, so retry goes directly to agent
    workflow.add_conditional_edges(
        "error_handler",
        should_retry_conversion,
        {
            "retry": "agent",
            "fail": "save_results",
        },
    )

    # Edge: save_results → END (final state)
    workflow.add_edge("save_results", END)

    # Edge: parse_to_json → convert_docx (Story 5.4: convert to DOCX)
    workflow.add_edge("parse_to_json", "convert_docx")

    # Conditional edge: convert_docx → quality_check (Story 5.5: quality check)
    # Routes to quality_check if conversion succeeded, otherwise to error_handler
    def route_after_conversion(s: DocumentState) -> str:
        """Route after DOCX conversion: check conversion_success."""
        if s.get("conversion_success"):
            return "quality_check"
        return "error_handler"

    workflow.add_conditional_edges(
        "convert_docx",
        route_after_conversion,
        {"quality_check": "quality_check", "error_handler": "error_handler"},
    )

    # Conditional edge: quality_check → END or error_handler
    # Routes to END if quality passed, otherwise to error_handler
    def route_after_quality_check(s: DocumentState) -> str:
        """Route after quality check: check quality_passed."""
        if s.get("quality_passed"):
            return "end"
        return "error_handler"

    workflow.add_conditional_edges(
        "quality_check",
        route_after_quality_check,
        {"end": END, "error_handler": "error_handler"},
    )

    # Compile with checkpointer and interrupt_before (Story 2.4)
    checkpointer = MemorySaver()
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_input"],
    )
