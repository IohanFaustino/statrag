"""Tests for the LLM router (no real API calls)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.chat.llm.deepseek_client import DeepSeekChat
from src.services.chat.llm.groq_client import GroqChat
from src.services.chat.llm.openai_client import OpenAIChat
from src.services.chat.llm.router import GROQ_MODEL_IDS, get_llm, list_providers


# ---------------------------------------------------------------------------
# Helpers — prevent real SDK instantiation during tests
# ---------------------------------------------------------------------------


def _mock_openai_client() -> MagicMock:
    """Return a mock that satisfies openai.AsyncOpenAI construction."""
    return MagicMock()


# ---------------------------------------------------------------------------
# get_llm routing
# ---------------------------------------------------------------------------


def test_get_llm_gpt_returns_openai_chat() -> None:
    """get_llm with a GPT model ID should return an OpenAIChat instance."""
    with patch("src.services.chat.llm.openai_client.openai.AsyncOpenAI", return_value=_mock_openai_client()):
        client, model_id = get_llm("gpt-4o")

    assert isinstance(client, OpenAIChat)
    assert model_id == "gpt-4o"


def test_get_llm_deepseek_returns_deepseek_chat() -> None:
    """get_llm with a deepseek model ID should return a DeepSeekChat instance."""
    with (
        patch("src.services.chat.llm.deepseek_client.openai.AsyncOpenAI", return_value=_mock_openai_client()),
        patch("src.services.chat.llm.deepseek_client.settings") as mock_settings,
    ):
        mock_settings.deepseek_api_key = "sk-test-fake"
        mock_settings.deepseek_base_url = "https://api.deepseek.com/v1"
        client, model_id = get_llm("deepseek-chat")

    assert isinstance(client, DeepSeekChat)
    assert model_id == "deepseek-chat"


def test_get_llm_groq_returns_groq_chat() -> None:
    """Groq-listed model IDs should route to GroqChat."""
    with (
        patch("src.services.chat.llm.groq_client.openai.AsyncOpenAI", return_value=_mock_openai_client()),
        patch("src.services.chat.llm.groq_client.settings") as mock_settings,
    ):
        mock_settings.groq_api_key = "gsk-test-fake"
        mock_settings.groq_base_url = "https://api.groq.com/openai/v1"
        client, model_id = get_llm("meta-llama/llama-4-scout-17b-16e-instruct")

    assert isinstance(client, GroqChat)
    assert model_id == "meta-llama/llama-4-scout-17b-16e-instruct"


def test_get_llm_groq_gpt_oss_routes_to_groq_not_openai() -> None:
    """openai/gpt-oss-* IDs share an OpenAI-shaped prefix but are Groq-hosted."""
    with (
        patch("src.services.chat.llm.groq_client.openai.AsyncOpenAI", return_value=_mock_openai_client()),
        patch("src.services.chat.llm.groq_client.settings") as mock_settings,
    ):
        mock_settings.groq_api_key = "gsk-test-fake"
        mock_settings.groq_base_url = "https://api.groq.com/openai/v1"
        client, model_id = get_llm("openai/gpt-oss-120b")

    assert isinstance(client, GroqChat)
    assert model_id == "openai/gpt-oss-120b"


def test_get_llm_unknown_falls_back_to_openai() -> None:
    """An unrecognised model ID (not starting with 'deepseek') uses OpenAIChat."""
    with patch("src.services.chat.llm.openai_client.openai.AsyncOpenAI", return_value=_mock_openai_client()):
        client, model_id = get_llm("some-future-model")

    assert isinstance(client, OpenAIChat)
    assert model_id == "some-future-model"


# ---------------------------------------------------------------------------
# list_providers registry
# ---------------------------------------------------------------------------


def test_list_providers_returns_five_providers() -> None:
    """list_providers should return exactly 5 providers."""
    providers = list_providers()
    assert len(providers) == 5


def test_list_providers_ids() -> None:
    """Provider IDs must be 'openai', 'deepseek', 'groq', 'google', 'alibaba'."""
    ids = {p.id for p in list_providers()}
    assert ids == {"openai", "deepseek", "groq", "google", "alibaba"}


def test_list_providers_non_empty_models() -> None:
    """Every provider must expose at least one model."""
    for provider in list_providers():
        assert len(provider.models) > 0, f"Provider {provider.id!r} has no models"


def test_list_providers_openai_model_count() -> None:
    """OpenAI provider should have exactly 4 models."""
    openai_provider = next(p for p in list_providers() if p.id == "openai")
    assert len(openai_provider.models) == 4


def test_list_providers_deepseek_model_count() -> None:
    """DeepSeek provider should have exactly 3 models."""
    deepseek_provider = next(p for p in list_providers() if p.id == "deepseek")
    assert len(deepseek_provider.models) == 3


def test_list_providers_groq_model_count() -> None:
    """Groq provider should have exactly 4 models."""
    groq_provider = next(p for p in list_providers() if p.id == "groq")
    assert len(groq_provider.models) == 4


def test_groq_model_ids_match_provider_registry() -> None:
    """GROQ_MODEL_IDS routing set must match the registry exactly."""
    groq_provider = next(p for p in list_providers() if p.id == "groq")
    registry_ids = {m.id for m in groq_provider.models}
    assert registry_ids == GROQ_MODEL_IDS


def test_list_providers_model_fields_populated() -> None:
    """Every model should have non-empty id, name, tagline, cost, speed, ctx."""
    for provider in list_providers():
        for model in provider.models:
            assert model.id, f"Model id empty in provider {provider.id!r}"
            assert model.name, f"Model name empty for {model.id!r}"
            assert model.tagline, f"Model tagline empty for {model.id!r}"
            assert model.cost, f"Model cost empty for {model.id!r}"
            assert model.speed, f"Model speed empty for {model.id!r}"
            assert model.ctx, f"Model ctx empty for {model.id!r}"
