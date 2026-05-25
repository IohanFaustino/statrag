"""LLM router: maps model IDs to concrete client instances.

Routing rule
------------
- Model ID starts with ``"deepseek"``  →  :class:`DeepSeekChat`
- Anything else (``"gpt-*"`` or unknown)  →  :class:`OpenAIChat`

Public API
----------
``get_llm(model_id)``   Returns ``(client, model_id)`` ready for streaming.
``list_providers()``    Returns the static provider/model registry.
``router``              FastAPI ``APIRouter`` with ``GET /models``.
"""
from __future__ import annotations

import openai
from fastapi import APIRouter

from src.core.config import settings
from src.services.chat.llm.base import BaseLLM, LLMError
from src.services.chat.llm.deepseek_client import DeepSeekChat
from src.services.chat.llm.groq_client import GroqChat
from src.services.chat.llm.openai_client import OpenAIChat
from src.services.chat.schemas import Model, ModelProvider

# ---------------------------------------------------------------------------
# Static provider / model registry
# ---------------------------------------------------------------------------

_PROVIDERS: list[ModelProvider] = [
    ModelProvider(
        id="openai",
        name="OpenAI",
        short="OAI",
        color="#10A37F",
        models=[
            Model(
                id="gpt-4o",
                name="GPT-4o",
                tagline="Multimodal flagship",
                cost="$$$",
                speed="fast",
                ctx="128k",
            ),
            Model(
                id="gpt-4o-mini",
                name="GPT-4o mini",
                tagline="Cheap + fast",
                cost="$",
                speed="fast",
                ctx="128k",
            ),
            Model(
                id="gpt-5.4-nano-2026-03-17",
                name="GPT-5.4 nano",
                tagline="Project default — cheap nano",
                cost="$",
                speed="fast",
                ctx="200k",
            ),
            Model(
                id="gpt-5.4-2026-03-05",
                name="GPT-5.4",
                tagline="Full reasoning",
                cost="$$$$",
                speed="med",
                ctx="400k",
            ),
        ],
    ),
    ModelProvider(
        id="deepseek",
        name="DeepSeek",
        short="DS",
        color="#4D6BFE",
        models=[
            Model(
                id="deepseek-chat",
                name="DeepSeek Chat",
                tagline="General purpose",
                cost="$",
                speed="fast",
                ctx="128k",
            ),
            Model(
                id="deepseek-reasoner",
                name="DeepSeek Reasoner",
                tagline="Chain-of-thought",
                cost="$$",
                speed="slow",
                ctx="128k",
            ),
            Model(
                id="deepseek-v4-pro",
                name="DeepSeek V4 Pro",
                tagline="Latest pro tier",
                cost="$$",
                speed="med",
                ctx="128k",
            ),
        ],
    ),
    ModelProvider(
        id="groq",
        name="Groq",
        short="GQ",
        color="#F55036",
        models=[
            Model(
                id="meta-llama/llama-4-scout-17b-16e-instruct",
                name="Llama 4 Scout 17B",
                tagline="Groq default — fast multimodal",
                cost="$",
                speed="fast",
                ctx="128k",
            ),
            Model(
                id="llama-3.3-70b-versatile",
                name="Llama 3.3 70B",
                tagline="Versatile large",
                cost="$",
                speed="fast",
                ctx="128k",
            ),
            Model(
                id="openai/gpt-oss-120b",
                name="GPT-OSS 120B",
                tagline="Open-weight flagship",
                cost="$$",
                speed="fast",
                ctx="128k",
            ),
            Model(
                id="openai/gpt-oss-20b",
                name="GPT-OSS 20B",
                tagline="Open-weight small",
                cost="$",
                speed="fast",
                ctx="128k",
            ),
        ],
    ),
]


# Explicit set of model IDs routed to Groq. Membership avoids prefix collisions
# (e.g. ``openai/gpt-oss-*`` shares the ``openai/`` prefix with OpenAI-hosted IDs).
GROQ_MODEL_IDS: set[str] = {
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
}


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------


def get_llm(model_id: str) -> tuple[BaseLLM, str]:
    """Return a concrete LLM client paired with the model identifier to use.

    Routing rule: model IDs that start with ``"deepseek"`` are dispatched to
    :class:`DeepSeekChat`; everything else goes to :class:`OpenAIChat`.

    Args:
        model_id: The model string chosen by the caller (e.g. ``"gpt-4o"``
            or ``"deepseek-chat"``).

    Returns:
        A ``(client, model_id)`` tuple where *client* is a fresh
        :class:`BaseLLM` instance ready for streaming.
    """
    if model_id.startswith("deepseek"):
        return DeepSeekChat(), model_id
    if model_id in GROQ_MODEL_IDS:
        return GroqChat(), model_id
    return OpenAIChat(), model_id


def aclient_for(model_id: str | None) -> openai.AsyncOpenAI:
    """Return an ``openai.AsyncOpenAI`` client wired to the provider that
    hosts ``model_id``.

    Used by stage-internal code (deep_tutor, orchestrator_workers, coverage,
    image_judge, etc.) that calls ``client.chat.completions.create(model=...)``
    directly instead of through the streaming :class:`BaseLLM` clients. The
    same membership/prefix rules as :func:`get_llm` apply.

    Args:
        model_id: Model identifier (None falls back to OpenAI default key).

    Returns:
        AsyncOpenAI client with the correct ``base_url`` + ``api_key`` for the
        provider that hosts ``model_id``.

    Raises:
        LLMError: When the chosen provider's API key is missing.
    """
    if model_id and model_id in GROQ_MODEL_IDS:
        if not settings.groq_api_key:
            raise LLMError("GROQ_API_KEY missing")
        return openai.AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )
    if model_id and model_id.startswith("deepseek"):
        if not settings.deepseek_api_key:
            raise LLMError("DEEPSEEK_API_KEY missing")
        return openai.AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
    return openai.AsyncOpenAI(api_key=settings.openai_api_key)


def list_providers() -> list[ModelProvider]:
    """Return the full provider/model registry.

    Returns:
        A list of :class:`ModelProvider` objects describing every available
        provider and its associated models.
    """
    return _PROVIDERS


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter()


@router.get("/models", response_model=list[ModelProvider])
async def get_models() -> list[ModelProvider]:
    """Return all available LLM providers and their models."""
    return list_providers()
