"""run_qa SSE integration tests (all LLM + retrieval seams mocked)."""
from __future__ import annotations

import pytest

from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest

# Confident stub catalog + resolution — keeps resolve_book calls unit-scoped.
_STUB_CAT = [CatalogBook(slug="islp", name="ISLP", authors_short="James et al.",
                         field="ml_dp", chapters=["ch02"])]


async def _confident_resolve(*a, **k):
    return BookResolution(book_slug="islp", book_confidence=0.95,
                          book_candidates=["islp"])


def _src(rank=1):
    from src.services.chat.schemas import Source
    return Source(
        rank=rank, book="islp", chapter="ch02", section="2.2",
        title="t", excerpt="e", score=0.9, chunkId=f"c{rank}",
        chunk="Bias and variance trade off because …", book_name="ISLP",
    )


async def _collect(gen):
    return [ev async for ev in gen]


@pytest.mark.asyncio
async def test_run_qa_emits_full_event_sequence(monkeypatch):
    from src.services.chat.agents import qa

    async def fake_scope(query, *, model=None):
        return qa.QAScope(target_gap="why they trade off", assumed_known=["bias"])

    def fake_retrieve(scope, *, book_slugs, k=4):
        return [_src(1)], {"mode": "qa-test"}

    async def fake_gen(scope, sources, *, model=None):
        return qa.QAAnswer(text="answer [1]", scope=scope,
                           citations=[], math_blocks=[])

    async def fake_verify(answer, sources, *, model=None):
        return answer.model_copy(update={"grounding": {"ok": True, "unsupported": [], "confidence": 0.95}})

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_for_gap", fake_retrieve)
    monkeypatch.setattr(qa, "generate_scoped", fake_gen)
    monkeypatch.setattr(qa, "verify_grounding", fake_verify)

    req = ChatRequest(message="What is the tradeoff? I know bias.", mode="qa")
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert "structured_output" in types
    assert "sources_full" in types
    assert types[-1] == "done"
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "QAAnswer"
    assert so["data"]["grounding"]["ok"] is True


@pytest.mark.asyncio
async def test_run_qa_corpus_miss_no_fabricated_citation(monkeypatch):
    from src.services.chat.agents import qa

    async def fake_scope(query, *, model=None):
        return qa.QAScope(target_gap="obscure thing")

    def empty_retrieve(scope, *, book_slugs, k=4):
        return [], {"mode": "qa-test"}

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_for_gap", empty_retrieve)

    req = ChatRequest(message="obscure thing", mode="qa")
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]

    so = next(e for e in events if e["type"] == "structured_output")
    assert so["data"]["citations"] == []
    assert "not" in so["data"]["text"].lower()  # honest "not covered"

    # m4: corpus-miss path ends with done
    assert types[-1] == "done"

    # I3: corpus-miss path emits retrieval_meta and usage
    assert "retrieval_meta" in types
    assert "usage" in types


# C2: generate_scoped raising must still yield error + done (stream always terminates)
@pytest.mark.asyncio
async def test_run_qa_generate_error_yields_error_then_done(monkeypatch):
    from src.services.chat.agents import qa

    async def fake_scope(query, *, model=None):
        return qa.QAScope(target_gap="some query")

    def fake_retrieve(scope, *, book_slugs, k=4):
        return [_src(1)], {"mode": "qa-test"}

    async def boom_gen(scope, sources, *, model=None):
        raise RuntimeError("provider timed out")

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_for_gap", fake_retrieve)
    monkeypatch.setattr(qa, "generate_scoped", boom_gen)

    req = ChatRequest(message="some query", mode="qa")
    events = await _collect(qa.run_qa(req))
    types = [e["type"] for e in events]

    assert "error" in types
    assert types[-1] == "done"

    err = next(e for e in events if e["type"] == "error")
    assert err["code"] == "RuntimeError"
    assert "timed out" in err["message"]


# §10 conciseness KPI: a QA answer must be punctual (< 600 chars) not tutor-lengthy.
@pytest.mark.asyncio
async def test_run_qa_answer_is_concise(monkeypatch):
    """Spec §10: QA mode returns a punctual answer, not a long tutor exposition.

    A terse generate_scoped mock simulates normal QA output; we assert the
    structured_output text stays under the 600-char ceiling that distinguishes
    a punctual answer from a tutor-style essay.
    """
    from src.services.chat.agents import qa

    async def fake_scope(query, *, model=None):
        return qa.QAScope(target_gap="what is a p-value")

    def fake_retrieve(scope, *, book_slugs, k=4):
        return [_src(1)], {"mode": "qa-test"}

    async def fake_gen(scope, sources, *, model=None):
        # Terse 1-2 sentence QA answer — representative of well-behaved QA output.
        text = (
            "A p-value is the probability of obtaining results at least as extreme as "
            "the observed data, assuming the null hypothesis is true [1]."
        )
        return qa.QAAnswer(text=text, scope=scope, citations=[], math_blocks=[])

    async def fake_verify(answer, sources, *, model=None):
        return answer.model_copy(update={"grounding": {"ok": True, "unsupported": [], "confidence": 0.95}})

    monkeypatch.setattr(qa, "parse_catalog", lambda: _STUB_CAT)
    monkeypatch.setattr(qa, "resolve_book", _confident_resolve)
    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_for_gap", fake_retrieve)
    monkeypatch.setattr(qa, "generate_scoped", fake_gen)
    monkeypatch.setattr(qa, "verify_grounding", fake_verify)

    req = ChatRequest(message="What is a p-value?", mode="qa")
    events = await _collect(qa.run_qa(req))

    so = next(e for e in events if e["type"] == "structured_output")
    answer_text = so["data"]["text"]
    assert len(answer_text) < 600, (
        f"QA answer too long ({len(answer_text)} chars ≥ 600); "
        "QA mode must be punctual, not tutor-lengthy (spec §10)"
    )
