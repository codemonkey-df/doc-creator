"""Unit tests for SessionManager (Story 1.2). GIVEN-WHEN-THEN; use temp dirs."""

import pytest
from pathlib import Path

from backend.utils.session_manager import SessionManager
from backend.utils.settings import SessionSettings


# --- Fixtures ---

SESSION_SUBDIRS = ("inputs", "assets", "checkpoints", "logs")


@pytest.fixture
def temp_base(tmp_path: Path) -> Path:
    """GIVEN a temporary base directory for sessions and archive."""
    return tmp_path.resolve()


@pytest.fixture
def session_settings(temp_base: Path) -> SessionSettings:
    """GIVEN SessionSettings with temp base (no real ./docs touched)."""
    return SessionSettings(
        docs_base_path=temp_base,
        sessions_dir="sessions",
        archive_dir="archive",
    )


@pytest.fixture
def session_manager(session_settings: SessionSettings) -> SessionManager:
    """GIVEN a SessionManager configured with temp base."""
    return SessionManager(settings=session_settings)


# --- AC1.2.1: create() ---


def test_create_returns_uuid_and_creates_layout(
    session_manager: SessionManager,
    session_settings: SessionSettings,
) -> None:
    """GIVEN SessionManager with temp base / WHEN create() / THEN returns UUID and session root has inputs, assets, checkpoints, logs."""
    session_id = session_manager.create()

    assert session_id
    assert len(session_id) == 36  # UUID format
    path = session_manager.get_path(session_id)
    assert path.is_dir()
    for sub in SESSION_SUBDIRS:
        subdir = path / sub
        assert subdir.is_dir(), f"Missing subdir {sub}"
    # No extra subdirs (layout matches ARCHITECTURE exactly)
    direct_children = [p.name for p in path.iterdir() if p.is_dir()]
    assert set(direct_children) == set(SESSION_SUBDIRS)


def test_create_twice_returns_different_ids_and_dirs(
    session_manager: SessionManager,
) -> None:
    """GIVEN two create() calls / WHEN created in sequence / THEN two different session_ids and two distinct directories."""
    id1 = session_manager.create()
    id2 = session_manager.create()

    assert id1 != id2
    p1 = session_manager.get_path(id1)
    p2 = session_manager.get_path(id2)
    assert p1 != p2
    assert p1.is_dir() and p2.is_dir()


# --- AC1.2.2: get_path() ---


def test_get_path_returns_session_root(
    session_manager: SessionManager,
    session_settings: SessionSettings,
) -> None:
    """GIVEN session_id from create() / WHEN get_path(session_id) / THEN returns Path to session root (same path where subdirs exist)."""
    session_id = session_manager.create()
    path = session_manager.get_path(session_id)

    assert path == session_settings.docs_base_path / "sessions" / session_id
    assert path.is_dir()
    assert (path / "inputs").is_dir()


def test_get_path_does_not_check_existence(
    session_manager: SessionManager,
    session_settings: SessionSettings,
) -> None:
    """get_path(session_id) does not check existence; returns Path regardless (callers ensure session_id was created by this manager)."""
    unknown_id = "00000000-0000-0000-0000-000000000000"
    path = session_manager.get_path(unknown_id)

    assert path == session_settings.docs_base_path / "sessions" / unknown_id
    # Path may or may not exist; we do not require it to exist


# --- AC1.2.3: cleanup(archive=True) ---


def test_cleanup_archive_moves_to_archive_and_creates_parent(
    session_manager: SessionManager,
    session_settings: SessionSettings,
) -> None:
    """GIVEN existing session / WHEN cleanup(session_id, archive=True) / THEN session root moved to base/archive/session_id and session root no longer exists; archive parent created if missing."""
    session_id = session_manager.create()
    session_path = session_manager.get_path(session_id)
    archive_parent = session_settings.docs_base_path / "archive"
    archive_path = archive_parent / session_id

    assert session_path.is_dir()
    assert not archive_path.exists()

    session_manager.cleanup(session_id, archive=True)

    assert not session_path.exists()
    assert archive_path.is_dir()
    for sub in SESSION_SUBDIRS:
        assert (archive_path / sub).is_dir()


def test_cleanup_archive_creates_archive_parent_if_missing(
    session_manager: SessionManager,
    session_settings: SessionSettings,
) -> None:
    """GIVEN archive dir did not exist / WHEN cleanup with archive=True / THEN archive parent is created and move succeeds."""
    session_id = session_manager.create()
    archive_parent = session_settings.docs_base_path / "archive"

    assert not archive_parent.exists()

    session_manager.cleanup(session_id, archive=True)

    assert archive_parent.is_dir()
    assert (archive_parent / session_id).is_dir()


# --- AC1.2.3: cleanup(archive=False) ---


def test_cleanup_delete_removes_session(
    session_manager: SessionManager,
    session_settings: SessionSettings,
) -> None:
    """GIVEN existing session / WHEN cleanup(session_id, archive=False) / THEN session root is deleted (not under sessions or archive)."""
    session_id = session_manager.create()
    session_path = session_manager.get_path(session_id)
    archive_path = session_settings.docs_base_path / "archive" / session_id

    session_manager.cleanup(session_id, archive=False)

    assert not session_path.exists()
    assert not archive_path.exists()


# --- Idempotency / missing session ---


def test_cleanup_missing_session_archive_no_op(
    session_manager: SessionManager,
) -> None:
    """GIVEN session_id that does not exist / WHEN cleanup(session_id, archive=True) / THEN no exception; no-op."""
    session_manager.cleanup("00000000-0000-0000-0000-000000000000", archive=True)
    # No exception


def test_cleanup_missing_session_delete_no_op(
    session_manager: SessionManager,
) -> None:
    """GIVEN session_id that does not exist / WHEN cleanup(session_id, archive=False) / THEN no exception; no-op."""
    session_manager.cleanup("00000000-0000-0000-0000-000000000000", archive=False)
    # No exception


def test_cleanup_already_archived_idempotent(
    session_manager: SessionManager,
) -> None:
    """GIVEN already cleaned session / WHEN cleanup again / THEN no exception (idempotent)."""
    session_id = session_manager.create()
    session_manager.cleanup(session_id, archive=True)
    session_manager.cleanup(session_id, archive=True)
    # No exception


# --- AC1.2.5: concurrency (sequential create uniqueness) ---


def test_create_sequential_different_uuids(
    session_manager: SessionManager,
) -> None:
    """GIVEN two create() calls in sequence / WHEN created / THEN different UUIDs and dirs; no collision."""
    id1 = session_manager.create()
    id2 = session_manager.create()
    assert id1 != id2
    assert session_manager.get_path(id1) != session_manager.get_path(id2)


# --- exists(session_id) ---


def test_exists_true_after_create_false_after_cleanup(
    session_manager: SessionManager,
) -> None:
    """GIVEN created session / WHEN exists(session_id) / THEN True; after cleanup / THEN False."""
    session_id = session_manager.create()
    assert session_manager.exists(session_id) is True
    session_manager.cleanup(session_id, archive=False)
    assert session_manager.exists(session_id) is False


def test_exists_false_for_unknown_session(
    session_manager: SessionManager,
) -> None:
    """GIVEN unknown session_id / WHEN exists(session_id) / THEN False."""
    assert session_manager.exists("00000000-0000-0000-0000-000000000000") is False


# --- session_id validation (path traversal prevention) ---


def test_get_path_invalid_uuid_raises(
    session_manager: SessionManager,
) -> None:
    """GIVEN invalid session_id (path traversal attempt) / WHEN get_path() / THEN ValueError."""
    with pytest.raises(ValueError, match="Invalid session_id"):
        session_manager.get_path("../../etc/passwd")


def test_cleanup_invalid_uuid_raises(
    session_manager: SessionManager,
) -> None:
    """GIVEN invalid session_id / WHEN cleanup() / THEN ValueError."""
    with pytest.raises(ValueError, match="Invalid session_id"):
        session_manager.cleanup("not-a-uuid", archive=True)


def test_cleanup_archive_collision_raises(
    session_manager: SessionManager,
    session_settings: SessionSettings,
) -> None:
    """GIVEN session and pre-existing archive dir for same id / WHEN cleanup(archive=True) / THEN FileExistsError."""
    session_id = session_manager.create()
    archive_path = session_settings.docs_base_path / "archive" / session_id
    archive_path.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="Archive already exists"):
        session_manager.cleanup(session_id, archive=True)
