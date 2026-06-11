"""Pure-code researcher: corpus + wikipedia evidence with verbatim payload meta."""
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

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
    with patch("src.services.chat.research.hybrid_search",
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
    with patch("src.services.chat.research.hybrid_search",
               return_value=([_src()], None)):
        ev = corpus_evidence("q", subject_id="s1", exclude_book="x",
                             all_slugs=["x", "moss"], seen_ids=seen)
    assert ev == []


def test_corpus_evidence_legacy_fallback_chunk_id_book_slug():
    """Objects with legacy plan-name fields (chunk_id/book_slug/chapter_id) still work."""
    seen: set[str] = set()
    with patch("src.services.chat.research.hybrid_search",
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
    with patch("src.services.chat.research.hybrid_search",
               return_value=([_src_legacy()], None)):
        ev = corpus_evidence("q", subject_id="s1", exclude_book="x",
                             all_slugs=["x", "moss"], seen_ids=seen)
    assert ev == []


def test_wiki_evidence_returns_title_url_extract():
    payload = {"title": "Chebyshev's inequality",
               "extract": "In probability theory…",
               "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Chebyshev%27s_inequality"}}}
    with patch("src.services.chat.research._wiki_summary_json",
               return_value=payload):
        ev = wiki_evidence("Chebyshev inequality", subject_id="s2")
    e = ev[0]
    assert e.kind == "wikipedia" and e.meta["title"] == "Chebyshev's inequality"
    assert e.meta["url"].startswith("https://en.wikipedia.org/wiki/")
    assert "probability theory" in e.text


def test_wiki_evidence_empty_on_failure():
    with patch("src.services.chat.research._wiki_summary_json",
               return_value=None):
        assert wiki_evidence("nonexistent zzz", subject_id="s") == []


# ---------------------------------------------------------------------------
# New hardening tests
# ---------------------------------------------------------------------------

def test_corpus_evidence_env_parse_invalid_value_does_not_raise(monkeypatch):
    """EXTENSION_MIN_SCORE='auto' (non-numeric) must not raise; floor defaults to 0."""
    monkeypatch.setenv("EXTENSION_MIN_SCORE", "auto")
    with patch("src.services.chat.research.hybrid_search",
               return_value=([_src()], None)):
        ev = corpus_evidence("tail bounds", subject_id="s1",
                             exclude_book="hansen-probability",
                             all_slugs=["hansen-probability", "moss"], seen_ids=set())
    # floor=0 → no filtering; source with score 0.81 is kept
    assert len(ev) == 1


def test_corpus_evidence_score_floor_filters_low_score(monkeypatch):
    """Sources below EXTENSION_MIN_SCORE are excluded."""
    monkeypatch.setenv("EXTENSION_MIN_SCORE", "0.5")
    low_score_src = _src(score=0.3)
    with patch("src.services.chat.research.hybrid_search",
               return_value=([low_score_src], None)):
        ev = corpus_evidence("tail bounds", subject_id="s1",
                             exclude_book="hansen-probability",
                             all_slugs=["hansen-probability", "moss"], seen_ids=set())
    assert ev == []


def test_corpus_evidence_empty_slugs_no_hybrid_search_call():
    """When all slugs are excluded, hybrid_search is never called."""
    mock_hs = MagicMock()
    with patch("src.services.chat.research.hybrid_search", mock_hs):
        ev = corpus_evidence("tail bounds", subject_id="s1",
                             exclude_book="moss",
                             all_slugs=["moss"], seen_ids=set())
    assert ev == []
    mock_hs.assert_not_called()


def test_corpus_evidence_hybrid_search_raising_returns_empty():
    """hybrid_search raising an exception degrades cleanly to empty list."""
    with patch("src.services.chat.research.hybrid_search",
               side_effect=RuntimeError("connection refused")):
        ev = corpus_evidence("tail bounds", subject_id="s1",
                             exclude_book="hansen-probability",
                             all_slugs=["hansen-probability", "moss"], seen_ids=set())
    assert ev == []


def test_wiki_summary_json_sends_user_agent_on_direct_path():
    """_wiki_summary_json must pass a user-agent header on the direct summary GET.

    Wikipedia returns HTTP 403 without an identifying User-Agent; both GET call
    paths (direct summary + search-API fallback) must include the header.
    """
    from src.services.chat.agents.extension_agents.research import _wiki_summary_json

    ok_payload = {"title": "Chebyshev's inequality", "extract": "In probability…",
                  "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/C"}}}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = ok_payload

    with patch("src.services.chat.research.httpx.get",
               return_value=mock_resp) as mock_get:
        result = _wiki_summary_json("Chebyshev's inequality")

    assert result is not None
    assert mock_get.call_count >= 1
    # The direct-path GET must include a user-agent header.
    first_call_headers = mock_get.call_args_list[0].kwargs.get("headers", {})
    assert "user-agent" in first_call_headers, (
        "Direct summary GET must send a user-agent header to avoid Wikipedia 403"
    )


def test_wiki_summary_json_sends_user_agent_on_search_fallback_path():
    """_wiki_summary_json must pass a user-agent header on the search-API fallback GET.

    When the direct summary GET returns non-200 the function falls back to the
    search API (w/api.php).  That call must also carry the User-Agent header.
    """
    from src.services.chat.agents.extension_agents.research import _wiki_summary_json

    ok_payload = {"title": "Chebyshev's inequality", "extract": "In probability…",
                  "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/C"}}}

    miss_resp = MagicMock()
    miss_resp.status_code = 404   # direct summary miss → triggers fallback

    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.json.return_value = {"query": {"search": [{"title": "Chebyshev's inequality"}]}}

    hit_resp = MagicMock()
    hit_resp.status_code = 200
    hit_resp.json.return_value = ok_payload

    responses = [miss_resp, search_resp, hit_resp]

    with patch("src.services.chat.research.httpx.get",
               side_effect=responses) as mock_get:
        result = _wiki_summary_json("Chebyshev inequality")

    # Three GETs: direct miss, search-API, resolved title.
    assert mock_get.call_count == 3
    # The search-API call (second GET) must include a user-agent header.
    search_call_headers = mock_get.call_args_list[1].kwargs.get("headers", {})
    assert "user-agent" in search_call_headers, (
        "Search-API fallback GET must send a user-agent header to avoid Wikipedia 403"
    )
    assert result is not None


def test_corpus_evidence_dedupes_duplicate_chunk_id_within_one_call():
    """Two rows sharing the same chunkId in one call → only first is kept.

    This exercises the atomic check+add under _seen_lock: when two rows arrive
    in a single hybrid_search result with the same chunkId the second must be
    dropped even though seen_ids was empty at call time.
    """
    seen: set[str] = set()
    dup1 = _src(chunkId="dup-c1", score=0.9)
    dup2 = _src(chunkId="dup-c1", score=0.8)   # same id, lower score
    with patch("src.services.chat.research.hybrid_search",
               return_value=([dup1, dup2], None)):
        ev = corpus_evidence("tail bounds", subject_id="s1",
                             exclude_book="hansen-probability",
                             all_slugs=["hansen-probability", "moss"], seen_ids=seen)
    assert len(ev) == 1
    assert ev[0].meta["chunk_id"] == "dup-c1"
    # seen_ids must record the id so subsequent calls also dedupe correctly
    assert "dup-c1" in seen
