"""File discovery: list and validate requested files before workflow start (FC007).

This module provides:
- list_available_files(base_dir): flat (non-recursive) list of files with allowed
  extensions under base_dir. base_dir is the single allowed input root (absolute, resolved).
- validate_requested_files(requested, base_dir): validate each requested path via
  InputSanitizer; return (valid Paths, list of FileValidationError).

No workflow step should start until file discovery and validation complete; "file not
found" and similar errors are prevented before processing (FC007).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.utils.exceptions import SecurityError, ValidationError
from backend.utils.sanitizer import InputSanitizer
from backend.utils.settings import SanitizerSettings


@dataclass(frozen=True)
class FileValidationError:
    """Structured error for one requested file that failed validation.

    Codes align with sanitizer: MISSING, PATH_ESCAPE, EXTENSION_BLOCKED,
    EXTENSION_NOT_ALLOWED, FILE_TOO_LARGE, INVALID_UTF8, PATH_NOT_FILE.
    """

    path: str
    message: str
    code: str


def list_available_files(base_dir: Path) -> list[Path]:
    """List files in base_dir that have an allowed extension (flat, non-recursive).

    base_dir is the single allowed input root. It must be set to a dedicated input
    directory. It is resolved to absolute before use.

    Only direct children of base_dir are considered (no recursion). Only files whose
    extension is in the allowed list (SanitizerSettings) are returned. Returns
    resolved Paths. Listing is O(n) in the number of directory entries.

    Args:
        base_dir: Root directory to list (will be resolved to absolute).

    Returns:
        Sorted list of resolved Paths for allowed files; [] if base_dir is not a
        directory or is empty.
    """
    resolved_base = base_dir.resolve()
    if not resolved_base.is_dir():
        return []
    settings = SanitizerSettings()
    allowed_extensions_lower = {e.lower() for e in settings.allowed_extensions}
    result: list[Path] = []
    for p in resolved_base.iterdir():
        if p.is_file() and p.suffix.lower() in allowed_extensions_lower:
            result.append(p.resolve())
    # Sorted for deterministic output (tests and stable ordering).
    return sorted(result)


def validate_requested_files(
    requested: list[str],
    base_dir: Path,
    sanitizer: InputSanitizer | None = None,
) -> tuple[list[Path], list[FileValidationError]]:
    """Validate each requested path against the filesystem and sanitizer rules.

    base_dir is the single allowed input root (absolute, resolved). Each requested
    path is validated via InputSanitizer.validate; valid paths are collected and
    validation failures are returned as FileValidationError (path, message, code).
    No workflow step should start until the caller has checked errors and decided
    to proceed only when appropriate (FC007).

    Only FileNotFoundError, SecurityError, and ValidationError from the
    sanitizer are caught; other exceptions (e.g. OSError) propagate.

    Args:
        requested: List of paths (strings) requested by the user.
        base_dir: Allowed root directory (resolved to absolute).
        sanitizer: Optional InputSanitizer; default from env if not provided.

    Returns:
        Tuple of (valid_paths, errors). valid_paths is list of resolved Paths;
        errors is list of FileValidationError with path, message, and code.
    """
    resolved_base = base_dir.resolve()
    san = sanitizer or InputSanitizer()
    valid_paths: list[Path] = []
    errors: list[FileValidationError] = []
    for path_str in requested:
        try:
            resolved = san.validate(path_str, resolved_base)
            valid_paths.append(resolved)
        except FileNotFoundError as e:
            errors.append(
                FileValidationError(path=path_str, message=str(e), code="MISSING")
            )
        except SecurityError as e:
            errors.append(
                FileValidationError(path=path_str, message=str(e), code="PATH_ESCAPE")
            )
        except ValidationError as e:
            errors.append(
                FileValidationError(path=path_str, message=str(e), code=e.code)
            )
    return (valid_paths, errors)
