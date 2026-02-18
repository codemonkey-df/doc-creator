"""Tests for TUI panels."""

from src.tui.state import AppState, ChapterEntry
from src.tui.panels import render_sources, render_outline, render_log


class TestRenderSources:
    """Tests for render_sources function."""

    def test_returns_panel_with_title(self):
        """Panel should have 'Sources' title."""
        state = AppState(detected_files=[])
        panel = render_sources(state)
        assert panel.title == "Sources"

    def test_shows_empty_list_when_no_files(self):
        """Should show empty list when no files detected."""
        state = AppState(detected_files=[])
        panel = render_sources(state)
        assert "(none)" in str(panel.renderable)

    def test_shows_files_with_numeric_ids(self):
        """Files should be listed with [1], [2], etc. format."""
        state = AppState(detected_files=["intro.md", "chapter1.md", "chapter2.md"])
        panel = render_sources(state)
        content = str(panel.renderable)
        assert "[1] intro.md" in content
        assert "[2] chapter1.md" in content
        assert "[3] chapter2.md" in content

    def test_marks_used_intro_file(self):
        """Used intro file should be marked with checkmark."""
        state = AppState(
            detected_files=["intro.md", "chapter1.md"], intro_file="intro.md"
        )
        panel = render_sources(state)
        content = str(panel.renderable)
        assert "✓" in content

    def test_marks_used_chapter_files(self):
        """Used chapter files should be marked with checkmark."""
        state = AppState(
            detected_files=["intro.md", "chapter1.md", "chapter2.md"],
            chapters=[ChapterEntry("chapter1.md")],
        )
        panel = render_sources(state)
        content = str(panel.renderable)
        assert "✓" in content


class TestRenderOutline:
    """Tests for render_outline function."""

    def test_returns_panel_with_title(self):
        """Panel should have 'Outline' title."""
        state = AppState()
        panel = render_outline(state)
        assert panel.title == "Outline"

    def test_shows_default_title(self):
        """Should show 'Title: Untitled' by default."""
        state = AppState()
        panel = render_outline(state)
        content = str(panel.renderable)
        assert "Title: Untitled" in content

    def test_shows_custom_title(self):
        """Should show custom title when set."""
        state = AppState(title="My Document")
        panel = render_outline(state)
        content = str(panel.renderable)
        assert "Title: My Document" in content

    def test_shows_none_for_intro_when_not_set(self):
        """Should show 'Intro: (none)' when intro not set."""
        state = AppState()
        panel = render_outline(state)
        content = str(panel.renderable)
        assert "Intro: (none)" in content

    def test_shows_intro_file_when_set(self):
        """Should show intro file when set."""
        state = AppState(intro_file="intro.md")
        panel = render_outline(state)
        content = str(panel.renderable)
        assert "Intro: intro.md" in content

    def test_shows_none_for_chapters_when_empty(self):
        """Should show 'Chapters: (none)' when no chapters."""
        state = AppState()
        panel = render_outline(state)
        content = str(panel.renderable)
        assert "Chapters: (none)" in content

    def test_shows_chapter_list(self):
        """Should show list of chapters when set."""
        state = AppState(
            chapters=[ChapterEntry("chapter1.md"), ChapterEntry("chapter2.md")]
        )
        panel = render_outline(state)
        content = str(panel.renderable)
        assert "chapter1.md" in content
        assert "chapter2.md" in content


class TestRenderLog:
    """Tests for render_log function."""

    def test_returns_panel_with_title(self):
        """Panel should have 'Log' title."""
        state = AppState(log_lines=[])
        panel = render_log(state)
        assert panel.title == "Log"

    def test_shows_empty_when_no_logs(self):
        """Should show '(none)' when no log lines."""
        state = AppState(log_lines=[])
        panel = render_log(state)
        content = str(panel.renderable)
        assert "(none)" in content

    def test_shows_log_lines(self):
        """Should show log lines when present."""
        state = AppState(log_lines=["Log line 1", "Log line 2"])
        panel = render_log(state)
        content = str(panel.renderable)
        assert "Log line 1" in content
        assert "Log line 2" in content

    def test_respects_max_lines(self):
        """Should only show last N lines."""
        state = AppState(log_lines=["Line 1", "Line 2", "Line 3", "Line 4", "Line 5"])
        panel = render_log(state, max_lines=3)
        content = str(panel.renderable)
        assert "Line 1" not in content
        assert "Line 3" in content
        assert "Line 5" in content
