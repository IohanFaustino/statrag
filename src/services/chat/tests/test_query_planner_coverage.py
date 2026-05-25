"""Tests for the query-planner (top orchestrator) + coverage check (Option 2)."""
import pytest

from src.services.chat.schemas import Source
from src.services.chat.agents import deep_tutor as d
from src.services.chat.agents import coverage as cov


def _src(rank, cid):
    return Source(
        rank=rank, chunkId=cid, title="t", excerpt="x", chunk="hello",
        book="b", book_name="B", authors="A", authors_short="A",
        section="1", chapter="ch", score=0.5,
    )


# ── RRF merge ───────────────────────────────────────────────────────────────

def test_rrf_merge_dedups_and_fuses():
    a = [_src(1, "a"), _src(2, "b")]
    b = [_src(1, "b"), _src(2, "c")]
    merged = d._rrf_merge([a, b])
    ids = [s.chunkId for s in merged]
    assert ids[0] == "b"          # appears high in both → top
    assert set(ids) == {"a", "b", "c"}  # deduped


def test_rrf_merge_single_pool_passthrough_order():
    pool = [_src(1, "a"), _src(2, "b"), _src(3, "c")]
    assert [s.chunkId for s in d._rrf_merge([pool])] == ["a", "b", "c"]


# ── Query planner graceful fallback ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_concepts_ex_graceful_returns_queryplan(monkeypatch):
    class _Boom:
        class chat:
            class completions:
                @staticmethod
                async def create(*a, **k):
                    raise RuntimeError("boom")
    monkeypatch.setattr(d, "_async_client", lambda *_a, **_k: _Boom())
    qp = await d.extract_concepts_ex("what is the bias-variance tradeoff?")
    assert isinstance(qp, d.QueryPlan)
    assert qp.queries == [] and qp.facets == []   # degrades to legacy single-query
    assert isinstance(qp.suggested_authors, int)


@pytest.mark.asyncio
async def test_multi_query_candidates_empty_queries():
    assert await d._multi_query_candidates([], None, 10) == []


# ── Coverage check ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assess_coverage_empty_when_no_facets():
    assert await cov.assess_coverage("q", [], [_src(1, "a")]) == []


@pytest.mark.asyncio
async def test_assess_coverage_graceful_on_error(monkeypatch):
    class _Boom:
        class chat:
            class completions:
                @staticmethod
                async def create(*a, **k):
                    raise RuntimeError("boom")
    monkeypatch.setattr(cov, "_client", lambda *_a, **_k: _Boom())
    out = await cov.assess_coverage("q", ["bias formula", "variance formula"], [_src(1, "a")])
    assert out == []   # error → assume covered, never crash


@pytest.mark.asyncio
async def test_fill_missing_facets_dedups_against_seen(monkeypatch):
    from src.services.chat.schemas import RetrievalMetadata
    meta = RetrievalMetadata(rewrittenQuery="q", embedding="x", retrievalMs=1,
                             collections=[], filter="", topK=0, scoreThreshold=0.0, mode="m")
    def fake_hybrid(q, **k):
        return [_src(1, "a"), _src(2, "new")], meta
    monkeypatch.setattr(cov, "hybrid_search", fake_hybrid)
    seen = {"a"}
    out = await cov.fill_missing_facets(["variance formula"], None, 10, seen)
    assert [s.chunkId for s in out] == ["new"]   # "a" already seen → dropped
    assert "new" in seen                          # seen updated
