"""Session-scoped tools for the document generation agent (Story 2.2).

All paths are under SessionManager.get_path(session_id). Session ID is injected
via get_tools(session_id) so tools never accept session_id from the agent.
Path validation rejects /, \\, and .. in filename, label, and checkpoint_id.
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool

if TYPE_CHECKING:
    from backend.utils.session_manager import SessionManager

# Imports for copy_image (Story 3.3)
from backend.utils.image_scanner import resolve_image_path
from backend.utils.settings import AssetScanSettings

# Import shared checkpoint helper (Story 4.4)
from backend.utils.checkpoint import restore_from_checkpoint

logger = logging.getLogger(__name__)

TEMP_OUTPUT_FILENAME = "temp_output.md"
CHECKPOINTS_DIR = "checkpoints"
INPUTS_DIR = "inputs"


def _session_path(
    session_id: str,
    session_manager: SessionManager | None = None,
) -> Path:
    """Return session root path. Uses SessionManager.get_path(session_id)."""
    from backend.utils.session_manager import SessionManager

    sm = session_manager if session_manager is not None else SessionManager()
    return sm.get_path(session_id)


def _validate_filename(filename: str) -> None:
    """Reject empty or path-unsafe filename. Raises ValueError with clear message.

    AC2.2.3: filename must not contain /, \\, or .. (path traversal).
    """
    if not filename or not filename.strip():
        raise ValueError("Filename must not be empty")
    if "/" in filename or "\\" in filename:
        raise ValueError("Filename must not contain path separators (/, \\)")
    if ".." in filename:
        raise ValueError("Filename must not contain '..' (path traversal)")


def _validate_label(label: str) -> str:
    """Validate and sanitize label to safe chars (alphanumeric + underscore). Raises ValueError if empty or invalid."""
    if not label or not label.strip():
        raise ValueError("Label must not be empty")
    if "/" in label or "\\" in label or ".." in label:
        raise ValueError("Label must not contain path separators or '..'")
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", label.strip())
    if not sanitized:
        raise ValueError("Label must contain at least one alphanumeric or underscore")
    return sanitized


def _validate_checkpoint_id(checkpoint_id: str, session_path: Path) -> Path:
    """Require checkpoint_id as basename only; resolve under session and assert no escape. Raises ValueError."""
    cid = checkpoint_id.strip() if checkpoint_id else ""
    if not cid:
        raise ValueError("Checkpoint ID must not be empty")
    if "/" in cid or "\\" in cid:
        raise ValueError("Checkpoint ID must be a basename (no path separators)")
    if ".." in cid:
        raise ValueError("Checkpoint ID must not contain '..'")
    checkpoints_dir = session_path / CHECKPOINTS_DIR
    resolved = (checkpoints_dir / cid).resolve()
    session_resolved = session_path.resolve()
    if not resolved.is_relative_to(session_resolved):
        raise ValueError("Checkpoint path must be under session directory")
    return resolved


def list_files(
    session_id: str,
    session_manager: SessionManager | None = None,
) -> list[str]:
    """List filenames in the session input directory (FC007). No directory argument from agent.

    Returns:
        List of filenames in session inputs/ valid for processing.
    """
    session_path = _session_path(session_id, session_manager)
    inputs_dir = session_path / INPUTS_DIR
    if not inputs_dir.is_dir():
        return []
    names = sorted(f.name for f in inputs_dir.iterdir() if f.is_file())
    return names


def read_file(
    filename: str,
    session_id: str,
    session_manager: SessionManager | None = None,
) -> str:
    """Read session input file as UTF-8 (FC001). Filename must not contain /, \\, or .."""
    _validate_filename(filename)
    session_path = _session_path(session_id, session_manager)
    file_path = session_path / INPUTS_DIR / filename
    try:
        return file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("File not found: %s", file_path)
        raise
    except UnicodeDecodeError as e:
        logger.warning("Invalid UTF-8 in %s: %s", file_path, e)
        raise ValueError(f"File is not valid UTF-8: {filename}") from e


def read_generated_file(
    lines: int,
    session_id: str,
    session_manager: SessionManager | None = None,
) -> str:
    """Return last N lines of session temp_output.md (FC003). Returns empty string if file does not exist."""
    session_path = _session_path(session_id, session_manager)
    temp_path = session_path / TEMP_OUTPUT_FILENAME
    if not temp_path.exists():
        return ""
    if lines <= 0:
        return ""
    content = temp_path.read_text(encoding="utf-8")
    all_lines = content.splitlines()
    last_n = all_lines[-lines:]
    return "\n".join(last_n)


def append_to_markdown(
    content: str,
    session_id: str,
    session_manager: SessionManager | None = None,
) -> str:
    """Append content and newlines to session temp_output.md; create file if missing (FC002, FC004)."""
    session_path = _session_path(session_id, session_manager)
    temp_path = session_path / TEMP_OUTPUT_FILENAME
    with temp_path.open("a", encoding="utf-8") as f:
        f.write(content)
        f.write("\n\n")
    return f"Appended {len(content)} characters"


def edit_markdown_line(
    line_number: int,
    new_content: str,
    session_id: str,
    session_manager: SessionManager | None = None,
) -> str:
    """Replace line at 1-based index in temp_output.md (FC005). Validates line_number in range.

    new_content is the exact line replacement; no newline is added automatically.
    """
    session_path = _session_path(session_id, session_manager)
    temp_path = session_path / TEMP_OUTPUT_FILENAME
    if not temp_path.exists():
        raise FileNotFoundError("temp_output.md does not exist")
    lines_list = temp_path.read_text(encoding="utf-8").splitlines()
    if line_number < 1 or line_number > len(lines_list):
        raise ValueError(
            f"line_number must be between 1 and {len(lines_list)} (got {line_number})"
        )
    lines_list[line_number - 1] = new_content
    temp_path.write_text("\n".join(lines_list), encoding="utf-8")
    return f"Updated line {line_number}"


def create_checkpoint(
    label: str,
    session_id: str,
    session_manager: SessionManager | None = None,
) -> str:
    """Copy temp_output.md to checkpoints/{timestamp}_{label}.md (FC009). Returns checkpoint_id (basename)."""
    sanitized_label = _validate_label(label)
    session_path = _session_path(session_id, session_manager)
    temp_path = session_path / TEMP_OUTPUT_FILENAME
    if not temp_path.exists():
        raise FileNotFoundError(
            "temp_output.md does not exist; create content before checkpointing"
        )
    checkpoints_dir = session_path / CHECKPOINTS_DIR
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = f"{timestamp}_{sanitized_label}.md"
    dest_path = checkpoints_dir / basename
    shutil.copy2(temp_path, dest_path)
    logger.info("Checkpoint created: %s", basename)
    return basename


def rollback_to_checkpoint(
    checkpoint_id: str,
    session_id: str,
    session_manager: SessionManager | None = None,
) -> str:
    """Copy checkpoint file back to temp_output.md (FC009). checkpoint_id must be basename only.

    Uses shared restore_from_checkpoint helper (Story 4.4).
    Raises ValueError for invalid checkpoint_id, FileNotFoundError for missing file.
    """
    # Validate checkpoint_id first to preserve original ValueError behavior
    from backend.utils.checkpoint import _validate_checkpoint_id, _session_path

    session_path = _session_path(session_id, session_manager)
    try:
        _validate_checkpoint_id(checkpoint_id, session_path)
    except ValueError:
        raise

    # Now attempt restoration
    success = restore_from_checkpoint(session_id, checkpoint_id, session_manager)
    if not success:
        raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_id}")
    return f"Restored from checkpoint {checkpoint_id}"


def request_human_input(
    question: str,
    session_id: str,
    session_manager: SessionManager | None = None,
) -> str:
    """Signal that the agent needs user input (FC006). Returns the question string.

    When this tool is called, the tools node (Story 2.5) can set state['pending_question']
    from the return value so the graph routes to human_input. Use when you encounter
    a missing external file reference or need the user to upload/skip.
    """
    if not question or not str(question).strip():
        return "Please provide user input or skip."
    return str(question).strip()


def copy_image(
    source_path: str,
    session_id: str,
    session_manager: SessionManager | None = None,
) -> str:
    """Copy image to session assets/ and return relative path (Story 3.3, FC014).

    Resolves relative paths from session inputs/, validates absolute paths against allowed base.
    Returns a relative path string (e.g. "./assets/filename.png") on success.
    If source file does not exist or path is invalid, returns canonical placeholder
    "**[Image Missing: {basename}]**" so agent can insert it. No exception raised.

    Path validation:
    - Relative paths: resolved to session inputs/ directory
    - Absolute paths: validated against allowed_base_path (defaults to inputs dir)
    - URLs (http://, https://): skipped (returns placeholder)
    - Path traversal (.., path separators): rejected (returns placeholder)

    Args:
        source_path: Path to image file (relative to session inputs/ or absolute)
        session_id: Session ID (injected, not from agent)
        session_manager: SessionManager instance (optional, defaults to singleton)

    Returns:
        ./assets/{basename} on success, or **[Image Missing: {basename}]** if invalid
    """
    try:
        session_path = _session_path(session_id, session_manager)
        inputs_dir = session_path / INPUTS_DIR

        # Get allowed base path configuration (defaults to inputs dir)
        settings = AssetScanSettings()
        allowed_base = (
            settings.allowed_base_path if settings.allowed_base_path else inputs_dir
        )

        # Resolve path using same rules as scan_assets (Story 3.1)
        resolved = resolve_image_path(source_path, inputs_dir, allowed_base)

        # If resolution failed (invalid/missing/URL), return placeholder
        if resolved is None:
            basename = Path(source_path).name or "image"
            return f"**[Image Missing: {basename}]**"

        # If file doesn't exist, return placeholder
        if not resolved.exists():
            basename = resolved.name
            return f"**[Image Missing: {basename}]**"

        # File exists and is valid: copy to assets/
        assets_dir = session_path / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        basename = resolved.name
        dest_path = assets_dir / basename

        try:
            shutil.copy2(resolved, dest_path)
            logger.info("Image copied to assets: %s -> %s", source_path, basename)
            return f"./assets/{basename}"
        except (OSError, IOError) as e:
            logger.warning("Failed to copy image %s: %s", source_path, e)
            # On copy failure, return placeholder
            return f"**[Image Missing: {basename}]**"

    except Exception as e:
        # Catch-all: return placeholder for any unexpected error
        logger.error(
            "Unexpected error in copy_image(%s, %s): %s",
            source_path,
            session_id,
            e,
        )
        basename = Path(source_path).name or "image"
        return f"**[Image Missing: {basename}]**"


def get_tools(
    session_id: str,
    session_manager: SessionManager | None = None,
) -> list[StructuredTool]:
    """Return LangChain tools bound to session_id. Tool Node uses get_tools(state['session_id']).

    Tools never accept session_id from the agent; it is injected here.
    """
    sm = session_manager

    def _list_files() -> list[str]:
        return list_files(session_id, session_manager=sm)

    def _read_file(filename: str) -> str:
        return read_file(filename, session_id, session_manager=sm)

    def _read_generated_file(lines: int) -> str:
        return read_generated_file(lines, session_id, session_manager=sm)

    def _append_to_markdown(content: str) -> str:
        return append_to_markdown(content, session_id, session_manager=sm)

    def _edit_markdown_line(line_number: int, new_content: str) -> str:
        return edit_markdown_line(
            line_number, new_content, session_id, session_manager=sm
        )

    def _create_checkpoint(label: str) -> str:
        return create_checkpoint(label, session_id, session_manager=sm)

    def _rollback_to_checkpoint(checkpoint_id: str) -> str:
        return rollback_to_checkpoint(checkpoint_id, session_id, session_manager=sm)

    def _request_human_input(question: str) -> str:
        return request_human_input(question, session_id, session_manager=sm)

    def _copy_image(source_path: str) -> str:
        return copy_image(source_path, session_id, session_manager=sm)

    return [
        StructuredTool.from_function(
            func=_list_files,
            name="list_files",
            description="List filenames in the session input directory (FC007). Use to see which source files are available for processing. Returns only filenames in inputs/.",
        ),
        StructuredTool.from_function(
            func=_read_file,
            name="read_file",
            description="Read a source file from the session inputs directory as UTF-8 (FC001). Pass the filename only (e.g. from list_files). Use to get content of .txt, .log, .md files.",
        ),
        StructuredTool.from_function(
            func=_read_generated_file,
            name="read_generated_file",
            description="Read the last N lines of the current generated markdown (temp_output.md) (FC003). Use to see what has already been written before appending. Returns empty string if file does not exist.",
        ),
        StructuredTool.from_function(
            func=_append_to_markdown,
            name="append_to_markdown",
            description="Append content to the session temp markdown file (FC002, FC004). Creates the file if missing. Use to add new chapters, sections, and content. Preserve code/logs in fenced blocks.",
        ),
        StructuredTool.from_function(
            func=_edit_markdown_line,
            name="edit_markdown_line",
            description="Replace a single line in temp_output.md by 1-based line number (FC005). Use for granular fixes. line_number must be between 1 and the number of lines.",
        ),
        StructuredTool.from_function(
            func=_create_checkpoint,
            name="create_checkpoint",
            description="Save a snapshot of temp_output.md to checkpoints (FC009). Pass a short label (e.g. chapter1). Returns checkpoint_id for rollback. Call after each major section.",
        ),
        StructuredTool.from_function(
            func=_rollback_to_checkpoint,
            name="rollback_to_checkpoint",
            description="Restore temp_output.md from a checkpoint (FC009). Pass the checkpoint_id returned by create_checkpoint (basename only).",
        ),
        StructuredTool.from_function(
            func=_request_human_input,
            name="request_human_input",
            description="Ask the user for input (FC006). Call when you find a missing external file reference or need the user to upload/skip. Pass the question to show the user. The workflow will pause for human input.",
        ),
        StructuredTool.from_function(
            func=_copy_image,
            name="copy_image",
            description=(
                "Copy image to session assets/ and return relative path (FC014). "
                "Resolves relative paths from inputs/. Returns ./assets/{name} on "
                "success, or **[Image Missing: {name}]** if missing/invalid."
            ),
        ),
    ]
