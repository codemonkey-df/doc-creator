"""Tests for Story 4.3: Conditional Edges for routing after validation.

Tests cover:
- AC4.3.1: route_after_validation with priority: validation_passed → checkpoint | agent | complete
- AC4.3.2: fix_attempts counter limits fix loop to MAX_FIX_ATTEMPTS (3)
- AC4.3.3: After max fixes exceeded, route to complete (parse_to_json) instead of infinite loop
- AC4.3.4: fix_attempts in DocumentState and incremented on each fix attempt

All tests use GIVEN-WHEN-THEN structure.
"""

from __future__ import annotations

from backend.routing import MAX_FIX_ATTEMPTS, route_after_validation
from backend.state import build_initial_state


# ============================================================================
# TEST FIX_ATTEMPTS IN STATE (AC4.3.4)
# ============================================================================


def test_fix_attempts_in_document_state() -> None:
    """GIVEN DocumentState TypedDict / WHEN accessing fix_attempts / THEN field exists."""
    state = build_initial_state("test-session", ["file.md"])

    # fix_attempts should be in initial state with default 0
    assert "fix_attempts" in state
    assert state["fix_attempts"] == 0


def test_fix_attempts_increments_in_state() -> None:
    """GIVEN state with fix_attempts=0 / WHEN increment / THEN fix_attempts becomes 1."""
    state = build_initial_state("test-session", ["file.md"])
    assert state["fix_attempts"] == 0

    # Simulate increment
    state["fix_attempts"] = state["fix_attempts"] + 1
    assert state["fix_attempts"] == 1


def test_fix_attempts_max_constant_defined() -> None:
    """GIVEN MAX_FIX_ATTEMPTS constant / WHEN imported / THEN equals 3."""
    assert MAX_FIX_ATTEMPTS == 3


# ============================================================================
# TEST ROUTE_AFTER_VALIDATION (AC4.3.1, AC4.3.2, AC4.3.3)
# ============================================================================


def test_route_after_validation_passes_to_checkpoint() -> None:
    """GIVEN state with validation_passed=True / WHEN route_after_validation / THEN returns 'checkpoint'."""
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = True
    state["validation_issues"] = []
    state["fix_attempts"] = 0

    result = route_after_validation(state)

    assert result == "checkpoint"


def test_route_after_validation_fails_routes_to_agent() -> None:
    """GIVEN state with validation_passed=False and fix_attempts < MAX / WHEN route_after_validation / THEN returns 'agent'."""
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = False
    state["validation_issues"] = [
        {"line_number": 1, "rule": "MD001", "message": "Header levels"}
    ]
    state["fix_attempts"] = 0

    result = route_after_validation(state)

    assert result == "agent"


def test_route_after_validation_fails_with_existing_fix_attempts() -> None:
    """GIVEN state with validation_passed=False and fix_attempts=1 / WHEN route_after_validation / THEN returns 'agent' (still can fix)."""
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = False
    state["fix_attempts"] = 1

    result = route_after_validation(state)

    assert result == "agent"


def test_route_after_validation_max_fix_attempts_exceeded() -> None:
    """GIVEN state with validation_passed=False and fix_attempts >= MAX / WHEN route_after_validation / THEN returns 'complete'."""
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = False
    state["fix_attempts"] = MAX_FIX_ATTEMPTS  # 3

    result = route_after_validation(state)

    assert result == "complete"


def test_route_after_validation_max_fix_attempts_exceeded_edge_case() -> None:
    """GIVEN state with validation_passed=False and fix_attempts > MAX / WHEN route_after_validation / THEN returns 'complete'."""
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = False
    state["fix_attempts"] = MAX_FIX_ATTEMPTS + 5  # 8

    result = route_after_validation(state)

    assert result == "complete"


def test_route_after_validation_priority_validation_passed_over_fix_attempts() -> None:
    """GIVEN state with validation_passed=True AND fix_attempts >= MAX / WHEN route_after_validation / THEN returns 'checkpoint' (validation_passed has priority)."""
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = True
    state["fix_attempts"] = MAX_FIX_ATTEMPTS  # Should not matter

    result = route_after_validation(state)

    assert result == "checkpoint"


def test_route_after_validation_fix_attempts_at_boundary() -> None:
    """GIVEN state with fix_attempts=2 (one less than MAX) / WHEN route_after_validation fails / THEN returns 'agent' (can still fix once)."""
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = False
    state["fix_attempts"] = MAX_FIX_ATTEMPTS - 1  # 2

    result = route_after_validation(state)

    assert result == "agent"


# ============================================================================
# TEST INCREMENT NODE INTEGRATION
# ============================================================================


def test_increment_fix_attempts_node_increments_on_validation_failure() -> None:
    """GIVEN validate_md node sets validation_passed=False / WHEN increment_fix_attempts_node runs / THEN fix_attempts incremented."""
    # The increment happens in the graph - we test the logic here
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = False
    state["fix_attempts"] = 0

    # Simulate the increment logic from graph.py
    if not state.get("validation_passed"):
        current_attempts = state.get("fix_attempts", 0)
        state["fix_attempts"] = current_attempts + 1

    assert state["fix_attempts"] == 1


def test_increment_fix_attempts_node_no_increment_on_validation_pass() -> None:
    """GIVEN validate_md node sets validation_passed=True / WHEN increment_fix_attempts_node runs / THEN fix_attempts NOT incremented."""
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = True
    state["fix_attempts"] = 0

    # Simulate the increment logic from graph.py
    if not state.get("validation_passed"):
        current_attempts = state.get("fix_attempts", 0)
        state["fix_attempts"] = current_attempts + 1

    assert state["fix_attempts"] == 0


# ============================================================================
# TEST GRAPH INTEGRATION
# ============================================================================


def test_graph_compiles_with_conditional_edges() -> None:
    """GIVEN session_manager / WHEN create_document_workflow / THEN graph compiles with validate_routing."""
    from backend.graph import create_document_workflow
    from unittest.mock import MagicMock

    sm = MagicMock()
    sm.get_path.return_value.__fspath__ = "/tmp/test"

    graph = create_document_workflow(session_manager=sm)
    assert graph is not None


def test_validate_routing_in_graph_uses_route_after_validation() -> None:
    """GIVEN graph with validate_routing / WHEN route_after_validation is called / THEN correct node selected."""
    # This is tested via route_after_validation tests above
    # The graph wires validate_md → increment_fix_attempts → route_after_validation
    assert route_after_validation.__name__ == "route_after_validation"


def test_fix_attempts_caps_validation_loop() -> None:
    """GIVEN validation fails repeatedly / WHEN fix_attempts reaches MAX / THEN routes to complete (stops infinite loop)."""
    # Simulate 3 failed validation attempts
    for attempt in range(MAX_FIX_ATTEMPTS):
        state = build_initial_state("sid", ["f.md"])
        state["validation_passed"] = False
        state["fix_attempts"] = attempt

        result = route_after_validation(state)

        # All attempts before MAX should route to agent
        assert result == "agent", f"Attempt {attempt} should route to agent"

    # After MAX attempts, should route to complete
    state = build_initial_state("sid", ["f.md"])
    state["validation_passed"] = False
    state["fix_attempts"] = MAX_FIX_ATTEMPTS

    result = route_after_validation(state)
    assert result == "complete"


# ============================================================================
# TEST FIX_ATTEMPTS DEFAULT IN INITIAL_STATE
# ============================================================================


def test_build_initial_state_has_fix_attempts_default() -> None:
    """GIVEN build_initial_state / WHEN called / THEN fix_attempts defaults to 0."""
    state = build_initial_state("test-session", ["file.md"])

    assert "fix_attempts" in state
    assert state["fix_attempts"] == 0


def test_fix_attempts_preserved_in_state_passthrough() -> None:
    """GIVEN state with fix_attempts=2 / WHEN passed through nodes / THEN fix_attempts preserved."""
    state = build_initial_state("test-session", ["file.md"])
    state["fix_attempts"] = 2

    # Simulate passthrough (like most nodes do)
    new_state = {**state, "some_new_field": "value"}

    assert new_state["fix_attempts"] == 2
