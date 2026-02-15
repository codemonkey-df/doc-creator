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
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.agent import agent_node as agent_node_impl
from backend.graph_nodes import parse_to_json_node, tools_node, validate_md_node
from backend.routing import route_after_tools
from backend.state import DocumentState, ImageRefResult
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
    workflow.add_node("agent", _agent_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("validate_md", validate_md_node)
    workflow.add_node("parse_to_json", parse_to_json_node)

    # Entry point
    workflow.add_edge(START, "scan_assets")

    # Conditional edge 1: scan_assets → agent | human_input (interrupt point 1)
    # If missing_references detected, pause at human_input
    workflow.add_conditional_edges(
        "scan_assets",
        lambda s: "human_input" if s.get("missing_references") else "agent",
        {"human_input": "human_input", "agent": "agent"},
    )

    # Edge: human_input → agent (after interrupt resolved, resume to agent)
    workflow.add_edge("human_input", "agent")

    # Conditional edge 2: agent → human_input | tools (interrupt point 2)
    # Route to tools if agent generated tool_calls, otherwise route to human_input if pending_question set
    def agent_routing(s: DocumentState) -> str:
        """Route from agent: prioritize human_input, then check for tool_calls to route to tools."""
        # Check 1: Agent set pending_question (from content analysis)
        if s.get("pending_question") and str(s["pending_question"]).strip():
            return "human_input"

        # Check 2: Agent generated tool_calls
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

    # Edge: validate_md → agent (always route back to agent for fixes or next chapter)
    workflow.add_edge("validate_md", "agent")

    # Edge: parse_to_json → END (conversion complete)
    workflow.add_edge("parse_to_json", END)

    # Compile with checkpointer and interrupt_before (Story 2.4)
    checkpointer = MemorySaver()
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_input"],
    )
