"""Unit tests for should_retry_conversion routing function (Story 6.3)."""

from __future__ import annotations


from backend.routing import should_retry_conversion, MAX_RETRY_ATTEMPTS
from backend.state import build_initial_state


class TestShouldRetryConversion:
    """Test should_retry_conversion routing function."""

    def test_retry_when_retry_count_zero(self) -> None:
        """GIVEN retry_count=0 WHEN should_retry_conversion THEN returns 'retry'."""
        state = build_initial_state(session_id="test", input_files=["doc.md"])
        state["retry_count"] = 0

        result = should_retry_conversion(state)

        assert result == "retry"

    def test_retry_when_retry_count_one(self) -> None:
        """GIVEN retry_count=1 WHEN should_retry_conversion THEN returns 'retry'."""
        state = build_initial_state(session_id="test", input_files=["doc.md"])
        state["retry_count"] = 1

        result = should_retry_conversion(state)

        assert result == "retry"

    def test_retry_when_retry_count_two(self) -> None:
        """GIVEN retry_count=2 WHEN should_retry_conversion THEN returns 'retry'."""
        state = build_initial_state(session_id="test", input_files=["doc.md"])
        state["retry_count"] = 2

        result = should_retry_conversion(state)

        assert result == "retry"

    def test_fail_when_retry_count_three(self) -> None:
        """GIVEN retry_count=3 (at max) WHEN should_retry_conversion THEN returns 'fail'."""
        state = build_initial_state(session_id="test", input_files=["doc.md"])
        state["retry_count"] = 3

        result = should_retry_conversion(state)

        assert result == "fail"

    def test_fail_when_retry_count_exceeds_max(self) -> None:
        """GIVEN retry_count=5 (exceeds max) WHEN should_retry_conversion THEN returns 'fail'."""
        state = build_initial_state(session_id="test", input_files=["doc.md"])
        state["retry_count"] = 5

        result = should_retry_conversion(state)

        assert result == "fail"

    def test_retry_when_retry_count_not_in_state(self) -> None:
        """GIVEN retry_count not in state WHEN should_retry_conversion THEN defaults to 'retry'."""
        state = build_initial_state(session_id="test", input_files=["doc.md"])

        result = should_retry_conversion(state)

        assert result == "retry"

    def test_max_retry_attempts_is_three(self) -> None:
        """Verify MAX_RETRY_ATTEMPTS is 3."""
        assert MAX_RETRY_ATTEMPTS == 3
