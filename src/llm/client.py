"""LiteLLM client wrapper for LLM interactions."""

import logging
from typing import Optional

import litellm
from src.config import LlmConfig

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Custom exception for LLM-related errors.

    Attributes:
        stage: The stage where the error occurred.
        message: The error message.
    """

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        self.message = message
        super().__init__(f"[{stage}] {message}")


def call_llm(system: str, user: str, config: LlmConfig, stage: str = "llm") -> str:
    """Call the LLM with the given system and user prompts.

    Args:
        system: The system prompt.
        user: The user prompt.
        config: The LLM configuration.
        stage: Optional stage name for logging (e.g., "intro", "chapter", "toc").

    Returns:
        The text content from the LLM response.

    Raises:
        LLMError: If the LLM call fails.
    """
    # Log the prompts being sent (truncated for readability)
    system_display = system[:500] + "..." if len(system) > 500 else system
    user_display = user[:1000] + "..." if len(user) > 1000 else user
    logger.info(
        "llm_call_start",
        extra={
            "stage": stage,
            "model": config.model,
            "system_length": len(system),
            "user_length": len(user),
            "system_preview": system_display,
            "user_preview": user_display,
        },
    )

    try:
        response = litellm.completion(
            model=config.model,
            temperature=config.temperature,
            timeout=config.timeout,
            max_retries=config.max_retries,
            api_base=config.api_base,
            api_key=config.api_key.get_secret_value() if config.api_key else None,
            top_p=config.top_p,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content  # type: ignore[return-value]

        # Log the response
        content_display = content[:500] + "..." if content and len(content) > 500 else content
        logger.info(
            "llm_call_complete",
            extra={
                "model": config.model,
                "response_length": len(content) if content else 0,
                "response_preview": content_display,
            },
        )

        return content if content else ""
    except litellm.exceptions.APIError as e:
        raise LLMError(
            stage="llm_call",
            message=f"API error: {e}",
        ) from e
    except Exception as e:
        raise LLMError(
            stage="llm_call",
            message=f"Unexpected error: {e}",
        ) from e
