"""Unit tests for the self-heal module."""

from unittest.mock import MagicMock, patch

import pytest

from src.config import LlmConfig
from src.llm.healer import heal_markdown, needs_healing


@pytest.fixture
def config() -> LlmConfig:
    """Fixture to return a LlmConfig instance."""
    return LlmConfig()


class TestNeedsHealing:
    """Tests for the needs_healing function."""

    def test_matched_code_fences_returns_false(self) -> None:
        """Test that matched code fences don't need healing."""
        markdown = "```\ncode\n```"
        assert needs_healing(markdown) is False

    def test_unmatched_code_fences_returns_true(self) -> None:
        """Test that unmatched code fences need healing."""
        markdown = "```\ncode\n"
        assert needs_healing(markdown) is True

    def test_heading_without_blank_line_returns_true(self) -> None:
        """Test that headings without blank lines need healing."""
        # Heading preceded by content (no blank line) - needs healing
        markdown = "Content\n# Heading"
        assert needs_healing(markdown) is True

    def test_heading_with_blank_line_returns_false(self) -> None:
        """Test that headings with blank lines don't need healing."""
        markdown = "# Heading\n\nContent"
        assert needs_healing(markdown) is False

    def test_multiple_issues_returns_true(self) -> None:
        """Test that multiple issues (unmatched code) need healing."""
        # Heading preceded by content + unmatched code fence
        markdown = "Content\n# Heading\n\n```code"
        assert needs_healing(markdown) is True

    def test_normal_text_returns_false(self) -> None:
        """Test that normal text without issues doesn't need healing."""
        markdown = "Normal text"
        assert needs_healing(markdown) is False

    def test_empty_string_returns_false(self) -> None:
        """Test that empty string doesn't need healing."""
        assert needs_healing("") is False

    def test_heading_at_start_no_previous_line(self) -> None:
        """Test that heading at start of document doesn't need healing."""
        markdown = "# Title\n\nSome content"
        assert needs_healing(markdown) is False


class TestHealMarkdown:
    """Tests for the heal_markdown function."""

    @patch("src.llm.healer.call_llm")
    def test_heal_markdown_calls_llm(
        self, mock_call_llm: MagicMock, config: LlmConfig
    ) -> None:
        """Test that heal_markdown calls the LLM with the correct prompts."""
        mock_call_llm.return_value = "Fixed markdown"
        markdown = "```\ncode\n"

        result = heal_markdown(markdown, config)

        mock_call_llm.assert_called_once()
        call_args = mock_call_llm.call_args
        assert (
            call_args[0][0] == "You are a Markdown expert. Fix any malformed Markdown."
        )
        assert "```\ncode\n" in call_args[0][1]
        assert result == "Fixed markdown"

    @patch("src.llm.healer.call_llm")
    def test_heal_markdown_returns_llm_response(
        self, mock_call_llm: MagicMock, config: LlmConfig
    ) -> None:
        """Test that heal_markdown returns the LLM's response."""
        expected = "# Fixed Heading\n\nContent"
        mock_call_llm.return_value = expected

        result = heal_markdown("# Heading\nContent", config)

        assert result == expected
