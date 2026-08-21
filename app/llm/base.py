"""
LLM Provider Base Interfaces, Exception Hierarchy, and Chat Models.

Defines the abstract contract for LLM providers, tool call models, and custom domain exceptions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from typing import Any, Dict, List, Optional


import re

def strip_thinking_and_tool_tags(text: Optional[str]) -> str:
    """Removes internal <think>...</think> and <tool_call>...</tool_call> markup from text."""
    if not text:
        return ""
    cleaned = text
    # Strip complete <think>...</think> blocks
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    # Strip unclosed <think>... blocks
    cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    # Strip complete <tool_call>...</tool_call> blocks
    cleaned = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", cleaned, flags=re.IGNORECASE)
    # Strip unclosed <tool_call>... blocks
    cleaned = re.sub(r"<tool_call>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    # Strip function / parameter xml tags
    cleaned = re.sub(r"<function=[^>]*>[\s\S]*?</function>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<parameter=[^>]*>[\s\S]*?</parameter>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?(?:think|tool_call|function|parameter)[^>]*>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


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


@dataclass
class ToolCall:
    """Represents a tool invocation requested by the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }


@dataclass
class LLMChatResponse:
    """Represents the raw response from an LLM chat/completion call."""
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: Optional[str] = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


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

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMChatResponse:
        """
        Executes a chat completion request, optionally with tool definitions.
        Default implementation converts messages to prompt and delegates to generate().
        """
        prompt_parts = []
        system_prompt = None
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system_prompt = content
            else:
                prompt_parts.append(f"{role}: {content}")
        full_prompt = "\n\n".join(prompt_parts)
        text = self.generate(prompt=full_prompt, system_prompt=system_prompt)
        return LLMChatResponse(content=text)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generates text completion from the LLM provider.
        Maintains backward compatibility with v0.7 RAG pipeline.
        """
        if not prompt or not prompt.strip():
            raise LLMProviderError("Cannot generate response for an empty prompt.")

        messages = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": prompt.strip()})

        response = self.chat(messages=messages)
        if not response.content or not response.content.strip():
            raise LLMEmptyResponseError("LLM provider returned an empty response.")

        return response.content.strip()
