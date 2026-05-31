"""Tests for Alibaba Qwen provider routing (no real API calls)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.chat.llm.base import LLMError
from src.services.chat.llm.qwen_client import QwenChat
from src.services.chat.llm.router import QWEN_MODEL_IDS, aclient_for, get_llm, list_providers

_QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


# ---------------------------------------------------------------------------
# QwenChat client
# ---------------------------------------------------------------------------


def test_qwen_chat_requires_api_key() -> None:
    """Instantiation must raise LLMError when QWEN_API_KEY is empty."""
    with patch("src.services.chat.llm.qwen_client.settings") as mock_settings:
        mock_settings.qwen_api_key = ""
        with pytest.raises(LLMError, match="QWEN_API_KEY missing"):
            QwenChat()


def test_qwen_chat_wires_base_url_and_key() -> None:
    """AsyncOpenAI must be constructed with the Qwen base URL + key."""
    fake_client = MagicMock()
    with (
        patch(
            "src.services.chat.llm.qwen_client.openai.AsyncOpenAI",
            return_value=fake_client,
        ) as mock_ctor,
        patch("src.services.chat.llm.qwen_client.settings") as mock_settings,
    ):
        mock_settings.qwen_api_key = "sk-FakeQwenKey"
        mock_settings.qwen_base_url = _QWEN_BASE_URL
        QwenChat()

    mock_ctor.assert_called_once_with(
        api_key="sk-FakeQwenKey",
        base_url=_QWEN_BASE_URL,
    )


# ---------------------------------------------------------------------------
# get_llm routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model_id", sorted(QWEN_MODEL_IDS))
def test_get_llm_qwen_returns_qwen_chat(model_id: str) -> None:
    """get_llm('qwen-*') must return a QwenChat instance."""
    with (
        patch(
            "src.services.chat.llm.qwen_client.openai.AsyncOpenAI",
            return_value=MagicMock(),
        ),
        patch("src.services.chat.llm.qwen_client.settings") as mock_settings,
    ):
        mock_settings.qwen_api_key = "sk-FakeQwenKey"
        mock_settings.qwen_base_url = _QWEN_BASE_URL
        client, returned_id = get_llm(model_id)

    assert isinstance(client, QwenChat)
    assert returned_id == model_id


# ---------------------------------------------------------------------------
# aclient_for routing
# ---------------------------------------------------------------------------


def test_aclient_for_qwen_returns_qwen_backed_client() -> None:
    """aclient_for('qwen-plus') must return an AsyncOpenAI client pointed at
    the Qwen base URL."""
    fake_client = MagicMock()
    with (
        patch(
            "src.services.chat.llm.router.openai.AsyncOpenAI",
            return_value=fake_client,
        ) as mock_ctor,
        patch("src.services.chat.llm.router.settings") as mock_settings,
    ):
        mock_settings.qwen_api_key = "sk-FakeQwenKey"
        mock_settings.qwen_base_url = _QWEN_BASE_URL
        # Ensure groq / deepseek / gemini branches are not triggered
        mock_settings.groq_api_key = ""
        mock_settings.deepseek_api_key = ""
        mock_settings.gemini_api_key = ""
        result = aclient_for("qwen-plus")

    assert result is fake_client
    mock_ctor.assert_called_once_with(
        api_key="sk-FakeQwenKey",
        base_url=_QWEN_BASE_URL,
    )


def test_aclient_for_qwen_missing_key_raises_llm_error() -> None:
    """aclient_for must raise LLMError when QWEN_API_KEY is empty."""
    with patch("src.services.chat.llm.router.settings") as mock_settings:
        mock_settings.qwen_api_key = ""
        # not empty, so earlier branches won't fire
        mock_settings.groq_api_key = "x"
        mock_settings.deepseek_api_key = "x"
        mock_settings.gemini_api_key = "x"
        with pytest.raises(LLMError, match="QWEN_API_KEY missing"):
            aclient_for("qwen-plus")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_list_providers_includes_alibaba() -> None:
    """list_providers must include an 'alibaba' provider."""
    ids = {p.id for p in list_providers()}
    assert "alibaba" in ids


def test_alibaba_provider_has_three_models() -> None:
    """Alibaba provider must expose exactly 3 models."""
    alibaba = next(p for p in list_providers() if p.id == "alibaba")
    assert len(alibaba.models) == 3


def test_alibaba_provider_model_ids() -> None:
    """Alibaba provider model IDs must be qwen-plus, qwen-max and qwen-turbo."""
    alibaba = next(p for p in list_providers() if p.id == "alibaba")
    ids = {m.id for m in alibaba.models}
    assert ids == {"qwen-plus", "qwen-max", "qwen-turbo"}


def test_qwen_model_ids_match_provider_registry() -> None:
    """QWEN_MODEL_IDS routing set must match the alibaba provider registry."""
    alibaba = next(p for p in list_providers() if p.id == "alibaba")
    registry_ids = {m.id for m in alibaba.models}
    assert registry_ids == QWEN_MODEL_IDS
