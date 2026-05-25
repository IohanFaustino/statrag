"""Base abstractions for LLM clients used by the chat service."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


class LLMError(RuntimeError):
    """Raised when an LLM provider call fails."""


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str


class BaseLLM(ABC):
    """Abstract base for streaming LLM clients."""

    @abstractmethod
    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: object | None = None,
    ) -> AsyncIterator[str]:
        """Yield incremental text deltas from the model.

        Args:
            messages: Ordered conversation history.
            model: Model identifier string passed to the provider.
            temperature: Sampling temperature (0.0 = deterministic).
            max_tokens: Optional cap on generated tokens.

        Yields:
            String fragments as they arrive from the API.

        Raises:
            LLMError: On any provider-side error.
        """
        ...
