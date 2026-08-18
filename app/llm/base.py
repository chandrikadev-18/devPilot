"""
LLM Provider Base Interfaces and Exception Hierarchy.

Defines the abstract contract for LLM providers and custom domain exceptions.
"""

from abc import ABC, abstractmethod
from typing import Optional


class LLMError(Exception):
    """Base exception for all LLM-related errors in DevPilot."""
    pass


class LLMAuthenticationError(LLMError):
    """Raised when an LLM API key is missing or invalid."""
    pass


class LLMProviderError(LLMError):
    """Raised when the LLM provider fails to process a request."""
    pass


class LLMTimeoutError(LLMProviderError):
    """Raised when an LLM request times out."""
    pass


class LLMRateLimitError(LLMProviderError):
    """Raised when provider rate limits are exceeded."""
    pass


class LLMEmptyResponseError(LLMProviderError):
    """Raised when the LLM provider returns an empty or whitespace response."""
    pass


class LLMProvider(ABC):
    """
    Abstract interface for LLM providers.
    Decouples DevPilot from specific LLM vendors (Groq, OpenAI, Anthropic, etc.).
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the provider name identifier (e.g. 'groq')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Returns the model name identifier."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generates text completion from the LLM provider.

        Args:
            prompt: The user prompt containing question and codebase context.
            system_prompt: Optional system instructions guiding the LLM behavior.

        Returns:
            The generated response string.

        Raises:
            LLMAuthenticationError: If API key is missing or unauthorized.
            LLMRateLimitError: If provider rate limit is encountered.
            LLMTimeoutError: If the request times out.
            LLMEmptyResponseError: If the generated output is empty.
            LLMProviderError: For any other provider communication failure.
        """
        pass
