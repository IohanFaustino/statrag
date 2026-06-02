from unittest.mock import AsyncMock, patch

import pytest

from src.services.chat.schemas import (
    ChapterScope, ConceptAnchor, ConceptProvenance, FacilitateBlock, FacilitateDigest,
)


def test_facilitate_schemas_construct():
    prov = ConceptProvenance(book_slug="hansen", authors_short="Hansen",
                             section="7.1 INTRODUCTION", page_from=176, page_to=176,
                             chunk_id="x", same_author=True, fallback=False)
    c = ConceptAnchor(id="c1", term="strong assumption of normality",
                      kind="concept", explanation="Assumes the data are normal.",
                      provenance=prov)
    blk = FacilitateBlock(h2_path="7.1 INTRODUCTION", section_id="x",
                          key_points=["a", "b"], body="text [[c1]]", concepts=[c],
                          page_from=176, page_to=176)
    scope = ChapterScope(book_slug="hansen", chapter_id="ch07", requested_subtopics=[])
    dig = FacilitateDigest(mode="facilitate", scope=scope, blocks=[blk])
    assert dig.blocks[0].concepts[0].kind == "concept"
    assert dig.blocks[0].key_points == ["a", "b"]
    assert dig.mode == "facilitate"


import src.services.chat.retrieval as retrieval
from src.services.chat.schemas import Source


def _src(section, chunkId, text, book="hansen", score=0.5):
    return Source(rank=1, book=book, chapter="ch07", section=section, title=section,
                  excerpt=text[:120], score=score, chunkId=chunkId, chunk=text,
                  book_name="Probability and Statistics for Economists",
                  authors_short="Hansen", page_from=170, page_to=171)


def test_fetch_concept_support_prefers_same_author_prior(monkeypatch):
    pool = [
        _src("7.5 LATER", "s9", "uses normality again", score=0.9),
        _src("7.2 ASSUMPTIONS", "s2", "Definition: a strong assumption of normality means ...", score=0.6),
    ]
    monkeypatch.setattr(retrieval, "hybrid_search", lambda q, **k: (pool, None))
    monkeypatch.setattr(retrieval, "_section_order_in_book",
                        lambda slug: {"s2": 2, "s5": 5, "s9": 9})
    sup = retrieval.fetch_concept_support("strong assumption of normality",
                                          book_slug="hansen", before_section_id="s5",
                                          min_score=0.3)
    assert sup is not None
    assert sup.chunk_id == "s2"          # prior + formal beats later high-score
    assert sup.same_author is True
    assert sup.fallback is False


def test_fetch_concept_support_none_when_all_below_min(monkeypatch):
    monkeypatch.setattr(retrieval, "hybrid_search", lambda q, **k: ([], None))
    monkeypatch.setattr(retrieval, "_section_order_in_book", lambda slug: {})
    sup = retrieval.fetch_concept_support("x", book_slug="hansen",
                                          before_section_id="s5", min_score=0.3)
    assert sup is None


import pytest
from src.services.chat.agents import facilitate as fac
from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest

_CATF = [CatalogBook(slug="hansen", name="Probability and Statistics for Economists",
                     authors_short="Hansen", field="introduction", chapters=["ch07"])]


def _secf(title, cid, text):
    return Source(rank=1, book="hansen", chapter="ch07", section=title, title=title,
                  excerpt=text[:120], score=0.0, chunkId=cid, chunk=text,
                  book_name="Probability and Statistics for Economists",
                  authors_short="Hansen", page_from=176, page_to=176)


@pytest.mark.asyncio
async def test_run_facilitate_builds_digest_with_anchor(monkeypatch):
    monkeypatch.setattr(fac, "parse_catalog", lambda: _CATF)
    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="hansen", book_confidence=1.0,
                              book_candidates=["hansen"], chapter_id="ch07",
                              requested_subtopics=[])
    monkeypatch.setattr(fac, "resolve_book", fake_resolve)
    monkeypatch.setattr(fac, "fetch_chapter_sections",
                        lambda b, c, **k: [_secf("7.1 INTRODUCTION", "s1",
                                                 "Assumes a strong assumption of normality.")])
    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        sysmsg = messages[0]["content"]
        if "orient a learner before they read" in sysmsg:
            return "We will cover Chebyshev's inequality and why it bounds tail probabilities."
        if "analyse one textbook section" in sysmsg:
            return '{"key_points":["pt"],"concepts":[{"term":"strong assumption of normality","kind":"concept","status":"referenced"}]}'
        if "You explain one term" in sysmsg:
            return "It assumes the data are normally distributed."
        if "preparing THIS section as a short lesson" in sysmsg:
            return "- pt\n\nWe rely on the strong assumption of normality [[c1]]."
        if "proofreading a lesson" in sysmsg:
            return '{"fixed_body":"- pt\\n\\nWe rely on the strong assumption of normality [[c1]].","ok":true,"unsupported":[],"confidence":0.9}'
        return "{}"
    monkeypatch.setattr(fac, "_chat", fake_chat)
    from src.services.chat import retrieval as r
    monkeypatch.setattr(fac, "fetch_concept_support",
                        lambda term, **k: r.ConceptSupport(
                            chunk_id="s0", section="7.0", book_slug="hansen",
                            book_name="P&S", authors_short="Hansen", page_from=170,
                            page_to=170, text="def", same_author=True, fallback=False))
    req = ChatRequest(message="facilitate ch07 of hansen", mode="facilitate", bookFilter=["hansen"])
    evs = [e async for e in fac.run_facilitate(req)]
    so = next(e for e in evs if e["type"] == "structured_output")
    assert so["schema"] == "FacilitateDigest"
    blk = so["data"]["blocks"][0]
    assert blk["key_points"] == ["pt"]
    assert blk["concepts"][0]["id"] == "c1"
    assert "[[c1]]" in blk["body"]
    assert so["data"]["intro"] == "We will cover Chebyshev's inequality and why it bounds tail probabilities."
    assert evs[-1]["type"] == "done"


def _stub_run_facilitate(monkeypatch, map_return):
    """Shared stub setup for run_facilitate concept-path tests."""
    monkeypatch.setattr(fac, "parse_catalog", lambda: _CATF)

    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="hansen", book_confidence=1.0,
                              book_candidates=["hansen"], chapter_id="ch07",
                              requested_subtopics=[])
    monkeypatch.setattr(fac, "resolve_book", fake_resolve)
    monkeypatch.setattr(fac, "fetch_chapter_sections",
                        lambda b, c, **k: [_secf("7.1 INTRODUCTION", "s1",
                                                 "Some section text.")])
    monkeypatch.setattr(fac, "_section_order_in_book", lambda slug: {})

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        sysmsg = messages[0]["content"]
        if "analyse one textbook section" in sysmsg:
            return map_return
        if "You explain one term" in sysmsg:
            return "Explanation text."
        if "preparing THIS section as a short lesson" in sysmsg:
            return "- pt\n\nBody [[c1]]."
        if "proofreading a lesson" in sysmsg:
            return '{"fixed_body":"- pt\\n\\nBody [[c1]].","ok":true,"unsupported":[],"confidence":0.9}'
        return "{}"
    monkeypatch.setattr(fac, "_chat", fake_chat)


@pytest.mark.asyncio
async def test_explained_concept_skips_retrieval(monkeypatch):
    """Concepts with status='explained' must never trigger sub-retrieval."""
    map_json = '{"key_points":["pt"],"concepts":[{"term":"normality","kind":"concept","status":"explained"}]}'
    _stub_run_facilitate(monkeypatch, map_json)

    def must_not_be_called(term, **k):
        raise AssertionError("fetch_concept_support must not be called for explained concepts")
    monkeypatch.setattr(fac, "fetch_concept_support", must_not_be_called)

    req = ChatRequest(message="facilitate ch07 of hansen", mode="facilitate", bookFilter=["hansen"])
    evs = [e async for e in fac.run_facilitate(req)]
    so = next(e for e in evs if e["type"] == "structured_output")
    blk = so["data"]["blocks"][0]
    assert len(blk["concepts"]) == 1
    assert blk["concepts"][0]["term"] == "normality"


@pytest.mark.asyncio
async def test_referenced_concept_no_support_still_anchors_with_fallback(monkeypatch):
    """When fetch_concept_support returns None, fallback anchor is built from in-section text."""
    map_json = '{"key_points":["pt"],"concepts":[{"term":"normality","kind":"concept","status":"referenced"}]}'
    _stub_run_facilitate(monkeypatch, map_json)
    monkeypatch.setattr(fac, "fetch_concept_support", lambda term, **k: None)

    req = ChatRequest(message="facilitate ch07 of hansen", mode="facilitate", bookFilter=["hansen"])
    evs = [e async for e in fac.run_facilitate(req)]
    so = next(e for e in evs if e["type"] == "structured_output")
    blk = so["data"]["blocks"][0]
    assert len(blk["concepts"]) == 1
    anchor = blk["concepts"][0]
    assert anchor["provenance"]["fallback"] is True


@pytest.mark.asyncio
async def test_subretrieval_disabled_uses_in_section(monkeypatch):
    """When _SUBRETRIEVAL=False, referenced concepts fall back without any retrieval call."""
    map_json = '{"key_points":["pt"],"concepts":[{"term":"normality","kind":"concept","status":"referenced"}]}'
    _stub_run_facilitate(monkeypatch, map_json)
    monkeypatch.setattr(fac, "_SUBRETRIEVAL", False)

    def must_not_be_called(term, **k):
        raise AssertionError("fetch_concept_support must not be called when _SUBRETRIEVAL=False")
    monkeypatch.setattr(fac, "fetch_concept_support", must_not_be_called)

    req = ChatRequest(message="facilitate ch07 of hansen", mode="facilitate", bookFilter=["hansen"])
    evs = [e async for e in fac.run_facilitate(req)]
    so = next(e for e in evs if e["type"] == "structured_output")
    blk = so["data"]["blocks"][0]
    assert len(blk["concepts"]) == 1
    anchor = blk["concepts"][0]
    # fallback=True because status was "referenced" but no retrieval was attempted
    assert anchor["provenance"]["fallback"] is True


@pytest.mark.asyncio
async def test_run_facilitate_sets_intro(monkeypatch):
    """Intro node runs after per-section loop and sets FacilitateDigest.intro."""
    _EXPECTED_INTRO = "We will cover Chebyshev's inequality and why it bounds tail probabilities."
    map_json = '{"key_points":["pt"],"concepts":[]}'
    monkeypatch.setattr(fac, "parse_catalog", lambda: _CATF)

    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="hansen", book_confidence=1.0,
                              book_candidates=["hansen"], chapter_id="ch07",
                              requested_subtopics=[])
    monkeypatch.setattr(fac, "resolve_book", fake_resolve)
    monkeypatch.setattr(fac, "fetch_chapter_sections",
                        lambda b, c, **k: [_secf("7.1 INTRODUCTION", "s1",
                                                 "Assumes a strong assumption of normality.")])
    monkeypatch.setattr(fac, "_section_order_in_book", lambda slug: {})

    async def fake_chat(messages, *, model, max_tokens, temperature=0.0, schema=None):
        sysmsg = messages[0]["content"]
        if "orient a learner before they read" in sysmsg:
            return _EXPECTED_INTRO
        if "analyse one textbook section" in sysmsg:
            return map_json
        if "You explain one term" in sysmsg:
            return "Explanation text."
        if "preparing THIS section as a short lesson" in sysmsg:
            return "- pt\n\nBody text."
        if "proofreading a lesson" in sysmsg:
            return '{"fixed_body":"- pt\\n\\nBody text.","ok":true,"unsupported":[],"confidence":0.9}'
        return "{}"
    monkeypatch.setattr(fac, "_chat", fake_chat)
    monkeypatch.setattr(fac, "fetch_concept_support", lambda term, **k: None)

    req = ChatRequest(message="facilitate ch07 of hansen", mode="facilitate", bookFilter=["hansen"])
    evs = [e async for e in fac.run_facilitate(req)]

    # Check the intro stage event is emitted
    stage_labels = [e["stage"] for e in evs if e["type"] == "stage"]
    assert "intro" in stage_labels

    so = next(e for e in evs if e["type"] == "structured_output")
    assert so["data"]["intro"] == _EXPECTED_INTRO
    # Existing anchor assertions still hold (no concepts here, but blocks are built)
    assert len(so["data"]["blocks"]) == 1
    assert evs[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_chat_object_model_injects_hint_and_json_object():
    captured = {}

    class _Resp:
        class _Choice:
            class _Msg:
                content = '{"key_points": [], "concepts": []}'
            message = _Msg()
        choices = [_Choice()]

    async def _create(**kwargs):
        captured.update(kwargs)
        return _Resp()

    client = AsyncMock()
    client.chat.completions.create = _create
    with patch.object(fac, "aclient_for", return_value=client):
        await fac._chat(
            [{"role": "system", "content": "BASE"},
             {"role": "user", "content": "u"}],
            model="deepseek-v4-pro", max_tokens=100,
            schema=fac.FacilitateMap,
        )
    assert captured["response_format"] == {"type": "json_object"}
    sys_msg = captured["messages"][0]["content"]
    assert "BASE" in sys_msg and "json" in sys_msg.lower()
    assert "key_points" in sys_msg


@pytest.mark.asyncio
async def test_chat_schema_model_leaves_system_untouched():
    captured = {}

    class _Resp:
        class _Choice:
            class _Msg:
                content = "{}"
            message = _Msg()
        choices = [_Choice()]

    async def _create(**kwargs):
        captured.update(kwargs)
        return _Resp()

    client = AsyncMock()
    client.chat.completions.create = _create
    with patch.object(fac, "aclient_for", return_value=client):
        await fac._chat(
            [{"role": "system", "content": "BASE"},
             {"role": "user", "content": "u"}],
            model="gpt-4o", max_tokens=100,
            schema=fac.FacilitateMap,
        )
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["messages"][0]["content"] == "BASE"
