"""Reference resolver module for handling image, URL, and path references."""

from pathlib import Path

from src.llm.generator import ResolvedContext
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


def resolve_refs(refs: list[Ref], state: AppState) -> ResolvedContext:
    """Resolve references to content.

    This implementation skips all references by default.
    Full interactive resolution will be implemented in EPIC 5.

    Args:
        refs: List of references to resolve.
        state: The application state.

    Returns:
        ResolvedContext with all references skipped.
    """
    # Early return if no refs to resolve
    if not refs:
        return ResolvedContext()

    return ResolvedContext(skipped=refs)
