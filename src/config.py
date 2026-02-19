"""Unified configuration: database, storage, ingest limits, retention, thresholds.

All settings are loaded from environment (with optional .env). Used by API,
database, and services.
"""

from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LlmConfig(BaseSettings):
    """LLM adapter configuration

    All LLM settings (model, temperature, timeout, retries, api_base, api_key)
    are read from environment with prefix LLM_. API keys can also come from
    provider env vars (e.g. OPENAI_API_KEY, ANTHROPIC_API_KEY) when not set here.
    """

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model: str = Field(
        default="openai/gpt-4o-mini",
        description="LiteLLM model string (e.g. openai/gpt-4o, anthropic/claude-3-sonnet).",
    )
    temperature: float = Field(
        default=0.0, ge=0.0, le=2.0, description="Sampling temperature."
    )
    timeout: float = Field(
        default=60.0, gt=0, description="Request timeout in seconds."
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Max retry attempts for transient errors.",
    )
    api_base: str | None = Field(
        default=None, description="Optional API base URL (e.g. for proxy)."
    )
    api_key: SecretStr | None = Field(
        default=None,
        description="Optional API key; else from provider env vars.",
    )
    top_p: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Optional top_p sampling."
    )

    @field_validator("api_base")
    @classmethod
    def _validate_api_base(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("api_base must be a valid URL with scheme and netloc")
        return v
