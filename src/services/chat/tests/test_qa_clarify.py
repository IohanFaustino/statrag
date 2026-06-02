import pytest
from src.services.chat.agents import qa
from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest

_CAT = [CatalogBook(slug="islp", name="ISL", authors_short="James et al.",
                    field="ml_dp", chapters=["ch02"])]


@pytest.mark.asyncio
async def test_qa_clarify_on_unknown_book(monkeypatch):
    monkeypatch.setattr(qa, "parse_catalog", lambda: _CAT)
    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="", book_confidence=0.0, book_candidates=[])
    monkeypatch.setattr(qa, "resolve_book", fake_resolve)
    req = ChatRequest(message="in Hansen's probability, what is a sigma-algebra?",
                      mode="qa", bookFilter=[])
    evs = [e async for e in qa.run_qa(req)]
    types = [e["type"] for e in evs]
    assert "clarify" in types
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_qa_no_clarify_when_confident(monkeypatch):
    monkeypatch.setattr(qa, "parse_catalog", lambda: _CAT)
    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="islp", book_confidence=0.95,
                              book_candidates=["islp"])
    monkeypatch.setattr(qa, "resolve_book", fake_resolve)
    async def fake_scope(query, *, model=None):
        return qa.QAScope(target_gap="what is bias")
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    def fake_retrieve(scope, *, book_slugs, k=4):
        from src.services.chat.schemas import Source
        src = Source(rank=1, book="islp", chapter="ch02", section="2.1",
                     title="Bias", excerpt="Bias is ...", score=0.9,
                     chunkId="c1", chunk="Bias is ...", book_name="ISL")
        return [src], {"mode": "qa-test"}
    monkeypatch.setattr(qa, "retrieve_for_gap", fake_retrieve)
    async def fake_gen(scope, sources, *, model=None):
        return qa.QAAnswer(text="Bias is the error from wrong assumptions.",
                           scope=scope, citations=[], math_blocks=[])
    monkeypatch.setattr(qa, "generate_scoped", fake_gen)
    async def fake_verify(answer, sources, *, model=None):
        return answer.model_copy(update={"grounding": {"ok": True, "unsupported": [], "confidence": 0.95}})
    monkeypatch.setattr(qa, "verify_grounding", fake_verify)
    req = ChatRequest(message="what is bias?", mode="qa", bookFilter=["islp"])
    evs = [e async for e in qa.run_qa(req)]
    assert "clarify" not in [e["type"] for e in evs]
