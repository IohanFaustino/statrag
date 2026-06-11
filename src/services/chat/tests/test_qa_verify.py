"""Tests for qa.verify_story — advisory grounding audit.

Task 6 TDD. verify_story is ADVISORY:
  - prose fields (intro/deepening/conclusion) are NEVER changed.
  - grounding dict is updated with ok/unsupported/confidence from the LLM.
  - prior grounding keys (unbound_markers, lints, …) are preserved.
  - on any LLM exception → fail-open: prose intact, grounding keeps ok and
    gets a 0.5 confidence, no crash.
"""
from __future__ import annotations

import pytest

from src.services.chat import agents as _agents_pkg
from src.services.chat.agents import qa
from src.services.chat.schemas import QAScope, QAStoryAnswer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_answer(
    intro: str = "i",
    deepening: str = "d",
    conclusion: str = "c",
    grounding: dict | None = None,
) -> QAStoryAnswer:
    if grounding is None:
        grounding = {"unbound_markers": 0, "lints": []}
    return QAStoryAnswer(
        intro=intro,
        deepening=deepening,
        conclusion=conclusion,
        scope=QAScope(target_gap="x"),
        citations=[],
        math_blocks=[],
        grounding=grounding,
    )


# ---------------------------------------------------------------------------
# Happy path: LLM returns ok=False with unsupported claims
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_story_merges_grounding(monkeypatch: pytest.MonkeyPatch) -> None:
    """verify_story merges LLM audit into grounding without touching prose."""
    llm_payload = '{"ok":false,"unsupported":["claim"],"confidence":0.4}'

    async def _fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:  # noqa: ARG001
        return llm_payload

    monkeypatch.setattr(qa, "_chat", _fake_chat)

    ans = _make_answer()
    out = await qa.verify_story(ans, sources=[])

    # Prose must be completely unchanged
    assert out.intro == "i"
    assert out.deepening == "d"
    assert out.conclusion == "c"

    # LLM audit fields merged in
    assert out.grounding["ok"] is False
    assert out.grounding["unsupported"] == ["claim"]
    assert abs(out.grounding["confidence"] - 0.4) < 1e-9

    # Prior grounding keys preserved
    assert out.grounding["unbound_markers"] == 0
    assert "lints" in out.grounding


# ---------------------------------------------------------------------------
# Happy path: LLM returns ok=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_story_ok_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """verify_story correctly sets ok=True when LLM reports no unsupported claims."""
    llm_payload = '{"ok":true,"unsupported":[],"confidence":0.95}'

    async def _fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:  # noqa: ARG001
        return llm_payload

    monkeypatch.setattr(qa, "_chat", _fake_chat)

    ans = _make_answer(grounding={"unbound_markers": 2, "lints": ["intro: truncated"]})
    out = await qa.verify_story(ans, sources=[])

    assert out.grounding["ok"] is True
    assert out.grounding["unsupported"] == []
    assert abs(out.grounding["confidence"] - 0.95) < 1e-9
    # Prior keys preserved
    assert out.grounding["unbound_markers"] == 2
    assert out.grounding["lints"] == ["intro: truncated"]


# ---------------------------------------------------------------------------
# Fail-open: LLM raises → advisory pass, prose intact, no crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_story_fail_open_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """verify_story does NOT raise when _chat throws; returns prose unchanged."""

    async def _exploding_chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:  # noqa: ARG001
        raise RuntimeError("network timeout")

    monkeypatch.setattr(qa, "_chat", _exploding_chat)

    ans = _make_answer(grounding={"unbound_markers": 0, "lints": []})
    out = await qa.verify_story(ans, sources=[])  # must NOT raise

    # Prose untouched
    assert out.intro == "i"
    assert out.deepening == "d"
    assert out.conclusion == "c"

    # grounding gets an advisory-pass marker; prior keys survive
    assert "unbound_markers" in out.grounding
    assert "lints" in out.grounding
    # confidence must be present (advisory pass)
    assert "confidence" in out.grounding


# ---------------------------------------------------------------------------
# Fail-open: LLM returns malformed JSON → same advisory-pass behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_story_fail_open_on_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """verify_story is resilient to unparseable LLM output."""

    async def _bad_json_chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:  # noqa: ARG001
        return "not json at all"

    monkeypatch.setattr(qa, "_chat", _bad_json_chat)

    ans = _make_answer()
    out = await qa.verify_story(ans, sources=[])

    assert out.intro == "i"
    assert out.deepening == "d"
    assert out.conclusion == "c"
    assert "confidence" in out.grounding
