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
