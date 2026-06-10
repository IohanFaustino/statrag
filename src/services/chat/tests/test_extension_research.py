"""Pure-code researcher: corpus + wikipedia evidence with verbatim payload meta."""
from types import SimpleNamespace
from unittest.mock import patch

from src.services.chat.agents.extension_agents.research import (
    Evidence, corpus_evidence, wiki_evidence,
)


def _src(**over):
    base = dict(chunk="Chebyshev states that …", book_slug="moss",
                book_name="Probability", authors="Marcus Moss", year=2020,
                chapter_id="ch06", section="6.5.2", page_from=142, page_to=144,
                chunk_id="c-1", score=0.81)
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


def test_corpus_evidence_dedupes_seen_ids():
    seen = {"c-1"}
    with patch("src.services.chat.agents.extension_agents.research.hybrid_search",
               return_value=([_src()], None)):
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
