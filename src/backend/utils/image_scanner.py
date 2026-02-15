"""
Image reference scanner for markdown documents (Story 3.1: Asset Scan Node).

Provides utilities for:
- Extracting markdown image references: ![alt](path)
- URL detection and classification
- Path resolution (relative/absolute) with security validation
- File existence checking
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Image reference regex pattern
# Matches: ![anything](path) or ![anything](path "title")
# Captures: full content between parens (path with optional title)
# Title is stripped in extract_image_refs
IMAGE_REF_PATTERN = re.compile(
    r"!\[(?:[^\[\]]|\[.*?\])*\]"  # ![...] with nested bracket support
    r"\("  # opening (
    r"([^)]+)"  # capture full content between ( and )
    r"\)",  # closing )
    re.MULTILINE | re.DOTALL,
)


def extract_image_refs(content: str) -> list[str]:
    """
    Extract markdown image reference paths from content.

    Supports:
    - Basic syntax: ![alt](path)
    - With title: ![alt](path "title")
    - Nested brackets in alt: ![alt with [brackets]](path)
    - Spaces in path: ![alt](path with spaces.png)

    Args:
        content: Markdown content to scan

    Returns:
        List of extracted paths (title stripped, if present)

    Example:
        >>> extract_image_refs('![alt](./image.png)')
        ['./image.png']

        >>> extract_image_refs('![alt](path.png "Title")')
        ['path.png']
    """
    if not content:
        return []

    matches = IMAGE_REF_PATTERN.findall(content)
    # Strip optional title if present in captured group
    # Format: "path" or "path \"title\"" or "path 'title'"
    cleaned = []
    for match in matches:
        if not match:
            continue
        # Split on space followed by quote to separate path from title
        # Look for pattern: space + quote
        path = match.strip()
        # Find first space-quote combination
        for quote in ['"', "'"]:
            space_quote = f" {quote}"
            if space_quote in path:
                path = path.split(space_quote)[0]
                break
        path = path.strip()
        if path:
            cleaned.append(path)

    logger.debug(f"Extracted {len(cleaned)} image refs from content")
    return cleaned


def is_url(path: str) -> bool:
    """
    Check if path is a URL (http:// or https://).

    Args:
        path: Path string to check

    Returns:
        True if path starts with http:// or https://, False otherwise

    Example:
        >>> is_url("https://example.com/image.png")
        True

        >>> is_url("./image.png")
        False
    """
    if not path:
        return False
    return path.startswith("https://") or path.startswith("http://")


def resolve_image_path(
    path: str,
    input_file_dir: Path,
    allowed_base_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    Resolve image path with security validation.

    Resolution strategy:
    1. URL (http:// or https://): Return None (skip, no local copy needed)
    2. Relative path (no leading /): Resolve relative to input_file_dir
    3. Absolute path (leading /): Validate under allowed_base_path (if set)

    Security:
    - Relative paths cannot escape input_file_dir + allowed_base_path
    - Absolute paths must be under allowed_base_path (if set)
    - Symlinks pointing outside base are rejected
    - Returns None for invalid/escaped paths

    Args:
        path: Image path from markdown (original, unresolved)
        input_file_dir: Directory containing the markdown file
                       (used as base for relative paths)
        allowed_base_path: Allowed base for absolute paths.
                          If None, any absolute path under filesystem is allowed.
                          Should typically be session inputs or parent directory.

    Returns:
        Resolved absolute Path if file exists and passes security checks,
        None if URL, missing, or security violation

    Example:
        >>> resolve_image_path("./image.png", Path("/session/inputs"), None)
        Path('/session/inputs/image.png')  # if file exists

        >>> resolve_image_path("https://example.com/image.png", ...)
        None  # URLs return None

        >>> resolve_image_path("../../etc/passwd", Path("/session/inputs"), Path("/session"))
        None  # escapes base
    """
    if not path:
        return None

    try:
        # Step 1: Check if URL
        if is_url(path):
            logger.debug(f"Skipping URL: {path}")
            return None

        # Step 2: Resolve path
        path_obj = Path(path)

        if path_obj.is_absolute():
            # Absolute path: validate against allowed_base_path
            resolved = path_obj.resolve()
        else:
            # Relative path: resolve relative to input_file_dir
            resolved = (input_file_dir / path_obj).resolve()

        # Step 3: Security check - must not escape allowed base
        if allowed_base_path:
            allowed_resolved = allowed_base_path.resolve()
            try:
                # Check if resolved path is under allowed base
                resolved.relative_to(allowed_resolved)
            except ValueError:
                # Path is outside allowed base
                logger.warning(
                    f"Path escapes allowed base: {path} → {resolved} "
                    f"(allowed: {allowed_resolved})"
                )
                return None

        # Step 4: Check existence
        if not resolved.exists():
            logger.debug(f"Image file not found: {resolved}")
            return None

        # Step 5: Security check - symlink must not escape base
        if resolved.is_symlink():
            target = resolved.resolve()
            if allowed_base_path:
                allowed_resolved = allowed_base_path.resolve()
                try:
                    target.relative_to(allowed_resolved)
                except ValueError:
                    logger.warning(
                        f"Symlink target escapes allowed base: {resolved} → {target}"
                    )
                    return None

        logger.debug(f"Resolved image path: {path} → {resolved}")
        return resolved

    except (TypeError, OSError, RuntimeError) as e:
        logger.warning(f"Error resolving image path {path}: {e}")
        return None
