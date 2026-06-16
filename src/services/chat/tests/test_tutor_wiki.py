"""Tutor mode — Wikipedia augmentation (corpus-primary, cited 🌐 source).

Covers the _fetch_wiki_sources helper: gating, mapping wiki Evidence -> Source
with url set, dedupe, trailing-rank append (augment-only), and silent degrade.
All network I/O is mocked via research.wiki_evidence.
"""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")

from unittest.mock import patch

from src.services.chat.agents import deep_tutor
from src.services.chat.research import Evidence


def _wiki(title, text="summary", url="https://en.wikipedia.org/wiki/X"):
    return [Evidence(subject_id=title, kind="wikipedia", text=text,
                     meta={"title": title, "url": url})]


def test_fetch_wiki_sources_maps_evidence_to_source(monkeypatch):
    monkeypatch.setenv("TUTOR_DEEP_WIKI", "1")
    with patch.object(deep_tutor, "wiki_evidence",
                      side_effect=lambda c, **k: _wiki(f"Article {c}")):
        out = asyncio.run(deep_tutor._fetch_wiki_sources(["bias", "variance"]))
    assert len(out) == 2
    s = out[0]
    assert s.book == "wikipedia"
    assert s.book_name == "Wikipedia"
    assert s.url == "https://en.wikipedia.org/wiki/X"
    assert s.chunkId.startswith("wiki:")
    assert s.score == 0.0


def test_fetch_wiki_sources_disabled_by_env(monkeypatch):
    monkeypatch.setenv("TUTOR_DEEP_WIKI", "0")
    with patch.object(deep_tutor, "wiki_evidence",
                      side_effect=AssertionError("should not be called")):
        out = asyncio.run(deep_tutor._fetch_wiki_sources(["bias"]))
    assert out == []


def test_fetch_wiki_sources_dedupes_by_title(monkeypatch):
    monkeypatch.setenv("TUTOR_DEEP_WIKI", "1")
    with patch.object(deep_tutor, "wiki_evidence",
                      side_effect=lambda c, **k: _wiki("Bias of an estimator")):
        out = asyncio.run(deep_tutor._fetch_wiki_sources(["bias", "estimator bias"]))
    assert len(out) == 1


def test_fetch_wiki_sources_degrades_on_failure(monkeypatch):
    monkeypatch.setenv("TUTOR_DEEP_WIKI", "1")
    with patch.object(deep_tutor, "wiki_evidence",
                      side_effect=RuntimeError("network down")):
        out = asyncio.run(deep_tutor._fetch_wiki_sources(["bias"]))
    assert out == []


def test_wiki_sources_appended_after_corpus_keep_corpus_ranks():
    """Augment-only: corpus sources keep ranks 1..N; wiki gets trailing ranks."""
    from src.services.chat.schemas import Source
    corpus = [
        Source(rank=1, book="islp", chapter="ch02", section="2.1", title="t",
               excerpt="e", score=0.9, chunkId="islp-1", chunk="c"),
        Source(rank=2, book="esl", chapter="ch03", section="3.4", title="t",
               excerpt="e", score=0.8, chunkId="esl-1", chunk="c"),
    ]
    wiki = [Source(rank=0, book="wikipedia", chapter="", section="Bias", title="Bias",
                   excerpt="e", score=0.0, chunkId="wiki:Bias", chunk="c",
                   book_name="Wikipedia", url="http://w/Bias")]
    merged = deep_tutor._append_wiki_sources(corpus, wiki)
    assert [s.rank for s in merged] == [1, 2, 3]
    assert merged[0].book == "islp" and merged[1].book == "esl"
    assert merged[2].book == "wikipedia" and merged[2].rank == 3
