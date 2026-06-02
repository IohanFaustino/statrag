"""Unit tests for the structured-output capability gate."""
from __future__ import annotations

import pydantic
import pytest

from src.services.chat.llm.structured import (
    JsonMode,
    json_mode_for,
    resolve_response_format,
)


class _Shape(pydantic.BaseModel):
    key_points: list[str]
    ok: bool


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-4o", JsonMode.SCHEMA),
        ("gpt-5.4-nano-2026-03-17", JsonMode.SCHEMA),
        ("gemini-2.5-flash", JsonMode.SCHEMA),
        ("qwen-plus", JsonMode.SCHEMA),
        ("moonshotai/kimi-k2-instruct-0905", JsonMode.SCHEMA),
        ("deepseek-v4-pro", JsonMode.OBJECT),
        ("deepseek-chat", JsonMode.OBJECT),
        ("meta-llama/llama-4-scout-17b-16e-instruct", JsonMode.OBJECT),
        ("llama-3.3-70b-versatile", JsonMode.OBJECT),
        ("openai/gpt-oss-120b", JsonMode.OBJECT),
        ("openai/gpt-oss-20b", JsonMode.OBJECT),
        ("some-unknown-model", JsonMode.OBJECT),
        (None, JsonMode.OBJECT),
    ],
)
def test_json_mode_for(model, expected):
    assert json_mode_for(model) is expected


def test_resolve_schema_model_uses_native_schema():
    payload, hint = resolve_response_format("gpt-4o", _Shape)
    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["schema"]["properties"].keys() >= {"key_points", "ok"}
    assert hint is None


def test_resolve_object_model_uses_json_object_plus_hint():
    payload, hint = resolve_response_format("deepseek-v4-pro", _Shape)
    assert payload == {"type": "json_object"}
    assert hint is not None
    assert "json" in hint.lower()
    assert "key_points" in hint and "ok" in hint


def test_resolve_none_schema_returns_nothing():
    payload, hint = resolve_response_format("deepseek-v4-pro", None)
    assert payload is None and hint is None
