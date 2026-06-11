"""Degradation / edge-case tests for run_qa flat storytelling pipeline.

(a) write_story returns zero valid [[eid]] tokens → one redraft fired,
    write_story called twice, stream completes with done.
(b) retrieve_evidence returns [] → honest QAStoryAnswer, grounding["ok"]==False,
    citations==[], full SSE tail present.
(c) write_story RAISES → _fallback_story used, stream completes with done.
"""
from __future__ import annotations

import pytest

from src.services.chat.research import Evidence
from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest, QAScope

_STUB_CAT = [CatalogBook(slug="islp", name="ISLP", authors_short="James et al.",
                         field="ml_dp", chapters=["ch02"])]


async def _confident_resolve(*a, **k):
    return BookResolution(book_slug="islp", book_confidence=0.95,
                          book_candidates=["islp"])


def _corpus_ev(n: int = 1) -> Evidence:
    return Evidence(
        subject_id="qa",
        kind="corpus",
        text="Bias and variance trade off in supervised learning.",
        meta={
            "book_slug": "islp",
            "book_name": "ISLP",
            "chapter": "ch02",
            "section_id": "2.2",
            "chunk_id": f"chunk-{n}",
        },
        id=f"c{n}",
    )


async def _collect(gen):
    return [ev async for ev in gen]


# ---------------------------------------------------------------------------
# (a) Zero citations on first draft → one redraft fired
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_citations_triggers_one_redraft(monkeypatch):
    """write_story emits only an invalid [[bad]] token → binder produces zero
    citations → redraft is fired once; final stream ends with done."""
    from src.services.chat.agents import qa
    from src.services.chat.schemas import QAStoryDraft

    write_call_count = {"n": 0}

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap=query.strip())

    async def fake_retrieve(scope, *, book_slugs):
        return [_corpus_ev(1)]

    async def fake_write(scope, evidence, *, model=None):
        write_call_count["n"] += 1
        # Both calls emit only the invalid token so zero citations persist
        return QAStoryDraft(
            intro="The tradeoff [[bad]] is fundamental.",
            deepening="It affects every model [[bad]].",
            conclusion="Choose wisely [[bad]].",
        )

    async def fake_verify(answer, sources, *, model=None):
        return answer

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_evidence", fake_retrieve)
    monkeypatch.setattr(qa, "write_story", fake_write)
    monkeypatch.setattr(qa, "verify_story", fake_verify)

    req = ChatRequest(message="bias-variance tradeoff?", mode="qa")
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]

    # write_story called exactly twice (original + redraft)
    assert write_call_count["n"] == 2, (
        f"Expected write_story called 2 times but got {write_call_count['n']}"
    )

    # redraft progress event present
    progress_stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert "redraft" in progress_stages

    # Stream completes properly
    assert types[-1] == "done"
    assert "structured_output" in types

    # Still emits QAStoryAnswer (zero citations is acceptable after redraft)
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "QAStoryAnswer"
    # grounding ok=False because even redraft had zero citations
    assert so["data"]["grounding"].get("ok") is False


@pytest.mark.asyncio
async def test_zero_citations_redraft_succeeds_on_second_call(monkeypatch):
    """First write returns no valid tokens; second write (redraft) returns [[c1]].
    Final answer should have ≥1 citation and stream completes with done."""
    from src.services.chat.agents import qa
    from src.services.chat.schemas import QAStoryDraft

    call_n = {"n": 0}

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap=query.strip())

    async def fake_retrieve(scope, *, book_slugs):
        return [_corpus_ev(1)]

    async def fake_write(scope, evidence, *, model=None):
        call_n["n"] += 1
        if call_n["n"] == 1:
            # First draft: no valid eids
            return QAStoryDraft(
                intro="Tradeoff is important.",
                deepening="It matters.",
                conclusion="Consider it.",
            )
        # Second (redraft): valid [[c1]] token
        return QAStoryDraft(
            intro="Tradeoff [[c1]] is important.",
            deepening="It matters [[c1]].",
            conclusion="Consider it [[c1]].",
        )

    async def fake_verify(answer, sources, *, model=None):
        return answer

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_evidence", fake_retrieve)
    monkeypatch.setattr(qa, "write_story", fake_write)
    monkeypatch.setattr(qa, "verify_story", fake_verify)

    req = ChatRequest(message="tradeoff?", mode="qa")
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]

    assert call_n["n"] == 2
    assert types[-1] == "done"

    so = next(e for e in events if e["type"] == "structured_output")
    assert len(so["data"]["citations"]) >= 1


# ---------------------------------------------------------------------------
# (b) retrieve_evidence returns [] → honest QAStoryAnswer, no fabrications
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_evidence_honest_answer(monkeypatch):
    """retrieve_evidence returns [] → honest answer with ok=False, no citations,
    full SSE tail (structured_output + sources_full + retrieval_meta + usage + done)."""
    from src.services.chat.agents import qa

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap="very obscure thing")

    async def empty_retrieve(scope, *, book_slugs):
        return []

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_evidence", empty_retrieve)

    req = ChatRequest(message="very obscure thing", mode="qa")
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]

    # Full SSE tail must be present
    assert "structured_output" in types
    assert "sources_full" in types
    assert "retrieval_meta" in types
    assert "usage" in types
    assert types[-1] == "done"

    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "QAStoryAnswer"
    data = so["data"]
    assert data["citations"] == []
    assert data["grounding"]["ok"] is False
    assert data["grounding"].get("corpus_weak") is True

    # sources_full is empty (no corpus evidence)
    sf = next(e for e in events if e["type"] == "sources_full")
    assert sf["sources"] == []

    # intro is an honest "not covered" sentence, not a fabrication
    assert data["intro"].strip() != ""


# ---------------------------------------------------------------------------
# (c) write_story RAISES → _fallback_story used, stream completes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_story_exception_uses_fallback(monkeypatch):
    """When write_story raises, _fallback_story is invoked and stream ends
    properly with structured_output + done."""
    from src.services.chat.agents import qa
    from src.services.chat.schemas import QAStoryAnswer

    _SENTINEL = QAStoryAnswer(
        intro="FALLBACK sentinel answer.",
        deepening="",
        conclusion="",
        scope=QAScope(target_gap="sentinel"),
        citations=[],
        grounding={"ok": True, "fallback": True},
    )

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap=query.strip())

    async def fake_retrieve(scope, *, book_slugs):
        return [_corpus_ev(1)]

    async def boom_write(scope, evidence, *, model=None):
        raise RuntimeError("LLM provider exploded")

    async def fake_fallback(scope, sources, *, model=None):
        return _SENTINEL

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_evidence", fake_retrieve)
    monkeypatch.setattr(qa, "write_story", boom_write)
    monkeypatch.setattr(qa, "_fallback_story", fake_fallback)

    req = ChatRequest(message="bias-variance?", mode="qa")
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]

    # Stream must terminate cleanly
    assert types[-1] == "done"
    assert "structured_output" in types

    # Sentinel answer was emitted (no error event — fallback keeps stream clean)
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "QAStoryAnswer"
    assert so["data"]["intro"] == "FALLBACK sentinel answer."
    assert so["data"]["grounding"].get("fallback") is True

    # No error event (fallback is transparent)
    assert "error" not in types


@pytest.mark.asyncio
async def test_qa_bind_exception_uses_fallback(monkeypatch):
    """When qa_bind raises (e.g. internal error), the exception is caught and
    _fallback_story is used. Stream must end with done."""
    from src.services.chat.agents import qa
    from src.services.chat.schemas import QAStoryDraft, QAStoryAnswer

    _SENTINEL = QAStoryAnswer(
        intro="BIND FALLBACK.",
        deepening="",
        conclusion="",
        scope=QAScope(target_gap="bind-test"),
        citations=[],
        grounding={"ok": True, "fallback": True},
    )

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap=query.strip())

    async def fake_retrieve(scope, *, book_slugs):
        return [_corpus_ev(1)]

    async def fake_write(scope, evidence, *, model=None):
        return QAStoryDraft(intro="ok [[c1]]", deepening="d", conclusion="c")

    def boom_bind(draft, evidence, *, scope=None):
        raise ValueError("bind crashed")

    async def fake_fallback(scope, sources, *, model=None):
        return _SENTINEL

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_evidence", fake_retrieve)
    monkeypatch.setattr(qa, "write_story", fake_write)
    monkeypatch.setattr(qa, "qa_bind", boom_bind)
    monkeypatch.setattr(qa, "_fallback_story", fake_fallback)

    req = ChatRequest(message="bind test?", mode="qa")
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]

    assert types[-1] == "done"
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["data"]["intro"] == "BIND FALLBACK."
