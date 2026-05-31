"""run_qa SSE integration tests (all LLM + retrieval seams mocked)."""
from __future__ import annotations

import pytest

from src.services.chat.schemas import ChatRequest


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

    monkeypatch.setattr(qa, "extract_scope", fake_scope)
    monkeypatch.setattr(qa, "retrieve_for_gap", empty_retrieve)

    req = ChatRequest(message="obscure thing", mode="qa")
    events = await _collect(qa.run_qa(req))
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["data"]["citations"] == []
    assert "not" in so["data"]["text"].lower()  # honest "not covered"
