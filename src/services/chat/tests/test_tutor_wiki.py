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
    # corpus order preserved: first and third should be corpus sources
    assert merged[0].book == "islp" and merged[2].book == "esl"
    # wiki source interleaved (not trailing) at position 1
    assert merged[1].book == "wikipedia" and merged[1].rank == 2


def test_wiki_interleaved_not_all_trailing():
    from src.services.chat.agents.deep_tutor import _append_wiki_sources
    from src.services.chat.schemas import Source
    def mk(book, rank):
        return Source(rank=rank, book=book, chapter="", section=f"s{rank}", title="t",
                      excerpt="x", score=1.0, chunkId=f"{book}:{rank}", chunk="c",
                      book_name=book, url="")
    corpus = [mk("hansen", i) for i in range(1, 7)]   # 6 corpus
    wiki = [mk("wikipedia", 0), mk("wikipedia", 0)]   # 2 wiki
    out = _append_wiki_sources(corpus, wiki)
    assert len(out) == 8
    ranks = [s.rank for s in out]
    assert ranks == sorted(ranks) and len(set(ranks)) == 8   # contiguous unique 1..8
    wiki_positions = [i for i, s in enumerate(out) if s.book == "wikipedia"]
    assert max(wiki_positions) < len(out) - 1                # no wiki is last
    corpus_order = [s.chunkId for s in out if s.book == "hansen"]
    assert corpus_order == [f"hansen:{i}" for i in range(1, 7)]   # corpus order preserved
