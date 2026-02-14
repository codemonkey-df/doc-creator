"""LangGraph workflow for document generation (Stories 1.4, 2.1-2.5).

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
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.agent import agent_node as agent_node_impl
from backend.graph_nodes import parse_to_json_node, tools_node, validate_md_node
from backend.routing import route_after_tools
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
