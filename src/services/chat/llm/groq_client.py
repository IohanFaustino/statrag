"""Groq streaming LLM client for the chat service.

Groq exposes an OpenAI-compatible Chat Completions API, so this client reuses
the ``openai`` SDK pointed at the Groq base URL. Unlike DeepSeek, Groq supports
native ``response_format`` (json_object + json_schema) so structured output is
passed through verbatim.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import openai

from src.core.config import settings
from src.services.chat.llm.base import BaseLLM, ChatMessage, LLMError

logger = logging.getLogger(__name__)


def _build_response_format(schema: object | None) -> dict | None:
    """Translate a Pydantic schema class (or already-built dict) into a Groq
    ``response_format`` payload.

    Groq accepts ``{"type": "json_object"}`` universally and
    ``{"type": "json_schema", ...}`` on supported models. Mirrors the OpenAI
    client helper but with ``strict=False`` to avoid schema-feature rejections.
    """
    if schema is None:
        return None
    if isinstance(schema, dict):
        return schema
    name = getattr(schema, "__name__", "Output")
    try:
        json_schema = schema.model_json_schema()  # type: ignore[attr-defined]
    except AttributeError:
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": json_schema,
            "strict": False,
        },
    }


class GroqChat(BaseLLM):
    """Streaming client backed by the Groq Chat API (OpenAI-compatible)."""

    def __init__(self) -> None:
        if not settings.groq_api_key:
            raise LLMError("GROQ_API_KEY missing")
        self._client = openai.AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: object | None = None,
    ) -> AsyncIterator[str]:
        """Yield delta content strings from a streaming Groq completion."""
        payload = [{"role": m.role, "content": m.content} for m in messages]
        kwargs: dict = {
            "model": model,
            "messages": payload,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        rf = _build_response_format(response_format)
        if rf is not None:
            kwargs["response_format"] = rf

        logger.debug(
            "GroqChat.stream model=%s msgs=%d response_format=%s",
            model, len(messages), "yes" if rf else "no",
        )
        try:
            async with await self._client.chat.completions.create(**kwargs) as response:
                async for chunk in response:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield delta
        except openai.OpenAIError as exc:
            raise LLMError(f"Groq API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error from Groq client: {exc}") from exc
