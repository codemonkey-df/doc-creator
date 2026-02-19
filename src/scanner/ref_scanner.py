"""Reference scanner module for detecting image and path references in markdown files."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Ref:
    """Represents a reference found in a markdown file."""

    type: str  # "image" | "path" | "url"
    original: str  # The original matched string
    resolved_path: Optional[Path]  # Path object relative to source file's directory
    status: str  # "found" | "missing" | "external"
    source_file: Path  # Path to the file containing the reference
    line_number: int  # Line number where reference was found


# Regex patterns as specified
PATTERN_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
PATTERN_PATH = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)#\s]+)\)")
PATTERN_URL = re.compile(r"https?://[^\s\)\"<>]+")


def scan_file(path: Path) -> list[Ref]:
    """
    Scan a single file for image, path, and URL references.

    Args:
        path: Path to the markdown file to scan.

    Returns:
        List of Ref objects found in the file.
    """
    refs: list[Ref] = []

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, IOError):
        # Skip files that can't be read
        return refs

    source_dir = path.parent

    for line_number, line in enumerate(content.splitlines(), start=1):
        # Scan for image references
        for match in PATTERN_IMAGE.finditer(line):
            link_path = match.group(2)
            original = match.group(0)

            # Skip URL-like paths for images
            if link_path.startswith("http"):
                continue

            # Resolve path relative to source file's directory
            resolved = (source_dir / link_path).resolve()
            status = "found" if resolved.exists() else "missing"

            refs.append(
                Ref(
                    type="image",
                    original=original,
                    resolved_path=resolved,
                    status=status,
                    source_file=path,
                    line_number=line_number,
                )
            )

        # Scan for path references (excluding images and anchors)
        for match in PATTERN_PATH.finditer(line):
            link_path = match.group(2)
            original = match.group(0)

            # Skip URL-like paths
            if link_path.startswith("http"):
                continue

            # Resolve path relative to source file's directory
            resolved = (source_dir / link_path).resolve()
            status = "found" if resolved.exists() else "missing"

            refs.append(
                Ref(
                    type="path",
                    original=original,
                    resolved_path=resolved,
                    status=status,
                    source_file=path,
                    line_number=line_number,
                )
            )

        # Scan for URL references
        for match in PATTERN_URL.finditer(line):
            url = match.group(0)
            refs.append(
                Ref(
                    type="url",
                    original=url,
                    resolved_path=None,
                    status="external",
                    source_file=path,
                    line_number=line_number,
                )
            )

    return refs


def scan_files(paths: list[Path]) -> list[Ref]:
    """
    Scan multiple files for references.

    Args:
        paths: List of paths to markdown files to scan.

    Returns:
        Deduplicated list of Ref objects from all files.
    """
    all_refs: list[Ref] = []

    for path in paths:
        if not path.is_file():
            continue
        refs = scan_file(path)
        all_refs.extend(refs)

    return deduplicate_refs(all_refs)


def deduplicate_refs(refs: list[Ref]) -> list[Ref]:
    """Deduplicate refs by keeping first occurrence of each unique original value."""
    seen: set[str] = set()
    result: list[Ref] = []
    for ref in refs:
        if ref.original not in seen:
            seen.add(ref.original)
            result.append(ref)
    return result


def ref_count_by_type(refs: list[Ref]) -> dict[str, int]:
    """Count references by type."""
    return {
        "image": sum(1 for r in refs if r.type == "image"),
        "path": sum(1 for r in refs if r.type == "path"),
        "url": sum(1 for r in refs if r.type == "url"),
    }
