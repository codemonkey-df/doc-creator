"""Shared exception types and error codes for input validation and security.

Error codes used by InputSanitizer and file discovery (Story 1.3):
- PATH_ESCAPE: Path resolves outside allowed base directory (traversal or symlink).
- EXTENSION_BLOCKED: File extension is on the blocklist (e.g. .exe, .sh).
- EXTENSION_NOT_ALLOWED: File extension is not on the whitelist.
- FILE_TOO_LARGE: File size exceeds configured limit.
- INVALID_UTF8: File is not valid UTF-8 or appears binary.
- MISSING: File not found; this module uses FileNotFoundError for missing files.
"""


class SecurityError(Exception):
    """Raised when path escapes base directory or other security violation.

    Used for path traversal (e.g. ../), symlinks pointing outside base_dir,
    or any path that resolves outside the allowed root.
    """

    pass


class ValidationError(Exception):
    """Raised for extension, size, or encoding validation failure (non-security).

    Attributes:
        code: Machine-readable code for downstream handling (e.g. EXTENSION_BLOCKED).
        Message is available via str(exception) or exception.args[0].
    """

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code
