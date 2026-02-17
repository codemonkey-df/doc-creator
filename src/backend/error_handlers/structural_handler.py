"""Structural Error Handler - Fixes heading hierarchy issues."""

import logging
import re

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


# Regex pattern for markdown headings: #, ##, ###, ####, etc.
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _get_heading_level(heading: str) -> int:
    """Get the heading level from a heading string (# = 1, ## = 2, etc.)."""
    match = HEADING_PATTERN.match(heading)
    if match:
        return len(match.group(1))
    return 0


def _replace_heading_level(heading: str, new_level: int) -> str:
    """Replace heading level while preserving the text."""
    match = HEADING_PATTERN.match(heading)
    if match:
        hashes = "#" * new_level
        return f"{hashes} {match.group(2)}"
    return heading


def fix_heading_hierarchy(
    session_id: str,
    **kwargs,
) -> str:
    """Fix heading hierarchy issues in session's temp_output.md.

    Fixes two types of issues:
    1. Skipped levels: If a heading jumps more than one level (e.g., H1 -> H4),
       clamp it to the previous level + 1
    2. Clamp all levels to 1-3 (FC002 requirement)

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

        # Read content
        content = output_file.read_text(encoding="utf-8")
        lines = content.split("\n")

        fixed_lines: list[str] = []
        previous_level = 0
        skip_count = 0
        clamp_count = 0

        for line in lines:
            if HEADING_PATTERN.match(line):
                current_level = _get_heading_level(line)

                # Fix skipped levels (e.g., H1 -> H4 becomes H1 -> H2)
                # Skip = jump of more than 2 levels (i.e., +3 or more, so >= +3)
                # H1->H3 (+2) is valid, H1->H4 (+3) is a skip
                if current_level >= previous_level + 3:
                    # Clamp to previous + 1
                    new_level = min(previous_level + 1, current_level)
                    # Then clamp to max 3
                    new_level = min(new_level, 3)
                    if new_level != current_level:
                        skip_count += 1
                        current_level = new_level
                        line = _replace_heading_level(line, current_level)

                # Clamp levels to 1-3 (FC002)
                if current_level > 3:
                    new_level = 3
                    if new_level != current_level:
                        clamp_count += 1
                        line = _replace_heading_level(line, new_level)
                        current_level = new_level

                # Clamp levels below 1 (shouldn't happen but just in case)
                if current_level < 1:
                    current_level = 1
                    line = _replace_heading_level(line, current_level)

                previous_level = current_level

            fixed_lines.append(line)

        new_content = "\n".join(fixed_lines)

        # Only write if changes were made
        if skip_count > 0 or clamp_count > 0:
            output_file.write_text(new_content, encoding="utf-8")
            logger.info(
                "Fixed heading hierarchy issues",
                extra={
                    "session_id": session_id,
                    "skipped_levels_fixed": skip_count,
                    "clamped_to_3": clamp_count,
                },
            )

            if skip_count > 0 and clamp_count > 0:
                return f"Fixed {skip_count} skipped level(s) and clamped {clamp_count} level(s) to 3"
            elif skip_count > 0:
                return f"Fixed {skip_count} skipped level(s)"
            else:
                return f"Clamped {clamp_count} heading(s) to level 3"

        logger.info(
            "No heading hierarchy issues found",
            extra={"session_id": session_id},
        )
        return "No heading hierarchy issues found"

    except ValueError as e:
        return f"Fix failed: {e}"
    except OSError as e:
        return f"Fix failed: {e}"
    except Exception as e:
        logger.exception("Unexpected error in fix_heading_hierarchy")
        return f"Fix failed: {e}"
