"""Main DocForge TUI application."""

from rich.live import Live
from rich.console import Console, Group
from rich.text import Text
from rich.columns import Columns
from src.tui.state import AppState
from src.tui.panels import render_sources, render_outline, render_log
from src.tui.watcher import FileWatcher


class DocForgeApp:
    """Main TUI application with live rendering."""

    def __init__(self, state: AppState, watcher: FileWatcher):
        self.state = state
        self.watcher = watcher
        self._input_buffer = ""
        self._live = None

    def _make_layout(self):
        """Create the layout structure (placeholder for future Rich Layout)."""
        return None

    def _render(self):
        """Render all panels and return the complete display."""
        sources = render_sources(self.state)
        outline = render_outline(self.state)
        log_panel = render_log(self.state)

        # Top row: Sources | Outline
        top_row = Columns([sources, outline], equal=False)

        return Group(
            top_row,
            log_panel,
            Text(f"> {self._input_buffer}", style="bold cyan"),
        )

    def run(self):
        """Start the Live loop with refresh_per_second=4."""
        console = Console()
        with Live(
            self._render(), console=console, refresh_per_second=4, screen=True
        ) as live:
            self._live = live
            try:
                while True:
                    live.update(self._render())
                    import time

                    time.sleep(0.25)
            except KeyboardInterrupt:
                pass
