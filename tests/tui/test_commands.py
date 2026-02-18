"""Unit tests for command parsing and handlers."""

from src.tui.state import AppState, ChapterEntry
from src.tui.commands import (
    parse_command,
    handle_title,
    handle_intro,
    handle_chapter,
    handle_remove,
    handle_reset,
    handle_help,
    handle_quit,
)


class TestParseCommand:
    """Tests for parse_command function."""

    def test_parse_title_with_quoted_string(self):
        """Test parsing /title with quoted string."""
        cmd = parse_command('/title "My Document"')
        assert cmd is not None
        assert cmd.name == "title"
        assert cmd.args == ["My Document"]

    def test_parse_title_with_unquoted_string(self):
        """Test parsing /title with unquoted string."""
        cmd = parse_command("/title My Document")
        assert cmd is not None
        assert cmd.name == "title"
        assert cmd.args == ["My", "Document"]

    def test_parse_intro_with_id(self):
        """Test parsing /intro with numeric ID."""
        cmd = parse_command("/intro 1")
        assert cmd is not None
        assert cmd.name == "intro"
        assert cmd.args == ["1"]

    def test_parse_chapter_with_id_and_title(self):
        """Test parsing /chapter with ID and custom title."""
        cmd = parse_command('/chapter 2 "Custom Title"')
        assert cmd is not None
        assert cmd.name == "chapter"
        assert cmd.args == ["2", "Custom Title"]

    def test_parse_unknown_command(self):
        """Test that unknown commands return None."""
        cmd = parse_command("/unknown arg")
        assert cmd is None

    def test_parse_empty_string(self):
        """Test that empty string returns None."""
        cmd = parse_command("")
        assert cmd is None

    def test_parse_non_command(self):
        """Test that non-command strings return None."""
        cmd = parse_command("hello world")
        assert cmd is None


class TestHandleTitle:
    """Tests for handle_title function."""

    def test_sets_title(self):
        """Test that title is set correctly."""
        state = AppState()
        handle_title(state, ["My Title"])
        assert state.title == "My Title"
        assert "Title set to: My Title" in state.log_lines

    def test_empty_args_shows_usage(self):
        """Test that empty args shows usage message."""
        state = AppState()
        handle_title(state, [])
        assert state.title == "Untitled"
        assert "Usage: /title <title>" in state.log_lines


class TestHandleIntro:
    """Tests for handle_intro function."""

    def test_sets_intro_by_id(self):
        """Test that intro is set by numeric ID."""
        state = AppState(detected_files=["intro.md", "chapter1.md"])
        handle_intro(state, ["1"])
        assert state.intro_file == "intro.md"
        assert "Intro set to: intro.md" in state.log_lines

    def test_invalid_id_shows_error(self):
        """Test that invalid ID shows error."""
        state = AppState(detected_files=["intro.md"])
        handle_intro(state, ["99"])
        assert state.intro_file is None
        assert "Invalid ID: 99" in state.log_lines

    def test_empty_args_shows_usage(self):
        """Test that empty args shows usage message."""
        state = AppState()
        handle_intro(state, [])
        assert "Usage: /intro <id>" in state.log_lines


class TestHandleChapter:
    """Tests for handle_chapter function."""

    def test_adds_chapter(self):
        """Test that chapter is added correctly."""
        state = AppState(detected_files=["intro.md", "chapter1.md"])
        handle_chapter(state, ["2"])
        assert len(state.chapters) == 1
        assert state.chapters[0].file_path == "chapter1.md"
        assert state.chapters[0].custom_title is None
        assert "Added chapter: chapter1.md" in state.log_lines

    def test_adds_chapter_with_custom_title(self):
        """Test that chapter is added with custom title."""
        state = AppState(detected_files=["intro.md", "chapter1.md"])
        handle_chapter(state, ["2", "Custom Title"])
        assert len(state.chapters) == 1
        assert state.chapters[0].file_path == "chapter1.md"
        assert state.chapters[0].custom_title == "Custom Title"
        assert "Added chapter: chapter1.md (title: Custom Title)" in state.log_lines

    def test_invalid_id_shows_error(self):
        """Test that invalid ID shows error."""
        state = AppState(detected_files=["intro.md"])
        handle_chapter(state, ["99"])
        assert len(state.chapters) == 0
        assert "Invalid ID: 99" in state.log_lines

    def test_empty_args_shows_usage(self):
        """Test that empty args shows usage message."""
        state = AppState()
        handle_chapter(state, [])
        assert "Usage: /chapter <id> [title]" in state.log_lines


class TestHandleRemove:
    """Tests for handle_remove function."""

    def test_removes_chapter_by_index(self):
        """Test that chapter is removed by 1-based index."""
        state = AppState(chapters=[ChapterEntry("chapter1.md")])
        handle_remove(state, ["1"])
        assert len(state.chapters) == 0
        assert "Removed: chapter1.md" in state.log_lines

    def test_invalid_index_shows_error(self):
        """Test that invalid index shows error."""
        state = AppState(chapters=[ChapterEntry("chapter1.md")])
        handle_remove(state, ["99"])
        assert len(state.chapters) == 1
        assert "Invalid index: 99" in state.log_lines

    def test_empty_args_shows_usage(self):
        """Test that empty args shows usage message."""
        state = AppState()
        handle_remove(state, [])
        assert "Usage: /remove <index>" in state.log_lines


class TestHandleReset:
    """Tests for handle_reset function."""

    def test_resets_intro_and_chapters(self):
        """Test that intro and chapters are cleared."""
        state = AppState(intro_file="intro.md", chapters=[ChapterEntry("chapter1.md")])
        handle_reset(state)
        assert state.intro_file is None
        assert len(state.chapters) == 0
        assert "Reset: intro and chapters cleared" in state.log_lines


class TestHandleHelp:
    """Tests for handle_help function."""

    def test_displays_help(self):
        """Test that help text is added to log."""
        state = AppState()
        handle_help(state)
        assert "Commands:" in state.log_lines
        assert "/title" in state.log_lines[1]


class TestHandleQuit:
    """Tests for handle_quit function."""

    def test_sets_running_to_false(self):
        """Test that running flag is set to False."""
        state = AppState()
        running = [True]
        handle_quit(state, running)
        assert running[0] is False
        assert "Goodbye!" in state.log_lines
