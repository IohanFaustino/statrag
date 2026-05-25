"""OpenAI streaming LLM client for the chat service."""
from __future__ import annotations

import logging
from typing import AsyncIterator

import openai

from src.core.config import settings
from src.services.chat.llm.base import BaseLLM, ChatMessage, LLMError

logger = logging.getLogger(__name__)


def _build_response_format(schema: object | None) -> dict | None:
    """Translate a Pydantic schema class (or already-built dict) into the
    OpenAI ``response_format`` payload.

    T06 (ADR-008): when a mode declares an ``output_schema``, ask the API to
    enforce it at decode time so the model output never needs the legacy
    repair retry. Accepts either a Pydantic BaseModel class or a pre-built
    ``{"type": "json_schema", "json_schema": {...}}`` dict.

    Args:
        schema: Pydantic class or raw response_format dict, or ``None``.

    Returns:
        OpenAI response_format payload, or ``None`` when *schema* is ``None``.
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
            "strict": False,  # strict mode disallows many valid pydantic schemas
        },
    }


class OpenAIChat(BaseLLM):
    """Streaming client backed by the OpenAI Chat Completions API."""

    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: object | None = None,
    ) -> AsyncIterator[str]:
        """Yield delta content strings from a streaming OpenAI completion.

        Args:
            messages: Ordered conversation history.
            model: OpenAI model identifier (e.g. "gpt-4o").
            temperature: Sampling temperature.
            max_tokens: Optional token ceiling.
            response_format: Optional Pydantic schema class or pre-built
                ``response_format`` dict. When supplied, the API enforces
                the schema at decode time (T06, ADR-008).

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
        rf = _build_response_format(response_format)
        if rf is not None:
            kwargs["response_format"] = rf

        logger.debug(
            "OpenAIChat.stream model=%s msgs=%d response_format=%s",
            model, len(messages), "yes" if rf else "no",
        )
        try:
            async with await self._client.chat.completions.create(**kwargs) as response:
                async for chunk in response:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield delta
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error from OpenAI client: {exc}") from exc
