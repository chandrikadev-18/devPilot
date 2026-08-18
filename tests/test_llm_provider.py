"""
Tests for LLM Provider Abstraction and Groq Implementation.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.llm.base import (
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.provider import GroqProvider, create_llm_provider


def test_groq_missing_api_key(monkeypatch):
    """Verifies that missing API key raises LLMAuthenticationError with clear instructions."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(LLMAuthenticationError) as exc_info:
        GroqProvider(api_key=None)

    assert "LLM API key is not configured." in str(exc_info.value)
    assert "Please configure the required environment variable." in str(exc_info.value)


def test_groq_properties():
    """Verifies provider name and model name configuration."""
    provider = GroqProvider(api_key="gsk_test_key_123", model="llama-3.3-70b-versatile")
    assert provider.provider_name == "groq"
    assert provider.model_name == "llama-3.3-70b-versatile"


def test_groq_empty_prompt():
    """Verifies generating with an empty prompt raises an error."""
    provider = GroqProvider(api_key="gsk_test_key_123")
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate(prompt="")
    assert "Cannot generate response for an empty prompt" in str(exc_info.value)


def test_groq_successful_generation():
    """Verifies successful text generation with mocked Groq SDK client."""
    provider = GroqProvider(api_key="gsk_test_key_123", model="llama-3.3-70b-versatile")

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Authentication is handled in backend/auth.py via authenticate_user()."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    provider._client = mock_client

    result = provider.generate(
        prompt="Where is auth handled?",
        system_prompt="You are DevPilot.",
    )

    assert result == "Authentication is handled in backend/auth.py via authenticate_user()."
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "llama-3.3-70b-versatile"
    assert len(call_kwargs["messages"]) == 2
    assert call_kwargs["messages"][0] == {"role": "system", "content": "You are DevPilot."}
    assert call_kwargs["messages"][1] == {"role": "user", "content": "Where is auth handled?"}


def test_groq_empty_response():
    """Verifies that an empty or whitespace response from LLM raises LLMEmptyResponseError."""
    provider = GroqProvider(api_key="gsk_test_key_123")

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "   "
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    provider._client = mock_client

    with pytest.raises(LLMEmptyResponseError) as exc_info:
        provider.generate(prompt="Where is auth handled?")
    assert "empty response" in str(exc_info.value)


def test_groq_no_choices():
    """Verifies that empty choices list raises LLMEmptyResponseError."""
    provider = GroqProvider(api_key="gsk_test_key_123")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = []
    mock_client.chat.completions.create.return_value = mock_response

    provider._client = mock_client

    with pytest.raises(LLMEmptyResponseError):
        provider.generate(prompt="Where is auth handled?")


def test_create_llm_provider_factory(monkeypatch):
    """Verifies provider factory instantiates GroqProvider and validates unsupported providers."""
    monkeypatch.setenv("LLM_API_KEY", "gsk_test_key_factory")

    provider = create_llm_provider(provider_name="groq", model="custom-model")
    assert isinstance(provider, GroqProvider)
    assert provider.model_name == "custom-model"

    with pytest.raises(LLMProviderError) as exc_info:
        create_llm_provider(provider_name="unsupported_provider")
    assert "Unsupported LLM provider" in str(exc_info.value)
