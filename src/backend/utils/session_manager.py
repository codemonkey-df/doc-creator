"""Session lifecycle: create UUID session dirs, get_path, cleanup (archive or delete).

Directory layout (ARCHITECTURE): session root = {docs_base_path}/{sessions_dir}/{session_id}/
with subdirs: inputs, assets, checkpoints, logs. Archive = {docs_base_path}/{archive_dir}/{session_id}/.

get_path(session_id) returns the session root Path and does NOT check existence;
callers must ensure session_id was created by this manager. Use exists(session_id) if needed.
session_id must be a valid UUID string (validated to prevent path traversal).

Cleanup failure policy: archive parent is created with mkdir(parents=True) before move.
On move or rmtree failure we log and re-raise so the caller can retry or alert; no partial state.
If the session path does not exist, cleanup is a no-op (idempotent).
"""

import logging
import shutil
import uuid
from pathlib import Path

from backend.utils.settings import SessionSettings

logger = logging.getLogger(__name__)

SESSION_SUBDIRS = ("inputs", "assets", "checkpoints", "logs")


class SessionManager:
    """Creates and cleans up per-request session directories (UUID-based)."""

    def __init__(self, settings: SessionSettings | None = None) -> None:
        """Initialize with optional settings; defaults to env-loaded SessionSettings."""
        self._settings = settings if settings is not None else SessionSettings()

    def _validate_session_id(self, session_id: str) -> None:
        """Validate session_id is a valid UUID to prevent path traversal."""
        try:
            uuid.UUID(session_id)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid session_id format: {session_id!r}") from e

    def create(self) -> str:
        """Create a new session directory with UUID and standard subdirs.

        Returns:
            session_id: UUID string. Session root is {base}/{sessions_dir}/{session_id}/
            with subdirs: inputs, assets, checkpoints, logs.

        Raises:
            OSError: On mkdir failure (e.g. permission). Logged and re-raised.
            Partial session dir is removed on failure (no partial state).
        """
        session_id = str(uuid.uuid4())
        base = self._settings.docs_base_path / self._settings.sessions_dir / session_id
        try:
            base.mkdir(parents=True)
            for sub in SESSION_SUBDIRS:
                (base / sub).mkdir(parents=False)
        except OSError as e:
            if base.exists():
                try:
                    shutil.rmtree(base)
                except OSError:
                    pass
            logger.error(
                "Session create failed for session_id=%s: %s",
                session_id,
                e,
                exc_info=True,
            )
            raise
        logger.info("Session created: session_id=%s", session_id)
        return session_id

    def get_path(self, session_id: str) -> Path:
        """Return the session root path. Does not check existence.

        Callers must ensure session_id was created by this manager.
        Use exists(session_id) if you need to check presence.
        session_id must be a valid UUID (validated to prevent path traversal).

        Args:
            session_id: UUID string returned from create().

        Returns:
            Path to session root: {docs_base_path}/{sessions_dir}/{session_id}.

        Raises:
            ValueError: If session_id is not a valid UUID.
        """
        self._validate_session_id(session_id)
        return self._settings.docs_base_path / self._settings.sessions_dir / session_id

    def exists(self, session_id: str) -> bool:
        """Return True if the session directory exists."""
        return self.get_path(session_id).is_dir()

    def cleanup(self, session_id: str, archive: bool = True) -> None:
        """Move session to archive or delete it. Idempotent if session is missing.

        Archive: ensures archive parent exists (mkdir(parents=True)), then moves
        session tree to {docs_base_path}/{archive_dir}/{session_id}.
        Delete: removes session tree with shutil.rmtree.

        Cleanup failure policy: if session path does not exist, log and return (no-op).
        On move or rmtree failure we log and re-raise so caller can retry or alert.
        If archive destination already exists, raises FileExistsError.

        Args:
            session_id: UUID string.
            archive: If True, move to archive; if False, delete tree.

        Raises:
            ValueError: If session_id is not a valid UUID.
            FileExistsError: If archive=True and archive path already exists.
        """
        path = self.get_path(session_id)
        if not path.is_dir():
            logger.debug("Cleanup no-op: session_id=%s path does not exist", session_id)
            return

        if archive:
            archive_parent = self._settings.docs_base_path / self._settings.archive_dir
            archive_parent.mkdir(parents=True, exist_ok=True)
            archive_path = archive_parent / session_id
            if archive_path.exists():
                raise FileExistsError(
                    f"Archive already exists for session_id={session_id}; cannot overwrite"
                )
            try:
                shutil.move(path, archive_path)
                logger.info("Session archived: session_id=%s", session_id)
            except OSError as e:
                logger.error(
                    "Session archive failed: session_id=%s error=%s",
                    session_id,
                    e,
                    exc_info=True,
                )
                raise
        else:
            try:
                shutil.rmtree(path)
                logger.info("Session deleted: session_id=%s", session_id)
            except FileNotFoundError:
                logger.debug("Session already deleted: session_id=%s", session_id)
            except OSError as e:
                logger.error(
                    "Session delete failed: session_id=%s error=%s",
                    session_id,
                    e,
                    exc_info=True,
                )
                raise
