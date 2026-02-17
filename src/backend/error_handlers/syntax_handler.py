"""Syntax Error Handler - Fixes unclosed code blocks."""

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


def fix_unclosed_code_block(
    session_id: str,
    line_number: int | None = None,
    **kwargs,
) -> str:
    """Fix unclosed code blocks in session's temp_output.md.

    Args:
        session_id: The session UUID
        line_number: Optional line number hint (unused, for API compatibility)
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

        # Read content
        content = output_file.read_text(encoding="utf-8")

        # Count code fences (```)
        fence_count = content.count("```")

        # If odd number of fences, add closing fence
        if fence_count % 2 == 1:
            # Append closing fence
            new_content = content.rstrip() + "\n```\n"
            output_file.write_text(new_content, encoding="utf-8")
            logger.info(
                "Added closing code fence",
                extra={"session_id": session_id, "fence_count": fence_count},
            )
            return "Added closing code fence"

        # Even number of fences - no fix needed
        logger.info(
            "No unclosed code fence found",
            extra={"session_id": session_id, "fence_count": fence_count},
        )
        return "No unclosed code fence found"

    except ValueError as e:
        return f"Fix failed: {e}"
    except OSError as e:
        return f"Fix failed: {e}"
    except Exception as e:
        logger.exception("Unexpected error in fix_unclosed_code_block")
        return f"Fix failed: {e}"
