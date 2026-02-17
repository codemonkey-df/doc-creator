"""Asset Error Handler - Replaces missing images with placeholders."""

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


# Regex pattern to match markdown images: ![alt](path) or![](path)
IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def insert_placeholder(
    session_id: str,
    asset_ref: str | None = None,
    **kwargs,
) -> str:
    """Replace missing image references with placeholder text.

    Args:
        session_id: The session UUID
        asset_ref: The asset reference to replace. If None, uses "unknown_asset".
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

        # Use "unknown_asset" if no asset_ref provided
        # When using unknown_asset, replace ALL images
        replace_all = False
        if asset_ref is None:
            asset_ref = "unknown_asset"
            replace_all = True

        # Read content
        content = output_file.read_text(encoding="utf-8")

        # Find all image references matching asset_ref
        # asset_ref could be a full path or just a filename
        replacement = f"**[Image Missing: {asset_ref}]**"
        replacement_count = 0

        def replace_image(match: re.Match) -> str:
            nonlocal replacement_count
            path = match.group(2)

            # When replace_all is True (asset_ref was None), replace all images
            if replace_all:
                replacement_count += 1
                return replacement

            # Check if this path matches the asset_ref (full path or filename)
            if (
                asset_ref in path
                or path.endswith(asset_ref)
                or asset_ref in path.split("/")
            ):
                replacement_count += 1
                return replacement
            return match.group(0)  # Return original if no match

        new_content = IMAGE_PATTERN.sub(replace_image, content)

        if replacement_count > 0:
            output_file.write_text(new_content, encoding="utf-8")
            logger.info(
                "Replaced missing image with placeholder",
                extra={
                    "session_id": session_id,
                    "asset_ref": asset_ref,
                    "replacements": replacement_count,
                },
            )
            return f"Replaced {replacement_count} missing image(s) [{asset_ref}] with placeholder"

        logger.info(
            "No matching image reference found",
            extra={"session_id": session_id, "asset_ref": asset_ref},
        )
        return "No matching image reference found"

    except ValueError as e:
        return f"Fix failed: {e}"
    except OSError as e:
        return f"Fix failed: {e}"
    except Exception as e:
        logger.exception("Unexpected error in insert_placeholder")
        return f"Fix failed: {e}"
