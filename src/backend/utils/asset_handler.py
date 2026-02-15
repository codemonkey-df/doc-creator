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


def insert_placeholder(
    session_path: Path,
    image_identifier: str,
    target_file: str,
) -> str:
    """
    Replace image markdown with canonical placeholder for missing images.

    AC3.4.3: When user skips a missing image, insert canonical placeholder
    `**[Image Missing: {basename}]**` in the target file to allow document
    generation to continue.

    AC3.4.2: Placeholders applied to input files (so agent never sees broken ref).
    Supports temp_output.md for error-pipeline use.

    Args:
        session_path: Path to session root
        image_identifier: Original path as in markdown (e.g., "image.png" or "path/to/image.png")
        target_file: Relative path from session (e.g., "inputs/doc.md" or "temp_output.md")

    Returns:
        Confirmation message

    Raises:
        OSError: If target_file not found or permission denied
        UnicodeDecodeError: If file not UTF-8
    """
    file_path = session_path / target_file

    if not file_path.exists():
        logger.error(
            "Target file not found for placeholder insertion: %s",
            target_file,
        )
        raise OSError(f"Target file not found: {target_file}")

    try:
        # Read target file with UTF-8 encoding, detect line endings
        file_bytes = file_path.read_bytes()
        has_crlf = b"\r\n" in file_bytes

        content = file_bytes.decode("utf-8")

        # Extract basename for placeholder
        basename = Path(image_identifier).name

        # Find and replace markdown image ref matching image_identifier
        # Pattern: ![anything](image_identifier)
        # Escape special regex chars in image_identifier
        escaped_id = re.escape(image_identifier)
        pattern = rf"!\[([^\]]*)\]\(\s*{escaped_id}\s*\)"

        new_content = re.sub(pattern, f"**[Image Missing: {basename}]**", content)

        if new_content == content:
            logger.warning(
                "No matching image ref found for placeholder: %s in %s",
                image_identifier,
                target_file,
            )
        else:
            # Write back in-place with UTF-8, preserving line endings
            if has_crlf:
                # Normalize to LF first, then convert back to CRLF
                content_lf = new_content.replace("\r\n", "\n")
                content_crlf = content_lf.replace("\n", "\r\n")
                file_path.write_bytes(content_crlf.encode("utf-8"))
            else:
                # Write as-is (already LF or no line ending normalization)
                file_path.write_text(new_content, encoding="utf-8")

        logger.info(
            "Placeholder inserted for %s in %s",
            image_identifier,
            target_file,
        )

        return f"Placeholder inserted for {image_identifier} in {target_file}"

    except UnicodeDecodeError:
        logger.error(
            "Failed to read/write file (encoding error): %s",
            target_file,
            exc_info=True,
        )
        raise


def handle_upload_decision(
    session_path: Path,
    upload_path: str,
    image_identifier: str,
    source_file: str,
    allowed_base_path: Path | None = None,
) -> str:
    """
    Validate uploaded file, copy to assets, update ref in source_file.

    AC3.4.6: Upload path must be validated (no path escape). User-provided
    files are copied to session assets/ and refs are updated to point to
    session-local paths.

    AC3.4.4: Returns path for markdown ref so downstream can use it.

    Args:
        session_path: Session root
        upload_path: Absolute path to uploaded file (from caller)
        image_identifier: Original path in markdown (e.g., "missing.png")
        source_file: Input file containing ref (relative to session, e.g., "inputs/doc.md")
        allowed_base_path: Optional base for path validation (if None, only basic checks)

    Returns:
        Confirmation message with relative path for markdown

    Raises:
        ValueError: If upload_path outside allowed base, is directory, or invalid
        OSError: If file not readable or source_file not found
    """
    try:
        # Validate upload_path
        upload_full_path = Path(upload_path).resolve()

        # Check if path is a directory
        if upload_full_path.is_dir():
            raise ValueError(f"Upload path must be a file, not directory: {upload_path}")

        # Check if path exists and is readable
        if not upload_full_path.exists():
            raise ValueError(f"Upload file not found: {upload_path}")

        if not upload_full_path.is_file():
            raise ValueError(f"Upload path is not a regular file: {upload_path}")

        # Validate against allowed_base_path if provided
        if allowed_base_path:
            allowed_base = allowed_base_path.resolve()
            try:
                # Check if upload path is relative to allowed base
                upload_full_path.relative_to(allowed_base)
            except ValueError:
                logger.error(
                    "Upload path outside allowed base: %s not under %s",
                    upload_full_path,
                    allowed_base,
                )
                raise ValueError(
                    "Upload path is outside allowed base directory"
                ) from None

        # Check file is readable
        if not upload_full_path.stat().st_mode & 0o400:
            raise ValueError(f"Upload file is not readable: {upload_path}")

        # Step 1: Copy file to session assets/
        assets_dir = session_path / "assets"
        basename = upload_full_path.name
        dest_path = assets_dir / basename

        if dest_path.exists():
            logger.info(
                "Overwriting existing asset: %s",
                basename,
            )

        shutil.copy2(upload_full_path, dest_path)
        logger.info(
            "Uploaded file copied to assets: %s → assets/%s",
            upload_full_path,
            basename,
        )

        # Step 2: Update markdown ref in source_file
        input_file_path = session_path / source_file

        if not input_file_path.exists():
            raise OSError(f"Source file not found for ref update: {source_file}")

        # Read input file
        content = input_file_path.read_text(encoding="utf-8")

        # Rewrite ref using existing helper (reuses line ending preservation logic)
        new_content = rewrite_refs_in_content(content, image_identifier, basename)

        # Write back in-place (preserving encoding)
        input_file_path.write_text(new_content, encoding="utf-8")

        logger.info(
            "Markdown ref updated in %s: %s → ./assets/%s",
            source_file,
            image_identifier,
            basename,
        )

        return f"Uploaded file copied to assets/{basename}"

    except (OSError, ValueError) as e:
        logger.error(
            "Failed to handle upload decision for %s: %s",
            image_identifier,
            e,
            exc_info=True,
        )
        raise
