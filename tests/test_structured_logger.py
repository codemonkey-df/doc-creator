"""Unit tests for StructuredLogger (Story 6.5). GIVEN-WHEN-THEN; use temp dirs."""

import json
import uuid
from pathlib import Path

import pytest

# Import the module to test
from backend.utils.logger import (
    StructuredLogger,
    clear_loggers,
    get_logger,
)


# --- Fixtures ---


@pytest.fixture(autouse=True)
def clean_logger_registry() -> None:
    """GIVEN test environment / WHEN tests run / THEN clear logger registry after each test."""
    yield
    clear_loggers()


@pytest.fixture
def temp_session_path(tmp_path: Path) -> Path:
    """GIVEN a temporary session directory."""
    session_id = str(uuid.uuid4())
    session_path = tmp_path / session_id
    session_path.mkdir(parents=True)
    return session_path


@pytest.fixture
def logger_factory(temp_session_path: Path):
    """GIVEN a factory to create StructuredLogger instances."""

    def _create_logger(session_id: str | None = None) -> StructuredLogger:
        if session_id is None:
            session_id = str(uuid.uuid4())
        log_path = temp_session_path / "logs" / "session.jsonl"
        return StructuredLogger(session_id, log_path)

    return _create_logger


# --- AC6.5.1: Log file location and format ---


def test_structured_logger_writes_valid_jsonl(logger_factory) -> None:
    """GIVEN a StructuredLogger with valid path / WHEN log_event called / THEN log file contains valid JSON lines."""
    logger = logger_factory()
    logger.log_event("session_created", user_id="test_user")

    lines = logger.log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1

    # Each line should be valid JSON
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)


def test_structured_logger_required_fields(logger_factory) -> None:
    """GIVEN a valid event logged / WHEN log_event called / THEN line contains timestamp, session_id, event_type."""
    logger = logger_factory()
    logger.log_event("session_created", user_id="test_user")

    content = logger.log_path.read_text(encoding="utf-8")
    parsed = json.loads(content.strip().split("\n")[0])

    assert "timestamp" in parsed
    assert "session_id" in parsed
    assert parsed["session_id"] == logger.session_id
    assert "event_type" in parsed
    assert parsed["event_type"] == "session_created"
    # Verify timestamp is ISO8601-like
    assert "T" in parsed["timestamp"] or ":" in parsed["timestamp"]


def test_log_path_created(logger_factory) -> None:
    """GIVEN StructuredLogger / WHEN log_event called / THEN logs directory is created."""
    logger = logger_factory()
    logger.log_event("session_created")

    assert logger.log_path.parent.is_dir()
    assert logger.log_path.exists()


# --- AC6.5.1: Event type allowlist ---


def test_valid_event_types_accepted(logger_factory) -> None:
    """GIVEN valid event_type / WHEN log_event called / THEN no error raised."""
    valid_types = [
        "state_transition",
        "tool_call",
        "error",
        "session_created",
        "validation_ran",
        "conversion_started",
        "checkpoint_saved",
        "error_classified",
        "error_fix_attempted",
        "session_completed",
        "session_failed",
    ]
    logger = logger_factory()

    for event_type in valid_types:
        logger.log_event(event_type, data="test")

    # Should have written all events
    lines = logger.log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == len(valid_types)


def test_invalid_event_type_raises(logger_factory) -> None:
    """GIVEN invalid event_type / WHEN log_event called / THEN ValueError raised."""
    logger = logger_factory()

    with pytest.raises(ValueError) as exc_info:
        logger.log_event("invalid_event_type", data="test")

    assert "Invalid event_type" in str(exc_info.value)


# --- AC6.5.2: State transition logging ---


def test_state_transition_logging(logger_factory) -> None:
    """GIVEN from_state and to_state / WHEN log_state_transition called / THEN correct event_type and fields in log."""
    logger = logger_factory()
    logger.log_state_transition("processing", "validating")

    content = logger.log_path.read_text(encoding="utf-8")
    parsed = json.loads(content.strip().split("\n")[0])

    assert parsed["event_type"] == "state_transition"
    assert parsed["from_state"] == "processing"
    assert parsed["to_state"] == "validating"


# --- AC6.5.2: Tool call logging with sanitization ---


def test_tool_call_sanitizes_args(logger_factory) -> None:
    """GIVEN tool call with args containing sensitive data / WHEN log_tool_call called / THEN args show only types, not values."""
    logger = logger_factory()
    args = {
        "api_key": "secret_password_123",
        "file_path": "/etc/passwd",
        "count": 42,
    }
    logger.log_tool_call("process_document", args, "result")

    content = logger.log_path.read_text(encoding="utf-8")
    parsed = json.loads(content.strip().split("\n")[0])

    assert parsed["event_type"] == "tool_call"
    assert parsed["tool_name"] == "process_document"
    # Args should be sanitized - type only, not actual values
    assert parsed["args"]["api_key"] == "<str>"
    assert parsed["args"]["file_path"] == "<str>"
    assert parsed["args"]["count"] == "<int>"
    # Original values should NOT appear
    assert "secret_password" not in json.dumps(parsed)
    assert "/etc/passwd" not in json.dumps(parsed)


def test_tool_call_truncates_result(logger_factory) -> None:
    """GIVEN tool call with result > 200 chars / WHEN log_tool_call called / THEN result truncated to 200 chars."""
    logger = logger_factory()
    long_result = "x" * 500
    args = {"key": "value"}
    logger.log_tool_call("process", args, long_result)

    content = logger.log_path.read_text(encoding="utf-8")
    parsed = json.loads(content.strip().split("\n")[0])

    assert len(parsed["result"]) == 200
    assert parsed["result"].endswith("x" * 200)


# --- AC6.5.2: Error logging ---


def test_error_logging(logger_factory) -> None:
    """GIVEN error details / WHEN log_error called / THEN correct event_type and fields in log."""
    logger = logger_factory()
    logger.log_error("ValidationError", "Invalid document format", field="title")

    content = logger.log_path.read_text(encoding="utf-8")
    parsed = json.loads(content.strip().split("\n")[0])

    assert parsed["event_type"] == "error"
    assert parsed["error_type"] == "ValidationError"
    assert parsed["message"] == "Invalid document format"
    assert parsed["field"] == "title"


# --- AC6.5.3: get_logger singleton pattern ---


def test_get_logger_creates_and_caches(temp_session_path: Path) -> None:
    """GIVEN session_id / WHEN get_logger called twice / THEN returns same instance."""
    session_id = str(uuid.uuid4())
    logger1 = get_logger(session_id, temp_session_path)
    logger2 = get_logger(session_id, temp_session_path)

    assert logger1 is logger2


def test_get_logger_different_sessions(temp_session_path: Path) -> None:
    """GIVEN different session_ids with different session_paths / WHEN get_logger called / THEN returns different logger instances with different files."""
    session_id1 = str(uuid.uuid4())
    session_id2 = str(uuid.uuid4())

    # Each session has its own session root path
    session_path1 = temp_session_path / session_id1
    session_path2 = temp_session_path / session_id2
    session_path1.mkdir()
    session_path2.mkdir()

    logger1 = get_logger(session_id1, session_path1)
    logger2 = get_logger(session_id2, session_path2)

    assert logger1 is not logger2
    assert logger1.session_id != logger2.session_id
    assert logger1.log_path != logger2.log_path


def test_get_logger_creates_log_path(temp_session_path: Path) -> None:
    """GIVEN session_id / WHEN get_logger called / THEN creates logs directory."""
    session_id = str(uuid.uuid4())
    # Pass session root path (includes session_id)
    session_root = temp_session_path / session_id
    session_root.mkdir()

    logger = get_logger(session_id, session_root)

    # Directory should be created immediately on logger creation
    assert logger.log_path.parent.is_dir()
    assert logger.log_path.suffix == ".jsonl"


# --- AC6.5.4: LOG_LEVEL environment variable ---


def test_log_level_from_env(logger_factory, monkeypatch) -> None:
    """GIVEN LOG_LEVEL env var set to DEBUG / WHEN logger initialized / THEN uses DEBUG level."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    # Need to reimport to pick up new env var
    import importlib
    import backend.utils.logger as logger_module

    importlib.reload(logger_module)

    # Create a fresh logger after reload
    session_id = str(uuid.uuid4())
    log_path = logger_factory().log_path
    logger = logger_module.StructuredLogger(session_id, log_path)

    assert logger._log_level == 10  # logging.DEBUG = 10


def test_log_level_default_info(logger_factory, monkeypatch) -> None:
    """GIVEN LOG_LEVEL env var not set / WHEN logger initialized / THEN defaults to INFO."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    import importlib
    import backend.utils.logger as logger_module

    importlib.reload(logger_module)

    session_id = str(uuid.uuid4())
    log_path = logger_factory().log_path
    logger = logger_module.StructuredLogger(session_id, log_path)

    assert logger._log_level == 20  # logging.INFO = 20
