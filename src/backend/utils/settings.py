"""Pydantic settings for backend components.

SanitizerSettings is loaded from environment with prefix INPUT_.
Override via env vars, e.g.:
  INPUT_ALLOWED_EXTENSIONS='[".txt", ".log", ".md"]'  (JSON array)
  INPUT_BLOCKED_EXTENSIONS='[".exe", ".dll", ".sh"]'
  INPUT_MAX_FILE_SIZE_BYTES=104857600

SessionSettings is loaded from environment (DOCS_BASE_PATH, SESSIONS_DIR, ARCHIVE_DIR).
Override via env vars, e.g.:
  DOCS_BASE_PATH=/app/docs
  SESSIONS_DIR=sessions
  ARCHIVE_DIR=archive

Extensions are normalized to lowercase for case-insensitive matching.
All extensions must start with a dot (e.g. .txt).
"""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SanitizerSettings(BaseSettings):
    """Settings for InputSanitizer. Loaded from env with prefix INPUT_."""

    model_config = SettingsConfigDict(
        env_prefix="INPUT_",
        extra="ignore",
    )

    allowed_extensions: list[str] = [".txt", ".log", ".md"]
    blocked_extensions: list[str] = [
        ".exe",
        ".dll",
        ".so",
        ".bin",
        ".sh",
        ".bat",
    ]
    max_file_size_bytes: int = Field(
        default=104_857_600,
        gt=0,
        description="Maximum allowed file size in bytes (default: 100MB)",
    )

    @field_validator("allowed_extensions", "blocked_extensions", mode="before")
    @classmethod
    def normalize_extensions(cls, v: list[str] | None) -> list[str] | None:
        """Normalize extensions to lowercase for case-insensitive matching."""
        if v is None:
            return v
        return [ext.lower() if isinstance(ext, str) else ext for ext in v]

    @field_validator("allowed_extensions", "blocked_extensions")
    @classmethod
    def validate_extension_format(cls, v: list[str]) -> list[str]:
        """Ensure all extensions start with a dot."""
        for ext in v:
            if not ext.startswith("."):
                raise ValueError(f"Extension must start with '.': {ext!r}")
        return v


class SessionSettings(BaseSettings):
    """Settings for SessionManager. Loaded from env (DOCS_BASE_PATH, SESSIONS_DIR, ARCHIVE_DIR)."""

    model_config = SettingsConfigDict(
        extra="ignore",
    )

    docs_base_path: Path = Field(
        default=Path("./docs"),
        description="Base directory for sessions and archive",
    )
    sessions_dir: str = Field(
        default="sessions", description="Subdir under base for active sessions"
    )
    archive_dir: str = Field(
        default="archive", description="Subdir under base for archived sessions"
    )

    @field_validator("docs_base_path", mode="after")
    @classmethod
    def resolve_base_path(cls, v: Path) -> Path:
        """Resolve docs_base_path to absolute for deterministic behavior."""
        return v.resolve()
