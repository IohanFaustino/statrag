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
    async def fake_chat(messages, *, model, max_tokens, temperature=0.0):
        sysmsg = messages[0]["content"]
        if "analyse ONE textbook section" in sysmsg:
            return '{"key_points":["pt"],"concepts":[{"term":"strong assumption of normality","kind":"concept","status":"referenced"}]}'
        if "Explain the term" in sysmsg:
            return "It assumes the data are normally distributed."
        if "Rewrite this section" in sysmsg:
            return "- pt\n\nWe rely on the strong assumption of normality [[c1]]."
        if "Check the rewritten body" in sysmsg:
            return '{"ok":true,"unsupported":[],"confidence":0.9}'
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
    assert evs[-1]["type"] == "done"
