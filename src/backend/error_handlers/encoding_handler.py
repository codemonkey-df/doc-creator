"""Encoding Error Handler - Fixes invalid UTF-8 sequences."""

import logging

from backend.utils.session_manager import SessionManager

logger = logging.getLogger(__name__)

# Global SessionManager instance (lazy initialized)
_session_manager: SessionManager | None = None


def _get_session_manager() -> SessionManager:
    """Get or create the global SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def set_session_manager(manager: SessionManager) -> None:
    """Set a custom SessionManager (for testing)."""
    global _session_manager
    _session_manager = manager


def fix_invalid_utf8(
    session_id: str,
    **kwargs,
) -> str:
    """Fix invalid UTF-8 sequences in session's temp_output.md.

    Reads the file with UTF-8 errors='replace' to replace invalid sequences,
    then writes back with proper UTF-8 encoding.

    Args:
        session_id: The session UUID
        **kwargs: Additional keyword arguments (ignored)

    Returns:
        Outcome string describing what was done, or failure message.
    """
    try:
        manager = _get_session_manager()

        # Check session exists
        if not manager.exists(session_id):
            return "Fix failed: session not found"

        session_path = manager.get_path(session_id)
        output_file = session_path / "temp_output.md"

        if not output_file.exists():
            return "Fix failed: temp_output.md not found"

        # Read with replacement of invalid UTF-8 sequences
        content = output_file.read_text(encoding="utf-8", errors="replace")

        # Write back with proper UTF-8
        output_file.write_text(content, encoding="utf-8")

        logger.info(
            "Fixed invalid UTF-8 sequences",
            extra={"session_id": session_id, "content_length": len(content)},
        )
        return "Fixed invalid UTF-8 sequences"

    except ValueError as e:
        return f"Fix failed: {e}"
    except OSError as e:
        return f"Fix failed: {e}"
    except Exception as e:
        logger.exception("Unexpected error in fix_invalid_utf8")
        return f"Fix failed: {e}"
