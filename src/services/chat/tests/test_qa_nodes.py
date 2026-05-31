"""Q&A node + prompt tests."""
from __future__ import annotations


def test_prompts_present_and_nonempty():
    from src.services.chat.prompts.qa import (
        QA_SCOPE_PROMPT,
        QA_GENERATE_PROMPT,
        QA_VERIFY_PROMPT,
    )
    for p in (QA_SCOPE_PROMPT, QA_GENERATE_PROMPT, QA_VERIFY_PROMPT):
        assert isinstance(p, str) and len(p) > 50


def test_scope_prompt_demands_json_keys():
    from src.services.chat.prompts.qa import QA_SCOPE_PROMPT
    for key in ("target_gap", "assumed_known", "answer_form"):
        assert key in QA_SCOPE_PROMPT


def test_generate_prompt_forbids_explaining_known():
    from src.services.chat.prompts.qa import QA_GENERATE_PROMPT
    low = QA_GENERATE_PROMPT.lower()
    assert "assumed_known" in low or "already know" in low


import pytest


@pytest.mark.asyncio
async def test_extract_scope_parses_bias_variance(monkeypatch):
    from src.services.chat.agents import qa

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0):
        return (
            '{"target_gap":"why bias and variance trade off",'
            '"assumed_known":["what bias is","what variance is"],'
            '"answer_form":"explanation"}'
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

    async def boom(messages, *, model, max_tokens, temperature=0.0):
        return "not json at all"

    monkeypatch.setattr(qa, "_chat", boom)
    scope = await qa.extract_scope("explain gradient descent")
    # fail-open: whole query becomes the gap, nothing assumed known
    assert scope.target_gap == "explain gradient descent"
    assert scope.assumed_known == []


def test_retrieve_for_gap_uses_target_gap(monkeypatch):
    from src.services.chat.agents import qa

    captured = {}

    def fake_hybrid(query, *, book_slugs=None, top_k=5, rerank=True, adjacent_sections=False):
        captured["query"] = query
        captured["top_k"] = top_k
        return ([], {"mode": "test"})

    monkeypatch.setattr(qa, "hybrid_search", fake_hybrid)
    scope = qa.QAScope(target_gap="why bias and variance trade off")
    sources, meta = qa.retrieve_for_gap(scope, book_slugs=None, k=4)
    assert captured["query"] == "why bias and variance trade off"
    assert captured["top_k"] == 4
    assert sources == []


def _src(rank, **kw):
    from src.services.chat.schemas import Source
    base = dict(
        rank=rank, book="islp", chapter="ch02", section="2.2",
        title="Assessing Model Accuracy", excerpt="…", score=0.9,
        chunkId=f"c{rank}", chunk="Bias and variance trade off because …",
    )
    base.update(kw)
    return Source(**base)


@pytest.mark.asyncio
async def test_generate_scoped_builds_answer_and_passes_known(monkeypatch):
    from src.services.chat.agents import qa

    seen = {}

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0):
        seen["user"] = messages[-1]["content"]
        return (
            '{"text":"The tradeoff arises because lowering one raises the other [1].",'
            '"citations":[{"index":1,"chunkId":"c1","book_name":"ISLP","quote":"…"}],'
            '"math_blocks":[]}'
        )

    monkeypatch.setattr(qa, "_chat", fake_chat)
    scope = qa.QAScope(
        target_gap="why bias and variance trade off",
        assumed_known=["what bias is", "what variance is"],
    )
    ans = await qa.generate_scoped(scope, [_src(1)])
    assert ans.text.startswith("The tradeoff")
    assert ans.citations[0].index == 1
    # the assumed_known must be injected into the generate prompt context
    assert "what bias is" in seen["user"]


@pytest.mark.asyncio
async def test_generate_scoped_repairs_bad_json(monkeypatch):
    from src.services.chat.agents import qa
    calls = {"n": 0}

    async def flaky(messages, *, model, max_tokens, temperature=0.0):
        calls["n"] += 1
        if calls["n"] == 1:
            return "garbled not json"
        return '{"text":"ok","citations":[],"math_blocks":[]}'

    monkeypatch.setattr(qa, "_chat", flaky)
    scope = qa.QAScope(target_gap="x")
    ans = await qa.generate_scoped(scope, [_src(1)])
    assert ans.text == "ok"
    assert calls["n"] == 2  # one repair retry


@pytest.mark.asyncio
async def test_verify_flags_unsupported_and_softens(monkeypatch):
    from src.services.chat.agents import qa

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0):
        return (
            '{"ok":false,"unsupported":["claim about quantum tunnelling"],'
            '"confidence":0.4,"text":"The tradeoff arises because lowering one raises the other [1]."}'
        )

    monkeypatch.setattr(qa, "_chat", fake_chat)
    scope = qa.QAScope(target_gap="x")
    draft = qa.QAAnswer(text="… quantum tunnelling …", scope=scope)
    out = await qa.verify_grounding(draft, [_src(1)])
    assert out.grounding["ok"] is False
    assert out.grounding["confidence"] == 0.4
    assert "quantum tunnelling" in out.grounding["unsupported"][0]
    assert "lowering one raises the other" in out.text  # text replaced by verified text


@pytest.mark.asyncio
async def test_verify_fail_open_keeps_draft(monkeypatch):
    from src.services.chat.agents import qa

    async def boom(messages, *, model, max_tokens, temperature=0.0):
        raise RuntimeError("verify provider down")

    monkeypatch.setattr(qa, "_chat", boom)
    scope = qa.QAScope(target_gap="x")
    draft = qa.QAAnswer(text="original draft", scope=scope)
    out = await qa.verify_grounding(draft, [_src(1)])
    assert out.text == "original draft"
    assert out.grounding["ok"] is False
    assert out.grounding["confidence"] <= 0.5
