"""T03 acceptance: real LLM rewriter (B2) + fence-strip helper (B6)."""
from __future__ import annotations

import asyncio
import os

import pytest

from src.services.chat import rewriter
from src.services.chat._fences import strip_fences


# ---------------------------------------------------------------------------
# Fence-strip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", ""),
        ("{}", "{}"),
        ("```json\n{}\n```", "{}"),
        ("```\n{}\n```", "{}"),
        ("```json\n{\"a\": 1}\n```", '{"a": 1}'),
        # missing trailing fence
        ("```json\n{\"a\": 1}", '{"a": 1}'),
        ("```{}```", "{}"),
        ("  ```json\n[\"x\"]\n```  ", '["x"]'),
        # B6 regression: text whose tail happens to include chars in "```json"
        ("{\"key\": \"jsonjson\"}", '{"key": "jsonjson"}'),
    ],
)
def test_strip_fences(raw, expected):
    assert strip_fences(raw) == expected


def test_strip_fences_preserves_internal_backticks():
    """Internal ``` inside string content stays untouched."""
    raw = "```json\n{\"q\": \"see `code` block\"}\n```"
    assert strip_fences(raw) == '{"q": "see `code` block"}'


# ---------------------------------------------------------------------------
# Rewriter — no history short-circuit
# ---------------------------------------------------------------------------


def test_rewrite_no_history_returns_query_unchanged():
    out = rewriter.rewrite_query("what is OLS?")
    assert out == "what is OLS?"


def test_rewrite_empty_history_returns_query_unchanged():
    out = rewriter.rewrite_query("what is OLS?", history=[])
    assert out == "what is OLS?"


# ---------------------------------------------------------------------------
# Rewriter — concat fallback under env flag
# ---------------------------------------------------------------------------


def test_concat_fallback_under_legacy_flag(monkeypatch):
    monkeypatch.setenv("REWRITER_MODE", "concat")
    history = [
        {"role": "user", "content": "what is OLS"},
        {"role": "assistant", "content": "OLS is ..."},
    ]

    async def _drive():
        return await rewriter.arewrite_query("explain it", history)

    out = asyncio.run(_drive())
    assert "OLS" in out and "explain it" in out


# ---------------------------------------------------------------------------
# Rewriter — LLM path (mocked)
# ---------------------------------------------------------------------------


def test_arewrite_uses_llm_with_history(monkeypatch):
    """When history is present and LLM returns non-empty, that result is used."""
    history = [
        {"role": "user", "content": "what is OLS regression?"},
    ]

    class _Choice:
        def __init__(self, content):
            self.message = type("M", (), {"content": content})()

    class _Resp:
        def __init__(self, content):
            self.choices = [_Choice(content)]

    class _FakeChat:
        def __init__(self):
            self.completions = self

        async def create(self, **kw):
            return _Resp("Explain Ordinary Least Squares regression")

    class _FakeOpenAI:
        def __init__(self, api_key=None):
            self.chat = _FakeChat()

    monkeypatch.setattr(rewriter._openai, "AsyncOpenAI", _FakeOpenAI)

    async def _drive():
        return await rewriter.arewrite_query("explain it", history)

    out = asyncio.run(_drive())
    assert out == "Explain Ordinary Least Squares regression"


def test_arewrite_falls_back_on_llm_error(monkeypatch):
    """LLM raising must fall back to the raw query, not crash."""
    history = [{"role": "user", "content": "prior turn"}]

    class _FakeChat:
        def __init__(self):
            self.completions = self

        async def create(self, **kw):
            raise RuntimeError("API down")

    class _FakeOpenAI:
        def __init__(self, api_key=None):
            self.chat = _FakeChat()

    monkeypatch.setattr(rewriter._openai, "AsyncOpenAI", _FakeOpenAI)

    async def _drive():
        return await rewriter.arewrite_query("explain it", history)

    out = asyncio.run(_drive())
    assert out == "explain it"


def test_arewrite_skips_when_llm_returns_same_query(monkeypatch):
    """If the LLM output equals the input (case-insensitive), return input."""
    history = [{"role": "user", "content": "prior"}]

    class _Choice:
        message = type("M", (), {"content": "Explain it"})()

    class _Resp:
        choices = [_Choice()]

    class _FakeChat:
        def __init__(self):
            self.completions = self

        async def create(self, **kw):
            return _Resp()

    class _FakeOpenAI:
        def __init__(self, api_key=None):
            self.chat = _FakeChat()

    monkeypatch.setattr(rewriter._openai, "AsyncOpenAI", _FakeOpenAI)

    async def _drive():
        return await rewriter.arewrite_query("explain it", history)

    out = asyncio.run(_drive())
    assert out == "explain it"
