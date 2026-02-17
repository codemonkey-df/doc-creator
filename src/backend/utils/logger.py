"""Structured JSONL logger for session observability (FC015)."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# Event type allowlist per AC6.5.1
EVENT_TYPE_ALLOWLIST = frozenset(
    [
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
)

# Module-level registry for loggers
_loggers: dict[str, "StructuredLogger"] = {}

# Default log level from env
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Max result truncation per AC6.5.2
MAX_RESULT_LENGTH = 200


class StructuredLogger:
    """Session-scoped structured JSONL logger (FC015)."""

    def __init__(self, session_id: str, log_path: Path | None = None) -> None:
        """Initialize logger for session.

        Args:
            session_id: UUID of the session.
            log_path: Optional override for log file path. Defaults to {session}/logs/session.jsonl.
        """
        self.session_id = session_id
        self._log_path = log_path
        self._log_level = self._get_log_level()
        # Create log directory immediately on initialization
        if self._log_path is not None:
            self._ensure_log_dir()

    def _get_log_level(self) -> int:
        """Get numeric log level from environment."""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        return level_map.get(DEFAULT_LOG_LEVEL, logging.INFO)

    @property
    def log_path(self) -> Path:
        """Return log file path."""
        if self._log_path is not None:
            return self._log_path
        raise RuntimeError("log_path not set. Use get_logger(session_id) instead.")

    def _ensure_log_dir(self) -> None:
        """Create logs directory if it doesn't exist."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_line(self, event: dict[str, Any]) -> None:
        """Write a JSON line to the log file with flush."""
        self._ensure_log_dir()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()

    def log_event(self, event_type: str, **kwargs: Any) -> None:
        """Log a structured event.

        Args:
            event_type: Must be in EVENT_TYPE_ALLOWLIST.
            **kwargs: Event-specific fields.
        """
        if event_type not in EVENT_TYPE_ALLOWLIST:
            raise ValueError(
                f"Invalid event_type: {event_type}. Must be in {EVENT_TYPE_ALLOWLIST}"
            )

        event = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event_type": event_type,
            **kwargs,
        }
        self._write_line(event)

    def log_state_transition(
        self, from_state: str, to_state: str, **kwargs: Any
    ) -> None:
        """Log a state machine transition."""
        self.log_event(
            "state_transition",
            from_state=from_state,
            to_state=to_state,
            **kwargs,
        )

    def log_tool_call(self, tool_name: str, args: dict[str, Any], result: Any) -> None:
        """Log a tool invocation with sanitized args and truncated result.

        Args:
            tool_name: Name of the tool.
            args: Arguments dictionary - only keys are logged (no content).
            result: Result of the tool call - truncated to 200 chars.
        """
        # Sanitize args: only log keys, not values (per AC6.5.2)
        sanitized_args = {
            key: f"<{type(value).__name__}>" for key, value in args.items()
        }

        # Truncate result (per AC6.5.2)
        result_str = str(result)[:MAX_RESULT_LENGTH]

        self.log_event(
            "tool_call",
            tool_name=tool_name,
            args=sanitized_args,
            result=result_str,
        )

    def log_error(self, error_type: str, message: str, **kwargs: Any) -> None:
        """Log an error occurrence."""
        self.log_event(
            "error",
            error_type=error_type,
            message=message,
            **kwargs,
        )


def get_logger(session_id: str, session_path: Path | None = None) -> StructuredLogger:
    """Get or create a logger for the given session.

    This function provides session-scoped loggers. The logger is NOT stored
    in state (state must remain serializable).

    Args:
        session_id: UUID of the session.
        session_path: Optional session root path. If not provided, uses SessionManager.

    Returns:
        StructuredLogger instance for the session.
    """
    if session_id not in _loggers:
        # Determine log path
        if session_path is not None:
            log_path = session_path / "logs" / "session.jsonl"
        else:
            # Use SessionManager to get path
            from backend.utils.session_manager import SessionManager

            sm = SessionManager()
            session_root = sm.get_path(session_id)
            log_path = session_root / "logs" / "session.jsonl"

        _loggers[session_id] = StructuredLogger(session_id, log_path)

    return _loggers[session_id]


def clear_loggers() -> None:
    """Clear the logger registry. Useful for testing."""
    global _loggers
    _loggers = {}
