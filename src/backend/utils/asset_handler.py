"""
Asset handler for Story 3.2: Copy found images to session assets/ and rewrite refs.

This module provides utilities for:
- Copying images from resolved paths to session assets/ directory
- Rewriting markdown image references to use session-local paths (./assets/basename)
- Handling collisions (last copy wins)
- Preserving file encodings and line endings
- Logging all operations
"""

import logging
import re
import shutil
from pathlib import Path

from backend.state import ImageRefResult

logger = logging.getLogger(__name__)


# Regex pattern to match markdown image syntax: ![alt text](path)
# Captures the path part for replacement
IMAGE_MARKDOWN_PATTERN = re.compile(
    r"(!\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])"  # ![alt] part (handles nested brackets)
    r"\(\s*"  # opening (
    r"([^)]+)"  # captured path
    r"\s*\)",  # closing )
    re.MULTILINE,
)


def copy_found_images(
    session_path: Path,
    found_image_refs: list[ImageRefResult],
) -> dict[str, str]:
    """
    Copy found images to session assets/ directory.

    For each found ref, copies the file to session_path/assets/{basename}.
    If multiple refs resolve to the same basename, last copy wins (documented).

    AC3.2.1: Copy reads found_image_refs from state. Each entry has original_path,
    resolved_path, source_file. Destination filename is basename. Last copy wins
    on collisions.

    Args:
        session_path: Path to session root (contains assets/ subdirectory)
        found_image_refs: List of found image references from scan_assets

    Returns:
        Dict mapping original_path → basename for refs that were copied successfully
        (excluding nonexistent sources)
    """
    assets_dir = session_path / "assets"
    copy_results: dict[str, str] = {}

    if not found_image_refs:
        logger.debug("No found image refs to copy")
        return copy_results

    for ref in found_image_refs:
        original_path = ref["original_path"]
        resolved_path_str = ref["resolved_path"]
        source_file = ref["source_file"]

        try:
            resolved = Path(resolved_path_str)

            # Skip if source doesn't exist (shouldn't happen with story 3.1)
            if not resolved.exists():
                logger.warning(
                    "Skipping copy: resolved path does not exist: %s (from %s)",
                    resolved_path_str,
                    source_file,
                )
                continue

            # Get basename for destination
            basename = resolved.name
            dest = assets_dir / basename

            # Check for collision
            if dest.exists():
                logger.info(
                    "Image collision: overwriting %s (source: %s, from: %s)",
                    basename,
                    resolved_path_str,
                    source_file,
                )

            # Copy file
            shutil.copy2(resolved, dest)
            logger.debug(
                "Image copied: %s → assets/%s (from: %s)",
                resolved_path_str,
                basename,
                source_file,
            )

            # Track result
            copy_results[original_path] = basename

        except (OSError, TypeError) as e:
            logger.warning(
                "Failed to copy image %s (from: %s): %s",
                resolved_path_str,
                source_file,
                e,
                exc_info=True,
            )
            continue

    logger.info("Copied %d images to session assets/", len(copy_results))
    return copy_results


def rewrite_refs_in_content(
    content: str,
    original_path: str,
    basename: str,
) -> str:
    """
    Rewrite image reference paths in markdown content.

    AC3.2.2: Replace original_path with ./assets/basename within image syntax only.
    Preserves alt text exactly.

    Finds all markdown image syntax ![alt](path) and replaces the path part
    with ./assets/basename, but only if the path matches original_path exactly.

    Args:
        content: Markdown content to rewrite
        original_path: Original path to find (exact match, case-sensitive)
        basename: Basename to replace with (will be used as ./assets/{basename})

    Returns:
        Content with paths rewritten (or unchanged if no matches)
    """
    if not content:
        return content

    new_content = content
    replacement_count = 0

    # Find all image syntax matches
    for match in IMAGE_MARKDOWN_PATTERN.finditer(content):
        alt_part = match.group(1)  # ![alt text]
        path_part = match.group(2)  # path inside parens

        # Strip whitespace from captured path
        path_stripped = path_part.strip()

        # Handle optional title: "path \"title\"" or "path 'title'"
        # Extract just the path part if title is present
        path_only = path_stripped
        for quote in ['"', "'"]:
            space_quote = f" {quote}"
            if space_quote in path_only:
                path_only = path_only.split(space_quote)[0]
                break

        path_only = path_only.strip()

        # Check if this path matches our target (case-sensitive, exact)
        if path_only == original_path:
            # Build replacement: ![alt](./assets/basename)
            old_syntax = f"{alt_part}({path_stripped})"
            new_syntax = f"{alt_part}(./assets/{basename})"

            new_content = new_content.replace(old_syntax, new_syntax, 1)
            replacement_count += 1

            logger.debug(
                "Rewrote ref in content: %s → ./assets/%s",
                original_path,
                basename,
            )

    if replacement_count > 0:
        logger.debug(
            "Rewrote %d ref(s) for original_path=%s", replacement_count, original_path
        )

    return new_content


def rewrite_input_files(
    session_path: Path,
    found_image_refs: list[ImageRefResult],
    copy_results: dict[str, str],
) -> dict[str, int]:
    """
    Rewrite image references in input files.

    AC3.2.2: After copying, rewrite image syntax in input files. For each input file,
    apply rewrite for all refs found in that file, then write back in-place (UTF-8).

    AC3.2.6: Preserve UTF-8 encoding and line endings (CRLF/LF).

    Args:
        session_path: Path to session root
        found_image_refs: List of found image references (with source_file field)
        copy_results: Dict from copy_found_images (original_path → basename)

    Returns:
        Dict mapping source_file → count of refs rewritten
    """
    inputs_dir = session_path / "inputs"
    rewrite_results: dict[str, int] = {}

    if not found_image_refs or not copy_results:
        logger.debug("No refs to rewrite or no copy results")
        return rewrite_results

    # Group refs by source file
    refs_by_file: dict[str, list[ImageRefResult]] = {}
    for ref in found_image_refs:
        source_file = ref["source_file"]
        if source_file not in refs_by_file:
            refs_by_file[source_file] = []
        refs_by_file[source_file].append(ref)

    # Process each input file
    for source_file, refs_for_file in refs_by_file.items():
        file_path = inputs_dir / source_file

        if not file_path.exists():
            logger.warning("Input file not found, skipping rewrite: %s", source_file)
            continue

        try:
            # Read file (preserve original encoding)
            # We need to detect line endings before reading
            file_bytes = file_path.read_bytes()
            has_crlf = b"\r\n" in file_bytes

            # Read as UTF-8
            content = file_bytes.decode("utf-8")

            # Apply rewrites for each ref in this file
            rewrite_count = 0
            for ref in refs_for_file:
                original_path = ref["original_path"]

                # Check if this ref was actually copied
                if original_path not in copy_results:
                    logger.debug(
                        "Ref not in copy results, skipping rewrite: %s", original_path
                    )
                    continue

                basename = copy_results[original_path]

                # Rewrite refs in content
                new_content = rewrite_refs_in_content(content, original_path, basename)

                # Count rewrites (check for presence of new ref)
                if new_content != content:
                    asset_path = f"./assets/{basename}"
                    rewrite_count += new_content.count(asset_path) - content.count(
                        asset_path
                    )
                    content = new_content

            if rewrite_count == 0:
                logger.debug(
                    "No refs rewritten in %s (refs present but not in copy results)",
                    source_file,
                )
                continue

            # Write back with line ending preservation
            if has_crlf:
                # Normalize to LF first, then convert back to CRLF
                content_lf = content.replace("\r\n", "\n")
                content_crlf = content_lf.replace("\n", "\r\n")
                file_path.write_bytes(content_crlf.encode("utf-8"))
            else:
                # Write as-is (already LF or no line ending normalization)
                file_path.write_text(content, encoding="utf-8")

            rewrite_results[source_file] = rewrite_count
            logger.info("Rewrote %d ref(s) in %s", rewrite_count, source_file)

        except (OSError, UnicodeDecodeError) as e:
            logger.warning(
                "Failed to rewrite input file %s: %s",
                source_file,
                e,
                exc_info=True,
            )
            continue

    return rewrite_results


def apply_asset_scan_results(
    session_path: Path,
    found_image_refs: list[ImageRefResult],
) -> dict[str, object]:
    """
    Apply asset scan results: copy images and rewrite refs in input files.

    AC3.2.1-3.2.6: Orchestrates full workflow - copy found images to assets/,
    then rewrite refs in input files to use ./assets/basename paths.

    AC3.2.3: Deterministic and idempotent (same refs → same result).

    AC3.2.5: Can be called from scan_assets node after classification.

    Args:
        session_path: Path to session root
        found_image_refs: List of found image references from scan_assets

    Returns:
        Dict with operation summary:
        - copied: number of images copied
        - rewritten: total refs rewritten across all files
        - per_file: dict of source_file → rewrite count
        - copy_results: dict of original_path → basename
    """
    logger.info("Applying asset scan results for session")

    # Step 1: Copy images
    copy_results = copy_found_images(session_path, found_image_refs)

    # Step 2: Rewrite input files
    rewrite_results = rewrite_input_files(session_path, found_image_refs, copy_results)

    # Summarize
    total_rewritten = sum(rewrite_results.values())

    summary = {
        "copied": len(copy_results),
        "rewritten": total_rewritten,
        "per_file": rewrite_results,
        "copy_results": copy_results,
    }

    logger.info(
        "Asset scan results applied: copied=%d, rewritten=%d",
        len(copy_results),
        total_rewritten,
    )

    return summary
