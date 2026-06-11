"""Tests for qa.retrieve_evidence — corpus∥wiki gather.

Monkeypatches qa.corpus_evidence and qa.wiki_evidence (the names as
imported INTO qa.py) with fakes that record call args and return tiny
Evidence lists.  No network; no LLM.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

import src.services.chat.agents.qa as qa
from src.services.chat.research import Evidence
from src.services.chat.schemas import QAScope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scope(target_gap: str = "Chebyshev inequality",
                wiki_terms: list[str] | None = None) -> QAScope:
    return QAScope(
        target_gap=target_gap,
        wiki_terms=wiki_terms if wiki_terms is not None else ["Chebyshev", "Markov", "Extra"],
    )


def _make_corpus_evidence(query: str, **kwargs) -> list[Evidence]:
    return [Evidence(subject_id="qa", kind="corpus", text="corpus text",
                     meta={"chunk_id": "c1"}, id="c1")]


def _make_wiki_evidence(query: str, **kwargs) -> list[Evidence]:
    # Return distinct id per call so uniqueness is preserved
    import uuid
    return [Evidence(subject_id="qa", kind="wikipedia", text=f"wiki text for {query}",
                     meta={"title": query, "url": "http://example.com"}, id=uuid.uuid4().hex[:12])]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_evidence_calls_wiki_for_gap_and_terms():
    """wiki_evidence called once for target_gap + once per wiki_term (capped at
    _QA_WIKI_TERMS_MAX, default 2) → 3 wiki calls total.
    corpus_evidence called once.
    Returns a flat list[Evidence] with unique ids.
    """
    scope = _make_scope()  # wiki_terms = ["Chebyshev", "Markov", "Extra"]

    corpus_calls: list[str] = []
    wiki_calls: list[str] = []

    def fake_corpus(query: str, **kwargs) -> list[Evidence]:
        corpus_calls.append(query)
        return _make_corpus_evidence(query)

    def fake_wiki(query: str, **kwargs) -> list[Evidence]:
        wiki_calls.append(query)
        return _make_wiki_evidence(query)

    with patch.object(qa, "corpus_evidence", fake_corpus), \
         patch.object(qa, "wiki_evidence", fake_wiki):
        result = await qa.retrieve_evidence(scope, book_slugs=["hansen"])

    # 1 corpus call
    assert len(corpus_calls) == 1
    assert corpus_calls[0] == scope.target_gap

    # 1 (target_gap) + 2 (first 2 wiki_terms capped by _QA_WIKI_TERMS_MAX=2) = 3
    assert len(wiki_calls) == 3
    assert wiki_calls[0] == scope.target_gap
    assert wiki_calls[1] == "Chebyshev"
    assert wiki_calls[2] == "Markov"
    # "Extra" is the 3rd wiki_term — must NOT be called (capped at 2)

    # All results flattened; ids unique
    assert isinstance(result, list)
    ids = [e.id for e in result]
    assert len(ids) == len(set(ids)), "Evidence ids must be unique"
    assert len(result) == 4  # 1 corpus + 3 wiki


@pytest.mark.asyncio
async def test_retrieve_evidence_resilient_to_wiki_failure():
    """When wiki_evidence raises, retrieve_evidence must still return corpus
    evidence and must not propagate the exception (spec §6: wiki error → corpus-only)."""
    scope = _make_scope()

    def fake_corpus(query: str, **kwargs) -> list[Evidence]:
        return _make_corpus_evidence(query)

    def raising_wiki(query: str, **kwargs) -> list[Evidence]:
        raise RuntimeError("simulated wiki network failure")

    with patch.object(qa, "corpus_evidence", fake_corpus), \
         patch.object(qa, "wiki_evidence", raising_wiki):
        result = await qa.retrieve_evidence(scope, book_slugs=["hansen"])

    # Must not raise; must contain at least the corpus evidence
    assert len(result) >= 1
    corpus_items = [e for e in result if e.kind == "corpus"]
    assert len(corpus_items) >= 1, "corpus evidence must survive a wiki failure"


@pytest.mark.asyncio
async def test_retrieve_evidence_stamps_readable_ids():
    """After gather, corpus Evidence get c1/c2/... and wikipedia Evidence get
    w1/w2/w3/... regardless of the random hex ids produced by the factory.

    Scope has 2 wiki_terms; _QA_WIKI_TERMS_MAX=2 → 3 wiki calls (target_gap +
    Chebyshev + Markov), each returning 1 Evidence.  fake_corpus returns 2
    corpus Evidence.  Expected ids: c1, c2 (corpus) + w1, w2, w3 (wiki).
    """
    import re as _re

    scope = _make_scope()  # wiki_terms = ["Chebyshev", "Markov", "Extra"]

    def fake_corpus_two(query: str, **kwargs) -> list[Evidence]:
        """Return 2 corpus Evidence with random/hex ids (the production default)."""
        import uuid
        return [
            Evidence(subject_id="qa", kind="corpus", text="corpus text A",
                     meta={"chunk_id": "aaa"}, id=uuid.uuid4().hex[:12]),
            Evidence(subject_id="qa", kind="corpus", text="corpus text B",
                     meta={"chunk_id": "bbb"}, id=uuid.uuid4().hex[:12]),
        ]

    def fake_wiki_one(query: str, **kwargs) -> list[Evidence]:
        """Return 1 wikipedia Evidence per call with random/hex id."""
        import uuid
        return [
            Evidence(subject_id="qa", kind="wikipedia", text=f"wiki text for {query}",
                     meta={"title": query, "url": "http://example.com"},
                     id=uuid.uuid4().hex[:12]),
        ]

    with patch.object(qa, "corpus_evidence", fake_corpus_two), \
         patch.object(qa, "wiki_evidence", fake_wiki_one):
        result = await qa.retrieve_evidence(scope, book_slugs=["hansen"])

    # Total: 2 corpus + 3 wiki = 5 items
    assert len(result) == 5, f"expected 5 items, got {len(result)}: {[e.id for e in result]}"

    corpus_items = [e for e in result if e.kind == "corpus"]
    wiki_items = [e for e in result if e.kind == "wikipedia"]
    assert len(corpus_items) == 2
    assert len(wiki_items) == 3

    # Corpus ids must be c1, c2 (in order)
    assert corpus_items[0].id == "c1"
    assert corpus_items[1].id == "c2"

    # Wikipedia ids must be w1, w2, w3 (in order)
    assert wiki_items[0].id == "w1"
    assert wiki_items[1].id == "w2"
    assert wiki_items[2].id == "w3"

    # All ids are unique and match the readable scheme
    all_ids = [e.id for e in result]
    assert len(all_ids) == len(set(all_ids)), "ids must be unique across the full list"
    pattern = _re.compile(r'^[cw]\d+$')
    for eid in all_ids:
        assert pattern.match(eid), f"id {eid!r} does not match ^[cw]\\d+$"


@pytest.mark.asyncio
async def test_retrieve_evidence_skips_wiki_when_flag_off(monkeypatch):
    """When _QA_WIKI is False, wiki_evidence must NOT be called."""
    scope = _make_scope()

    corpus_calls: list[str] = []
    wiki_calls: list[str] = []

    def fake_corpus(query: str, **kwargs) -> list[Evidence]:
        corpus_calls.append(query)
        return _make_corpus_evidence(query)

    def fake_wiki(query: str, **kwargs) -> list[Evidence]:
        wiki_calls.append(query)
        return _make_wiki_evidence(query)

    monkeypatch.setattr(qa, "_QA_WIKI", False)

    with patch.object(qa, "corpus_evidence", fake_corpus), \
         patch.object(qa, "wiki_evidence", fake_wiki):
        result = await qa.retrieve_evidence(scope, book_slugs=["hansen"])

    assert len(wiki_calls) == 0, "wiki_evidence must not be called when _QA_WIKI is False"
    assert len(corpus_calls) == 1
    assert all(e.kind == "corpus" for e in result)
