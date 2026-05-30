"""Google Gemini streaming LLM client for the chat service.

Gemini exposes an OpenAI-compatible Chat Completions endpoint at
``https://generativelanguage.googleapis.com/v1beta/openai/``, so this client
reuses the ``openai`` SDK pointed at that base URL — identical pattern to
``GroqChat`` and ``DeepSeekChat``.

Structured output via ``response_format`` is passed through verbatim; the
caller falls back to the JSON-repair path if the Gemini compat layer rejects
the schema (same safety net as DeepSeek).
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import openai

from src.core.config import settings
from src.services.chat.llm.base import BaseLLM, ChatMessage, LLMError

logger = logging.getLogger(__name__)


def _build_response_format(schema: object | None) -> dict | None:
    """Translate a Pydantic schema class (or already-built dict) into a
    ``response_format`` payload accepted by the Gemini OpenAI-compat layer.

    Mirrors :func:`groq_client._build_response_format` exactly — ``strict=False``
    to avoid schema-feature rejections on the compat endpoint.
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


class GeminiChat(BaseLLM):
    """Streaming client backed by the Google Gemini Chat API (OpenAI-compatible)."""

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY missing")
        self._client = openai.AsyncOpenAI(
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
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
        """Yield delta content strings from a streaming Gemini completion."""
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
            "GeminiChat.stream model=%s msgs=%d response_format=%s",
            model, len(messages), "yes" if rf else "no",
        )
        try:
            async with await self._client.chat.completions.create(**kwargs) as response:
                async for chunk in response:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield delta
        except openai.OpenAIError as exc:
            raise LLMError(f"Gemini API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error from Gemini client: {exc}") from exc
