"""Command parsing and handlers for DocForge TUI."""

import logging
import shlex
from dataclasses import dataclass

from src.pipeline.pipeline import run_pipeline_in_background
from src.tui.state import AppState, ChapterEntry

logger = logging.getLogger(__name__)

# ── Autocomplete metadata (used by the popup in panels.py) ────────────────
COMMAND_DESCRIPTIONS: dict[str, str] = {
    "title":    "Set document title",
    "intro":    "Set intro file by ID",
    "chapter":  "Add chapter by ID",
    "remove":   "Remove chapter by index",
    "reset":    "Clear intro & chapters",
    "generate": "Generate the document",
    "help":     "Show all commands",
    "quit":     "Exit DocForge",
}


@dataclass
class Command:
    """Represents a parsed command."""

    name: str
    args: list[str]


def parse_command(raw: str) -> Command | None:
    """Parse a raw command string into a Command object.

    Handles:
    - Quoted arguments: /title "My Doc" -> args: ["My Doc"]
    - Unquoted arguments: /intro 1 -> args: ["1"]

    Returns None for unknown commands or parse errors.
    """
    raw = raw.strip()
    if not raw or not raw.startswith("/"):
        return None

    try:
        parts = shlex.split(raw)
    except ValueError:
        return None

    if not parts:
        return None

    name = parts[0].lstrip("/")
    args = parts[1:] if len(parts) > 1 else []

    if name not in COMMAND_DESCRIPTIONS:
        return None

    return Command(name=name, args=args)


def handle_title(state: AppState, args: list[str]) -> None:
    """Set the document title."""
    if not args:
        state.log_lines.append("Usage: /title <title>")
        return
    title = " ".join(args)
    state.title = title
    state.log_lines.append(f"Title set to: {title}")
    logger.info("title_set", extra={"title": title})


def handle_intro(state: AppState, args: list[str]) -> None:
    """Set the intro file by numeric ID."""
    if not args:
        state.log_lines.append("Usage: /intro <id>")
        return
    try:
        idx = int(args[0]) - 1
        if idx < 0 or idx >= len(state.detected_files):
            state.log_lines.append(f"Invalid ID: {args[0]}")
            return
        filename = state.detected_files[idx]
        state.intro_file = filename
        state.log_lines.append(f"Intro set to: {filename}")
        logger.info("intro_set", extra={"filename": filename})
    except ValueError:
        state.log_lines.append(f"Invalid ID: {args[0]}")


def handle_chapter(state: AppState, args: list[str]) -> None:
    """Add a chapter by numeric ID, optionally with a custom title."""
    if not args:
        state.log_lines.append("Usage: /chapter <id> [title]")
        return
    try:
        idx = int(args[0]) - 1
        if idx < 0 or idx >= len(state.detected_files):
            state.log_lines.append(f"Invalid ID: {args[0]}")
            return
        filename = state.detected_files[idx]
        custom_title = " ".join(args[1:]) if len(args) > 1 else None
        chapter = ChapterEntry(file_path=filename, custom_title=custom_title)
        state.chapters.append(chapter)
        if custom_title:
            state.log_lines.append(f"Added chapter: {filename} (title: {custom_title})")
        else:
            state.log_lines.append(f"Added chapter: {filename}")
        logger.info("chapter_added", extra={"filename": filename, "custom_title": custom_title})
    except ValueError:
        state.log_lines.append(f"Invalid ID: {args[0]}")


def handle_remove(state: AppState, args: list[str]) -> None:
    """Remove a chapter by 1-based index."""
    if not args:
        state.log_lines.append("Usage: /remove <index>")
        return
    try:
        idx = int(args[0]) - 1
        if idx < 0 or idx >= len(state.chapters):
            state.log_lines.append(f"Invalid index: {args[0]}")
            return
        removed = state.chapters.pop(idx)
        state.log_lines.append(f"Removed: {removed.file_path}")
        logger.info("chapter_removed", extra={"filename": removed.file_path})
    except ValueError:
        state.log_lines.append(f"Invalid index: {args[0]}")


def handle_reset(state: AppState) -> None:
    """Reset intro and chapters."""
    state.intro_file = None
    state.chapters.clear()
    state.log_lines.append("Reset: intro and chapters cleared")
    logger.info("state_reset")


def handle_help(state: AppState) -> None:
    """Display help text."""
    state.log_lines.append("─── Commands ───────────────────────────────")
    for cmd, desc in COMMAND_DESCRIPTIONS.items():
        state.log_lines.append(f"  /{cmd:<10} {desc}")
    state.log_lines.append("────────────────────────────────────────────")
    logger.info("help_displayed")


def handle_generate(state: AppState) -> None:
    """Generate the document from the outline."""
    state.log_lines.append("Starting generation in background…")
    logger.info("document_generation_started", extra={"title": state.title})
    run_pipeline_in_background(state)


def handle_quit(state: AppState, running_ref: list[bool]) -> None:
    """Quit the application."""
    running_ref[0] = False
    state.log_lines.append("Goodbye!")
    logger.info("quit")