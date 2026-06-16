import pytest
from src.services.chat.agents import qa
from src.services.chat.research import Evidence
from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest, QAScope

_CAT = [CatalogBook(slug="islp", name="ISL", authors_short="James et al.",
                    field="ml_dp", chapters=["ch02"])]


@pytest.mark.asyncio
async def test_qa_never_clarifies_answers_across_all_books_when_ambiguous(monkeypatch):
    """Q&A is separated from the shared book-disambiguation gate: when the book
    is ambiguous it does NOT clarify — it answers across all books
    (retrieve called with book_slugs=None)."""
    monkeypatch.setattr(qa, "parse_catalog", lambda: _CAT)

    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="", book_confidence=0.0, book_candidates=[])

    monkeypatch.setattr(qa, "resolve_book", fake_resolve)

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap="what is a sigma-algebra")

    monkeypatch.setattr(qa, "extract_scope", fake_scope)

    seen = {}

    async def fake_retrieve(scope, *, book_slugs):
        seen["book_slugs"] = book_slugs
        return [Evidence(
            subject_id="qa", kind="corpus", text="A sigma-algebra is a collection of sets.",
            meta={"book_slug": "islp", "book_name": "ISL", "chapter": "ch02",
                  "section_id": "2.1", "chunk_id": "c1"}, id="c1",
        )]

    monkeypatch.setattr(qa, "retrieve_evidence", fake_retrieve)

    from src.services.chat.schemas import QAStoryDraft

    async def fake_write(scope, evidence, *, model=None):
        return QAStoryDraft(intro="A sigma-algebra [[c1]] is a collection of sets.",
                            deepening="", conclusion="")

    monkeypatch.setattr(qa, "write_story", fake_write)

    async def fake_verify(answer, sources, *, model=None):
        return answer.model_copy(update={
            "grounding": {**answer.grounding, "ok": True, "confidence": 0.95}})

    monkeypatch.setattr(qa, "verify_story", fake_verify)

    req = ChatRequest(message="in Hansen's probability, what is a sigma-algebra?",
                      mode="qa", bookFilter=[])
    evs = [e async for e in qa.run_qa(req)]
    types = [e["type"] for e in evs]
    assert "clarify" not in types
    assert seen["book_slugs"] is None  # retrieved across all books


@pytest.mark.asyncio
async def test_qa_no_clarify_when_confident(monkeypatch):
    monkeypatch.setattr(qa, "parse_catalog", lambda: _CAT)

    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="islp", book_confidence=0.95,
                              book_candidates=["islp"])

    monkeypatch.setattr(qa, "resolve_book", fake_resolve)

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap="what is bias")

    monkeypatch.setattr(qa, "extract_scope", fake_scope)

    async def fake_retrieve(scope, *, book_slugs):
        return [Evidence(
            subject_id="qa", kind="corpus",
            text="Bias is the error from wrong assumptions.",
            meta={"book_slug": "islp", "book_name": "ISL", "chapter": "ch02",
                  "section_id": "2.1", "chunk_id": "c1"},
            id="c1",
        )]

    monkeypatch.setattr(qa, "retrieve_evidence", fake_retrieve)

    from src.services.chat.schemas import QAStoryDraft

    async def fake_write(scope, evidence, *, model=None):
        return QAStoryDraft(
            intro="Bias [[c1]] is the error from wrong model assumptions.",
            deepening="",
            conclusion="",
        )

    monkeypatch.setattr(qa, "write_story", fake_write)

    async def fake_verify(answer, sources, *, model=None):
        return answer.model_copy(update={
            "grounding": {**answer.grounding, "ok": True, "confidence": 0.95}
        })

    monkeypatch.setattr(qa, "verify_story", fake_verify)

    req = ChatRequest(message="what is bias?", mode="qa", bookFilter=["islp"])
    evs = [e async for e in qa.run_qa(req)]
    assert "clarify" not in [e["type"] for e in evs]
