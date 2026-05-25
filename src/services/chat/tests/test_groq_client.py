"""Unit tests for the Groq chat client (no real API calls)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.chat.llm.base import LLMError
from src.services.chat.llm.groq_client import GroqChat, _build_response_format


def test_groq_chat_requires_api_key() -> None:
    """Instantiation must raise LLMError when GROQ_API_KEY missing."""
    with patch("src.services.chat.llm.groq_client.settings") as mock_settings:
        mock_settings.groq_api_key = ""
        with pytest.raises(LLMError, match="GROQ_API_KEY missing"):
            GroqChat()


def test_groq_chat_wires_base_url_and_key() -> None:
    """AsyncOpenAI must be constructed with the Groq base URL + key."""
    fake_client = MagicMock()
    with (
        patch("src.services.chat.llm.groq_client.openai.AsyncOpenAI", return_value=fake_client) as mock_ctor,
        patch("src.services.chat.llm.groq_client.settings") as mock_settings,
    ):
        mock_settings.groq_api_key = "gsk-test-fake"
        mock_settings.groq_base_url = "https://api.groq.com/openai/v1"
        GroqChat()

    mock_ctor.assert_called_once_with(
        api_key="gsk-test-fake",
        base_url="https://api.groq.com/openai/v1",
    )


def test_build_response_format_passthrough_dict() -> None:
    """A pre-built dict (e.g. {'type': 'json_object'}) is returned as-is."""
    payload = {"type": "json_object"}
    assert _build_response_format(payload) is payload


def test_build_response_format_none_returns_none() -> None:
    assert _build_response_format(None) is None


def test_build_response_format_pydantic_schema() -> None:
    """A Pydantic class is translated into a json_schema payload."""
    from pydantic import BaseModel

    class Demo(BaseModel):
        x: int

    out = _build_response_format(Demo)
    assert out is not None
    assert out["type"] == "json_schema"
    assert out["json_schema"]["name"] == "Demo"
    assert out["json_schema"]["strict"] is False
    assert "x" in out["json_schema"]["schema"]["properties"]
