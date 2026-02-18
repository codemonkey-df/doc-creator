"""Tests for src/tui/state.py module."""

from src.tui.state import AppState, ChapterEntry


class TestAppState:
    """Tests for AppState dataclass."""

    def test_appstate_dataclass_exists(self):
        """AppState should be importable from src.tui.state."""
        from src.tui.state import AppState

        assert AppState is not None

    def test_appstate_default_values(self):
        """AppState should have correct default values."""
        state = AppState()

        assert state.title == "Untitled"
        assert state.intro_file is None
        assert state.chapters == []
        assert state.detected_files == []
        assert state.log_lines == []

    def test_appstate_can_be_instantiated_with_values(self):
        """AppState should accept custom values."""
        state = AppState(
            title="My Document",
            intro_file="intro.md",
            chapters=["chapter1.md", "chapter2.md"],
            detected_files=["file1.md", "file2.md"],
            log_lines=["Starting..."],
        )

        assert state.title == "My Document"
        assert state.intro_file == "intro.md"
        assert state.chapters == ["chapter1.md", "chapter2.md"]
        assert state.detected_files == ["file1.md", "file2.md"]
        assert state.log_lines == ["Starting..."]


class TestChapterEntry:
    """Tests for ChapterEntry dataclass."""

    def test_chapter_entry_dataclass_exists(self):
        """ChapterEntry should be importable from src.tui.state."""
        from src.tui.state import ChapterEntry

        assert ChapterEntry is not None

    def test_chapter_entry_fields(self):
        """ChapterEntry should have correct fields."""
        entry = ChapterEntry(file_path="chapter1.md", custom_title="Custom Title")

        assert entry.file_path == "chapter1.md"
        assert entry.custom_title == "Custom Title"

    def test_chapter_entry_custom_title_optional(self):
        """ChapterEntry custom_title should be optional."""
        entry = ChapterEntry(file_path="chapter1.md")

        assert entry.file_path == "chapter1.md"
        assert entry.custom_title is None
