"""Q&A node + prompt tests — flat storytelling pipeline."""
from __future__ import annotations

import pytest  # I2: moved to top


def test_prompts_present_and_nonempty():
    from src.services.chat.prompts.qa import (
        QA_SCOPE_PROMPT,
        QA_STORY_WRITE_PROMPT,
        QA_VERIFY_PROMPT,
    )
    for p in (QA_SCOPE_PROMPT, QA_STORY_WRITE_PROMPT, QA_VERIFY_PROMPT):
        assert isinstance(p, str) and len(p) > 50


def test_scope_prompt_demands_json_keys():
    from src.services.chat.prompts.qa import QA_SCOPE_PROMPT
    for key in ("target_gap", "assumed_known", "answer_form"):
        assert key in QA_SCOPE_PROMPT


def test_story_write_prompt_mentions_evidence_tokens():
    """QA_STORY_WRITE_PROMPT must instruct the model to use [[eid]] tokens."""
    from src.services.chat.prompts.qa import QA_STORY_WRITE_PROMPT
    low = QA_STORY_WRITE_PROMPT.lower()
    assert "[[" in low or "eid" in low or "evidence" in low


@pytest.mark.asyncio
async def test_extract_scope_parses_bias_variance(monkeypatch):
    from src.services.chat.agents import qa

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return (
            '{"target_gap":"why bias and variance trade off",'
            '"assumed_known":["what bias is","what variance is"],'
            '"answer_form":"explanation","wiki_terms":[]}'
        )

    monkeypatch.setattr(qa, "_chat", fake_chat)
    scope = await qa.extract_scope(
        "What is the bias-variance tradeoff? I know the elements except the tradeoff."
    )
    assert "trade off" in scope.target_gap
    assert any("bias" in k for k in scope.assumed_known)


@pytest.mark.asyncio
async def test_extract_scope_fail_open(monkeypatch):
    from src.services.chat.agents import qa

    async def boom(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return "not json at all"

    monkeypatch.setattr(qa, "_chat", boom)
    scope = await qa.extract_scope("explain gradient descent")
    # fail-open: whole query becomes the gap, nothing assumed known
    assert scope.target_gap == "explain gradient descent"
    assert scope.assumed_known == []


# ---------------------------------------------------------------------------
# write_story node tests
# ---------------------------------------------------------------------------

def _ev(eid="c1"):
    from src.services.chat.research import Evidence
    return Evidence(subject_id="qa", kind="corpus",
                    text="Bias and variance trade off because of model flexibility.",
                    meta={"book_slug": "islp", "section_id": "2.2"},
                    id=eid)


@pytest.mark.asyncio
async def test_write_story_builds_draft(monkeypatch):
    from src.services.chat.agents import qa

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return (
            '{"intro":"The tradeoff [[c1]] arises from model flexibility.",'
            '"deepening":"Lowering bias raises variance [[c1]].",'
            '"conclusion":"Choose the right complexity [[c1]].",'
            '"math_blocks":[]}'
        )

    monkeypatch.setattr(qa, "_chat", fake_chat)
    scope = qa.QAScope(
        target_gap="why bias and variance trade off",
        assumed_known=["what bias is", "what variance is"],
    )
    draft = await qa.write_story(scope, [_ev()])
    assert "[[c1]]" in draft.intro or "[[c1]]" in draft.deepening or "[[c1]]" in draft.conclusion
    assert isinstance(draft.math_blocks, list)


@pytest.mark.asyncio
async def test_write_story_repairs_bad_json(monkeypatch):
    from src.services.chat.agents import qa
    calls = {"n": 0}

    async def flaky(messages, *, model, max_tokens, temperature=0.0, schema=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return "garbled not json"
        return '{"intro":"ok [[c1]]","deepening":"d","conclusion":"c","math_blocks":[]}'

    monkeypatch.setattr(qa, "_chat", flaky)
    scope = qa.QAScope(target_gap="x")
    draft = await qa.write_story(scope, [_ev()])
    assert draft.intro == "ok [[c1]]"
    assert calls["n"] == 2  # one repair retry


@pytest.mark.asyncio
async def test_write_story_handles_fenced_json(monkeypatch):
    from src.services.chat.agents import qa

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return '```json\n{"intro":"x [[c1]]","deepening":"d","conclusion":"c","math_blocks":[]}\n```'

    monkeypatch.setattr(qa, "_chat", fake_chat)
    scope = qa.QAScope(target_gap="test fenced")
    draft = await qa.write_story(scope, [_ev()])
    assert draft.intro == "x [[c1]]"


# ---------------------------------------------------------------------------
# verify_story node tests (advisory grounding audit)
# ---------------------------------------------------------------------------

def _story_answer():
    from src.services.chat.schemas import QAStoryAnswer, QAScope
    return QAStoryAnswer(
        intro="The tradeoff arises because ...",
        deepening="Lowering bias raises variance.",
        conclusion="Choose complexity carefully.",
        scope=QAScope(target_gap="bias-variance tradeoff"),
        citations=[],
        grounding={"unbound_markers": 0, "lints": []},
    )


def _src():
    from src.services.chat.schemas import Source
    return Source(
        rank=1, book="islp", chapter="ch02", section="2.2",
        title="Assessing Model Accuracy", excerpt="...", score=0.9,
        chunkId="c1", chunk="Bias and variance trade off because ...",
    )


@pytest.mark.asyncio
async def test_verify_story_flags_unsupported(monkeypatch):
    from src.services.chat.agents import qa

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return (
            '{"ok":false,"unsupported":["claim about quantum tunnelling"],'
            '"confidence":0.4,"text":""}'
        )

    monkeypatch.setattr(qa, "_chat", fake_chat)
    answer = _story_answer()
    out = await qa.verify_story(answer, [_src()])
    assert out.grounding["ok"] is False
    assert out.grounding["confidence"] == 0.4
    assert "quantum tunnelling" in out.grounding["unsupported"][0]
    # Prose fields remain unchanged by verify_story
    assert out.intro == answer.intro


@pytest.mark.asyncio
async def test_verify_story_fail_open_keeps_prose(monkeypatch):
    from src.services.chat.agents import qa

    async def boom(messages, *, model, max_tokens, temperature=0.0, schema=None):
        raise RuntimeError("verify provider down")

    monkeypatch.setattr(qa, "_chat", boom)
    answer = _story_answer()
    out = await qa.verify_story(answer, [_src()])
    # Fail-open: prose intact
    assert out.intro == answer.intro
    assert out.deepening == answer.deepening
    # Advisory pass — grounding still has a confidence key
    assert "confidence" in out.grounding


@pytest.mark.asyncio
async def test_verify_story_preserves_prior_grounding_keys(monkeypatch):
    """verify_story must merge, not replace — unbound_markers and lints
    from qa_bind must survive the verify pass."""
    from src.services.chat.agents import qa
    from src.services.chat.schemas import QAStoryAnswer, QAScope

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return '{"ok":true,"unsupported":[],"confidence":0.9,"text":""}'

    monkeypatch.setattr(qa, "_chat", fake_chat)

    answer = QAStoryAnswer(
        intro="answer", deepening="", conclusion="",
        scope=QAScope(target_gap="x"),
        citations=[],
        grounding={
            "unbound_markers": 3,
            "lints": ["intro: truncated"],
            "corpus_weak": False,
            "wiki_unavailable": False,
        },
    )
    out = await qa.verify_story(answer, [_src()])
    # Newly added verify keys
    assert out.grounding["ok"] is True
    assert out.grounding["confidence"] == 0.9
    # Prior keys preserved
    assert out.grounding["unbound_markers"] == 3
    assert "intro: truncated" in out.grounding["lints"]
