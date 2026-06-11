"""Tests for write_story — single storytelling writer call.

TDD Task 5: covers write_story which builds an evidence block, calls _chat
with QA_STORY_WRITE_PROMPT, and returns a QAStoryDraft.
"""
from __future__ import annotations

import json
import pytest

from src.services.chat.agents import qa
from src.services.chat.research import Evidence
from src.services.chat.schemas import QAScope, QAStoryDraft


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def corpus_ev() -> Evidence:
    return Evidence(
        subject_id="qa",
        kind="corpus",
        text="The bias-variance decomposition partitions expected squared error.",
        meta={
            "book_slug": "islp",
            "book_name": "Introduction to Statistical Learning",
            "authors_short": "James et al.",
            "year": 2023,
            "chapter": "ch02",
            "section": "2.2",
        },
        id="c1",
    )


@pytest.fixture()
def wiki_ev() -> Evidence:
    return Evidence(
        subject_id="qa",
        kind="wikipedia",
        text="Chebyshev's inequality bounds the probability of a value being far from the mean.",
        meta={
            "title": "Chebyshev's inequality",
            "url": "https://en.wikipedia.org/wiki/Chebyshev%27s_inequality",
        },
        id="w1",
    )


@pytest.fixture()
def scope() -> QAScope:
    return QAScope(
        target_gap="why bias and variance trade off",
        assumed_known=["what bias is"],
    )


# ---------------------------------------------------------------------------
# Recording mock
# ---------------------------------------------------------------------------

def _make_record_mock(raw: str):
    """Returns (mock_fn, captured_messages_list)."""
    captured: list = []

    async def _mock(messages, *, model, max_tokens, temperature=0.0, schema=None):
        captured.extend(messages)
        return raw

    return _mock, captured


# ---------------------------------------------------------------------------
# T1 — happy path: returns QAStoryDraft with correct fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_story_returns_draft(monkeypatch, scope, corpus_ev, wiki_ev):
    """write_story returns a QAStoryDraft with the parsed intro/deepening/conclusion."""
    payload = json.dumps({
        "intro": "Hook [[c1]].",
        "deepening": "Body [[c1]] and [[w1]].",
        "conclusion": "Close.",
        "math_blocks": [],
    })
    mock, _ = _make_record_mock(payload)
    monkeypatch.setattr(qa, "_chat", mock)

    draft = await qa.write_story(scope, [corpus_ev, wiki_ev], model="gpt-5.4-nano-2026-03-17")

    assert isinstance(draft, QAStoryDraft)
    assert draft.intro == "Hook [[c1]]."
    assert draft.deepening == "Body [[c1]] and [[w1]]."
    assert draft.conclusion == "Close."
    assert draft.math_blocks == []


# ---------------------------------------------------------------------------
# T2 — user message contains eids, kinds, and target_gap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_story_user_message_content(monkeypatch, scope, corpus_ev, wiki_ev):
    """The user message passed to _chat must mention c1, w1, corpus, wikipedia/wiki,
    and the target_gap so the writer knows which tokens are valid."""
    payload = json.dumps({
        "intro": "Hook [[c1]].",
        "deepening": "Body [[c1]] and [[w1]].",
        "conclusion": "Close.",
        "math_blocks": [],
    })
    mock, captured = _make_record_mock(payload)
    monkeypatch.setattr(qa, "_chat", mock)

    await qa.write_story(scope, [corpus_ev, wiki_ev], model="gpt-5.4-nano-2026-03-17")

    # Find the user message
    user_msgs = [m for m in captured if m.get("role") == "user"]
    assert len(user_msgs) == 1
    user_content = user_msgs[0]["content"]

    # Evidence ids must appear so the model knows the valid [[eid]] tokens
    assert "c1" in user_content
    assert "w1" in user_content

    # Evidence kinds must be labelled
    assert "corpus" in user_content
    assert "wiki" in user_content or "wikipedia" in user_content

    # target_gap must appear so the writer knows what to answer
    assert "why bias and variance trade off" in user_content


# ---------------------------------------------------------------------------
# T3 — system message is QA_STORY_WRITE_PROMPT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_story_system_prompt(monkeypatch, scope, corpus_ev, wiki_ev):
    """write_story uses QA_STORY_WRITE_PROMPT as the system message."""
    from src.services.chat.prompts.qa import QA_STORY_WRITE_PROMPT

    payload = json.dumps({
        "intro": "I.", "deepening": "D.", "conclusion": "C.", "math_blocks": [],
    })
    mock, captured = _make_record_mock(payload)
    monkeypatch.setattr(qa, "_chat", mock)

    await qa.write_story(scope, [corpus_ev, wiki_ev])

    sys_msgs = [m for m in captured if m.get("role") == "system"]
    assert len(sys_msgs) == 1
    assert sys_msgs[0]["content"] == QA_STORY_WRITE_PROMPT
