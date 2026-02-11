"""Pydantic settings for backend components.

SanitizerSettings is loaded from environment with prefix INPUT_.
Override via env vars, e.g.:
  INPUT_ALLOWED_EXTENSIONS='[".txt", ".log", ".md"]'  (JSON array)
  INPUT_BLOCKED_EXTENSIONS='[".exe", ".dll", ".sh"]'
  INPUT_MAX_FILE_SIZE_BYTES=104857600

Extensions are normalized to lowercase for case-insensitive matching.
All extensions must start with a dot (e.g. .txt).
"""

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
