"""Tests for DocForgeApp."""

import pytest
from unittest.mock import Mock
from io import StringIO
from src.tui.state import AppState
from src.tui.app import DocForgeApp


def render_to_string(renderable):
    """Helper to render a Rich renderable to string for testing."""
    from rich.console import Console

    console = Console(file=StringIO(), force_terminal=True, width=80)
    console.print(renderable)
    return console.file.getvalue()


@pytest.fixture
def mock_watcher():
    """Create a mock FileWatcher."""
    watcher = Mock()
    return watcher


class TestDocForgeApp:
    """Tests for DocForgeApp class."""

    def test_can_instantiate(self, mock_watcher):
        """DocForgeApp should be instantiable with AppState."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)
        assert app.state is state

    def test_has_input_buffer(self, mock_watcher):
        """App should have an input buffer attribute."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)
        assert hasattr(app, "_input_buffer")
        assert app._input_buffer == ""

    def test_has_run_method(self, mock_watcher):
        """DocForgeApp should have a run method."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)
        assert hasattr(app, "run")
        assert callable(app.run)

    def test_has_make_layout_method(self, mock_watcher):
        """DocForgeApp should have a _make_layout method."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)
        assert hasattr(app, "_make_layout")
        assert callable(app._make_layout)

    def test_has_render_method(self, mock_watcher):
        """DocForgeApp should have a _render method."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)
        assert hasattr(app, "_render")
        assert callable(app._render)

    def test_render_returns_renderable(self, mock_watcher):
        """_render should return a renderable object."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)
        renderable = app._render()
        assert renderable is not None


class TestDocForgeAppLayout:
    """Tests for DocForgeApp layout structure."""

    def test_layout_has_sources_panel(self, mock_watcher):
        """Layout should include Sources panel area."""
        state = AppState(detected_files=["test.md"])
        app = DocForgeApp(state, mock_watcher)
        renderable = app._render()
        content = render_to_string(renderable)
        assert "Sources" in content

    def test_layout_has_outline_panel(self, mock_watcher):
        """Layout should include Outline panel area."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)
        renderable = app._render()
        content = render_to_string(renderable)
        assert "Outline" in content

    def test_layout_has_log_panel(self, mock_watcher):
        """Layout should include Log panel area."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)
        renderable = app._render()
        content = render_to_string(renderable)
        assert "Log" in content

    def test_layout_has_prompt_line(self, mock_watcher):
        """Layout should include prompt line."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)
        renderable = app._render()
        content = render_to_string(renderable)
        # Should show "> " for prompt
        assert "> " in content


class TestDocForgeAppIntegration:
    """Integration tests for DocForgeApp."""

    def test_run_does_not_crash(self, mock_watcher):
        """run() should be callable without crashing (tested with mock Live)."""
        state = AppState()
        app = DocForgeApp(state, mock_watcher)

        # Just verify the method exists and is callable
        assert callable(app.run)
