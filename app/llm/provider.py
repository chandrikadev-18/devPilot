"""
LLM Provider Implementations and Factory Function.

Contains Groq provider implementation with error translation,
bounded retries, and API key protection.
"""

import time
from typing import Optional

from app.config import (
    get_llm_api_key,
    get_llm_model,
    get_llm_provider,
)
from app.llm.base import (
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)


class GroqProvider(LLMProvider):
    """
    Groq LLM Provider implementation using the official Groq Python SDK.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ):
        self._api_key = api_key or get_llm_api_key(provider="groq")
        self._model = model or get_llm_model(default="llama-3.3-70b-versatile")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = None

        if not self._api_key or not self._api_key.strip():
            raise LLMAuthenticationError(
                "LLM API key is not configured.\n"
                "Please configure the required environment variable."
            )

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self):
        """Lazy initialization of Groq SDK client."""
        if self._client is None:
            try:
                from groq import Groq
                self._client = Groq(
                    api_key=self._api_key,
                    timeout=self._timeout,
                )
            except ImportError as e:
                raise LLMProviderError(
                    f"Groq SDK is not installed. Run 'pip install groq' to enable it: {e}"
                ) from e
            except Exception as e:
                raise LLMProviderError(f"Failed to initialize Groq client: {e}") from e
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Executes a completion request against Groq with bounded retry and error mapping.
        """
        if not prompt or not prompt.strip():
            raise LLMProviderError("Cannot generate response for an empty prompt.")

        messages = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": prompt})

        client = self._get_client()

        # Import groq exception classes safely
        try:
            from groq import (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                AuthenticationError,
                RateLimitError,
            )
        except ImportError:
            AuthenticationError = Exception
            RateLimitError = Exception
            APITimeoutError = Exception
            APIConnectionError = Exception
            APIStatusError = Exception

        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                chat_completion = client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=0.1,
                )

                if not chat_completion.choices:
                    raise LLMEmptyResponseError("LLM provider returned no completion choices.")

                choice = chat_completion.choices[0]
                content = choice.message.content

                if not content or not content.strip():
                    raise LLMEmptyResponseError("LLM provider returned an empty response.")

                return content.strip()

            except AuthenticationError as e:
                # Do not retry authentication failures
                raise LLMAuthenticationError(
                    f"Groq API authentication failed. Check your API key: {e}"
                ) from e
            except RateLimitError as e:
                last_error = LLMRateLimitError(f"Groq API rate limit reached: {e}")
                if attempt < self._max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise last_error from e
            except APITimeoutError as e:
                last_error = LLMTimeoutError(f"Groq API request timed out after {self._timeout}s: {e}")
                if attempt < self._max_retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise last_error from e
            except (APIConnectionError, APIStatusError) as e:
                last_error = LLMProviderError(f"Groq API communication error: {e}")
                if attempt < self._max_retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise last_error from e
            except LLMError:
                raise
            except Exception as e:
                raise LLMProviderError(f"Unexpected error communicating with Groq: {e}") from e

        if last_error:
            raise last_error
        raise LLMProviderError("Failed to generate response after maximum retries.")


def create_llm_provider(
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMProvider:
    """
    Factory function to instantiate the configured LLMProvider.

    Args:
        provider_name: Name of the provider ('groq', etc.). Defaults to config.
        model: Optional model name. Defaults to config.
        api_key: Optional API key. Defaults to config / environment.

    Returns:
        Instance of LLMProvider.
    """
    selected_provider = (provider_name or get_llm_provider()).lower().strip()
    selected_model = model or get_llm_model()

    if selected_provider == "groq":
        return GroqProvider(
            api_key=api_key,
            model=selected_model,
        )
    else:
        raise LLMProviderError(
            f"Unsupported LLM provider '{selected_provider}'. "
            f"Currently supported providers: 'groq'."
        )
