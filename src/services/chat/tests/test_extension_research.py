"""Pure-code researcher: corpus + wikipedia evidence with verbatim payload meta."""
from types import SimpleNamespace
from unittest.mock import patch

from src.services.chat.agents.extension_agents.research import (
    Evidence, corpus_evidence, wiki_evidence,
)


def _src(**over):
    """Mirrors real Source shape: chunkId, book, chapter (production field names)."""
    base = dict(chunk="Chebyshev states that …", book="moss",
                book_name="Probability", authors="Marcus Moss", year=2020,
                chapter="ch06", section="6.5.2", page_from=142, page_to=144,
                chunkId="c-1", score=0.81)
    base.update(over)
    return SimpleNamespace(**base)


def _src_legacy(**over):
    """Mirrors old plan-name shape: chunk_id, book_slug, chapter_id (fallback path)."""
    base = dict(chunk="Chebyshev states that …", book_slug="moss",
                book_name="Probability", authors="Marcus Moss", year=2020,
                chapter_id="ch06", section="6.5.2", page_from=142, page_to=144,
                chunk_id="c-legacy", score=0.75)
    base.update(over)
    return SimpleNamespace(**base)


def test_corpus_evidence_copies_payload_meta_verbatim():
    with patch("src.services.chat.agents.extension_agents.research.hybrid_search",
               return_value=([_src()], None)) as hs:
        ev = corpus_evidence("tail bounds", subject_id="s1",
                             exclude_book="hansen-probability",
                             all_slugs=["hansen-probability", "moss"], seen_ids=set())
    assert hs.call_args.kwargs["book_slugs"] == ["moss"]      # target book excluded
    assert hs.call_args.kwargs["rerank"] is True
    e = ev[0]
    assert isinstance(e, Evidence) and e.kind == "corpus" and e.subject_id == "s1"
    assert e.meta["book_name"] == "Probability" and e.meta["pages"] == "142–144"
    assert e.meta["section_id"] == "6.5.2" and e.meta["chunk_id"] == "c-1"
    # Real Source field names correctly read
    assert e.meta["book_slug"] == "moss"
    assert e.meta["chapter"] == "ch06"


def test_corpus_evidence_dedupes_seen_ids():
    """Deduplication works via real chunkId field."""
    seen = {"c-1"}
    with patch("src.services.chat.agents.extension_agents.research.hybrid_search",
               return_value=([_src()], None)):
        ev = corpus_evidence("q", subject_id="s1", exclude_book="x",
                             all_slugs=["x", "moss"], seen_ids=seen)
    assert ev == []


def test_corpus_evidence_legacy_fallback_chunk_id_book_slug():
    """Objects with legacy plan-name fields (chunk_id/book_slug/chapter_id) still work."""
    seen: set[str] = set()
    with patch("src.services.chat.agents.extension_agents.research.hybrid_search",
               return_value=([_src_legacy()], None)):
        ev = corpus_evidence("tail bounds", subject_id="s1",
                             exclude_book="hansen-probability",
                             all_slugs=["hansen-probability", "moss"], seen_ids=seen)
    assert len(ev) == 1
    e = ev[0]
    assert e.meta["chunk_id"] == "c-legacy"
    assert e.meta["book_slug"] == "moss"
    assert e.meta["chapter"] == "ch06"
    # Fallback id was added to seen_ids so a second call dedupes
    assert "c-legacy" in seen


def test_corpus_evidence_dedupes_via_legacy_chunk_id():
    """Deduplication also works when the object only exposes legacy chunk_id."""
    seen = {"c-legacy"}
    with patch("src.services.chat.agents.extension_agents.research.hybrid_search",
               return_value=([_src_legacy()], None)):
        ev = corpus_evidence("q", subject_id="s1", exclude_book="x",
                             all_slugs=["x", "moss"], seen_ids=seen)
    assert ev == []


def test_wiki_evidence_returns_title_url_extract():
    payload = {"title": "Chebyshev's inequality",
               "extract": "In probability theory…",
               "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Chebyshev%27s_inequality"}}}
    with patch("src.services.chat.agents.extension_agents.research._wiki_summary_json",
               return_value=payload):
        ev = wiki_evidence("Chebyshev inequality", subject_id="s2")
    e = ev[0]
    assert e.kind == "wikipedia" and e.meta["title"] == "Chebyshev's inequality"
    assert e.meta["url"].startswith("https://en.wikipedia.org/wiki/")
    assert "probability theory" in e.text


def test_wiki_evidence_empty_on_failure():
    with patch("src.services.chat.agents.extension_agents.research._wiki_summary_json",
               return_value=None):
        assert wiki_evidence("nonexistent zzz", subject_id="s") == []
