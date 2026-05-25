"""End-to-end integration test.

Skipped unless:
  - OPENAI_API_KEY is set to a real value (not the dummy test placeholder), AND
  - A Chroma server responds to a heartbeat on settings.chroma_host:port.

Run explicitly with:  pytest -m integration
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def _chroma_available():
    """Skip if OPENAI_API_KEY missing or Chroma unreachable."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key == "test-dummy-key":
        pytest.skip("OPENAI_API_KEY not set to a real value")

    chromadb = pytest.importorskip("chromadb")
    from src.core.config import settings

    try:
        client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        client.heartbeat()
    except Exception as exc:  # broad: any connection error skips
        pytest.skip(f"Chroma not reachable: {exc}")
    return True


def test_end_to_end_ingest_and_query(
    _chroma_available, tmp_markdown_corpus: Path, monkeypatched_settings
):
    from src import ingest as ingest_mod
    from src.services.retrieval.chain import build_chain

    # Point ingest at the temp corpus dir.
    docs = ingest_mod._load_markdown(tmp_markdown_corpus)
    chunks = ingest_mod._split(docs)
    chunks, ids = ingest_mod._dedupe(chunks)
    ingest_mod._persist_chroma(chunks, ids)
    ingest_mod._persist_bm25(chunks, ids)

    chain = build_chain()
    result = chain.invoke("What is hypothesis testing?")

    assert isinstance(result, dict)
    assert isinstance(result.get("answer"), str) and result["answer"].strip()
    sources = result.get("sources") or []
    assert len(sources) >= 1
    assert any("source" in (s.metadata or {}) for s in sources)
