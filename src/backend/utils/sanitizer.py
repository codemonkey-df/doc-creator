"""Input sanitizer: path resolution, extensions, size, encoding (FC016).

Validation order (enforced):
  1. Resolve path to absolute.
  2. Check resolved path is under base_dir (else SecurityError). Done before
     exists so that path traversal always raises SecurityError.
  3. Check path exists and is a file (else FileNotFoundError / ValidationError).
  4. Check extension: blocklist first (ValidationError EXTENSION_BLOCKED),
     then whitelist (ValidationError EXTENSION_NOT_ALLOWED if not allowed).
  5. Check size via stat() only (ValidationError FILE_TOO_LARGE if over limit).
  6. UTF-8 / binary check (ValidationError INVALID_UTF8 if invalid).

Size is never determined by reading the file; only stat() is used.
Security-related tests are tagged @pytest.mark.security.
"""

import logging
import stat
from pathlib import Path

from backend.utils.exceptions import SecurityError, ValidationError
from backend.utils.settings import SanitizerSettings

logger = logging.getLogger(__name__)


class InputSanitizer:
    """Validates user-provided file paths: boundary, extension, size, UTF-8.

    Contract:
      - validate(path: str, base_dir: Path) -> Path
      - Returns resolved, validated Path.
      - Raises: SecurityError (path escape/symlink), ValidationError(message, code),
        FileNotFoundError (missing file). No bare except.
    """

    def __init__(self, settings: SanitizerSettings | None = None) -> None:
        """Initialize with optional settings; defaults from env."""
        self._settings = settings or SanitizerSettings()
        self._allowed = {e.lower() for e in self._settings.allowed_extensions}
        self._blocked = {e.lower() for e in self._settings.blocked_extensions}

    def validate(self, path: str, base_dir: Path) -> Path:
        """Validate path and return resolved Path; raise on failure.

        Order: resolve -> under base_dir -> exists -> extension (blocklist then whitelist)
        -> size (stat only) -> UTF-8 check.
        """
        resolved = Path(path).resolve()
        base_resolved = base_dir.resolve()

        try:
            if not resolved.is_relative_to(base_resolved):
                raise SecurityError(f"Path escapes allowed directory: {resolved}")
        except (ValueError, TypeError):
            raise SecurityError(f"Path escapes allowed directory: {resolved}")

        if not resolved.exists():
            raise FileNotFoundError(f"Path does not exist: {resolved}")

        try:
            stat_result = resolved.stat()
        except OSError as e:
            raise FileNotFoundError(f"Cannot stat path: {resolved}") from e

        if not stat.S_ISREG(stat_result.st_mode):
            raise ValidationError(
                f"Path is not a file: {resolved}",
                "PATH_NOT_FILE",
            )

        suffix = resolved.suffix.lower()
        if suffix in self._blocked:
            raise ValidationError(
                f"Extension {suffix!r} is blocked",
                "EXTENSION_BLOCKED",
            )
        if suffix not in self._allowed:
            raise ValidationError(
                f"Extension {suffix!r} is not allowed",
                "EXTENSION_NOT_ALLOWED",
            )

        size = stat_result.st_size
        if size > self._settings.max_file_size_bytes:
            raise ValidationError(
                f"File size {size} exceeds limit {self._settings.max_file_size_bytes}",
                "FILE_TOO_LARGE",
            )

        self._validate_utf8(resolved)

        return resolved

    def _validate_utf8(self, path: Path) -> None:
        """Verify file is valid UTF-8; reject binary (null byte) or decode errors."""
        chunk_size = 8192
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                if b"\x00" in chunk:
                    raise ValidationError(
                        "File appears to be binary (null byte detected)",
                        "INVALID_UTF8",
                    )
                try:
                    chunk.decode("utf-8")
                except UnicodeDecodeError as e:
                    raise ValidationError(
                        f"File is not valid UTF-8: {e!s}",
                        "INVALID_UTF8",
                    ) from e
