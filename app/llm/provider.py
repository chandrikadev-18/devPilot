"""
LLM Provider Implementations and Factory Function.

Contains Groq provider implementation with tool calling support, error translation,
bounded retries, and API key protection.
"""

import json
import time
from typing import Any, Dict, List, Optional

from app.config import (
    get_llm_api_key,
    get_llm_model,
    get_llm_provider,
)
from app.llm.base import (
    LLMAuthenticationError,
    LLMChatResponse,
    LLMEmptyResponseError,
    LLMError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    ToolCall,
)


class GroqProvider(LLMProvider):
    """
    Groq LLM Provider implementation using the official Groq Python SDK.
    Supports chat completion and native OpenAI-compatible tool/function calling.
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

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMChatResponse:
        """
        Executes a chat completion request against Groq, optionally providing tool definitions.
        """
        if not messages:
            raise LLMProviderError("Cannot execute chat request with empty messages list.")

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

        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                chat_completion = client.chat.completions.create(**kwargs)

                if not chat_completion.choices:
                    raise LLMEmptyResponseError("LLM provider returned no completion choices.")

                choice = chat_completion.choices[0]
                message = choice.message

                parsed_tool_calls: Optional[List[ToolCall]] = None
                raw_tool_calls = getattr(message, "tool_calls", None)
                if raw_tool_calls:
                    parsed_tool_calls = []
                    for raw_tc in raw_tool_calls:
                        tc_id = getattr(raw_tc, "id", f"call_{int(time.time()*1000)}")
                        fn_obj = getattr(raw_tc, "function", None)
                        fn_name = getattr(fn_obj, "name", "") if fn_obj else ""
                        fn_args_raw = getattr(fn_obj, "arguments", "{}") if fn_obj else "{}"

                        if isinstance(fn_args_raw, str):
                            try:
                                fn_args = json.loads(fn_args_raw)
                            except Exception:
                                fn_args = {"raw_input": fn_args_raw}
                        elif isinstance(fn_args_raw, dict):
                            fn_args = fn_args_raw
                        else:
                            fn_args = {}

                        parsed_tool_calls.append(
                            ToolCall(
                                id=tc_id,
                                name=fn_name,
                                arguments=fn_args,
                            )
                        )

                content = getattr(message, "content", None)

                return LLMChatResponse(
                    content=content,
                    tool_calls=parsed_tool_calls,
                    finish_reason=getattr(choice, "finish_reason", None),
                )

            except AuthenticationError as e:
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
