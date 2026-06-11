"""Tests for qa._fallback_story — corpus-only regression-safety generator.

Task 6 TDD. _fallback_story must:
  - Return a QAStoryAnswer with the 3 prose fields populated from the LLM.
  - Bind scope (not copy — same object reference or equal value).
  - Produce citations=[] (fallback skips the citation binder).
  - Stamp grounding with ok=True, a confidence value, fallback=True, and
    unbound_markers=0 / lints=[].
  - NEVER raise — even on complete LLM failure it returns a minimal honest answer.
"""
from __future__ import annotations

import pytest

from src.services.chat.agents import qa
from src.services.chat.schemas import QAScope, QAStoryAnswer, Source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scope(gap: str = "why X") -> QAScope:
    return QAScope(target_gap=gap)


def _make_source() -> Source:
    return Source(
        rank=1,
        book="test_book",
        chapter="ch01",
        section="1.1",
        title="Intro",
        excerpt="Some text.",
        score=0.9,
        chunkId="abc123",
        chunk="Some text.",
    )


# ---------------------------------------------------------------------------
# Happy path: LLM returns valid JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_story_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fallback_story builds a QAStoryAnswer from valid LLM output."""
    llm_payload = (
        '{"intro":"Fallback intro","deepening":"body",'
        '"conclusion":"end","math_blocks":[]}'
    )

    async def _fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:  # noqa: ARG001
        return llm_payload

    monkeypatch.setattr(qa, "_chat", _fake_chat)

    scope = _make_scope("why X")
    ans = await qa._fallback_story(scope, sources=[_make_source()])

    assert isinstance(ans, QAStoryAnswer)
    assert ans.intro == "Fallback intro"
    assert ans.deepening == "body"
    assert ans.conclusion == "end"

    # scope preserved
    assert ans.scope is scope or ans.scope == scope

    # fallback must bind NO citations
    assert ans.citations == []

    # grounding: ok=True, confidence present, fallback flag set
    assert ans.grounding.get("ok") is True
    assert "confidence" in ans.grounding
    assert ans.grounding.get("fallback") is True

    # grounding must carry corpus_weak / wiki_unavailable on every path (Finding 3)
    assert "corpus_weak" in ans.grounding
    assert "wiki_unavailable" in ans.grounding
    # called with one source → corpus not weak
    assert ans.grounding["corpus_weak"] is False
    assert ans.grounding["wiki_unavailable"] is False


# ---------------------------------------------------------------------------
# Grounding defaults — unbound_markers and lints must be initialised
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_story_grounding_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fallback_story stamps unbound_markers=0 and lints=[] in grounding."""
    llm_payload = '{"intro":"i","deepening":"d","conclusion":"c","math_blocks":[]}'

    async def _fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:  # noqa: ARG001
        return llm_payload

    monkeypatch.setattr(qa, "_chat", _fake_chat)

    ans = await qa._fallback_story(_make_scope(), sources=[])

    assert ans.grounding.get("unbound_markers") == 0
    assert ans.grounding.get("lints") == []
    # empty sources list → corpus_weak=True; wiki_unavailable=False (Finding 3)
    assert ans.grounding.get("corpus_weak") is True
    assert ans.grounding.get("wiki_unavailable") is False


# ---------------------------------------------------------------------------
# Regression-safety: LLM raises → degenerate answer, never raises
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_story_never_raises_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fallback_story absorbs ALL exceptions and returns a minimal honest answer."""
    call_count = 0

    async def _always_explode(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        raise RuntimeError("LLM unreachable")

    monkeypatch.setattr(qa, "_chat", _always_explode)

    scope = _make_scope("degenerate test")
    ans = await qa._fallback_story(scope, sources=[])  # must NOT raise

    assert isinstance(ans, QAStoryAnswer)
    # scope still bound
    assert ans.scope is scope or ans.scope == scope
    # citations empty
    assert ans.citations == []
    # grounding must exist and be a dict (even if minimal)
    assert isinstance(ans.grounding, dict)
    # intro must be a non-empty honest message (not an empty string silently)
    assert isinstance(ans.intro, str)
    # degenerate path must also carry corpus_weak / wiki_unavailable (Finding 3)
    assert "corpus_weak" in ans.grounding
    assert "wiki_unavailable" in ans.grounding


# ---------------------------------------------------------------------------
# math_blocks forwarded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_story_forwards_math_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fallback_story passes through math_blocks from the LLM output."""
    llm_payload = (
        '{"intro":"i","deepening":"d","conclusion":"c",'
        '"math_blocks":["\\\\sigma^2","\\\\mu"]}'
    )

    async def _fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:  # noqa: ARG001
        return llm_payload

    monkeypatch.setattr(qa, "_chat", _fake_chat)

    ans = await qa._fallback_story(_make_scope(), sources=[])

    assert len(ans.math_blocks) == 2
    assert ans.math_blocks[0] == "\\sigma^2"
    assert ans.math_blocks[1] == "\\mu"
