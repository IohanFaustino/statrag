"""Unit tests for src.retrieval.chain helpers (no network)."""
from __future__ import annotations

from langchain_core.documents import Document

from src.services.retrieval import chain as chain_mod


def test_format_context_includes_source_tag():
    docs = [Document(page_content="content body", metadata={"source": "a.md"})]
    out = chain_mod._format_context(docs)
    assert "[a.md]" in out
    assert "content body" in out


def test_format_context_handles_missing_source():
    docs = [Document(page_content="orphan body", metadata={})]
    out = chain_mod._format_context(docs)
    assert "[unknown]" in out
    assert "orphan body" in out
