"""Provider factory for LLM enrichment.

Both OpenAI and DeepSeek expose an OpenAI-compatible chat API, so we use
`langchain_openai.ChatOpenAI` for both — DeepSeek is wired via `base_url`.

Selection:
    get_llm("openai")    -> gpt-5.4-nano-2026-03-17
    get_llm("deepseek")  -> deepseek-v4-pro
    get_llm()            -> settings.default_provider
"""
from __future__ import annotations

import logging
from typing import Literal

from langchain_openai import ChatOpenAI

from src.core.config import settings

logger = logging.getLogger(__name__)

Provider = Literal["openai", "deepseek"]


def get_llm(provider: Provider | None = None, *, temperature: float = 0.0) -> ChatOpenAI:
    """Return a ChatOpenAI client wired to the chosen provider."""
    chosen: Provider = provider or settings.default_provider  # type: ignore[assignment]
    if chosen == "deepseek":
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY missing in environment.")
        logger.info("LLM provider=deepseek model=%s", settings.deepseek_model)
        return ChatOpenAI(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=temperature,
        )
    if chosen == "openai":
        logger.info("LLM provider=openai model=%s", settings.openai_model_nano)
        return ChatOpenAI(
            model=settings.openai_model_nano,
            api_key=settings.openai_api_key,
            temperature=temperature,
        )
    raise ValueError(f"Unknown provider: {chosen}")
