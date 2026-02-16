"""Checkpoint utilities (Story 4.4).

Provides shared helper functions for restoring from checkpoints.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from backend.utils.session_manager import SessionManager

if TYPE_CHECKING:
    from backend.utils.session_manager import SessionManager

logger = logging.getLogger(__name__)

TEMP_OUTPUT_FILENAME = "temp_output.md"
CHECKPOINTS_DIR = "checkpoints"


def _session_path(
    session_id: str,
    session_manager: "SessionManager | None" = None,
) -> Path:
    """Return session root path. Uses SessionManager.get_path(session_id)."""
    sm = session_manager if session_manager is not None else SessionManager()
    return sm.get_path(session_id)


def _validate_checkpoint_id(checkpoint_id: str, session_path: Path) -> Path:
    """Require checkpoint_id as basename only; resolve under session and assert no escape.

    Raises ValueError if invalid.
    """
    cid = checkpoint_id.strip() if checkpoint_id else ""
    if not cid:
        raise ValueError("Checkpoint ID must not be empty")
    if "/" in cid or "\\" in cid:
        raise ValueError("Checkpoint ID must be a basename (no path separators)")
    if ".." in cid:
        raise ValueError("Checkpoint ID must not contain '..'")
    checkpoints_dir = session_path / CHECKPOINTS_DIR
    resolved = (checkpoints_dir / cid).resolve()
    session_resolved = session_path.resolve()
    if not resolved.is_relative_to(session_resolved):
        raise ValueError("Checkpoint path must be under session directory")
    return resolved


def restore_from_checkpoint(
    session_id: str,
    checkpoint_id: str,
    session_manager: "SessionManager | None" = None,
) -> bool:
    """Copy checkpoint file to temp_output.md.

    Validates checkpoint_id is basename only (no path traversal).
    Returns True if restored successfully, False if checkpoint file missing/invalid.

    Args:
        session_id: Session ID for the session
        checkpoint_id: Checkpoint basename to restore from (e.g., "20240215_120000_chapter_1.md")
        session_manager: Optional SessionManager instance

    Returns:
        True if restoration succeeded, False if checkpoint missing or invalid
    """
    try:
        session_path = _session_path(session_id, session_manager)
        src_path = _validate_checkpoint_id(checkpoint_id, session_path)

        if not src_path.exists():
            logger.warning(
                "restore_from_checkpoint: checkpoint file not found: %s",
                checkpoint_id,
            )
            return False

        dest_path = session_path / TEMP_OUTPUT_FILENAME
        shutil.copy2(src_path, dest_path)

        logger.info(
            "restore_from_checkpoint: restored %s -> temp_output.md",
            checkpoint_id,
        )
        return True

    except ValueError as e:
        logger.warning(
            "restore_from_checkpoint: invalid checkpoint_id %s: %s",
            checkpoint_id,
            e,
        )
        return False
    except Exception as e:
        logger.error(
            "restore_from_checkpoint: failed to restore %s: %s",
            checkpoint_id,
            e,
        )
        return False
