"""DeepSeek streaming LLM client for the chat service.

DeepSeek exposes an OpenAI-compatible Chat Completions API, so this client
reuses the ``openai`` SDK pointed at the DeepSeek base URL.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import openai

from src.core.config import settings
from src.services.chat.llm.base import BaseLLM, ChatMessage, LLMError

logger = logging.getLogger(__name__)


class DeepSeekChat(BaseLLM):
    """Streaming client backed by the DeepSeek Chat API (OpenAI-compatible)."""

    def __init__(self) -> None:
        if not settings.deepseek_api_key:
            raise LLMError("DEEPSEEK_API_KEY missing")
        self._client = openai.AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: object | None = None,  # noqa: ARG002 — DeepSeek ignores native JSON-schema; orchestrator falls back to repair retry
    ) -> AsyncIterator[str]:
        """Yield delta content strings from a streaming DeepSeek completion.

        Args:
            messages: Ordered conversation history.
            model: DeepSeek model identifier (e.g. "deepseek-chat").
            temperature: Sampling temperature.
            max_tokens: Optional token ceiling.

        Yields:
            Incremental text fragments from the assistant turn.

        Raises:
            LLMError: Wraps any ``openai.OpenAIError`` or unexpected exception.
        """
        payload = [{"role": m.role, "content": m.content} for m in messages]
        kwargs: dict = {
            "model": model,
            "messages": payload,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        logger.debug("DeepSeekChat.stream model=%s msgs=%d", model, len(messages))
        try:
            async with await self._client.chat.completions.create(**kwargs) as response:
                async for chunk in response:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield delta
        except openai.OpenAIError as exc:
            raise LLMError(f"DeepSeek API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error from DeepSeek client: {exc}") from exc
