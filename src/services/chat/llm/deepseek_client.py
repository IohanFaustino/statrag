"""DeepSeek streaming LLM client for the chat service.

DeepSeek exposes an OpenAI-compatible Chat Completions API, so this client
reuses the ``openai`` SDK pointed at the DeepSeek base URL.
"""
from __future__ import annotations

import logging
import os
from typing import AsyncIterator

import openai

from src.core.config import settings
from src.services.chat.llm.base import BaseLLM, ChatMessage, LLMError

logger = logging.getLogger(__name__)


def _thinking_extra_body(model: str) -> dict | None:
    """Return an ``extra_body`` payload that disables DeepSeek thinking, or None.

    DeepSeek v4 ids (``deepseek-v4-pro``, ``deepseek-chat``) default to THINKING
    mode: they burn the output budget on hidden reasoning and return empty
    ``content`` on the structured draft path (see memory
    ``deepseek-model-unreachable``). Disabling thinking makes them usable as a
    fast draft model. ``deepseek-reasoner`` is a genuine chain-of-thought model
    where thinking is the point, so it is exempt.

    Gated by ``DEEPSEEK_DISABLE_THINKING`` (default ``"1"``); set to ``"0"`` to
    leave thinking untouched for every model.
    """
    if os.environ.get("DEEPSEEK_DISABLE_THINKING", "1") != "1":
        return None
    if model == "deepseek-reasoner":
        return None
    return {"thinking": {"type": "disabled"}}


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
        extra_body = _thinking_extra_body(model)
        if extra_body is not None:
            kwargs["extra_body"] = extra_body

        logger.debug(
            "DeepSeekChat.stream model=%s msgs=%d thinking_disabled=%s",
            model, len(messages), extra_body is not None,
        )
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
