"""Panel rendering functions for DocForge TUI."""

from rich.panel import Panel
from rich.text import Text
from src.scanner.ref_scanner import Ref
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


def render_resolution_screen(refs: list[Ref]) -> str:
    """Render the resolution screen for references.

    Args:
        refs: List of references to resolve.

    Returns:
        A string representation of the resolution UI.
    """
    lines = []
    lines.append("\033[1;37;44m" + " Reference Resolution ".center(60) + "\033[0m")
    lines.append("")
    lines.append("The following references were detected in your documents:")
    lines.append("\033[90m" + "─" * 60 + "\033[0m")
    lines.append("")

    for idx, ref in enumerate(refs, start=1):
        # Type badge
        if ref.type == "image":
            badge = "\033[1;36m[IMAGE]\033[0m"
        elif ref.type == "url":
            badge = "\033[1;35m[URL]\033[0m"
        else:
            badge = "\033[1;33m[PATH]\033[0m"

        # Status indicator
        if ref.status == "found":
            status = "\033[1;32m✓\033[0m"
        elif ref.status == "missing":
            status = "\033[1;31m✗\033[0m"
        else:
            status = "\033[1;34m→\033[0m"

        lines.append(f"  {idx}. {badge} {status}")
        lines.append(f"      Original: {ref.original}")
        if ref.resolved_path:
            lines.append(f"      Path: {ref.resolved_path}")
        lines.append(f"      Source: {ref.source_file}:{ref.line_number}")
        lines.append("")

    lines.append("\033[90m" + "─" * 60 + "\033[0m")
    lines.append("Options:")
    lines.append("  s - Skip this reference")
    lines.append("  p - Provide a path to include")
    lines.append("  r - Read the content and summarize")
    lines.append("  a - Skip all remaining references")
    lines.append("")
    lines.append("Enter choice (s/p/r/a): ")

    return "\n".join(lines)


def render_resolution_screen(refs: list[Ref]) -> str:
    """Render the resolution screen for references.

    Args:
        refs: List of references to resolve.

    Returns:
        A string representation of the resolution UI.
    """
    from src.resolver.ref_resolver import format_placeholder

    lines = []
    lines.append("\033[1;37;44m" + " Reference Resolution ".center(60) + "\033[0m")
    lines.append("")
    lines.append("The following references were detected in your document:")
    lines.append("")

    for idx, ref in enumerate(refs, start=1):
        # Type badge with color
        if ref.type == "image":
            badge = "\033[1;32m[image]\033[0m"
        elif ref.type == "url":
            badge = "\033[1;34m[url]\033[0m"
        else:
            badge = "\033[1;33m[path]\033[0m"

        # Status indicator
        if ref.status == "found":
            status = "\033[1;32m✓ found\033[0m"
        elif ref.status == "missing":
            status = "\033[1;31m✗ missing\033[0m"
        else:
            status = "\033[1;36m→ external\033[0m"

        placeholder = format_placeholder(ref)
        lines.append(f"  {idx}. {badge} {status}")
        lines.append(f"     Original: {ref.original}")
        lines.append(f"     Placeholder: {placeholder}")
        lines.append("")

    lines.append("\033[1;37mActions:\033[0m")
    lines.append("  [s] Skip this reference (use placeholder)")
    lines.append("  [p] Provide path to actual content")
    lines.append("  [r] Read and summarize content")
    lines.append("")
    lines.append("  After making choices above:")
    lines.append("  [a] Skip all remaining references")
    lines.append("")

    return "\n".join(lines)
