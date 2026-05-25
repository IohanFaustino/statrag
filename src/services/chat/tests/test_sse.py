"""Tests for the SSE orchestrator and the FastAPI /api/chat + /api/health endpoints.

All external I/O (Qdrant, OpenAI, figure search) is mocked so tests run fully
offline.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on PYTHONPATH and a dummy API key is present
# ---------------------------------------------------------------------------

_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_source(rank: int = 1) -> "Source":  # noqa: F821
    from src.services.chat.schemas import Source

    return Source(
        rank=rank,
        book="islp",
        chapter="ch01",
        section="1.1",
        title="Introduction",
        excerpt="Short excerpt.",
        score=0.9,
        page=1,
        chunkId=uuid.uuid4().hex,
        chunk="Full chunk text about linear regression and statistics.",
        highlights=[],
    )


def _make_metadata() -> "RetrievalMetadata":  # noqa: F821
    from src.services.chat.schemas import RetrievalMetadata

    return RetrievalMetadata(
        rewrittenQuery="what is regression",
        embedding="text-embedding-3-large",
        retrievalMs=50,
        collections=["introduction_textbooks"],
        filter="none",
        topK=5,
        scoreThreshold=0.0,
        mode="hybrid (RRF: dense + sparse)",
    )


async def _mock_llm_stream(
    messages,  # noqa: ANN001
    *,
    model: str,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> AsyncIterator[str]:
    """Yield 3 fixed token chunks to simulate an LLM stream."""
    for chunk in ["Hello ", "world\n\n", "more"]:
        yield chunk


# ---------------------------------------------------------------------------
# Tests — stream_chat
# ---------------------------------------------------------------------------


class TestStreamChat:
    """Test the stream_chat() orchestrator function end-to-end with mocks."""

    @pytest.fixture
    def mock_hybrid_search(self, monkeypatch: pytest.MonkeyPatch):
        """Replace hybrid_search with a deterministic stub."""
        source = _make_source()
        metadata = _make_metadata()

        def _fake_search(query, *, book_slugs=None, top_k=5, rerank=False, rerank_top_n=None, **_kw):
            return [source], metadata

        monkeypatch.setattr(
            "src.services.chat.orchestrator.hybrid_search",
            _fake_search,
        )
        # Also stub expand_queries so no real OpenAI call is made (returns [query])
        import asyncio as _asyncio

        async def _fake_expand(query, *, flags):
            return [query]

        monkeypatch.setattr(
            "src.services.chat.orchestrator.expand_queries",
            _fake_expand,
        )
        return source, metadata

    @pytest.fixture
    def mock_search_figures(self, monkeypatch: pytest.MonkeyPatch):
        """Replace search_figures with a stub returning an empty list."""

        def _fake_figures(query, book_slugs=None, k=2):
            return []

        monkeypatch.setattr(
            "src.services.chat.orchestrator.search_figures",
            _fake_figures,
        )

    @pytest.fixture
    def mock_highlights(self, monkeypatch: pytest.MonkeyPatch):
        """Replace compute_highlights with a no-op stub."""

        def _fake_highlights(query, chunk, max_spans=2):
            return []

        monkeypatch.setattr(
            "src.services.chat.orchestrator.compute_highlights",
            _fake_highlights,
        )

    @pytest.fixture
    def mock_llm(self, monkeypatch: pytest.MonkeyPatch):
        """Replace get_llm with a stub whose .stream() yields fixed tokens."""
        from src.services.chat.llm.base import BaseLLM

        class _StubLLM(BaseLLM):
            async def stream(self, messages, *, model, temperature=0.2, max_tokens=None, response_format=None):
                for chunk in ["Hello ", "world\n\n", "more"]:
                    yield chunk

        def _fake_get_llm(model_id: str):
            return _StubLLM(), model_id

        monkeypatch.setattr(
            "src.services.chat.orchestrator.get_llm",
            _fake_get_llm,
        )

    def _collect(self, coro) -> list[dict]:
        """Drain an async generator into a plain list synchronously."""

        async def _inner():
            return [ev async for ev in coro]

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_inner())
        finally:
            loop.close()

    def test_meta_is_first_event(
        self,
        mock_hybrid_search,
        mock_search_figures,
        mock_highlights,
        mock_llm,
    ) -> None:
        """The very first event yielded must be type=meta."""
        from src.services.chat.orchestrator import stream_chat
        from src.services.chat.schemas import ChatRequest

        req = ChatRequest(message="what is regression?")
        events = self._collect(stream_chat(req))

        assert events, "stream_chat yielded no events"
        assert events[0]["type"] == "meta"

    def test_done_is_last_event(
        self,
        mock_hybrid_search,
        mock_search_figures,
        mock_highlights,
        mock_llm,
    ) -> None:
        """The last event must always be type=done."""
        from src.services.chat.orchestrator import stream_chat
        from src.services.chat.schemas import ChatRequest

        req = ChatRequest(message="what is regression?")
        events = self._collect(stream_chat(req))

        assert events[-1]["type"] == "done"

    def test_sources_full_is_present(
        self,
        mock_hybrid_search,
        mock_search_figures,
        mock_highlights,
        mock_llm,
    ) -> None:
        """sources_full must appear somewhere in the event stream."""
        from src.services.chat.orchestrator import stream_chat
        from src.services.chat.schemas import ChatRequest

        req = ChatRequest(message="what is regression?")
        events = self._collect(stream_chat(req))

        types = [e["type"] for e in events]
        assert "sources_full" in types

    def test_retrieval_meta_is_present(
        self,
        mock_hybrid_search,
        mock_search_figures,
        mock_highlights,
        mock_llm,
    ) -> None:
        """retrieval_meta must appear somewhere in the event stream."""
        from src.services.chat.orchestrator import stream_chat
        from src.services.chat.schemas import ChatRequest

        req = ChatRequest(message="what is regression?")
        events = self._collect(stream_chat(req))

        types = [e["type"] for e in events]
        assert "retrieval_meta" in types

    def test_token_events_are_present(
        self,
        mock_hybrid_search,
        mock_search_figures,
        mock_highlights,
        mock_llm,
    ) -> None:
        """There must be at least one token event from the LLM stream."""
        from src.services.chat.orchestrator import stream_chat
        from src.services.chat.schemas import ChatRequest

        req = ChatRequest(message="what is regression?")
        events = self._collect(stream_chat(req))

        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) > 0

    def test_paragraph_break_emitted_for_double_newline(
        self,
        mock_hybrid_search,
        mock_search_figures,
        mock_highlights,
        mock_llm,
    ) -> None:
        """The \\n\\n in the mock token stream must emit a paragraph_break event."""
        from src.services.chat.orchestrator import stream_chat
        from src.services.chat.schemas import ChatRequest

        req = ChatRequest(message="what is regression?")
        events = self._collect(stream_chat(req))

        types = [e["type"] for e in events]
        assert "paragraph_break" in types

    def test_ordering_meta_before_tokens_before_sources(
        self,
        mock_hybrid_search,
        mock_search_figures,
        mock_highlights,
        mock_llm,
    ) -> None:
        """meta must precede any tokens; sources_full must follow all tokens."""
        from src.services.chat.orchestrator import stream_chat
        from src.services.chat.schemas import ChatRequest

        req = ChatRequest(message="what is regression?")
        events = self._collect(stream_chat(req))

        types = [e["type"] for e in events]
        meta_idx = types.index("meta")
        sources_idx = types.index("sources_full")
        token_indices = [i for i, t in enumerate(types) if t == "token"]

        assert meta_idx == 0
        if token_indices:
            assert meta_idx < token_indices[0]
            assert token_indices[-1] < sources_idx

    def test_error_event_on_llm_failure(
        self,
        mock_hybrid_search,
        mock_search_figures,
        mock_highlights,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An LLMError during streaming must produce an error event then done."""
        from src.services.chat.llm.base import BaseLLM, LLMError
        from src.services.chat.orchestrator import stream_chat
        from src.services.chat.schemas import ChatRequest

        class _BrokenLLM(BaseLLM):
            async def stream(self, messages, *, model, temperature=0.2, max_tokens=None, response_format=None):
                raise LLMError("provider exploded")
                yield  # make it a generator

        monkeypatch.setattr(
            "src.services.chat.orchestrator.get_llm",
            lambda model_id: (_BrokenLLM(), model_id),
        )

        req = ChatRequest(message="trigger failure")
        events = self._collect(stream_chat(req))

        types = [e["type"] for e in events]
        assert "error" in types
        assert types[-1] == "done"

    def test_meta_contains_expected_fields(
        self,
        mock_hybrid_search,
        mock_search_figures,
        mock_highlights,
        mock_llm,
    ) -> None:
        """The meta event must carry mode, books, sourceCount, latencyMs, model."""
        from src.services.chat.orchestrator import stream_chat
        from src.services.chat.schemas import ChatRequest

        req = ChatRequest(message="what is regression?", mode="tutor")
        events = self._collect(stream_chat(req))

        meta = events[0]
        assert meta["type"] == "meta"
        assert "mode" in meta
        assert "books" in meta
        assert "sourceCount" in meta
        assert "latencyMs" in meta
        assert "model" in meta

    def test_book_filter_list_passed_through(
        self,
        mock_search_figures,
        mock_highlights,
        mock_llm,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When bookFilter is a list, it must be forwarded to hybrid_search."""
        from src.services.chat.schemas import ChatRequest

        captured: list = []
        source = _make_source()
        metadata = _make_metadata()

        def _capturing_search(query, *, book_slugs=None, top_k=5, rerank=False, rerank_top_n=None, **_kw):
            captured.append(book_slugs)
            return [source], metadata

        monkeypatch.setattr(
            "src.services.chat.orchestrator.hybrid_search",
            _capturing_search,
        )

        async def _fake_expand(query, *, flags):
            return [query]

        monkeypatch.setattr(
            "src.services.chat.orchestrator.expand_queries",
            _fake_expand,
        )

        from src.services.chat.orchestrator import stream_chat

        req = ChatRequest(message="test", bookFilter=["islp", "hansen"])
        self._collect(stream_chat(req))

        assert captured == [["islp", "hansen"]]

    def test_book_filter_all_passes_none(
        self,
        mock_search_figures,
        mock_highlights,
        mock_llm,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When bookFilter == 'ALL', hybrid_search must receive book_slugs=None."""
        from src.services.chat.schemas import ChatRequest

        captured: list = []
        source = _make_source()
        metadata = _make_metadata()

        def _capturing_search(query, *, book_slugs=None, top_k=5, rerank=False, rerank_top_n=None, **_kw):
            captured.append(book_slugs)
            return [source], metadata

        monkeypatch.setattr(
            "src.services.chat.orchestrator.hybrid_search",
            _capturing_search,
        )

        async def _fake_expand(query, *, flags):
            return [query]

        monkeypatch.setattr(
            "src.services.chat.orchestrator.expand_queries",
            _fake_expand,
        )

        from src.services.chat.orchestrator import stream_chat

        req = ChatRequest(message="test", bookFilter="ALL")
        self._collect(stream_chat(req))

        assert captured == [None]


# ---------------------------------------------------------------------------
# Tests — FastAPI endpoints
# ---------------------------------------------------------------------------


class TestFastAPIEndpoints:
    """Test the mounted FastAPI application via TestClient."""

    @pytest.fixture
    def client(self):
        """Return a synchronous TestClient for the chat app."""
        from fastapi.testclient import TestClient
        from src.services.chat.api import app

        return TestClient(app)

    def test_health_returns_200(self, client) -> None:
        """/api/health must respond 200 with status ok."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_models_endpoint_returns_list(self, client) -> None:
        """/api/models must return a non-empty list of providers."""
        resp = client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_books_endpoint_returns_list(self, client) -> None:
        """/api/books must return a list (possibly empty when no YAML files)."""
        resp = client.get("/api/books")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
