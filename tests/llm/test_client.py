"""Unit tests for the LLM client."""

from unittest.mock import MagicMock, patch

import pytest

from src.llm.client import LLMError, call_llm
from src.config import LlmConfig


@pytest.fixture
def config() -> LlmConfig:
    """Fixture to return a LlmConfig instance."""
    return LlmConfig()


class TestCallLLM:
    """Tests for the call_llm function."""

    def test_call_llm_returns_text_content(self, config) -> None:
        """Test that call_llm returns the text content from the LLM response."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Test response"

        with patch("src.llm.client.litellm.completion", return_value=mock_response):
            result = call_llm("system prompt", "user prompt", config)

        assert result == "Test response"

    def test_docforge_model_env_var_override(self, config) -> None:
        """Test that DOCFORGE_MODEL environment variable overrides default model."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Response"

        config.model = "gpt-4o-mini"
        with patch(
            "src.llm.client.litellm.completion", return_value=mock_response
        ) as mock_completion:
            call_llm("system", "user", config)

            mock_completion.assert_called_once()
            call_kwargs = mock_completion.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o-mini"

    def test_api_error_raises_llm_error(self, config) -> None:
        """Test that litellm.exceptions.APIError is re-raised as LLMError."""
        import litellm

        with patch(
            "src.llm.client.litellm.completion",
            side_effect=litellm.exceptions.APIError(
                status_code=401,
                message="Invalid API key",
                llm_provider="openai",
                model="gpt-4o",
            ),
        ):
            with pytest.raises(LLMError) as exc_info:
                call_llm("system", "user", config)

            assert exc_info.value.stage == "llm_call"
            assert "API error" in exc_info.value.message

    def test_custom_model_used_when_no_env_var(self, config) -> None:
        """Test that custom model parameter is used when no env var is set."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Response"

        with patch(
            "src.llm.client.litellm.completion", return_value=mock_response
        ) as mock_completion:
            config.model = "gpt-4o-mini"
            call_llm("system", "user", config)

            mock_completion.assert_called_once()
            call_kwargs = mock_completion.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o-mini"

    def test_llm_error_contains_cause(self, config) -> None:
        """Test that LLMError contains the original exception as cause."""
        import litellm

        original_error = litellm.exceptions.APIError(
            status_code=429,
            message="Rate limited",
            llm_provider="openai",
            model="gpt-4o",
        )
        with patch("src.llm.client.litellm.completion", side_effect=original_error):
            with pytest.raises(LLMError) as exc_info:
                call_llm("system", "user", config)

            assert exc_info.value.__cause__ is original_error
