"""Tests for extract_scope — wiki_terms parsing + fail-open behaviour.

TDD Task 5: covers the extended extract_scope that emits wiki_terms.
"""
from __future__ import annotations

import json
import pytest

from src.services.chat.agents import qa
from src.services.chat.schemas import QAScope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chat_mock(raw: str):
    """Return an async function that always resolves to `raw`."""
    async def _mock(messages, *, model, max_tokens, temperature=0.0, schema=None):
        return raw
    return _mock


def _make_chat_raiser(exc: Exception):
    """Return an async function that always raises `exc`."""
    async def _mock(messages, *, model, max_tokens, temperature=0.0, schema=None):
        raise exc
    return _mock


# ---------------------------------------------------------------------------
# T1 — wiki_terms capped at _QA_WIKI_TERMS_MAX (currently 2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wiki_terms_capped(monkeypatch):
    """Model returns 4 wiki_terms → only the first 2 survive the cap."""
    payload = json.dumps({
        "target_gap": "why X",
        "assumed_known": [],
        "answer_form": "explanation",
        "wiki_terms": ["Chebyshev", "Markov", "Third", "Fourth"],
    })
    monkeypatch.setattr(qa, "_chat", _make_chat_mock(payload))

    scope = await qa.extract_scope("q")

    assert scope.wiki_terms == ["Chebyshev", "Markov"]
    assert len(scope.wiki_terms) == qa._QA_WIKI_TERMS_MAX


# ---------------------------------------------------------------------------
# T2 — LLM raises → fail-open: wiki_terms=[] + whole query becomes target_gap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wiki_terms_fail_open_on_raise(monkeypatch):
    """LLM call raises → fail-open scope with wiki_terms=[]."""
    monkeypatch.setattr(qa, "_chat", _make_chat_raiser(RuntimeError("boom")))

    scope = await qa.extract_scope("what is bias-variance tradeoff?")

    assert scope.wiki_terms == []
    assert scope.target_gap == "what is bias-variance tradeoff?"
    assert scope.assumed_known == []


# ---------------------------------------------------------------------------
# T3 — wiki_terms key MISSING in JSON → wiki_terms=[] (no crash)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wiki_terms_missing_key(monkeypatch):
    """JSON response has no wiki_terms key → defaults to [] without crashing."""
    payload = json.dumps({
        "target_gap": "why X",
        "assumed_known": [],
        "answer_form": "explanation",
        # wiki_terms intentionally omitted
    })
    monkeypatch.setattr(qa, "_chat", _make_chat_mock(payload))

    scope = await qa.extract_scope("q")

    assert scope.wiki_terms == []
    assert scope.target_gap == "why X"


# ---------------------------------------------------------------------------
# T4 — wiki_terms with non-strings/empties → only valid strings survive
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wiki_terms_non_string_filtered(monkeypatch):
    """wiki_terms containing non-strings or empty strings → only 'Good' survives."""
    payload = json.dumps({
        "target_gap": "why X",
        "assumed_known": [],
        "answer_form": "explanation",
        "wiki_terms": [1, "", "Good"],
    })
    monkeypatch.setattr(qa, "_chat", _make_chat_mock(payload))

    scope = await qa.extract_scope("q")

    assert scope.wiki_terms == ["Good"]
