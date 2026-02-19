"""Reference resolver module for handling image, URL, and path references."""

import shutil
from pathlib import Path

from src.config import LlmConfig
from src.llm.client import call_llm
from src.llm.generator import ResolvedContext
from src.llm.prompts import prompt_summarize_external
from src.scanner.ref_scanner import Ref
from src.tui.state import AppState


def format_placeholder(ref: Ref) -> str:
    """Format a reference as a placeholder string.

    Args:
        ref: The reference to format.

    Returns:
        A placeholder string in the format [Type: value].
    """
    if ref.type == "image":
        # Extract filename from the original match
        # Original format: ![alt](filename)
        path = ref.original.split("](")[1].rstrip(")")
        return f"[Image: {path}]"
    elif ref.type == "url":
        return f"[External URL: {ref.original}]"
    elif ref.type == "path":
        # Extract path from the original match
        # Original format: [text](path)
        path = ref.original.split("](")[1].rstrip(")")
        return f"[External Path: {path}]"
    else:
        return f"[Unknown: {ref.original}]"


def provide_path(ref: Ref, input_dir: Path, file_path: str) -> tuple[Ref, bool]:
    """Copy a file to input directory and update reference status.

    Args:
        ref: The reference to provide.
        input_dir: The input directory to copy the file to.
        file_path: The path to the file to copy.

    Returns:
        A tuple of (updated_ref, success). If success is False, the ref
        status will be set to "error" with error information.
    """
    source = Path(file_path)

    if not source.exists():
        # Return error indicator
        error_ref = Ref(
            type=ref.type,
            original=ref.original,
            resolved_path=source,
            status="error",
            source_file=ref.source_file,
            line_number=ref.line_number,
        )
        return (error_ref, False)

    # Ensure input_dir exists
    input_dir.mkdir(parents=True, exist_ok=True)

    # Copy file to input directory
    dest = input_dir / source.name
    shutil.copy2(source, dest)

    # Update ref with new path and status
    updated_ref = Ref(
        type=ref.type,
        original=ref.original,
        resolved_path=dest,
        status="provided",
        source_file=ref.source_file,
        line_number=ref.line_number,
    )

    return (updated_ref, True)


def summarize_ref(ref: Ref, config: LlmConfig) -> tuple[str, str]:
    """Read a file, generate summary via LLM, return (file_path, summary).

    Args:
        ref: The reference to summarize.
        config: The LLM configuration.

    Returns:
        A tuple of (file_path, summary). Raises ValueError for URL refs.

    Raises:
        ValueError: If the reference is a URL (cannot summarize URLs).
    """
    if ref.type == "url":
        raise ValueError("Cannot summarize URL references")

    if ref.resolved_path is None:
        raise ValueError("Reference has no resolved path")

    # Read file content
    try:
        content = ref.resolved_path.read_text(encoding="utf-8")
    except (OSError, IOError) as e:
        raise ValueError(f"Cannot read file: {e}") from e

    # Extract chapter context from source file name
    context = ref.source_file.stem if ref.source_file else "general"

    # Generate summary via LLM
    system, user = prompt_summarize_external(content, context)
    summary = call_llm(system, user, config)

    return (str(ref.resolved_path), summary)


def resolve_refs(
    refs: list[Ref],
    state: AppState,
    provided_refs: list[Ref] | None = None,
    summarized_refs: list[tuple[str, str]] | None = None,
) -> ResolvedContext:
    """Resolve references to content.

    This implementation handles provided (copied) and summarized refs,
    and skips all others by default.

    Args:
        refs: List of references to resolve.
        state: The application state.
        provided_refs: Optional list of refs that have been provided (copied).
        summarized_refs: Optional list of (file_path, summary) tuples.

    Returns:
        ResolvedContext with provided, summarized, and skipped references.
    """
    # Early return if no refs to resolve
    if not refs:
        return ResolvedContext()

    # Initialize with empty lists if not provided
    if provided_refs is None:
        provided_refs = []
    if summarized_refs is None:
        summarized_refs = []

    # Get the set of original strings for provided refs
    provided_originals = {ref.original for ref in provided_refs}
    summarized_paths = {path for path, _ in summarized_refs}

    # Categorize refs: skip those not in provided or summarized
    skipped = []
    for ref in refs:
        # Check if this ref was provided
        if ref.original in provided_originals:
            continue
        # Check if this ref was summarized
        if ref.resolved_path and str(ref.resolved_path) in summarized_paths:
            continue
        # Otherwise skip
        skipped.append(ref)

    return ResolvedContext(
        skipped=skipped,
        provided=provided_refs,
        to_summarize=summarized_refs,
    )
