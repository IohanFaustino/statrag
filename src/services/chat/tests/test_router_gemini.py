"""Tests for Gemini provider routing (no real API calls)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.chat.llm.base import LLMError
from src.services.chat.llm.gemini_client import GeminiChat
from src.services.chat.llm.router import GEMINI_MODEL_IDS, aclient_for, get_llm, list_providers


# ---------------------------------------------------------------------------
# GeminiChat client
# ---------------------------------------------------------------------------


def test_gemini_chat_requires_api_key() -> None:
    """Instantiation must raise LLMError when GEMINI_API_KEY is empty."""
    with patch("src.services.chat.llm.gemini_client.settings") as mock_settings:
        mock_settings.gemini_api_key = ""
        with pytest.raises(LLMError, match="GEMINI_API_KEY missing"):
            GeminiChat()


def test_gemini_chat_wires_base_url_and_key() -> None:
    """AsyncOpenAI must be constructed with the Gemini base URL + key."""
    fake_client = MagicMock()
    with (
        patch(
            "src.services.chat.llm.gemini_client.openai.AsyncOpenAI",
            return_value=fake_client,
        ) as mock_ctor,
        patch("src.services.chat.llm.gemini_client.settings") as mock_settings,
    ):
        mock_settings.gemini_api_key = "AIzaFakeKey"
        mock_settings.gemini_base_url = (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        GeminiChat()

    mock_ctor.assert_called_once_with(
        api_key="AIzaFakeKey",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )


# ---------------------------------------------------------------------------
# get_llm routing
# ---------------------------------------------------------------------------


def test_get_llm_gemini_flash_returns_gemini_chat() -> None:
    """get_llm('gemini-2.5-flash') must return a GeminiChat instance."""
    with (
        patch(
            "src.services.chat.llm.gemini_client.openai.AsyncOpenAI",
            return_value=MagicMock(),
        ),
        patch("src.services.chat.llm.gemini_client.settings") as mock_settings,
    ):
        mock_settings.gemini_api_key = "AIzaFakeKey"
        mock_settings.gemini_base_url = (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        client, model_id = get_llm("gemini-2.5-flash")

    assert isinstance(client, GeminiChat)
    assert model_id == "gemini-2.5-flash"


def test_get_llm_gemini_pro_returns_gemini_chat() -> None:
    """get_llm('gemini-2.5-pro') must return a GeminiChat instance."""
    with (
        patch(
            "src.services.chat.llm.gemini_client.openai.AsyncOpenAI",
            return_value=MagicMock(),
        ),
        patch("src.services.chat.llm.gemini_client.settings") as mock_settings,
    ):
        mock_settings.gemini_api_key = "AIzaFakeKey"
        mock_settings.gemini_base_url = (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        client, model_id = get_llm("gemini-2.5-pro")

    assert isinstance(client, GeminiChat)
    assert model_id == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# aclient_for routing
# ---------------------------------------------------------------------------


def test_aclient_for_gemini_returns_gemini_backed_client() -> None:
    """aclient_for('gemini-2.5-flash') must return an AsyncOpenAI client
    pointed at the Gemini base URL."""
    fake_client = MagicMock()
    with (
        patch(
            "src.services.chat.llm.router.openai.AsyncOpenAI",
            return_value=fake_client,
        ) as mock_ctor,
        patch("src.services.chat.llm.router.settings") as mock_settings,
    ):
        mock_settings.gemini_api_key = "AIzaFakeKey"
        mock_settings.gemini_base_url = (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        # Ensure groq / deepseek branches are not triggered
        mock_settings.groq_api_key = ""
        mock_settings.deepseek_api_key = ""
        result = aclient_for("gemini-2.5-flash")

    assert result is fake_client
    mock_ctor.assert_called_once_with(
        api_key="AIzaFakeKey",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )


def test_aclient_for_gemini_missing_key_raises_llm_error() -> None:
    """aclient_for must raise LLMError when GEMINI_API_KEY is empty."""
    with (
        patch("src.services.chat.llm.router.settings") as mock_settings,
    ):
        mock_settings.gemini_api_key = ""
        mock_settings.groq_api_key = "x"  # not empty, so groq branch won't fire
        with pytest.raises(LLMError, match="GEMINI_API_KEY missing"):
            aclient_for("gemini-2.5-flash")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_list_providers_includes_google() -> None:
    """list_providers must include a 'google' provider."""
    ids = {p.id for p in list_providers()}
    assert "google" in ids


def test_google_provider_has_two_models() -> None:
    """Google provider must expose exactly 2 models."""
    google = next(p for p in list_providers() if p.id == "google")
    assert len(google.models) == 2


def test_google_provider_model_ids() -> None:
    """Google provider model IDs must be gemini-2.5-flash and gemini-2.5-pro."""
    google = next(p for p in list_providers() if p.id == "google")
    ids = {m.id for m in google.models}
    assert ids == {"gemini-2.5-flash", "gemini-2.5-pro"}


def test_gemini_model_ids_match_provider_registry() -> None:
    """GEMINI_MODEL_IDS routing set must match the google provider registry."""
    google = next(p for p in list_providers() if p.id == "google")
    registry_ids = {m.id for m in google.models}
    assert registry_ids == GEMINI_MODEL_IDS
