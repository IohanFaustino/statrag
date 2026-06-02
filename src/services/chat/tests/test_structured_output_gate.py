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


def test_resolve_non_pydantic_schema_returns_nothing():
    class Dummy:  # no model_json_schema
        pass
    payload, hint = resolve_response_format("gpt-4o", Dummy)
    assert payload is None and hint is None


def test_schema_hint_public_helper():
    from src.services.chat.llm.structured import schema_hint

    class _S(pydantic.BaseModel):
        a: int
        b: str
    h = schema_hint(_S)
    assert h and "json" in h.lower() and "a" in h and "b" in h

    class Dummy:
        pass
    assert schema_hint(Dummy) is None


def test_schema_hint_wrapped_in_response_format_token():
    from src.services.chat.llm.structured import schema_hint

    class _S(pydantic.BaseModel):
        a: int
        b: str
    h = schema_hint(_S)
    assert h is not None
    assert h.strip().startswith("<response_format>")
    assert h.strip().endswith("</response_format>")
    assert "json" in h.lower() and "a" in h and "b" in h


def test_apply_structured_output_object_model_injects_token():
    from src.services.chat.llm.structured import apply_structured_output

    class _S(pydantic.BaseModel):
        a: int
    msgs = [{"role": "system", "content": "BASE"},
            {"role": "user", "content": "u"}]
    out_msgs, rf = apply_structured_output(msgs, "deepseek-v4-pro", _S)
    assert rf == {"type": "json_object"}
    assert "BASE" in out_msgs[0]["content"]
    assert "<response_format>" in out_msgs[0]["content"]
    assert msgs[0]["content"] == "BASE"  # original not mutated


def test_apply_structured_output_schema_model_untouched():
    from src.services.chat.llm.structured import apply_structured_output

    class _S(pydantic.BaseModel):
        a: int
    msgs = [{"role": "system", "content": "BASE"}]
    out_msgs, rf = apply_structured_output(msgs, "gpt-4o", _S)
    assert rf["type"] == "json_schema"
    assert out_msgs[0]["content"] == "BASE"


def test_apply_structured_output_no_system_message_prepends():
    from src.services.chat.llm.structured import apply_structured_output

    class _S(pydantic.BaseModel):
        a: int
    msgs = [{"role": "user", "content": "u"}]
    out_msgs, rf = apply_structured_output(msgs, "deepseek-v4-pro", _S)
    assert out_msgs[0]["role"] == "system"
    assert "<response_format>" in out_msgs[0]["content"]
    assert out_msgs[-1]["role"] == "user"


def test_apply_structured_output_no_schema_noop():
    from src.services.chat.llm.structured import apply_structured_output

    msgs = [{"role": "system", "content": "BASE"}]
    out_msgs, rf = apply_structured_output(msgs, "gpt-4o", None)
    assert rf is None
    assert out_msgs[0]["content"] == "BASE"


def test_chapter_schemas_importable_from_package():
    from src.services.chat.schemas import (
        ChapterParse, ChapterResolveMatches, ChapterMapBlock,
        ChapterStitchOut, ChapterGroundOut,
    )
    assert ChapterParse().book_slug == ""
    assert ChapterResolveMatches().matches == []
    assert ChapterMapBlock().math_blocks == []
    assert ChapterStitchOut().intro == ""
    assert ChapterGroundOut().confidence == 0.5
