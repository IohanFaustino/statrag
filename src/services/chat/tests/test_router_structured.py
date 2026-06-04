"""Tests for is_structured_output_capable predicate and recommended flag."""
from src.services.chat.llm.router import is_structured_output_capable, list_providers


def test_is_structured_output_capable():
    assert is_structured_output_capable("gpt-5.4-nano-2026-03-17") is True
    assert is_structured_output_capable("gpt-4o") is True
    assert is_structured_output_capable(None) is True
    assert is_structured_output_capable("deepseek-chat") is False
    assert is_structured_output_capable("qwen-plus") is False
    assert is_structured_output_capable("gemini-2.5-flash") is False
    assert is_structured_output_capable("openai/gpt-oss-120b") is False  # groq


def test_recommended_flag_is_nano_not_qwen():
    rec = [m.id for p in list_providers() for m in p.models if getattr(m, "recommended", False)]
    assert rec == ["gpt-5.4-nano-2026-03-17"]
