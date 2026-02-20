"""Unit tests for prompt templates."""

from src.llm.prompts import (
    prompt_generate_toc,
    prompt_self_heal,
    prompt_structure_chapter,
    prompt_summarize_intro,
)


class TestPromptSummarizeIntro:
    """Tests for prompt_summarize_intro."""

    def test_returns_non_empty_tuple(self) -> None:
        """Test that the function returns a non-empty tuple."""
        result = prompt_summarize_intro("Some content")

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0]  # system prompt not empty
        assert result[1]  # user prompt not empty

    def test_contains_content_in_user_prompt(self) -> None:
        """Test that the content is included in the user prompt."""
        content = "Test content here"
        _, user = prompt_summarize_intro(content)

        assert content in user


class TestPromptStructureChapter:
    """Tests for prompt_structure_chapter."""

    def test_returns_non_empty_tuple(self) -> None:
        """Test that the function returns a non-empty tuple."""
        result = prompt_structure_chapter("Some content", "My Chapter")

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0]  # system prompt not empty
        assert result[1]  # user prompt not empty

    def test_injects_title_into_user_message(self) -> None:
        """Test that the chapter title is injected into the user message."""
        title = "Introduction"
        _, user = prompt_structure_chapter("Content here", title)

        assert title in user
        assert f'"{title}"' in user


class TestPromptGenerateToc:
    """Tests for prompt_generate_toc."""

    def test_returns_non_empty_tuple(self) -> None:
        """Test that the function returns a non-empty tuple."""
        # New format: list of tuples (chapter_title, subheadings_list)
        chapters = [("Chapter 1", []), ("Chapter 2", ["Sub A", "Sub B"])]
        result = prompt_generate_toc("My Document", chapters)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0]  # system prompt not empty
        assert result[1]  # user prompt not empty

    def test_includes_chapters_in_user_prompt(self) -> None:
        """Test that chapter titles are included in the user prompt."""
        # New format: list of tuples (chapter_title, subheadings_list)
        chapters = [("Chapter 1", []), ("Chapter 2", ["Sub A", "Sub B"])]
        _, user = prompt_generate_toc("Doc Title", chapters)

        assert "Chapter 1" in user
        assert "Chapter 2" in user

    def test_includes_subheadings_in_user_prompt(self) -> None:
        """Test that subheadings are included in the user prompt."""
        chapters = [("Chapter 1", ["Introduction", "Background"])]
        _, user = prompt_generate_toc("Doc Title", chapters)

        assert "Introduction" in user
        assert "Background" in user


class TestPromptSelfHeal:
    """Tests for prompt_self_heal."""

    def test_returns_non_empty_tuple(self) -> None:
        """Test that the function returns a non-empty tuple."""
        result = prompt_self_heal("# Broken Markdown")

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0]  # system prompt not empty
        assert result[1]  # user prompt not empty

    def test_contains_markdown_in_user_prompt(self) -> None:
        """Test that the markdown content is included in the user prompt."""
        markdown = "# Title\n\nSome content"
        _, user = prompt_self_heal(markdown)

        assert markdown in user
