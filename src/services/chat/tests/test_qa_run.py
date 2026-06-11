"""run_qa SSE integration tests — flat storytelling pipeline (all seams mocked)."""
from __future__ import annotations

import pytest

from src.services.chat.research import Evidence
from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest, QAScope

_STUB_CAT = [CatalogBook(slug="islp", name="ISLP", authors_short="James et al.",
                         field="ml_dp", chapters=["ch02"])]


async def _confident_resolve(*a, **k):
    return BookResolution(book_slug="islp", book_confidence=0.95,
                          book_candidates=["islp"])


def _corpus_ev(n=1) -> Evidence:
    return Evidence(
        subject_id="qa",
        kind="corpus",
        text=f"Bias and variance trade off because of the squared-bias term [c{n}].",
        meta={
            "book_slug": "islp",
            "book_name": "ISLP",
            "authors": "James et al.",
            "year": 2023,
            "chapter": "ch02",
            "section_id": "2.2",
            "chunk_id": f"chunk-{n}",
        },
        id=f"c{n}",
    )


def _wiki_ev() -> Evidence:
    return Evidence(
        subject_id="qa",
        kind="wikipedia",
        text="Bias-variance tradeoff is a central concept in supervised learning.",
        meta={"title": "Bias-variance tradeoff", "url": "https://en.wikipedia.org/wiki/Bias%E2%80%93variance_tradeoff"},
        id="w1",
    )


async def _collect(gen):
    return [ev async for ev in gen]


@pytest.mark.asyncio
async def test_run_qa_emits_full_event_sequence(monkeypatch):
    """Happy-path: meta → progress(retrieving) → progress(writing) → progress(binding)
    → structured_output(QAStoryAnswer) → sources_full → retrieval_meta → usage → done."""
    from src.services.chat.agents import qa
    from src.services.chat.schemas import QAStoryDraft

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap="why bias and variance trade off",
                       assumed_known=["bias", "variance"])

    async def fake_retrieve(scope, *, book_slugs):
        return [_corpus_ev(1), _wiki_ev()]

    async def fake_write(scope, evidence, *, model=None):
        return QAStoryDraft(
            intro="Bias and variance trade off [[c1]] because lowering bias raises variance.",
            deepening="This is fundamental [[c1]].",
            conclusion="In sum, the tradeoff [[c1]] governs model selection.",
        )

    async def fake_verify(answer, sources, *, model=None):
        return answer.model_copy(update={
            "grounding": {**answer.grounding, "ok": True, "confidence": 0.9}
        })

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_evidence", fake_retrieve)
    monkeypatch.setattr(qa, "write_story", fake_write)
    monkeypatch.setattr(qa, "verify_story", fake_verify)

    req = ChatRequest(message="What is the bias-variance tradeoff?", mode="qa")
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]

    # Mandatory sequence checks
    assert types[0] == "meta"
    assert types[-1] == "done"
    assert "structured_output" in types
    assert "sources_full" in types
    assert "retrieval_meta" in types
    assert "usage" in types

    # Progress events present
    progress_stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert "retrieving" in progress_stages
    assert "writing" in progress_stages
    assert "binding" in progress_stages

    # structured_output uses QAStoryAnswer schema with 3-field shape
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "QAStoryAnswer"
    assert "intro" in so["data"]
    assert "deepening" in so["data"]
    assert "conclusion" in so["data"]

    # citations bound from [[c1]] token
    assert len(so["data"]["citations"]) >= 1


@pytest.mark.asyncio
async def test_run_qa_structured_output_schema_is_qa_story_answer(monkeypatch):
    """structured_output.schema must be 'QAStoryAnswer', never 'QAAnswer'."""
    from src.services.chat.agents import qa
    from src.services.chat.schemas import QAStoryDraft

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap=query.strip())

    async def fake_retrieve(scope, *, book_slugs):
        return [_corpus_ev(1)]

    async def fake_write(scope, evidence, *, model=None):
        return QAStoryDraft(
            intro="Answer [[c1]].",
            deepening="More detail [[c1]].",
            conclusion="In summary [[c1]].",
        )

    async def fake_verify(answer, sources, *, model=None):
        return answer

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_evidence", fake_retrieve)
    monkeypatch.setattr(qa, "write_story", fake_write)
    monkeypatch.setattr(qa, "verify_story", fake_verify)

    req = ChatRequest(message="p-value?", mode="qa")
    events = await _collect(qa.run_qa(req))

    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "QAStoryAnswer", (
        f"Expected 'QAStoryAnswer' but got {so['schema']!r} — "
        "run_qa must emit the new schema, not legacy QAAnswer"
    )
    assert "text" not in so["data"], "QAStoryAnswer has no 'text' field"


@pytest.mark.asyncio
async def test_run_qa_sources_full_built_from_corpus_ev(monkeypatch):
    """sources_full must contain rows derived from corpus Evidence meta."""
    from src.services.chat.agents import qa
    from src.services.chat.schemas import QAStoryDraft

    async def fake_scope(query, *, model=None):
        return QAScope(target_gap=query.strip())

    async def fake_retrieve(scope, *, book_slugs):
        return [_corpus_ev(1), _wiki_ev()]  # 1 corpus + 1 wiki

    async def fake_write(scope, evidence, *, model=None):
        return QAStoryDraft(intro="[[c1]]", deepening="[[c1]]", conclusion="[[c1]]")

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

    sf = next(e for e in events if e["type"] == "sources_full")
    # Only corpus (not wiki) → exactly 1 row
    assert len(sf["sources"]) == 1
    row = sf["sources"][0]
    assert row["book"] == "islp"
    assert row["book_name"] == "ISLP"
    assert row["chapter"] == "ch02"


@pytest.mark.asyncio
async def test_run_qa_clarify_emitted_on_unknown_book(monkeypatch):
    """When resolve_book returns low-confidence, clarify + done are emitted."""
    from src.services.chat.agents import qa

    async def zero_confidence(*a, **k):
        return BookResolution(book_slug="", book_confidence=0.0, book_candidates=[])

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", zero_confidence)

    req = ChatRequest(message="In Hansen's book, what is a sigma-algebra?",
                      mode="qa", bookFilter=[])
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]
    assert "clarify" in types
    assert types[-1] == "done"
    # No structured_output on clarify path
    assert "structured_output" not in types
