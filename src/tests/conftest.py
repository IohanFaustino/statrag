"""Shared pytest fixtures for the RAG test suite.

Ensures:
- Project root is on PYTHONPATH so `from src.core.X import Y` / `from src.ingestion.X import Y` / `from src.services.retrieval.X import Y` works.
- A dummy OPENAI_API_KEY is set BEFORE any `src.*` import, since
  `src.config.Settings` validates it at import time.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# --- Path / env setup must happen before importing src.* anywhere ----------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")


@pytest.fixture
def tmp_markdown_corpus(tmp_path: Path) -> Path:
    """Write 3 small markdown files with #/## headers into a temp dir."""
    corpus = tmp_path / "raw"
    corpus.mkdir(parents=True, exist_ok=True)

    (corpus / "alpha.md").write_text(
        "# Alpha\n\n"
        "Intro paragraph about alpha topics in statistics.\n\n"
        "## Section A1\n\n"
        "More detail on alpha section one. Mean and variance are core.\n\n"
        "## Section A2\n\n"
        "Continuation: distributions and estimators.\n",
        encoding="utf-8",
    )
    (corpus / "beta.md").write_text(
        "# Beta\n\n"
        "Beta document overview paragraph.\n\n"
        "## Section B1\n\n"
        "Hypothesis testing fundamentals and p-values.\n\n"
        "## Section B2\n\n"
        "Confidence intervals and standard errors.\n",
        encoding="utf-8",
    )
    (corpus / "gamma.md").write_text(
        "# Gamma\n\n"
        "Gamma summary paragraph about regression.\n\n"
        "## Section G1\n\n"
        "Linear regression coefficients and residuals.\n",
        encoding="utf-8",
    )
    return corpus


@pytest.fixture
def monkeypatched_settings(monkeypatch, tmp_path: Path):
    """Redirect BM25_PICKLE and RAW_DIR into tmp_path for isolated tests."""
    from src import config as cfg

    raw_dir = tmp_path / "raw"
    bm25_dir = tmp_path / "bm25"
    bm25_pickle = bm25_dir / "corpus.pkl"
    raw_dir.mkdir(parents=True, exist_ok=True)
    bm25_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cfg, "RAW_DIR", raw_dir, raising=True)
    monkeypatch.setattr(cfg, "BM25_DIR", bm25_dir, raising=True)
    monkeypatch.setattr(cfg, "BM25_PICKLE", bm25_pickle, raising=True)

    # Also patch the names already imported into src.ingest / src.retrieval.retrievers.
    try:
        from src import ingest as ingest_mod

        monkeypatch.setattr(ingest_mod, "RAW_DIR", raw_dir, raising=False)
        monkeypatch.setattr(ingest_mod, "BM25_DIR", bm25_dir, raising=False)
        monkeypatch.setattr(ingest_mod, "BM25_PICKLE", bm25_pickle, raising=False)
    except Exception:
        pass

    try:
        from src import retrievers as retr_mod

        monkeypatch.setattr(retr_mod, "BM25_PICKLE", bm25_pickle, raising=False)
    except Exception:
        pass

    return {
        "RAW_DIR": raw_dir,
        "BM25_DIR": bm25_dir,
        "BM25_PICKLE": bm25_pickle,
    }


class _StubEmbeddings:
    """Deterministic, offline stand-in for OpenAIEmbeddings."""

    def __init__(self, *args, **kwargs):
        self.dim = 8

    def _vec(self, text: str) -> list[float]:
        # Deterministic pseudo-embedding from the text bytes.
        b = text.encode("utf-8") or b"x"
        return [(b[i % len(b)] % 17) / 17.0 for i in range(self.dim)]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str):
        return self._vec(text)


@pytest.fixture
def stub_embeddings(monkeypatch):
    """Replace OpenAIEmbeddings in src.ingest and src.retrieval.retrievers namespaces."""
    try:
        from src import ingest as ingest_mod

        monkeypatch.setattr(ingest_mod, "OpenAIEmbeddings", _StubEmbeddings, raising=False)
    except Exception:
        pass
    try:
        from src import retrievers as retr_mod

        monkeypatch.setattr(retr_mod, "OpenAIEmbeddings", _StubEmbeddings, raising=False)
    except Exception:
        pass
    return _StubEmbeddings
