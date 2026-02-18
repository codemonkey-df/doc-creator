"""Panel rendering functions for DocForge TUI."""

from rich.panel import Panel
from rich.text import Text
from src.tui.state import AppState


def _is_file_used(state: AppState, filepath: str) -> bool:
    """Check if a file is used as intro or in chapters."""
    if filepath == state.intro_file:
        return True
    return any(chapter.file_path == filepath for chapter in state.chapters)


def render_sources(state: AppState) -> Panel:
    """Render the Sources panel with detected files and numeric IDs."""
    if not state.detected_files:
        content = Text("(none)", style="dim")
    else:
        lines = []
        for idx, filepath in enumerate(state.detected_files, start=1):
            line = f"[{idx}] {filepath}"
            # Mark used files with checkmark
            if _is_file_used(state, filepath):
                line += " ✓"
            lines.append(line)
        content = Text("\n".join(lines))

    return Panel(content, title="Sources", border_style="blue")


def render_outline(state: AppState) -> Panel:
    """Render the Outline panel with title, intro, chapters."""
    lines = [
        f"Title: {state.title}",
        f"Intro: {state.intro_file or '(none)'}",
    ]

    if state.chapters:
        lines.append("Chapters:")
        for idx, chapter in enumerate(state.chapters, start=1):
            title = chapter.custom_title or chapter.file_path
            lines.append(f"  - {idx}. {title}")
    else:
        lines.append("Chapters: (none)")

    content = Text("\n".join(lines))
    return Panel(content, title="Outline", border_style="green")


def render_log(state: AppState, max_lines: int = 10) -> Panel:
    """Render the Log panel with last N log lines."""
    log_lines = state.log_lines[-max_lines:]

    if not log_lines:
        content = Text("(none)", style="dim")
    else:
        content = Text("\n".join(log_lines))

    return Panel(content, title="Log", border_style="yellow")
